# Report: rubric-based evaluation of written responses with Ollama + Nimble

Prepared 3 October 2026 for the corporate learning evaluation project.

## 1. Summary

- **Nimble is a good fit for scoring, but it cannot write feedback.** It is a 9B *decision* model: you give it text plus typed questions and it returns a choice, a yes/no, or a rubric level, each with a probability. It does not generate explanations. Feedback text has to come from your rubric's level descriptions or from a second, generative model. The app does both.
- **It is fast and private.** Around 100 ms per decision on high-end Apple hardware, and all criteria for one response go in a single call. Everything runs on your machine, which suits learner data.
- **Accuracy on graded rubric levels is the weak spot.** Published comparisons find Jev-style models match LLM judges on yes/no criteria but trail on multi-level scales, and *all* automated judges tend to score lower than human raters. You need to measure agreement on your own rubrics before automating. The app has a built-in human-vs-model agreement panel for this.
- **Recommended use:** automate first-pass scoring and feedback, route low-confidence or borderline results to a human, and keep a human-scored calibration set per rubric.

## 2. What Nimble and "Jev" are

| | |
|---|---|
| Jev | A proprietary "System One" decision API from TypeSafe AI. It returns typed answers (choice / yes-no ("noul") / score) with calibrated probabilities instead of free text. |
| Nimble | An open-source (Apache 2.0) 9B model from Bespoke Labs, fine-tuned from Qwen3.5-9B to make Jev-style decisions. It is inspired by Jev but not distilled from it. |
| Ollama support | Ollama 0.35 added a local `/v1/systemone` endpoint that follows the Jev API, with `nimble` (9B, about 9.5 GB) and the experimental `tev1` (4B and 0.8B) models. |
| Reported accuracy | 90.1% agreement on Bespoke's held-out set (Jev: 93.2%, base Qwen: 66.4%); 75.7% across 13 public datasets. |

**Limits that shape the design** (from the Ollama model page and the Nimble README):
- Text only. At most **8,192 tokens** per request (rubric + assignment + response), 64 KiB body, 1 to 64 questions.
- Score questions take **2 to 10 levels**, ordered lowest to highest.
- Each question is answered independently; any cross-criterion logic is yours.
- "Confidence" measures how concentrated the probabilities are, not the chance of being right. Thresholds must be tuned on your data.

## 3. How the API maps to a rubric

One request per learner response. Every rubric criterion becomes one named question:

```json
POST http://localhost:11434/v1/systemone
{
  "model": "nimble",
  "state": "ASSIGNMENT GIVEN TO THE LEARNER:\n...\n\nLEARNER'S WRITTEN RESPONSE:\n...",
  "questions": {
    "c3_analysis_and_learning": {
      "type": "score",
      "instructions": "Criterion \"Analysis and learning\". How deeply does the learner analyse why things happened?",
      "criteria": [
        "Beginning: No analysis; restates events without explaining causes.",
        "Developing: Some explanation of causes, but learning is generic.",
        "Proficient: Identifies specific causes and states clear lessons.",
        "Exemplary: Insightful, multi-perspective analysis with transferable lessons."
      ]
    },
    "c5_professional_tone": {
      "type": "noul",
      "instructions": "Is the entry written in a professional, respectful tone?",
      "criteria": { "true": "Respectful and professional throughout.", "false": "Contains insults or blame-laden language." }
    }
  }
}
```

