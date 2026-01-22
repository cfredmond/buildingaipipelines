## Pipeline CLI

This folder contains a small Python CLI that runs a simple content triage pipeline:

- `search`: export Google Custom Search Engine (CSE) results to a pipeline-ready CSV
- `extract`: fetch each URL and populate `extracted_text` (or record an error)
- `enrich`: use an LLM to label/score each row based on `extracted_text`

### Setup

1) Install dependencies

From the repo root:

```bash
pip install -r pipeline/requirements.txt
```

Or from inside this folder:

```bash
cd pipeline
pip install -r requirements.txt
```

2) Set environment variables

Create a `.env` file in the directory you run the commands from (commonly the repo root). `pipeline.py` will load it automatically if `python-dotenv` is installed.

Required:
- `GOOGLE_CSE_API_KEY`
- `GOOGLE_CSE_CX`
- `OPENAI_API_KEY`

Optional:
- `OPENAI_MODEL` (default: `gpt-4o-mini`)

### Usage

Run from the repo root:

```bash
python pipeline/pipeline.py search  --query "UFO sightings (UAP reports)" --num 5 --out results.csv --run-id 2026-01-05
python pipeline/pipeline.py extract --in results.csv   --out extracted.csv --max-rows 5
python pipeline/pipeline.py enrich  --in extracted.csv --out enriched.csv  --max-rows 5
```

Notes:
- Some sites block automated downloads (you’ll see `http_error:403` in `extraction_error`). Those rows are skipped by enrichment.
- The CSV contains multi-line fields; viewing in Sheets/Excel is easiest.

