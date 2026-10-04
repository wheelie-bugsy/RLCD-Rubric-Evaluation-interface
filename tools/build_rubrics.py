#!/usr/bin/env python3
"""Build the benchmark rubrics WORD FOR WORD from each dataset's official rubric file.

Only formatting changes are allowed: line breaks and repeated spaces become one space,
and leading/trailing spaces are trimmed. Every level description is then checked to be an
exact substring of the whitespace-normalised source text. Two broken words in the ELLIPSE
.docx ("capitalizatio n", "inappropri ately": a space inside the word, a PDF-conversion
artefact) are re-joined; this is listed in the report. Nothing else is changed.

Needs: pdftotext (poppler) for the PERSUADE PDFs. Writes:
  datasets/bench/rubrics.json          (used by the app and benchmark.py)
  datasets/rubrics/<id>.rubric.csv     (importable in the Rubrics tab)
  datasets/rubrics/VERIFY.md           (the exactness report)
"""
import csv, json, os, re, subprocess, zipfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "datasets")
ws = lambda s: re.sub(r"\s+", " ", s).strip()
report, fixes = [], []

def crit(key, name, levels, weight=1, instructions=""):
    return {"key": key, "name": name, "type": "score", "weight": weight, "instructions": instructions,
            "levels": [{"label": l, "desc": d, "points": p} for l, d, p in levels]}

def verify(rid, source_name, source_text, rubric):
    src = ws(source_text)
    rows = []
    for c in rubric["criteria"]:
        for L in c["levels"]:
            ok = L["desc"] in src
            rows.append((c["name"], L["label"], ok))
            if not ok: raise SystemExit(f"NOT EXACT: {rid} / {c['name']} / {L['label']}: {L['desc'][:80]}")
        if c["instructions"]:
            assert c["instructions"] in src, ("instructions not exact", rid, c["name"])
        assert ws(c["name"]).rstrip(":") in src or c["name"] in rubric.get("nameMap", {}), ("name not in source", rid, c["name"])
    report.append((rid, source_name, rows))

R = {}
# ---------- ASAP set 7: the dataset's own `rubrics` column ----------
row = next(csv.DictReader(open(os.path.join(D, "asap7", "asap-7-original.csv"), encoding="utf-8")))
txt, prompt = row["rubrics"], row["prompt"]
blocks = re.split(r"\n(?=[A-Z][A-Za-z ()]+:\n)", "\n" + txt.strip())
crits = []
for b in [x for x in blocks if x.strip()]:
    head, *lines = b.strip().split("\n")
    name = head.rstrip(":").strip()
    lv = []
    for l in lines:
        m = re.match(r"^(\d+):\s*(.*)$", l)
        if m: lv.append((m.group(1), ws(m.group(2)), int(m.group(1))))
    key = re.sub(r"[^a-z]+", "_", name.split(" (")[0].lower()).strip("_")
    crits.append(crit(key, name, lv, weight=2 if "doubled" in name else 1))
R["asap7"] = {"id": "asap7", "name": "ASAP set 7 (patience narrative)", "source": "llm-aes/asap-7-original, column `rubrics` (Hewlett ASAP-AES set 7)",
              "criteria": crits, "sourceText": txt}
verify("asap7", "asap-7-original.csv `rubrics` column", txt, R["asap7"])

# ---------- PERSUADE holistic (independent and source-based PDFs) ----------
def pdftext(p): return subprocess.run(["pdftotext", p, "-"], capture_output=True, text=True, check=True).stdout
for rid, f, nm in [("persuade_holistic_indy", "sat_rubric_only_indy.pdf", "independent"), ("persuade_holistic_source", "sat_rubric_only_source_based.pdf", "source-based")]:
    t = pdftext(os.path.join(D, "persuade", f)); flat = ws(t)
    intro = flat[flat.index("After reading"):flat.index("SCORE OF 6")].strip()
    parts = re.split(r"SCORE OF (\d): ", flat)
    lv = {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}
    c = crit("holistic", "Holistic Rating Form", [(f"SCORE OF {i}", lv[i], i) for i in range(1, 7)], instructions=intro)
    R[rid] = {"id": rid, "name": f"PERSUADE 2.0 holistic ({nm})", "source": f"persuade_corpus_2.0/{f}", "criteria": [c], "sourceText": t}
    verify(rid, f, t, R[rid])

