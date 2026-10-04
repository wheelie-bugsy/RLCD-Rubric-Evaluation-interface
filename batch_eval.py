#!/usr/bin/env python3
"""Score a batch of written responses against a rubric with Nimble, no browser.

The rubric can be the CSV template from the app (Rubrics > Import & template, or Export CSV)
or a run/rubric JSON exported from the app.

    python3 batch_eval.py my-rubric.csv responses.csv -o results.csv
    python3 batch_eval.py my-rubric.csv responses.txt        # '---' separated, 'Name: x' first line

Every model exchange is also written verbatim to <out>.audit.jsonl (one line per response:
request sent, raw response text, SHA-256, timings) for auditability.

CSV input needs a text column (response/answer/text/...) and optionally a name column.
Python 3.8+, standard library only.
"""
import argparse, csv, datetime, hashlib, json, math, os, re, sys, time, urllib.request, urllib.error

def qkey(c, i):
    s = re.sub(r"[^a-z0-9]+", "_", (c.get("name") or "criterion").lower()).strip("_")[:40]
    return "c%d_%s" % (i + 1, s)

def level_text(l):
    return "%s: %s" % (l["label"], l["desc"]) if l.get("label") and l.get("desc") else (l.get("desc") or l.get("label") or "")

def build_questions(rb, relevance):
    qs = {}
    for i, c in enumerate(rb["criteria"]):
        instr = c.get("instructions") or "How well does the response demonstrate: %s?" % c["name"]
        lv = c["levels"]
        if c["type"] == "score":
            qs[qkey(c, i)] = {"type": "score", "instructions": 'Criterion "%s". %s' % (c["name"], instr), "criteria": [level_text(l) for l in lv]}
        elif c["type"] == "noul":
            qs[qkey(c, i)] = {"type": "noul", "instructions": instr, "criteria": {"true": lv[1].get("desc") or "Yes", "false": lv[0].get("desc") or "No"}}
        else:
            qs[qkey(c, i)] = {"type": "choice", "instructions": instr, "criteria": {(l.get("label") or "option_%d" % j): (l.get("desc") or l.get("label")) for j, l in enumerate(lv)}}
    if relevance and rb.get("prompt"):
        qs["_on_topic"] = {"type": "noul", "instructions": "Is the learner's response a genuine attempt to answer the assignment?",
                           "criteria": {"true": "The response addresses the assignment.", "false": "The response is off-topic, empty, copied instructions, or nonsense."}}
    return qs

def interpret(c, a):
    n = len(c["levels"])
    if a is None:
        return None
    if c["type"] == "score":
        probs = [0.0] * n
        for k, v in (a.get("probabilities") or {}).items():
            if str(k).isdigit() and int(k) < n:
                probs[int(k)] = float(v)
        if not any(probs) and isinstance(a.get("score"), (int, float)):
            probs[max(0, min(n - 1, round(a["score"])))] = 1.0
        lvl = probs.index(max(probs))
        conf = a.get("confidence")
        if conf is None:
            h = -sum(p * math.log(p) for p in probs if p > 0); conf = 1 - h / math.log(n) if n > 1 else 1
        top = sorted(probs, reverse=True)
        return {"level": lvl, "expected": a.get("score"), "confidence": conf, "margin": top[0] - (top[1] if n > 1 else 0)}
    if c["type"] == "noul":
        p = a.get("noul")
        if isinstance(p, bool) or p is None:
            p = (a.get("probabilities") or {}).get("true", 1.0 if p else 0.0)
        p = float(p)
        return {"level": 1 if p >= 0.5 else 0, "expected": p, "confidence": a.get("confidence", abs(p - .5) * 2), "margin": abs(2 * p - 1)}
    labels = [l.get("label") or "option_%d" % j for j, l in enumerate(c["levels"])]
    probs = [float((a.get("probabilities") or {}).get(l, 0)) for l in labels]
    lvl = labels.index(a["choice"]) if a.get("choice") in labels else probs.index(max(probs))
    top = sorted(probs, reverse=True)
    return {"level": lvl, "expected": lvl, "confidence": a.get("confidence", top[0]), "margin": top[0] - (top[1] if len(top) > 1 else 0)}

def crit_pct(c, lvl):
    pts = [float(l.get("points", i)) for i, l in enumerate(c["levels"])]
    return 1.0 if max(pts) == min(pts) else (pts[lvl] - min(pts)) / (max(pts) - min(pts))

HIGH = re.compile(r"^(excellent|exemplary|outstanding|exceeds|exceptional|distinguished|advanced|expert|mastery|superior|high|strong)", re.I)

