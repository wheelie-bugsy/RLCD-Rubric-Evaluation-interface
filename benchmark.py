#!/usr/bin/env python3
"""Benchmark a Jev-style model (or an LLM judge) against human essay grades.

Same data, rubrics, sampling and results CSV as the app's Benchmark tab, for long or
unattended runs. Python 3.8+, standard library only.

  1. Prepare the downloaded datasets (once, or after adding files to datasets/):
       python3 benchmark.py prepare

  2. See what you can run:
       python3 benchmark.py list

  3. Run a benchmark (resumes automatically if the output file already exists):
       python3 benchmark.py run --dataset ellipse --prompt "Distance learning" --sample 200 -o ellipse-dl-nimble.csv
       python3 benchmark.py run --dataset asap7 --sample all --model tev1
       python3 benchmark.py run --dataset asap7 --rubric adjusted          # the "Adjusted" rubric
       python3 benchmark.py run --dataset persuade --prompt "Car-free cities" --provider openai \\
           --url https://api.openai.com/v1 --model gpt-4.1-mini        # key from OPENAI_API_KEY

  Open the results CSV in the app: Benchmark tab > Explore > Open results CSV.

Rubrics come from datasets/bench/rubrics.json, built word for word from each dataset's
official rubric by tools/build_rubrics.py (see datasets/rubrics/VERIFY.md). With
--rubric adjusted, the "Adjusted" version from datasets/bench/rubrics_adjusted.json is used
instead: the same level text plus a context block sent with every essay and a plain question
per criterion (tools/build_adjusted_rubrics.py, datasets/rubrics/ADJUSTED.md). --context
replaces the context block with your own text.
Every exchange with the model is written verbatim to <out>.audit.jsonl.
"""
import argparse, csv, datetime, hashlib, json, math, os, re, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "datasets")
BENCH = os.path.join(DS, "bench")
csv.field_size_limit(1 << 30)

# The only text the benchmark adds around the rubric (the API needs a question per criterion).
BENCH_QUESTION = "Which level of this rubric criterion does the essay meet?"
BENCH_QUESTION_ELEMENT = "Which level of this rubric criterion does the argument element meet?"
JUDGE_SYSTEM = ("You are an experienced, fair essay rater. You judge a piece of student writing against rubric questions. "
                "Judge only what is actually written. Apply each level description literally. Give probabilities that honestly "
                "reflect your uncertainty. Reply with one JSON object and nothing else: no prose, no markdown.")

# ----------------------------------------------------------------- shared helpers
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60] or "x"

def words(s):
    return len(re.findall(r"\S+", s or ""))

def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None

def fmt(v):
    if v is None or v == "":
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else ("%.4f" % f).rstrip("0").rstrip(".")

def mulberry32(a):
    """Same generator as the app, so a seed picks the same essays in both."""
    state = [a & 0xFFFFFFFF]
    def imul(x, y):
        return (x * y) & 0xFFFFFFFF
    def r():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        a = state[0]
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r

def stratum(row, keys):
    vals = [num(row.get(k + "_human")) for k in keys]
    vals = [v for v in vals if v is not None]
    return int(math.floor(sum(vals) + 0.5)) if vals else -1  # same rounding as JS Math.round

def sample(rows, keys, n, mode="stratified", seed=42):
    """Mirror of sampleRows() in index.html."""
    rows = sorted(rows, key=lambda r: str(r["essay_id"]) + "|" + str(r.get("criterion", "")))
    if mode == "first":
        return rows[:n]
    rng = mulberry32(seed)
    rows = rows[:]
    for i in range(len(rows) - 1, 0, -1):
        j = int(rng() * (i + 1))
        rows[i], rows[j] = rows[j], rows[i]
    if n >= len(rows):
        return rows
    if mode == "random":
        return rows[:n]
    groups = {}
    for r in rows:
        groups.setdefault(stratum(r, keys), []).append(r)
    ks = sorted(groups)
    total = len(rows)
    alloc = {k: int(n * len(groups[k]) / total) for k in ks}
    rema = sorted(ks, key=lambda k: (-(n * len(groups[k]) / total - alloc[k]), k))
    i = 0
    while sum(alloc.values()) < n:
        alloc[rema[i % len(rema)]] += 1
        i += 1
    if n >= 3 * len(ks):  # make sure the rare score levels are represented
        for k in ks:
            want = min(3, len(groups[k]))
            while alloc[k] < want:
                donor = max(ks, key=lambda d: (alloc[d] - min(3, len(groups[d])), -d))
                if alloc[donor] - min(3, len(groups[donor])) <= 0:
                    break
                alloc[donor] -= 1
                alloc[k] += 1
    pick = set()
    for k in ks:
        for r in groups[k][:alloc[k]]:
            pick.add(id(r))
    return [r for r in rows if id(r) in pick]

