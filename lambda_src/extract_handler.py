from __future__ import annotations

import json
import os
from typing import Any

from common import s3_put_text


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Extract results writer (fast). This replaces the old sequential extractor.

    Input:
      {
        "run_id": "...",
        "urls_s3_key": "runs/<run_id>/urls.json",                 # optional (kept for pass-through)
        "extract_results": [ { ...row... }, { ...row... } ],      # required (from Step Functions Map)
        "extracted_s3_key": "runs/<run_id>/extracted.jsonl"       # optional
      }

    Output:
      { "run_id": "...", "urls_s3_key": "...", "extracted_s3_key": "..." }
    """
    run_id = str((event or {}).get("run_id") or "").strip()
    urls_s3_key = str((event or {}).get("urls_s3_key") or "").strip()
    extracted_s3_key = str((event or {}).get("extracted_s3_key") or "").strip() or f"runs/{run_id}/extracted.jsonl"
    extract_results = (event or {}).get("extract_results")

    if not run_id:
        raise RuntimeError("Missing required field: run_id")
    if not isinstance(extract_results, list):
        raise RuntimeError("Missing required field: extract_results (must be a list)")

    bucket = str((event or {}).get("artifacts_bucket") or "").strip() or os.environ["ARTIFACTS_BUCKET"]

    out_lines: list[str] = []
    for row in extract_results:
        if not isinstance(row, dict):
            continue
        out_lines.append(json.dumps(row, ensure_ascii=False))

    s3_put_text(bucket, extracted_s3_key, "\n".join(out_lines) + ("\n" if out_lines else ""), content_type="application/x-ndjson")
    return {"run_id": run_id, "urls_s3_key": urls_s3_key, "extracted_s3_key": extracted_s3_key}

