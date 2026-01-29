from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from common import s3_get_text, s3_put_text


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Input:
      {
        "run_id": "...",
        "enriched_s3_key": "runs/<run_id>/enriched.jsonl",
        "report_s3_key": "runs/<run_id>/report.csv"   # optional
      }

    Output:
      { "run_id": "...", "enriched_s3_key": "...", "report_s3_key": "..." }
    """
    run_id = str((event or {}).get("run_id") or "").strip()
    enriched_s3_key = str((event or {}).get("enriched_s3_key") or "").strip()
    report_s3_key = str((event or {}).get("report_s3_key") or "").strip() or f"runs/{run_id}/report.csv"
    if not run_id:
        raise RuntimeError("Missing required field: run_id")
    if not enriched_s3_key:
        raise RuntimeError("Missing required field: enriched_s3_key")

    bucket = str((event or {}).get("artifacts_bucket") or "").strip() or os.environ["ARTIFACTS_BUCKET"]
    raw = s3_get_text(bucket, enriched_s3_key)
    rows = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]

    # Simple report columns (easy to extend later)
    fieldnames = ["run_id", "date", "source", "title", "url", "label", "type", "relevance_score", "reason"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        out = {k: r.get(k, "") for k in fieldnames}
        w.writerow(out)

    s3_put_text(bucket, report_s3_key, buf.getvalue(), content_type="text/csv")
    return {"run_id": run_id, "enriched_s3_key": enriched_s3_key, "report_s3_key": report_s3_key}