# ---------- PERSUADE argument-element effectiveness ----------
t = pdftext(os.path.join(D, "persuade", "argumentation_effectiveness_rubric.pdf"))
EFF = [("lead", "Lead", ["The lead may not grab the readers' attention and may not point to the position.", "The lead attempts to grab the reader’s attention and points toward the position.", "The lead grabs the reader’s attention and strongly points toward the position."]),
 ("position", "Position", ["The position is not relevant to the topic, and/or it shows no clear stance.", "The position addresses the topic but generally repeats the prompt's stance.", "The position states a clear stance closely related to the topic."]),
 ("claim", "Claim", ["The claim is irrelevant to the position. It may also be weak and/or not acceptable.", "The claim relates to the position but may simply repeat part of the position or state a claim without support. The claim is moderately valid and acceptable.", "The claim is closely relevant to the position and backs up the position with specific points or perspectives. The claim is valid and acceptable."]),
 ("counterclaim", "Counterclaim", ["The counterclaim is neither reasonable nor relevant.", "The counterclaim is not quite a reasonable opposing opinion, or it is not closely relevant to the position.", "The counterclaim is reasonable and relevant. It represents a valid objection to the position."]),
 ("rebuttal", "Rebuttal", ["The rebuttal misses the target. It does not refute the counterclaim.", "The rebuttal does not answer the counterclaim directly and it is not strong and/or valid.", "The rebuttal directly answers and refutes the counterclaim."]),
 ("evidence", "Evidence", ["The evidence is irrelevant to the claim it backs up and provide few valid examples. The evidence uses unsubstantiated assumptions that sound quite unacceptable.", "The evidence is not closely relevant to the claim it supports. The evidence contains some detailed examples but they may not be relevant to each other and only loosely bound together. The evidence uses some unsubstantiated or unsound claims or assumptions.", "The evidence is closely relevant to the claim they support and back up the claim objectively with concrete facts, examples, research, statistics, or studies. The reasons in the evidence support the claim and are sound and well substantiated."]),
 ("concluding_statement", "Concluding summary", ["The concluding summary is irrelevant to the claims. The conclusion may also misrepresent the claims.", "The concluding summary merely copies the claims or may restates only part of the claims. It may partially misrepresent the claims.", "The concluding summary effectively restates the claims using different wording. It may readdress the claims in light of the evidence provided."])]
R["persuade_elements"] = {"id": "persuade_elements", "name": "PERSUADE 2.0 argument element effectiveness", "source": "persuade_corpus_2.0/argumentation_effectiveness_rubric.pdf",
    "criteria": [crit(k, n, [(l, d, i) for i, (l, d) in enumerate(zip(["Ineffective", "Adequate", "Effective"], v))]) for k, n, v in EFF], "sourceText": t,
    "note": "One criterion per element type. Each element is scored only on the criterion for its own type."}
verify("persuade_elements", "argumentation_effectiveness_rubric.pdf", t, R["persuade_elements"])

# ---------- ELLIPSE (.docx) ----------
x = zipfile.ZipFile(os.path.join(D, "ellipse", "ELL_Rubrics.docx")).read("word/document.xml").decode()
def cell(c): return ws(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", " ", c)).replace("&amp;", "&").replace("&apos;", "'").replace("&quot;", '"'))
rows = [[cell(c) for c in re.findall(r"<w:tc>.*?</w:tc>", tr, flags=re.S)] for tr in re.findall(r"<w:tr[ >].*?</w:tr>", x, flags=re.S)]
raw_text = " ".join(" ".join(r) for r in rows)
REJOIN = {"capitalizatio n": "capitalization", "inappropri ately": "inappropriately"}
def fix(s):
    for a, b in REJOIN.items():
        if a in s: fixes.append(f"ELLIPSE: re-joined “{a}” → “{b}”"); s = s.replace(a, b)
    return s
header = next(r for r in rows if "Cohesion" in r)
names = [h for h in header if h][-7:]
lv = {int(r[0]): r[1:8] for r in rows if r and r[0] in "12345" and r[0] and len(r) >= 8}
R["ellipse"] = {"id": "ellipse", "name": "ELLIPSE English proficiency", "source": "ELLIPSE-Corpus/ELL_Rubrics.docx",
    "criteria": [crit(n.lower(), n, [(str(i), fix(lv[i][j]), i) for i in range(1, 6)]) for j, n in enumerate(names)], "sourceText": raw_text}
src_fixed = raw_text
for a, b in REJOIN.items(): src_fixed = src_fixed.replace(a, b)
verify("ellipse", "ELL_Rubrics.docx (two broken words re-joined)", src_fixed, R["ellipse"])

# ---------- write ----------
out = {k: {kk: vv for kk, vv in v.items() if kk != "sourceText"} for k, v in R.items()}
json.dump(out, open(os.path.join(D, "bench", "rubrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.makedirs(os.path.join(D, "rubrics"), exist_ok=True)
for f in os.listdir(os.path.join(D, "rubrics")):
    if f.endswith(".rubric.csv"): os.remove(os.path.join(D, "rubrics", f))
for rid, rb in out.items():
    with open(os.path.join(D, "rubrics", f"{rid}.rubric.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Rubric name", rb["name"]]); w.writerow([])
        n = max(len(c["levels"]) for c in rb["criteria"])
        lv0 = rb["criteria"][0]["levels"]
        w.writerow(["Criterion", "Type", "Weight", "Question for the model"] + [f'{L["label"]} ({L["points"]})' for L in lv0])
        for c in rb["criteria"]:
            w.writerow([c["name"], "score", c["weight"], c["instructions"]] + [L["desc"] for L in c["levels"]])
with open(os.path.join(D, "rubrics", "VERIFY.md"), "w", encoding="utf-8") as f:
    f.write(f"# Rubric exactness check\n\nBuilt {datetime.date.today()} by tools/build_rubrics.py.\n\n"
            "Every level description below was checked to be an exact substring of the official source file, "
            "after only whitespace was normalised (line breaks and repeated spaces become one space).\n\n")
    f.write("Changes other than whitespace:\n\n" + ("\n".join(f"- {x}" for x in sorted(set(fixes))) or "- none") + "\n\n")
    for rid, src, rows in report:
        f.write(f"## {out[rid]['name']}\n\nSource: {src}\n\n| Criterion | Level | Exact |\n|---|---|---|\n")
        for c, l, ok in rows: f.write(f"| {c} | {l} | {'yes' if ok else 'NO'} |\n")
        f.write("\n")
print("ok:", {k: len(v["criteria"]) for k, v in out.items()}, "fixes:", sorted(set(fixes)))
