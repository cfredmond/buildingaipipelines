from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from common import get_api_keys, s3_put_text

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def _extract_published_date(item: dict[str, Any]) -> str:
    """
    Best-effort (copied from pipeline.py): return ISO date (YYYY-MM-DD) when possible; else empty.
    """
    pagemap = item.get("pagemap") or {}
    metatags = pagemap.get("metatags") or []
    if metatags and isinstance(metatags, list):
        mt = metatags[0] or {}
        candidates = [
            mt.get("article:published_time"),
            mt.get("og:published_time"),
            mt.get("date"),
            mt.get("pubdate"),
        ]
        for c in candidates:
            if not c or not isinstance(c, str):
                continue
            if re.match(r"^\\d{4}-\\d{2}-\\d{2}", c):
                return c[:10]
    return ""


def _google_search_page(api_key: str, cx: str, q: str, start: int, num: int) -> dict[str, Any]:
    params = {
        "key": api_key,
        "cx": cx,
        "q": q,
        "num": min(num, 10),  # API max per request is 10
        "start": start,  # pagination: 1, 11, 21, ...
    }
    url = f"{GOOGLE_CSE_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _google_search_results(api_key: str, cx: str, q: str, total: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    start = 1
    while len(results) < total:
        data = _google_search_page(api_key=api_key, cx=cx, q=q, start=start, num=min(10, total - len(results)))
        items = data.get("items", []) or []
        if not items:
            break
        results.extend(items)
        start += 10
    return results[:total]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Input (from schedule / Step Functions):
      {
        "run_id": "2026-01-05",
        "query": "...",
        "max_urls": 50
      }

    Output:
      {
        "run_id": "...",
        "urls_s3_key": "runs/<run_id>/urls.json",
        "urls": [ ... ]   # returned for Step Functions Map fan-out
      }
    """
    run_id = str((event or {}).get("run_id") or "").strip()
    query = str((event or {}).get("query") or "").strip()
    max_urls = int((event or {}).get("max_urls") or 50)
    if not run_id:
        raise RuntimeError("Missing required field: run_id")
    if not query:
        raise RuntimeError("Missing required field: query")

    bucket = str((event or {}).get("artifacts_bucket") or "").strip()  # optional override
    if not bucket:
        # default from Lambda env set by Terraform
        import os

        bucket = os.environ["ARTIFACTS_BUCKET"]

    keys = get_api_keys()
    api_key = str(keys.get("GOOGLE_CSE_API_KEY") or "").strip()
    cx = str(keys.get("GOOGLE_CSE_CX") or "").strip()
    if not api_key or not cx:
        raise RuntimeError("Missing GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX in Secrets Manager JSON secret")

    items = _google_search_results(api_key=api_key, cx=cx, q=query, total=max(1, max_urls))
    urls = []
    for item in items:
        url = item.get("link") or ""
        urls.append(
            {
                "url": url,
                "title": item.get("title") or "",
                "source": item.get("displayLink") or "",
                "published_at": _extract_published_date(item),
            }
        )

    urls_s3_key = f"runs/{run_id}/urls.json"
    s3_put_text(bucket, urls_s3_key, json.dumps(urls, ensure_ascii=False, indent=2), content_type="application/json")

    return {"run_id": run_id, "urls_s3_key": urls_s3_key, "urls": urls}

