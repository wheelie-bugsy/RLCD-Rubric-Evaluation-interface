#!/usr/bin/env python3
"""Build the "Adjusted" variant of every benchmark rubric.

The official rubrics (datasets/bench/rubrics.json, built word for word by build_rubrics.py)
are left untouched. Each Adjusted rubric keeps every level description EXACTLY as in the
official one (this script asserts it) and changes only what is sent around the rubric:

  context       a block sent with every essay: who the writers are, which standard to
                judge against, and notes about the text (e.g. anonymisation tokens).
  instructions  a plain-language question per criterion instead of the generic
                "Which level of this rubric criterion does the essay meet?".

Why: the nimble benchmark runs on ELLIPSE and ASAP set 7 (4 Oct 2026) ranked essays about as
well as a second human rater but scored them 0.8 levels too low, mostly on language criteria,
because the request never said who the writers were (see analysis/nimble-vs-human-gap.md in
the project files).

Writes:
  datasets/bench/rubrics_adjusted.json        (read by the app and benchmark.py)
  datasets/rubrics/<id>_adjusted.rubric.csv   (importable in the Rubrics tab)
  datasets/rubrics/ADJUSTED.md                (what changed, criterion by criterion)
and refreshes the embedded copy in index.html.
"""
import csv, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
BENCH = os.path.join(ROOT, "datasets", "bench")
RUB = os.path.join(ROOT, "datasets", "rubrics")

ANON_NOTE = ("NOTES ON THE TEXT: names, places, dates, numbers and some capitalised words were replaced with tokens "
             "such as @PERSON1, @LOCATION1, @DATE1, @NUM1 and @CAPS1 when the essays were anonymised. Read each token as a "
             "correctly written word and do not count it as an error or as unclear writing. Runs of \"???\" mark characters "
             "that were lost from the data; do not count them as the writer's errors.")

ADJ = {
    "asap7": {
        "context": "ABOUT THE WRITERS: US students in grade 7 (age 12 to 13), each writing a short story about patience in "
                   "class. Score as a trained grade 7 rater would: judge every criterion against what is expected of a "
                   "grade 7 writer, not against polished adult writing. Take into account how much the student wrote: a "
                   "longer, developed story with some errors usually deserves more credit than a very short one with none.\n\n"
                   + ANON_NOTE,
        "q": {
            "ideas": "How well does this grade 7 writer's story stay focused on patience and develop it with specific, relevant details?",
            "organization": "How clearly is this grade 7 writer's story organised, with events and ideas connected in a logical sequence?",
            "style": "How well does this grade 7 writer use language (word choice and sentence variety) to tell the story, judged against grade 7 expectations and the amount written?",
            "conventions": "How well does this grade 7 writer control grammar, usage, spelling, capitalisation and punctuation for the grade level? Judge the overall pattern across the whole story: some errors are normal at grade 7. Ignore anonymisation tokens such as @CAPS1.",
        },
    },
    "persuade_holistic_indy": {
        "context": "ABOUT THE WRITERS: US students in grades 6 to 12, each writing an argumentative essay on the assignment "
                   "without a source text. Score as a trained rater of student writing would: the six scores span the full "
                   "range of school writing, so judge against what students in grades 6 to 12 produce, not against "
                   "published or adult writing. Most student essays score 2, 3 or 4.",
        "q": {"holistic": "Which score from 1 to 6 best describes this student's essay as a whole: its point of view, critical thinking, use of examples and evidence, organisation, language and sentence structure, and conventions?"},
    },
    "persuade_holistic_source": {
        "context": "ABOUT THE WRITERS: US students in grades 6 to 12, each writing an argumentative essay based on a source "
                   "text they read. Score as a trained rater of student writing would: the six scores span the full range of "
                   "school writing, so judge against what students in grades 6 to 12 produce, not against published or adult "
                   "writing. Most student essays score 2, 3 or 4. Using and building on the source text is expected, not copying.",
        "q": {"holistic": "Which score from 1 to 6 best describes this student's essay as a whole: its point of view, critical thinking, use of evidence from the source, organisation, language and sentence structure, and conventions?"},
    },
    "persuade_elements": {
        "context": "ABOUT THE WRITERS: US students in grades 6 to 12. You are rating ONE argument element (for example a "
                   "lead, claim or piece of evidence) taken from a student's argumentative essay; the full essay is included "
                   "only so you can see how the element fits. Score as a trained rater of student writing would: Adequate is "
                   "the usual rating for an element that does its job in an ordinary way; keep Effective for elements that "
                   "are clearly strong and Ineffective for elements that fail at their job. Do not mark an element down for "
                   "spelling or grammar.",
        "q": {
            "lead": "Does this lead catch the reader's attention and point towards the writer's position?",
            "position": "Does this position take a clear stance that is closely related to the topic?",
            "claim": "How relevant is this claim to the writer's position, and how well does it back the position up?",
            "counterclaim": "Is this counterclaim a reasonable, relevant objection to the writer's position?",
            "rebuttal": "How directly and convincingly does this rebuttal answer the counterclaim?",
            "evidence": "How relevant and sound is this evidence for the claim it supports?",
            "concluding_statement": "How well does this concluding statement restate or pull together the essay's claims?",
        },
    },
    "ellipse": {
        "context": "ABOUT THE WRITERS: English language learners in grades 8 to 12 at US schools, each writing an "
                   "argumentative essay on the assignment. Score as a trained rater of English learners would: judge every "
                   "criterion against the range of writing seen in English learners at this stage, not against native "
                   "speakers or adult writers. Level 3 is the typical, middle performance for these learners; use levels 4 "
                   "and 5 for writers who show real control and range even if some errors remain. Judge errors by how "
                   "often they occur across the whole essay and whether they get in the way of meaning, not by counting "
                   "every slip.",
        "q": {
            "overall": "Overall, how well does this English learner use English to communicate their argument?",
            "cohesion": "How well does this English learner organise the essay and connect ideas within and across sentences and paragraphs?",
            "syntax": "How varied and accurate are this English learner's sentence structures?",
            "vocabulary": "How wide and accurate is this English learner's vocabulary for the topic?",
            "phraseology": "How varied and accurate are this English learner's multi-word phrases (idioms, collocations and set expressions)?",
            "grammar": "How accurate is this English learner's grammar and usage, judged across the whole essay and relative to its length?",
            "conventions": "How well does this English learner control spelling, capitalisation and punctuation, judged across the whole essay and relative to its length?",
        },
    },
}