def level_text(l):
    return "%s: %s" % (l["label"], l["desc"]) if l.get("label") and l.get("desc") else (l.get("desc") or l.get("label") or "")

def qkey(c, i):
    return "c%d_%s" % (i + 1, c["key"])

def build_request(rb, row, prompt_info, model, keep_alive=None):
    """Mirror of benchRequest() in index.html."""
    qs = {}
    for i, c in enumerate(rb["criteria"]):
        if row.get("criterion") and row["criterion"] != c["key"]:
            continue
        instr = 'Criterion "%s". %s' % (c["name"], c.get("instructions") or (BENCH_QUESTION_ELEMENT if row.get("element_type") else BENCH_QUESTION))
        qs[qkey(c, i)] = {"type": "score", "instructions": instr, "criteria": [level_text(l) for l in c["levels"]]}
    parts = []
    if prompt_info.get("assignment"):
        parts.append("ASSIGNMENT GIVEN TO THE WRITER:\n" + prompt_info["assignment"])
    if prompt_info.get("source_text"):
        parts.append("SOURCE TEXT GIVEN TO THE WRITER:\n" + prompt_info["source_text"])
    if rb.get("context"):
        parts.append("CONTEXT FOR SCORING:\n" + rb["context"])
    if row.get("context"):
        parts.append("FULL ESSAY (context only):\n" + row["context"])
    label = "ARGUMENT ELEMENT TO SCORE (%s)" % row["element_type"] if row.get("element_type") else "ESSAY"
    parts.append(label + ":\n" + row["text"])
    body = {"model": model, "state": "\n\n".join(parts), "questions": qs}
    if keep_alive:
        body["keep_alive"] = keep_alive
    return body

# ----------------------------------------------------------------- prepare
def write_rows(path, rows, cols):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def score_cols(keys):
    return [k + s for k in keys for s in ("_r1", "_r2", "_human")]

def dist(rows, keys):
    d = {}
    for r in rows:
        s = stratum(r, keys)
        d[s] = d.get(s, 0) + 1
    return {str(k): d[k] for k in sorted(d)}

