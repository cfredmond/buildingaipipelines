from __future__ import annotations

import os
from typing import Any

from common import html_to_text, http_get, normalize_dedupe_key


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    One-URL extractor (for Step Functions Map fan-out).

    Input (one item + run metadata):
      {
        "run_id": "...",
        "url": "https://example.com",
        "title": "...",                # optional
        "source": "...",               # optional
        "published_at": "YYYY-MM-DD",  # optional

        "timeout_s": 20,               # optional
        "max_chars": 8000,             # optional
        "user_agent": "...",           # optional
      }

    Output: one row (success or error-as-data)
    """
    run_id = str((event or {}).get("run_id") or "").strip()
    url = str((event or {}).get("url") or "").strip()
    title = str((event or {}).get("title") or "")
    source = str((event or {}).get("source") or "")
    date = str((event or {}).get("published_at") or "")

    timeout_s = int((event or {}).get("timeout_s") or 20)
    max_chars = int((event or {}).get("max_chars") or 8000)
    user_agent = str((event or {}).get("user_agent") or "").strip() or "Mozilla/5.0 (compatible; buildingaipipelines.com/1.0)"

    extracted_text = ""
    extraction_status = "error"
    extraction_error = ""

    if not run_id:
        raise RuntimeError("Missing required field: run_id")

    if not url:
        extraction_error = "missing_url"
    else:
        try:
            body, content_type = http_get(url, timeout_s=timeout_s, user_agent=user_agent)
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                extraction_error = f"unsupported_content_type:{(content_type.split(';')[0] or 'unknown')}"
            else:
                text = html_to_text(body.decode("utf-8", errors="ignore"))
                text = text[:max_chars] if max_chars and max_chars > 0 else text
                if not text.strip():
                    extraction_error = "empty_extracted_text"
                else:
                    extracted_text = text
                    extraction_status = "ok"
        except Exception as e:
            extraction_error = f"extraction_error:{type(e).__name__}"

    return {
        "run_id": run_id,
        "title": title,
        "source": source,
        "date": date,
        "url": url,
        "dedupe_key": normalize_dedupe_key(url),
        "extracted_text": extracted_text,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error,
    }