def build():
    official = json.load(open(os.path.join(BENCH, "rubrics.json"), encoding="utf-8"))
    out = {}
    for rid, rb in official.items():
        a = ADJ[rid]
        crits = []
        for c in rb["criteria"]:
            nc = json.loads(json.dumps(c))
            nc["instructions"] = a["q"][c["key"]]
            crits.append(nc)
        adj = {"id": rid + "_adjusted", "name": rb["name"] + " Adjusted", "adjustedFrom": rid,
               "source": rb.get("source", ""), "context": a["context"], "criteria": crits,
               "note": "Same level descriptions as the official rubric, word for word. Adds a context block sent with every "
                       "essay and a plain question per criterion. See datasets/rubrics/ADJUSTED.md."}
        if rb.get("note"):
            adj["note"] = rb["note"] + " " + adj["note"]
        # the level text must be identical to the official rubric
        assert [c["key"] for c in crits] == [c["key"] for c in rb["criteria"]], rid
        for c0, c1 in zip(rb["criteria"], crits):
            assert c0["levels"] == c1["levels"], (rid, c0["key"], "levels changed")
        out[adj["id"]] = adj
    return official, out


def write(official, out):
    json.dump(out, open(os.path.join(BENCH, "rubrics_adjusted.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for rid, rb in out.items():
        with open(os.path.join(RUB, f"{rid}.rubric.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Rubric name", rb["name"]])
            w.writerow(["Context", rb["context"]])
            w.writerow([])
            lv0 = rb["criteria"][0]["levels"]
            w.writerow(["Criterion", "Type", "Weight", "Question for the model"] + [f'{L["label"]} ({L["points"]})' for L in lv0])
            for c in rb["criteria"]:
                w.writerow([c["name"], "score", c["weight"], c["instructions"]] + [L["desc"] for L in c["levels"]])
    with open(os.path.join(RUB, "ADJUSTED.md"), "w", encoding="utf-8") as f:
        f.write("# Adjusted rubrics\n\nBuilt by tools/build_adjusted_rubrics.py. Each Adjusted rubric keeps every level "
                "description of the official rubric word for word (the script checks this). Only two things change:\n\n"
                "1. **Context**: a block sent with every essay, between the assignment and the essay, saying who the "
                "writers are and which standard to judge against.\n"
                "2. **Question for the model**: a plain question per criterion, replacing the generic \"Which level of "
                "this rubric criterion does the essay meet?\".\n\n"
                "Why: on ELLIPSE and ASAP set 7, nimble ranked essays about as well as a second human rater but scored "
                "them about 0.8 levels too low, mostly on language criteria, because the request never said who the "
                "writers were.\n\n")
        for rid, rb in out.items():
            o = official[rb["adjustedFrom"]]
            f.write(f"## {rb['name']}\n\nOfficial rubric: {o['name']} (`{o['id']}`)\n\n**Context sent with every essay**\n\n")
            f.write("\n".join("> " + l if l else ">" for l in rb["context"].split("\n")) + "\n\n")
            f.write("| Criterion | Official question | Adjusted question |\n|---|---|---|\n")
            for c0, c1 in zip(o["criteria"], rb["criteria"]):
                q0 = c0["instructions"] or "Which level of this rubric criterion does the essay meet? (generic)"
                f.write(f"| {c0['name']} | {q0} | {c1['instructions']} |\n")
            f.write("\n")
    # refresh the copy embedded in index.html
    p = os.path.join(ROOT, "index.html")
    s = open(p, encoding="utf-8").read()
    line = "const BENCH_RUBRICS_ADJUSTED = " + json.dumps(out, ensure_ascii=False) + ";"
    s2, n = re.subn(r"^const BENCH_RUBRICS_ADJUSTED = .*;$", lambda m: line, s, flags=re.M)
    if n != 1:
        raise SystemExit("index.html: BENCH_RUBRICS_ADJUSTED line not found")
    open(p, "w", encoding="utf-8").write(s2)
    print("ok:", ", ".join(out))


if __name__ == "__main__":
    write(*build())
