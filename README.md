## Pipeline CLI

This folder contains a small Python CLI that runs a simple content triage pipeline:

- `search`: export Google Custom Search Engine (CSE) results to a pipeline-ready CSV
- `extract`: fetch each URL and populate `extracted_text` (or record an error)
- `enrich`: use an LLM to label/score each row based on `extracted_text`

It also contains a copy of the **Terraform infrastructure** and **Lambda source** used in the tutorial’s AWS deployment:

- `infra/`: Terraform to provision AWS (IAM, Secrets Manager, S3, Lambda, Step Functions, Scheduler)
- `lambda_src/`: Python Lambda handlers deployed by Terraform

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

Or run from inside this folder:

```bash
cd pipeline
python pipeline.py search  --query "UFO sightings (UAP reports)" --num 5 --out results.csv --run-id 2026-01-05
python pipeline.py extract --in results.csv   --out extracted.csv --max-rows 5
python pipeline.py enrich  --in extracted.csv --out enriched.csv  --max-rows 5
```

Notes:
- Some sites block automated downloads (you’ll see `http_error:403` in `extraction_error`). Those rows are skipped by enrichment.
- The CSV contains multi-line fields; viewing in Sheets/Excel is easiest.

## AWS deployment (Terraform) — starter copy

The Terraform in `pipeline/infra/` is intended to be copied into a separate “starter” repo (it’s a copy, not the live stateful Terraform working directory).

From inside `pipeline/infra/`:

```bash
cd pipeline/infra
terraform init
```

Put a `.env` file in `pipeline/.env` (so `source ../.env` works from the Terraform folder), then:

```bash
set -a
source ../.env
set +a

export TF_VAR_google_cse_api_key="$GOOGLE_CSE_API_KEY"
export TF_VAR_google_cse_cx="$GOOGLE_CSE_CX"
export TF_VAR_openai_api_key="$OPENAI_API_KEY"
export TF_VAR_openai_model="${OPENAI_MODEL:-}"

terraform apply
```