Each score answer returns `score` (the probability-weighted level, e.g. 1.43), `probabilities` per level, a `legend`, and `confidence`. The app takes the **most probable level** (the same rule Nimble's own benchmarks use), converts it to points, applies criterion weights, and maps the overall percentage to outcome bands.

## 4. The system built

The files are in this folder; see `README.md` to run it.

```
Browser (index.html) ──► serve.py (localhost:8787) ──► Ollama (localhost:11434)
   Evaluate / Results /        static files + proxy          /v1/systemone  → nimble (scores)
   History / Settings                                         /api/chat      → optional feedback model
```

- **Evaluate tab:** rubric builder (score, yes/no and choice criteria, weights, points), paste/import from Excel, Word, Markdown or JSON, rubric library, response import (`---` separated or CSV), pre-flight checks (level counts, the 8,192-token limit, short responses), request preview and copyable curl.
- **Results tab:** summary cards, average by criterion, outcome band distribution, a sortable and filterable table with coloured level chips, and per-response detail showing the probability of every level, feedback, and raw output.
- **Review rules:** a result is flagged if any criterion's confidence is below 0.5, the top two levels are within 15 points, the response is under 40 words, or the built-in "on-topic" check fails. All of these are adjustable.
- **Human calibration:** record a human score per criterion (or "agree with model") and the Results tab shows exact agreement, within-one-level agreement, and model bias per criterion.
- **Feedback:** always generated from the rubric ("you're at Developing; to reach Proficient: …"). Optionally, a generative model (for example `qwen3:8b`) writes narrative feedback, and it is told the scores are fixed so it can't contradict them.
- **History and reports:** runs are saved in the browser and can be exported to CSV, JSON or HTML, or printed. `batch_eval.py` does the same scoring from the command line for automation.

**Testing note:** this was built in a cloud sandbox with no GPU, so it was tested end to end in a real browser against a mock Ollama that implements the documented `/v1/systemone` format, not against the real nimble weights. The answer parser also accepts small variations in the response shape. If anything looks off on your first real run, open a result's "Raw model output" and send it over; the fix will be quick.

## 5. Will it be accurate enough? What the evidence says

The most relevant study, *JEV vs. LLMs as Rubric Judges* (arXiv 2609.29769), found:
- Jev matched or beat LLM judges on **binary** criteria, but trailed on **graded** scales. On ELLIPSE essay scoring, its exact-level accuracy was 13.4% against Gemini's 29.8%.
- LLM judges cost 29 to 325 times more and were 30 to 220 times slower.
- All judges **scored systematically lower than human raters**, and agreed with each other more than with humans. The criterion text alone lacks the raters' unwritten conventions.
- Cascading to a bigger model on low confidence helped little, because the errors are correlated.

What that means for reflective diaries and written answers:
1. **Turn graded criteria into observable checks where you can.** "States a specific action with a timeframe" (yes/no) is much more reliable than "quality of action plan, 1 to 5". A good pattern is a few yes/no evidence checks plus 3 to 4 level scores.
2. **Write levels as observable descriptions, not degrees.** "Identifies specific causes and states lessons learned" beats "Good analysis". Keep each criterion to one dimension. The Score docs say this directly, and the builder warns about empty descriptions.
3. **Put rater conventions into the text.** If your assessors expect a newcomer to sit at "Developing", say so in the level descriptions; this addresses the under-scoring the study found.
4. **Use 4 levels, not 10.** Fewer, clearly separated levels give higher exact agreement.
5. **Calibrate before automating.** For each rubric, have humans score 30 to 50 responses, record their scores in the app, and check exact and within-one-level agreement plus bias. Rough bar: at least 70% exact on yes/no checks and at least 85% within one level on 4-level scales before results go to learners without review.
6. **Keep a human in the loop for flagged items.** Tune the confidence threshold until flagged items catch most disagreements.

## 6. Practical notes for a corporate rollout

- **Hardware:** about 18 GB of memory for nimble's weights plus overhead. Apple Silicon with 32 GB or more, or an NVIDIA GPU with 16 to 24 GB, is comfortable. Add about 6 GB if you also run an 8B feedback model.
- **Privacy:** fully local by default. To share on a network, run `serve.py --host 0.0.0.0` behind your normal access controls.
- **Long responses:** stay under about 6,000 words including the rubric. For longer submissions, score section by section.
- **Other use cases** fit the same pattern: compliance-scenario answers (yes/no checks), coaching-conversation transcripts (choice and score), routing submissions to the right reviewer (choice), and safety or tone screening (yes/no).
- **Next steps:** (1) run your real rubrics on 30 to 50 human-scored responses; (2) tighten level wording where agreement is low; (3) set review thresholds; (4) wire `batch_eval.py` into your LMS export and import.

## Sources

- [Ollama blog: Ollama now supports Jev-style decision models](https://ollama.com/blog/ollama-now-supports-jev-style-decision-models)
- [Ollama library: nimble](https://ollama.com/library/nimble)
- [bespokelabsai/nimble on GitHub](https://github.com/bespokelabsai/nimble) and its [public benchmarks](https://github.com/bespokelabsai/nimble/blob/main/docs/PUBLIC_BENCHMARKS.md)
- [TypeSafe Jev API reference](https://docs.typesafe.ai/api) and the [Score primitive](https://docs.typesafe.ai/primitives/score)
- [JEV vs. LLMs as Rubric Judges (arXiv 2609.29769)](https://arxiv.org/abs/2609.29769)
- [Jev, Nimble & Laya: Can Decision Models Run Locally? (LocalClaw)](https://localclaw.io/blog/jev-nimble-laya-local-decision-models)