def prepare(args):
    rub = json.load(open(os.path.join(BENCH, "rubrics.json"), encoding="utf-8"))
    manifest = {"version": 1, "prepared": datetime.datetime.now().isoformat(timespec="seconds"), "datasets": []}

    def add(ds, prompts_rows, keys, seg_cols, base_cols=("essay_id", "prompt", "text", "words")):
        cols = list(base_cols) + seg_cols + score_cols(keys)
        out = []
        for p, info in sorted(prompts_rows.items()):
            rows = info.pop("rows")
            f = "%s/%s.csv" % (ds["id"], slug(p))
            write_rows(os.path.join(BENCH, f), rows, cols)
            out.append(dict(name=p, file=f, count=len(rows), dist=dist(rows, keys), **info))
        ds["prompts"] = out
        ds["segments"] = seg_cols
        manifest["datasets"].append(ds)
        print("  %-10s %6d rows, %d prompt(s)" % (ds["id"], sum(p["count"] for p in out), len(out)))

    # ASAP set 7 ---------------------------------------------------------
    f = os.path.join(DS, "asap7", "asap-7-original.csv")
    if os.path.exists(f):
        keys = [c["key"] for c in rub["asap7"]["criteria"]]
        rows, assignment = [], ""
        for r in csv.DictReader(open(f, encoding="utf-8")):
            assignment = r["prompt"]
            o = {"essay_id": r["essay_id"], "prompt": "Patience", "text": r["essay"], "words": words(r["essay"])}
            for i, k in enumerate(keys, 1):
                a, b = num(r["rater1_trait%d" % i]), num(r["rater2_trait%d" % i])
                o[k + "_r1"], o[k + "_r2"] = fmt(a), fmt(b)
                o[k + "_human"] = fmt((a + b) / 2) if a is not None and b is not None else fmt(a if a is not None else b)
            rows.append(o)
        add({"id": "asap7", "name": "ASAP-AES set 7", "rubric": "asap7", "raters": 2, "humanIs": "mean of rater 1 and rater 2",
             "source": "https://huggingface.co/datasets/llm-aes/asap-7-original", "licence": "Kaggle competition data (research use)",
             "writers": "US students, grade 7"},
            {"Patience": {"rows": rows, "assignment": assignment, "task": "Narrative"}}, keys, [])

    # PERSUADE holistic --------------------------------------------------
    f = os.path.join(DS, "persuade", "persuade_2.0_essays.csv")
    if os.path.exists(f):
        keys = ["holistic"]
        by = {}
        for r in csv.DictReader(open(f, encoding="utf-8")):
            p = r["prompt_name"]
            info = by.setdefault(p, {"rows": [], "assignment": r["assignment"], "task": r["task"],
                                     "source_text": r["source_text"] if r["task"] != "Independent" else "",
                                     "rubric": "persuade_holistic_indy" if r["task"] == "Independent" else "persuade_holistic_source"})
            info["rows"].append({"essay_id": r["essay_id_comp"], "prompt": p, "text": r["full_text"], "words": r["essay_word_count"] or words(r["full_text"]),
                                 "seg_grade": fmt(num(r["grade_level"])), "seg_gender": r["gender"], "seg_ell": r["ell_status"],
                                 "seg_economic": r["economically_disadvantaged"], "seg_race": r["race_ethnicity"],
                                 "seg_disability": r["student_disability_status"],
                                 "holistic_r1": "", "holistic_r2": "", "holistic_human": fmt(num(r["holistic_essay_score"]))})
        add({"id": "persuade", "name": "PERSUADE 2.0 (holistic)", "rubric": "persuade_holistic_indy", "raters": 1, "humanIs": "final holistic score",
             "source": "https://github.com/scrosseye/persuade_corpus_2.0", "licence": "CC BY-NC-SA 4.0", "writers": "US students, grades 6 to 12"},
            by, keys, ["seg_grade", "seg_gender", "seg_ell", "seg_economic", "seg_race", "seg_disability"])

    # PERSUADE elements --------------------------------------------------
    f = os.path.join(DS, "persuade", "persuade_2.0_elements.csv")
    if os.path.exists(f):
        crits = rub["persuade_elements"]["criteria"]
        keys = [c["key"] for c in crits]
        tmap = {"Concluding Statement": "concluding_statement"}
        eff = {"Ineffective": 0, "Adequate": 1, "Effective": 2}
        assign = {}
        ef = os.path.join(DS, "persuade", "persuade_2.0_essays.csv")
        if os.path.exists(ef):
            for r in csv.DictReader(open(ef, encoding="utf-8")):
                assign.setdefault(r["prompt_name"], (r["assignment"], r["task"]))
        by, seq = {}, {}
        for r in csv.DictReader(open(f, encoding="utf-8")):
            seq[r["essay_id_comp"]] = seq.get(r["essay_id_comp"], 0) + 1  # element number within its essay (discourse_id is not unique)
            if r["discourse_effectiveness"] not in eff:
                continue
            p, t = r["prompt_name"], r["discourse_type"]
            k = tmap.get(t, t.lower())
            a = assign.get(p, ("", r["task"]))
            info = by.setdefault(p, {"rows": [], "assignment": a[0], "task": a[1]})
            o = {"essay_id": "%s:%02d" % (r["essay_id_comp"], seq[r["essay_id_comp"]]), "prompt": p, "criterion": k, "element_type": t,
                 "text": r["discourse_text"].strip(), "words": words(r["discourse_text"]),
                 "essay": r["essay_id_comp"],
                 "seg_element": t, "seg_grade": fmt(num(r["grade_level"])), "seg_ell": r["ell_status"],
                 "seg_holistic": r["holistic_essay_score"]}
            for kk in keys:
                o[kk + "_r1"] = o[kk + "_r2"] = o[kk + "_human"] = ""
            o[k + "_human"] = str(eff[r["discourse_effectiveness"]])
            info["rows"].append(o)
        add({"id": "persuade_elements", "name": "PERSUADE 2.0 (argument elements)", "rubric": "persuade_elements", "raters": 1,
             "humanIs": "final effectiveness rating", "unit": "element", "contextFrom": "persuade", "source": "https://github.com/scrosseye/persuade_corpus_2.0",
             "licence": "CC BY-NC-SA 4.0", "writers": "US students, grades 6 to 12"},
            by, keys, ["seg_element", "seg_grade", "seg_ell", "seg_holistic"],
            base_cols=("essay_id", "prompt", "criterion", "element_type", "essay", "text", "words"))

    # ELLIPSE ------------------------------------------------------------
    d = os.path.join(DS, "ellipse")
    if os.path.exists(os.path.join(d, "ELLIPSE_Final_github_train.csv")):
        crits = rub["ellipse"]["criteria"]
        keys = [c["key"] for c in crits]
        raw = {}
        rf = os.path.join(d, "ellipsis_raw_rater_scores_anon_all_essay.csv")
        if os.path.exists(rf):
            raw = {r["text_id_kaggle"]: r for r in csv.DictReader(open(rf, encoding="utf-8", errors="replace"))}
        by = {}
        for fn, split in (("ELLIPSE_Final_github_train.csv", "train"), ("ELLIPSE_Final_github_test.csv", "test")):
            if not os.path.exists(os.path.join(d, fn)):
                continue
            for r in csv.DictReader(open(os.path.join(d, fn), encoding="utf-8", errors="replace")):
                p = r["prompt"]
                info = by.setdefault(p, {"rows": [], "assignment": p, "task": r["task"]})
                rr = raw.get(r["text_id_kaggle"], {})
                o = {"essay_id": r["text_id_kaggle"], "prompt": p, "text": r["full_text"], "words": r["num_words"] or words(r["full_text"]),
                     "seg_grade": r["grade"], "seg_gender": r["gender"], "seg_economic": r["SES"], "seg_race": r["race_ethnicity"], "seg_split": split}
                for c in crits:
                    n = c["name"]
                    o[c["key"] + "_r1"] = rr.get(n + "_1", "")
                    o[c["key"] + "_r2"] = rr.get(n + "_2", "")
                    o[c["key"] + "_human"] = r[n]
                info["rows"].append(o)
        add({"id": "ellipse", "name": "ELLIPSE (English learners)", "rubric": "ellipse", "raters": 2,
             "humanIs": "published score (mean of the two raters; adjudicated when they were far apart)",
             "source": "https://github.com/scrosseye/ELLIPSE-Corpus", "licence": "CC BY-NC-SA 4.0", "writers": "English language learners, grades 8 to 12"},
            by, keys, ["seg_grade", "seg_gender", "seg_economic", "seg_race", "seg_split"])

    manifest["rubrics"] = rub
    json.dump(manifest, open(os.path.join(BENCH, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("Wrote", os.path.relpath(os.path.join(BENCH, "manifest.json"), HERE))

# ----------------------------------------------------------------- model calls
def http_json(url, body, headers, timeout=900):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

def judge_prompt(body):
    qs = []
    for k, q in body["questions"].items():
        lv = "\n".join("    %d: %s" % (i, c) for i, c in enumerate(q["criteria"]))
        qs.append('"%s" (rubric level)\n  Question: %s\n  Levels, lowest to highest:\n%s\n  Answer as {"level": <0 to %d>, "probabilities": [%d numbers that sum to 1, one per level]}'
                  % (k, q["instructions"], lv, len(q["criteria"]) - 1, len(q["criteria"])))
    user = "TEXT TO JUDGE:\n<<<\n%s\n>>>\n\nQUESTIONS:\n\n%s\n\nReturn one JSON object whose keys are exactly: %s." % (
        body["state"], "\n\n".join(qs), ", ".join('"%s"' % k for k in body["questions"]))
    return JUDGE_SYSTEM, user

def parse_judge(txt):
    t = re.sub(r"<think>[\s\S]*?</think>", "", txt or "")
    t = re.sub(r"```(?:json)?", "", t, flags=re.I).strip()
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise ValueError("The model did not reply with valid JSON")

def judge_answers(body, obj):
    out = {}
    for k, q in body["questions"].items():
        a = obj.get(k)
        if a is None:
            continue
        n = len(q["criteria"])
        ps = a.get("probabilities") if isinstance(a, dict) else None
        if isinstance(ps, dict):
            ps = [float(ps.get(str(i), ps.get(i, 0)) or 0) for i in range(n)]
        lvl = a.get("level") if isinstance(a, dict) else a
        if not isinstance(ps, list) or len(ps) != n or not any(float(x or 0) > 0 for x in ps):
            ps = [0.0] * n
            if isinstance(lvl, (int, float)):
                ps[max(0, min(n - 1, int(round(lvl))))] = 1.0
        ps = [max(0.0, float(x or 0)) for x in ps]
        s = sum(ps) or 1
        ps = [x / s for x in ps]
        out[k] = {"type": "score", "score": sum(p * i for i, p in enumerate(ps)), "probabilities": {str(i): round(p, 4) for i, p in enumerate(ps)}}
    return out

def call_model(args, body, audit):
    p = args.provider
    key = args.key or os.environ.get({"jev": "JEV_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(p, ""), "")
    base = args.url.rstrip("/")
    if p == "ollama":
        url = base + "/v1/systemone"
        audit.update(url=url, request=body)
        status, txt = http_json(url, body, {})
        audit.update(httpStatus=status, responseText=txt)
        return json.loads(txt).get("answers") or {}, None
    if p == "jev":
        b = dict(body); b.pop("keep_alive", None)
        url = base + "/systemone"
        audit.update(url=url, request=b)
        status, txt = http_json(url, b, {"Authorization": "Bearer " + key})
        audit.update(httpStatus=status, responseText=txt)
        return json.loads(txt).get("answers") or {}, None
    system, user = judge_prompt(body)
    if p == "anthropic":
        req = {"model": args.model, "max_tokens": 2000, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]}
        url = base + "/messages"
        audit.update(url=url, request=req, jevQuestions=body)
        status, txt = http_json(url, req, {"x-api-key": key, "anthropic-version": "2023-06-01"})
        text = "".join(c.get("text", "") for c in json.loads(txt).get("content", []) if c.get("type") == "text")
    else:
        req = {"model": args.model, "temperature": 0, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "response_format": {"type": "json_object"}}
        url = base + "/chat/completions"
        audit.update(url=url, request=req, jevQuestions=body)
        hdr = {"Authorization": "Bearer " + key} if key else {}
        try:
            status, txt = http_json(url, req, hdr)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            req.pop("response_format")
            status, txt = http_json(url, req, hdr)
        text = json.loads(txt)["choices"][0]["message"]["content"]
    audit.update(httpStatus=status, responseText=txt, judgeText=text)
    return judge_answers(body, parse_judge(text)), "LLM judge: probabilities are self-reported"

def interpret(c, a):
    n = len(c["levels"])
    probs = [0.0] * n
    for k, v in ((a or {}).get("probabilities") or {}).items():
        if str(k).lstrip("-").isdigit() and 0 <= int(k) < n:
            probs[int(k)] = float(v or 0)
    s = sum(probs)
    exp = a.get("score") if isinstance(a.get("score"), (int, float)) else (sum(p * i for i, p in enumerate(probs)) / s if s else None)
    if not s and exp is not None:
        probs[max(0, min(n - 1, int(round(exp))))] = 1.0
    lvl = probs.index(max(probs))
    conf = a.get("confidence")
    if not isinstance(conf, (int, float)):
        h = -sum(p * math.log(p) for p in probs if p > 0)
        conf = max(0.0, 1 - h / math.log(n)) if n > 1 else 1.0
    return lvl, exp, probs, conf

# ----------------------------------------------------------------- run
RESULT_BASE = ["run_id", "run_name", "dataset", "rubric_id", "prompt", "model", "provider", "essay_id", "criterion", "element_type", "essay", "words"]

def result_columns(rb, segs, two_raters):
    cols = RESULT_BASE + segs + ["text"]
    for c in rb["criteria"]:
        k = c["key"]
        cols += [k + "_r1", k + "_r2", k + "_human", k + "_model", k + "_expected", k + "_confidence"]
        cols += ["%s_p%s" % (k, fmt(l["points"])) for l in c["levels"]]
    return cols + ["total_human", "total_model", "ms", "error", "response_sha256", "scored_at"]

def load_manifest():
    f = os.path.join(BENCH, "manifest.json")
    if not os.path.exists(f):
        sys.exit("No prepared datasets yet. Run: python3 benchmark.py prepare")
    return json.load(open(f, encoding="utf-8"))

def find_prompt(ds, name):
    if not name:
        if len(ds["prompts"]) == 1:
            return ds["prompts"][0]
        sys.exit("Choose a prompt with --prompt. Options:\n  " + "\n  ".join("%s (%d)" % (p["name"], p["count"]) for p in ds["prompts"]))
    for p in ds["prompts"]:
        if p["name"].lower() == name.lower() or slug(p["name"]) == slug(name):
            return p
    sys.exit('No prompt "%s" in %s.' % (name, ds["id"]))

def run(args):
    m = load_manifest()
    ds = next((d for d in m["datasets"] if d["id"] == args.dataset), None)
    if not ds:
        sys.exit("Unknown dataset. Run: python3 benchmark.py list")
    pinfo = find_prompt(ds, args.prompt)
    rid = pinfo.get("rubric") or ds["rubric"]
    rb = m["rubrics"][rid]
    if args.rubric == "adjusted":
        f = os.path.join(BENCH, "rubrics_adjusted.json")
        adj = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        if rid + "_adjusted" not in adj:
            sys.exit("No Adjusted rubric for %s. Run: python3 tools/build_adjusted_rubrics.py" % rid)
        rid = rid + "_adjusted"
        rb = adj[rid]
    if args.context is not None:
        rb = dict(rb, context=args.context.strip())
    keys = [c["key"] for c in rb["criteria"]]
    rows = list(csv.DictReader(open(os.path.join(BENCH, pinfo["file"]), encoding="utf-8")))
    n = len(rows) if args.sample == "all" else int(args.sample)
    picked = sample(rows, keys, n, args.sampling, args.seed)
    if ds.get("contextFrom"):  # elements are scored with their full essay as context
        src = next(d for d in m["datasets"] if d["id"] == ds["contextFrom"])
        sp = next((p for p in src["prompts"] if p["name"] == pinfo["name"]), None)
        full = {r["essay_id"]: r["text"] for r in csv.DictReader(open(os.path.join(BENCH, sp["file"]), encoding="utf-8"))} if sp else {}
        for r in picked:
            r["context"] = full.get(r["essay"], "")
    tag = " · Adjusted" if rid.endswith("_adjusted") else ""
    out = args.output or "%s-%s%s-%s.csv" % (ds["id"], slug(pinfo["name"]), "-adjusted" if tag else "", slug(args.model))
    done = set()
    if os.path.exists(out):
        for r in csv.DictReader(open(out, encoding="utf-8")):
            if not r.get("error"):
                done.add(r["essay_id"])
    cols = result_columns(rb, ds["segments"], ds.get("raters") == 2)
    new_file = not os.path.exists(out)
    fout = open(out, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fout, fieldnames=cols, extrasaction="ignore")
    if new_file:
        w.writeheader()
    faud = open(re.sub(r"\.csv$", "", out) + ".audit.jsonl", "a", encoding="utf-8")
    run_id = args.run_id or slug("%s-%s-%s%s-%s" % (ds["id"], pinfo["name"], args.model, "-adjusted" if tag else "", args.seed))
    todo = [r for r in picked if r["essay_id"] not in done]
    print("%s / %s: %d picked (%s, seed %d), %d already scored, %d to go -> %s" % (ds["name"], pinfo["name"], len(picked), args.sampling, args.seed, len(picked) - len(todo), len(todo), out))
    t_all = time.time()
    for i, row in enumerate(todo, 1):
        body = build_request(rb, row, pinfo, args.model, args.keep_alive)
        audit = {"essay_id": row["essay_id"], "provider": args.provider, "startedAt": datetime.datetime.now().isoformat()}
        res = {"run_id": run_id, "run_name": args.name or "%s · %s%s · %s" % (ds["name"], pinfo["name"], tag, args.model), "dataset": ds["id"], "rubric_id": rid,
               "prompt": pinfo["name"], "model": args.model, "provider": args.provider, "scored_at": audit["startedAt"]}
        for k in RESULT_BASE[7:] + ds["segments"] + ["text"]:
            if k in row:
                res[k] = row[k]
        t0 = time.time()
        try:
            answers, note = call_model(args, body, audit)
            if note:
                audit["scoringNote"] = note
            tm, th, complete = 0, 0, True
            for ci, c in enumerate(rb["criteria"]):
                k = c["key"]
                for s in ("_r1", "_r2", "_human"):
                    res[k + s] = row.get(k + s, "")
                q = qkey(c, ci)
                if q not in body["questions"]:
                    continue
                if q not in answers:
                    raise ValueError("No answer for %s" % c["name"])
                lvl, exp, probs, conf = interpret(c, answers[q])
                base = c["levels"][0]["points"]
                res[k + "_model"] = fmt(c["levels"][lvl]["points"])
                res[k + "_expected"] = fmt(base + exp) if exp is not None else ""
                res[k + "_confidence"] = fmt(round(conf, 4))
                for li, l in enumerate(c["levels"]):
                    res["%s_p%s" % (k, fmt(l["points"]))] = fmt(round(probs[li], 4))
                h = num(row.get(k + "_human"))
                tm += c["levels"][lvl]["points"]
                if h is None:
                    complete = False
                else:
                    th += h
            if len(body["questions"]) > 1:
                res["total_model"] = fmt(tm)
                res["total_human"] = fmt(th) if complete else ""
        except Exception as e:  # keep going; the row records the error
            if isinstance(e, urllib.error.HTTPError):
                msg = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
            else:
                msg = str(e)
            res["error"] = msg
            audit["error"] = msg
            for c in rb["criteria"]:
                for s in ("_r1", "_r2", "_human"):
                    res[c["key"] + s] = row.get(c["key"] + s, "")
            if i == 1 and isinstance(e, (urllib.error.URLError, ConnectionError)) and not isinstance(e, urllib.error.HTTPError):
                print("Could not reach the model at %s: %s" % (args.url, e))
                return 1
        res["ms"] = int((time.time() - t0) * 1000)
        txt = audit.get("responseText") or ""
        res["response_sha256"] = audit["responseSha256"] = hashlib.sha256(txt.encode()).hexdigest() if txt else ""
        audit["finishedAt"] = datetime.datetime.now().isoformat()
        w.writerow(res)
        fout.flush()
        faud.write(json.dumps(audit, ensure_ascii=False) + "\n")
        faud.flush()
        rate = (time.time() - t_all) / i
        print("  %d/%d %s %s  (%.1fs each, about %d min left)" % (i, len(todo), row["essay_id"], ("error: " + res["error"][:80]) if res.get("error") else "ok", rate, rate * (len(todo) - i) / 60))
    print("Done. Open %s in the app: Benchmark > Explore > Open results CSV." % out)
    return 0

def list_cmd(args):
    m = load_manifest()
    for d in m["datasets"]:
        print("%s  (%s; human = %s)" % (d["id"], d["name"], d["humanIs"]))
        for p in sorted(d["prompts"], key=lambda p: -p["count"])[: (None if args.all else 8)]:
            print("    %-45s %6d" % (p["name"], p["count"]))
        if len(d["prompts"]) > 8 and not args.all:
            print("    … %d more (use --all)" % (len(d["prompts"]) - 8))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare", help="convert the downloaded datasets into datasets/bench/")
    lp = sub.add_parser("list", help="list prepared datasets and prompts")
    lp.add_argument("--all", action="store_true")
    rp = sub.add_parser("run", help="score a sample and write the results CSV")
    rp.add_argument("--dataset", required=True, help="asap7, persuade, persuade_elements or ellipse")
    rp.add_argument("--prompt", help="prompt name (see: benchmark.py list)")
    rp.add_argument("--sample", default="200", help="number of essays, or 'all' (default 200)")
    rp.add_argument("--sampling", default="stratified", choices=["stratified", "random", "first"])
    rp.add_argument("--seed", type=int, default=42)
    rp.add_argument("--rubric", default="official", choices=["official", "adjusted"], help="official (word for word, default) or adjusted")
    rp.add_argument("--context", help="text sent with every essay under CONTEXT FOR SCORING (replaces the rubric's own; '' sends none)")
    rp.add_argument("--provider", default="ollama", choices=["ollama", "jev", "openai", "anthropic"])
    rp.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"), help="API base URL")
    rp.add_argument("--model", default="nimble")
    rp.add_argument("--key", help="API key (or set JEV_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    rp.add_argument("--keep-alive", default="30m")
    rp.add_argument("--name", help="run name shown in the explorer")
    rp.add_argument("--run-id")
    rp.add_argument("-o", "--output")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a)
    elif a.cmd == "list":
        list_cmd(a)
    else:
        if a.provider == "ollama" and a.keep_alive == "":
            a.keep_alive = None
        sys.exit(run(a))

if __name__ == "__main__":
    main()
