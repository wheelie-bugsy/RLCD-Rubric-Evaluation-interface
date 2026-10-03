# Nimble Rubric Evaluator

A local web app that scores learners' written responses against your rubric using the
**nimble** decision model running in **Ollama** on your own machine. Nothing leaves your computer.

## Start it (2 minutes)

1. Ollama **0.35 or newer** (it added the `/v1/systemone` endpoint nimble needs):
   `ollama --version`
2. Get the model (about 9.5 GB): `ollama pull nimble`
3. Optional, for written narrative feedback: `ollama pull qwen3:8b` (or any chat model)
4. In this folder: `python3 serve.py` (on Windows: `py serve.py`)
   Your browser opens at http://localhost:8787. The green dot top right means nimble is ready.

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
  Record a **human score** there; agreement between model and human appears on the Results tab.
- **History**: every run is kept in this browser; reopen, rename, reuse its rubric, or export.
- **Audit trail**: every response keeps the exact request sent to Ollama, the raw response text
  (with a SHA-256 fingerprint), timings, model version/digest, the parsed probabilities per level,
  the scoring arithmetic, review flags, human overrides with timestamps, and any feedback-model exchange.
  Open a result to see it, or download it per response (HTML report or raw JSON).
- **Exports**: CSV (includes raw request/response columns), JSON (everything), HTML report,
  Audit report (parsed + raw for every response), print. Runs are stored in the browser's database,
  so raw outputs are never trimmed.
- **Settings**: model names, review thresholds, outcome bands, demo mode (simulated scores to try the UI without Ollama).

## Batch / automation

```
python3 batch_eval.py sample-rubric.csv sample-responses.txt -o results.csv
python3 batch_eval.py my-rubric.csv submissions.csv -o results.csv
```
The rubric is the same CSV template the app uses. Alongside `results.csv` it writes
`results.audit.jsonl`: one line per response with the request, the verbatim model output and its SHA-256.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole web app (no internet or installs needed) |
| `serve.py` | Local server + Ollama proxy (Python standard library only) |
| `batch_eval.py` | Command-line batch scorer using the same rubric format |
| `rubric-template.csv` | Blank rubric template to fill in Excel (also downloadable in the app) |
| `sample-rubric.csv`, `sample-responses.txt` | Reflective-diary example (rubric in template format) |
| `REPORT.md` | Research findings and recommendations |