def load_rubric(path):
    if not path.lower().endswith((".csv", ".tsv")):
        rb = json.load(open(path, encoding="utf-8-sig")); rb = rb.get("rubric", rb)
        if rb.get("v") == 2:  # grid format saved by the app
            out = []
            for c in rb["criteria"]:
                if c["type"] == "noul":
                    out.append({"name": c["name"], "type": "noul", "weight": c.get("weight", 1), "instructions": c.get("instructions", ""),
                                "levels": [{"label": "No", "desc": c.get("no", ""), "points": 0}, {"label": "Yes", "desc": c.get("yes", ""), "points": 1}]})
                else:
                    out.append({"name": c["name"], "type": "score", "weight": c.get("weight", 1), "instructions": c.get("instructions", ""),
                                "levels": [{"label": L["label"], "desc": d, "points": L["points"]} for L, d in zip(rb["levels"], c["cells"]) if d.strip()]})
            rb = {"name": rb.get("name"), "prompt": rb.get("prompt"), "context": rb.get("context", ""), "criteria": out}
        return rb
    rows = list(csv.reader(open(path, encoding="utf-8-sig"), delimiter="\t" if path.lower().endswith(".tsv") else ","))
    rows = [[x.strip() for x in r] for r in rows]
    name = prompt = context = ""; hi = None
    for i, r in enumerate(rows):
        a = (r[0] if r else "").lower()
        if not any(r) or a.startswith("#"): continue
        if a in ("rubric name", "rubric", "name", "title") and not any(r[2:]): name = r[1] if len(r) > 1 else ""; continue
        if a in ("assignment", "prompt", "task") and not any(r[2:]): prompt = r[1] if len(r) > 1 else ""; continue
        if a in ("context", "context for the model", "about the learners", "about the writers") and not any(r[2:]): context = r[1] if len(r) > 1 else ""; continue
        hi = i; break
    if hi is None: sys.exit("No header row found in %s" % path)
    H = [h.lower() for h in rows[hi]]
    role = lambda h: ("name" if h in ("criterion", "criteria", "name") else "type" if h == "type" else "weight" if h.startswith("weight")
                      else "q" if h in ("question", "question for the model", "instructions", "instruction", "prompt") else "skip" if not h else "level")
    roles = [role(h) for h in H]
    if "name" not in roles: roles[0] = "name"
    lv = [i for i, r in enumerate(roles) if r == "level"]
    def hdr(h, i):
        m = re.match(r"^(.*?)[\s(\[]*(-?\d+(?:\.\d+)?)\s*(?:pts?|points?)?[)\]]?\s*$", h, re.I)
        return (m.group(1).strip() or "Level " + m.group(2), float(m.group(2)), True) if m else (h.strip(), float(i), False)
    levels = [hdr(rows[hi][c], k) for k, c in enumerate(lv)]
    if (all(l[2] for l in levels) and levels[0][1] > levels[-1][1]) or (HIGH.match(levels[0][0]) and not HIGH.match(levels[-1][0])):
        lv, levels = lv[::-1], levels[::-1]
    col = lambda k: roles.index(k) if k in roles else None
    crits = []
    for r in rows[hi + 1:]:
        if not any(r) or r[0].startswith("#"): continue
        g = lambda i: r[i] if i is not None and i < len(r) else ""
        cells = [g(c) for c in lv]
        if not g(col("name")): continue
        typ = "noul" if re.search(r"yes|no|bool|check|y/n|pass", g(col("type")), re.I) else "score"
        try: w = float(g(col("weight")) or 1)
        except ValueError: w = 1.0
        if typ == "noul":
            f = [d for d in cells if d]
            levs = [{"label": "No", "desc": f[0] if len(f) > 1 else "", "points": 0}, {"label": "Yes", "desc": f[-1] if len(f) > 1 else "", "points": 1}]
        else:
            levs = [{"label": L[0], "desc": d, "points": L[1]} for L, d in zip(levels, cells) if d]
            if len(levs) < 2: print("  skipping %r: needs at least 2 levels" % g(col("name")), file=sys.stderr); continue
        crits.append({"name": g(col("name")), "type": typ, "weight": w, "instructions": g(col("q")), "levels": levs})
    # same order as the app: score criteria first, then yes/no checks
    crits = [c for c in crits if c["type"] != "noul"] + [c for c in crits if c["type"] == "noul"]
    return {"name": name, "prompt": prompt, "context": context, "criteria": crits}

