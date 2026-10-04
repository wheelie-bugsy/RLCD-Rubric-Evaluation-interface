# Nimble Rubric Evaluator

A local web app that scores learners' written responses against your rubric using the
**nimble** decision model running in **Ollama** on your own machine. Nothing leaves your computer.
Cloud models (TypeSafe Jev, OpenAI, Anthropic, Gemini, OpenRouter, Groq, Mistral) can be used instead.

**New to it?** Read `help/quick-start-guide.pdf` (13 pages, no install needed to read), or open the **? Help** tab in the app.

## Start it (2 minutes)

1. Ollama **0.35 or newer** (it added the `/v1/systemone` endpoint nimble needs):
   `ollama --version`
2. Get the model (about 9.5 GB): `ollama pull nimble`
3. Optional, for written narrative feedback: `ollama pull qwen3:8b` (or any chat model)
4. In this folder: `python3 serve.py` (on Windows: `py serve.py`)
   Your browser opens at http://localhost:8787. The blue dot top right means nimble is ready.

`serve.py` serves the page and forwards requests to Ollama, so no CORS setup is needed.
If you'd rather open `index.html` directly, set Settings → Ollama URL to `http://localhost:11434`
and start Ollama with `OLLAMA_ORIGINS="*" ollama serve`.

## Using it

- **Rubrics**: your rubric library on the left. The **Edit** view shows the rubric as a grid
  (criteria as rows, levels as columns, lowest to highest). Click any cell to edit it.
  **Import & template**: download the blank or sample CSV template, fill it in Excel, then drop,
  upload or paste it. You get a row-by-row preview (ready / warning / error) before anything is saved.
  **Export CSV** turns any rubric back into the same template layout.
- **Evaluate**: pick a rubric, paste responses separated by `---` lines (start each with `Name: …`)
  or import a CSV (there's a responses template too), then run. "Try sample" loads a worked example.
- **Results**: summary cards, average per criterion, outcome bands, and a sortable table.
  Click any row for the probability Nimble gave each level, feedback text, and the raw output.
- **Reviewing scores**: every score in the table has a ✓ circle (tick = agree with the model) and a
  dropdown on the level name (pick a different level = override). Each row has **✓ Agree rest**.
  Tick rows on the left for the bulk bar: agree on all or one criterion, set a criterion to a level,
  or clear. The detail view has a level button strip per criterion. Agreement stats update live.
- **History**: every run is kept in this browser; reopen, rename, reuse its rubric, or export.
- **Audit trail**: every response keeps the exact request sent to Ollama, the raw response text
  (with a SHA-256 fingerprint), timings, model version/digest, the parsed probabilities per level,
  the scoring arithmetic, review flags, human overrides with timestamps, and any feedback-model exchange.
  Open a result to see it, or download it per response (HTML report or raw JSON).
- **Exports**: CSV (includes raw request/response columns), JSON (everything), HTML report,
  Audit report (parsed + raw for every response), print. Runs are stored in the browser's database,
  so raw outputs are never trimmed.
- **Connecting other models** (Settings → Connect to): Ollama nimble / tev1 / remote Ollama; TypeSafe Jev cloud
  (API key); or a general LLM as judge via OpenAI, Anthropic, Gemini, OpenRouter, Groq, Mistral or any
  OpenAI-compatible API, plus local Ollama chat models or LM Studio. Cloud calls go through `serve.py`, which only
  forwards to known AI provider hosts (add more with `EXTRA_HOSTS=host python3 serve.py`). API keys stay in the browser.
- **Blind grading**: tick it on Evaluate (or the switch on Results) to hide the model's scores, flags and feedback
  while you grade. Click **Reveal model results** when done.
- **Model vs human alignment**: under the results table. Exact match, within one level, model higher/lower,
  kappa, a model-vs-human grid per criterion, per-response comparison, and a full change history of every
  grade given, changed, cleared or undone. Download it for the whole run or per learner.
- **No confirm popups**: single grading edits are confirmed in the cell itself; other actions (delete, clear, rename, bulk review) show ONE compact message in the
  bottom-left with **Undo** for 10 seconds (hover to pause, or press Ctrl/Cmd+Z).
- **Colours**: colour-blind-safe Okabe-Ito scale (vermillion → orange → sky → blue, low to high);
  the rest of the UI is neutral ink, and status pills also carry ✓ / ! / ✕ icons.
- **Benchmark** (◎ tab): checks the model against people before you trust it. Pick a public human-graded
  dataset (ASAP-AES set 7, PERSUADE 2.0 holistic or argument elements, ELLIPSE) and one prompt, choose a sample
  (stratified by human score, seeded so it's repeatable), and run. Each essay is scored with the dataset's own
  rubric, word for word (`datasets/rubrics/VERIFY.md` records the check). Progress is saved after every essay;
  pause and resume any time. **Explore results** compares model and humans: QWK, exact / within one, bias,
  rater-vs-rater ceiling, filters by grade, gender, ELL status and so on, charts, and every essay with both
  scores and the exact request and reply. You can also upload your own graded CSV and benchmark your own rubric.
- **Settings**: model names, review thresholds, outcome bands, demo mode (simulated scores to try the UI without Ollama).

## Batch / automation

```
python3 batch_eval.py sample-rubric.csv sample-responses.txt -o results.csv
python3 batch_eval.py my-rubric.csv submissions.csv -o results.csv
```
The rubric is the same CSV template the app uses. Alongside `results.csv` it writes
`results.audit.jsonl`: one line per response with the request, the verbatim model output and its SHA-256.

### Benchmark from the terminal

```
python3 benchmark.py list
python3 benchmark.py run --dataset ellipse --prompt "Distance learning" --sample 200 -o ellipse-dl-nimble.csv
python3 benchmark.py run --dataset asap7 --sample all --model tev1
```
Same rubrics, request, sampling and columns as the tab (the same seed picks the same essays), and its CSV opens
in the explorer. Re-running the same command resumes. Keys come from `--key` or `JEV_API_KEY` / `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` and are never written to the results. To rebuild from the original downloads:
`python3 tools/build_rubrics.py` then `python3 benchmark.py prepare`.

Data sources: ASAP set 7 (huggingface.co/datasets/llm-aes/asap-7-original), PERSUADE 2.0
(github.com/scrosseye/persuade_corpus_2.0), ELLIPSE (github.com/scrosseye/ELLIPSE-Corpus).
PERSUADE and ELLIPSE are CC BY-NC-SA 4.0: internal benchmarking with attribution only, no commercial use or redistribution.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole web app (no internet or installs needed) |
| `serve.py` | Local server + Ollama proxy (Python standard library only) |
| `batch_eval.py` | Command-line batch scorer using the same rubric format |
| `rubric-template.csv` | Blank rubric template to fill in Excel (also downloadable in the app) |
| `sample-rubric.csv`, `sample-responses.txt` | Reflective-diary example (rubric in template format) |
| `REPORT.md` | Research findings and recommendations |
| `help/quick-start-guide.pdf` | Printable scenario-based quick start guide |
| `help/*.png` | Annotated screenshots used by the Help tab |
| `benchmark.py` | Command-line benchmark runner (standard library only) |
| `tools/build_rubrics.py` | Rebuilds the benchmark rubrics from the official rubric files and checks they're word for word |
| `datasets/bench/` | Prepared benchmark data (one CSV per prompt) and `manifest.json` the app loads |
| `datasets/rubrics/` | Benchmark rubrics as importable CSVs, plus `VERIFY.md` |
| `datasets/asap7/`, `persuade/`, `ellipse/` | Original downloads (not in the zip; see above for where to get them) |