def load_responses(path):
    text = open(path, encoding="utf-8-sig").read()
    if path.lower().endswith((".csv", ".tsv")):
        rows = list(csv.reader(text.splitlines(), delimiter="\t" if path.lower().endswith(".tsv") else ","))
        h = [x.lower() for x in rows[0]]
        ti = next((i for i, x in enumerate(h) if re.search(r"response|answer|text|reflection|entry|diary|submission", x)), None)
        ni = next((i for i, x in enumerate(h) if re.search(r"name|learner|id|user|participant|email", x) and i != ti), None)
        if ti is None:
            ti = max(range(len(h)), key=lambda i: sum(len(r[i]) if i < len(r) else 0 for r in rows[1:]))
        return [{"name": (r[ni] if ni is not None and ni < len(r) else "Response %d" % (k + 1)), "text": r[ti]} for k, r in enumerate(rows[1:]) if ti < len(r) and r[ti].strip()]
    out = []
    for k, ch in enumerate([c.strip() for c in re.split(r"^\s*(?:-{3,}|={3,})\s*$", text, flags=re.M) if c.strip()]):
        m = re.match(r"^(?:name|learner|id|user|participant)\s*:\s*(.+)\n?", ch, re.I)
        name = m.group(1).strip() if m else "Response %d" % (k + 1)
        out.append({"name": name, "text": ch[m.end():].strip() if m else ch})
    return out

def post(url, body):
    """Returns (status, raw_text). Raw text is kept verbatim for the audit log."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rubric"); ap.add_argument("responses")
    ap.add_argument("-o", "--out", default="results.csv")
    ap.add_argument("--model", default="nimble")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--conf", type=float, default=0.5, help="flag below this confidence")
    ap.add_argument("--no-relevance", action="store_true")
    a = ap.parse_args()
    host = a.host if a.host.startswith("http") else "http://" + a.host
    rb = load_rubric(a.rubric)
    if not rb["criteria"]: sys.exit("No usable criteria in %s" % a.rubric)
    resps = load_responses(a.responses)
    qs = build_questions(rb, not a.no_relevance)
    head = ["learner", "overall_pct", "flags", "words"]
    for c in rb["criteria"]:
        head += ["%s | level" % c["name"], "%s | confidence" % c["name"]]
    audit_path = re.sub(r"\.csv$", "", a.out) + ".audit.jsonl"
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f, open(audit_path, "w", encoding="utf-8") as audit:
        w = csv.writer(f); w.writerow(head)
        for i, r in enumerate(resps, 1):
            state = (("ASSIGNMENT GIVEN TO THE LEARNER:\n%s\n\n" % rb["prompt"] if rb.get("prompt") else "")
                     + ("CONTEXT FOR SCORING:\n%s\n\n" % rb["context"].strip() if (rb.get("context") or "").strip() else "")
                     + "LEARNER'S WRITTEN RESPONSE:\n" + r["text"])
            t0 = time.time(); started = datetime.datetime.now(datetime.timezone.utc).isoformat()
            body = {"model": a.model, "state": state, "questions": qs}
            try:
                status, raw = post(host.rstrip("/") + "/v1/systemone", body)
            except Exception as e:
                sys.exit("Could not reach Ollama at %s: %s" % (host, e))
            audit.write(json.dumps({"learner": r["name"], "started_at": started, "duration_ms": round((time.time() - t0) * 1000),
                                    "endpoint": host.rstrip("/") + "/v1/systemone", "http_status": status, "request": body,
                                    "raw_response_text": raw, "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest()}) + "\n")
            if status != 200:
                print("  %s: HTTP %s %s" % (r["name"], status, raw[:200]), file=sys.stderr); continue
            data = json.loads(raw)
            ans = data.get("answers", {})
            row, flags, tw, acc = [], [], 0.0, 0.0
            for j, c in enumerate(rb["criteria"]):
                s = interpret(c, ans.get(qkey(c, j)))
                if not s:
                    row += ["", ""]; flags.append("no answer: " + c["name"]); continue
                if s["confidence"] < a.conf: flags.append("low confidence: " + c["name"])
                wt = float(c.get("weight", 1)); tw += wt; acc += wt * crit_pct(c, s["level"])
                lab = ("Yes" if s["level"] else "No") if c["type"] == "noul" else (c["levels"][s["level"]].get("label") or s["level"])
                row += [lab, round(s["confidence"], 3)]
            ot = ans.get("_on_topic")
            if ot and interpret({"type": "noul", "levels": [{}, {}]}, ot)["expected"] < 0.5: flags.append("possibly off-topic")
            overall = round(acc / tw * 100, 1) if tw else ""
            w.writerow([r["name"], overall, "; ".join(flags), len(r["text"].split())] + row)
            print("[%d/%d] %-24s %5s%%  %4d ms  %s" % (i, len(resps), r["name"][:24], overall, (time.time() - t0) * 1000, "; ".join(flags)))
    print("Wrote", a.out, "and", audit_path)

if __name__ == "__main__":
    main()
