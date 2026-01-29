from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date as date_type
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

import requests
from bs4 import BeautifulSoup

if load_dotenv:
    load_dotenv()

URL = "https://www.googleapis.com/customsearch/v1"

CSV_COLUMNS = [
    "run_id",
    "query",
    "title",
    "source",
    "date",
    "url",
    "dedupe_key",
    "snippet",
    "extracted_text",
    "extraction_status",
    "extraction_error",
    "label",
    "type",
    "relevance_score",
    "reason",
]

ENRICH_PROMPT_TEMPLATE = """You are helping me triage search results for the topic: "{topic}".

Return ONLY valid JSON with:
- label: "on_topic" or "off_topic"
- type: one of "sighting_report", "analysis", "government_or_policy", "entertainment", "other"
- relevance_score: integer 0-100
- reason: one short sentence explaining the score

Text:
\"\"\"
{text}
\"\"\""""


def normalize_dedupe_key(raw_url: str) -> str:
    """
    A stable key to dedupe across runs:
    - lowercase host
    - strip fragments
    - drop tracking query params (utm_*, gclid, fbclid, etc.)
    - keep path
    Output is "host/path" (no scheme) to stay compact.
    """
    raw = (raw_url or "").strip()
    if not raw:
        return ""

    try:
        u = urlparse(raw)
    except Exception:
        return raw.lower()

    drop_prefixes = ("utm_",)
    drop_keys = {"gclid", "fbclid", "yclid", "mc_cid", "mc_eid"}

    kept = []
    for k, v in parse_qsl(u.query, keep_blank_values=True):
        kl = (k or "").lower()
        if any(kl.startswith(p) for p in drop_prefixes):
            continue
        if kl in drop_keys:
            continue
        kept.append((k, v))

    query = urlencode(kept, doseq=True)
    cleaned = urlunparse((u.scheme, u.netloc, u.path, u.params, query, ""))  # strip fragment

    cu = urlparse(cleaned)
    host = (cu.netloc or "").lower()
    path = re.sub(r"/+$", "", cu.path or "/")  # remove trailing slashes
    return f"{host}{path}"


def extract_published_date(item: dict) -> str:
    """
    Best-effort extraction. Google CSE sometimes exposes dates in pagemap metatags.
    Return ISO date (YYYY-MM-DD) when possible; else empty.
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
            if re.match(r"^\d{4}-\d{2}-\d{2}", c):
                return c[:10]
    return ""


def google_search_page(api_key: str, cx: str, q: str, start: int, num: int) -> dict:
    params = {
        "key": api_key,
        "cx": cx,
        "q": q,
        "num": min(num, 10),  # API max per request is 10
        "start": start,  # pagination: 1, 11, 21, ...
    }
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def google_search_results(api_key: str, cx: str, q: str, total: int) -> list[dict]:
    results: list[dict] = []
    start = 1
    while len(results) < total:
        data = google_search_page(api_key, cx, q, start=start, num=min(10, total - len(results)))
        items = data.get("items", []) or []
        if not items:
            break
        results.extend(items)
        start += 10
    return results[:total]


def write_csv(out_path: str, rows: list[dict]) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_csv(in_path: str) -> list[dict]:
    with open(in_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: list[dict] = []
        for row in reader:
            rows.append({k: (v if v is not None else "") for k, v in row.items()})
        return rows


def _extract_first_json_object(text: str) -> dict:
    """
    Best-effort: try strict JSON first; if that fails, locate the first {...} block.
    """
    s = (text or "").strip()
    if not s:
        raise ValueError("empty LLM response")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(s[start : end + 1])


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")

    # Remove non-content / chrome elements that frequently pollute extraction.
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
            "button",
            "iframe",
        ]
    ):
        tag.decompose()

    # Prefer main content containers when available.
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find(id=re.compile(r"(content|main|article)", re.I))
        or soup.find(class_=re.compile(r"(content|main|article)", re.I))
        or soup
    )

    # Drop common boilerplate blocks by class/id hints.
    junk_re = re.compile(
        r"(nav|menu|footer|header|sidebar|breadcrumb|cookie|consent|banner|modal|subscribe|newsletter|share|social|promo|advert|ads?)",
        re.I,
    )
    for el in list(main.find_all(attrs={"class": junk_re})) + list(main.find_all(attrs={"id": junk_re})):
        try:
            el.decompose()
        except Exception:
            pass

    text = main.get_text(separator="\n")

    # Normalize whitespace and drop empty lines. Also collapse adjacent duplicates
    # (common in site chrome, e.g. repeated menu labels).
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    deduped: list[str] = []
    for ln in lines:
        if not deduped or deduped[-1] != ln:
            deduped.append(ln)
    return "\n".join(deduped)


def fetch_extracted_text(url: str, *, timeout_s: int, user_agent: str, max_chars: int) -> tuple[str, str, str]:
    """
    Returns: (extracted_text, extraction_status, extraction_error)
    """
    u = (url or "").strip()
    if not u:
        return "", "error", "missing_url"

    headers = {"User-Agent": user_agent} if user_agent else {}
    try:
        r = requests.get(u, headers=headers, timeout=timeout_s)
        r.raise_for_status()
        content_type = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return "", "error", f"unsupported_content_type:{content_type.split(';')[0] or 'unknown'}"
        text = html_to_text(r.text)
        text = text[:max_chars] if max_chars and max_chars > 0 else text
        if not text.strip():
            return "", "error", "empty_extracted_text"
        return text, "ok", ""
    except requests.exceptions.Timeout:
        return "", "error", "timeout"
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        return "", "error", f"http_error:{status or 'unknown'}"
    except requests.exceptions.RequestException:
        return "", "error", "request_error"
    except Exception:
        return "", "error", "extraction_error"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def extract_rows(
    rows: list[dict],
    *,
    max_rows: int | None,
    overwrite: bool,
    timeout_s: int,
    user_agent: str,
    max_chars: int,
) -> list[dict]:
    out: list[dict] = []
    processed = 0
    total = min(len(rows), max_rows) if max_rows is not None else len(rows)

    for row in rows:
        if max_rows is not None and processed >= max_rows:
            out.append(row)
            continue

        current_text = (row.get("extracted_text") or "").strip()
        if current_text and not overwrite:
            url = (row.get("url") or "").strip()
            log(f"[extract {processed + 1}/{total}] SKIP (already has extracted_text) {url}")
            out.append(row)
            continue

        url = row.get("url") or ""
        log(f"[extract {processed + 1}/{total}] GET {url}")
        extracted_text, status, err = fetch_extracted_text(
            url,
            timeout_s=timeout_s,
            user_agent=user_agent,
            max_chars=max_chars,
        )
        row["extracted_text"] = extracted_text
        row["extraction_status"] = status
        row["extraction_error"] = err
        if status == "ok":
            log(f"[extract {processed + 1}/{total}] OK ({len(extracted_text)} chars)")
        else:
            log(f"[extract {processed + 1}/{total}] ERROR ({err})")

        processed += 1
        out.append(row)

    return out


def openai_enrich(api_key: str, model: str, topic: str, text: str) -> dict:
    """
    Uses OpenAI Chat Completions API to return the required JSON fields.
    Requires env var OPENAI_API_KEY (or passed api_key).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = ENRICH_PROMPT_TEMPLATE.format(topic=topic, text=text)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise assistant that returns only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    parsed = _extract_first_json_object(content)
    return parsed


def enrich_rows(
    rows: list[dict],
    *,
    provider: str,
    model: str,
    topic: str,
    only_missing: bool,
    max_rows: int | None,
) -> list[dict]:
    api_key = os.getenv("OPENAI_API_KEY")
    if provider == "openai" and not api_key:
        raise SystemExit("Missing env var: OPENAI_API_KEY")

    out: list[dict] = []
    processed = 0
    total = min(len(rows), max_rows) if max_rows is not None else len(rows)
    for row in rows:
        if max_rows is not None and processed >= max_rows:
            out.append(row)
            continue

        extracted_text = (row.get("extracted_text") or "").strip()
        extraction_status = (row.get("extraction_status") or "").strip().lower()
        if not extracted_text or (extraction_status and extraction_status != "ok"):
            url = (row.get("url") or "").strip()
            reason = "missing_extracted_text" if not extracted_text else f"extraction_status={extraction_status}"
            log(f"[enrich {processed + 1}/{total}] SKIP ({reason}) {url}")
            out.append(row)
            continue

        if only_missing and (row.get("label") or row.get("type") or row.get("relevance_score") or row.get("reason")):
            url = (row.get("url") or "").strip()
            log(f"[enrich {processed + 1}/{total}] SKIP (already enriched) {url}")
            out.append(row)
            continue

        if provider == "openai":
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            log(f"[enrich {processed + 1}/{total}] ENRICH {title or url}")
            try:
                result = openai_enrich(api_key=api_key or "", model=model, topic=topic, text=extracted_text)
                row["label"] = str(result.get("label", "") or "")
                row["type"] = str(result.get("type", "") or "")
                row["relevance_score"] = str(result.get("relevance_score", "") or "")
                row["reason"] = str(result.get("reason", "") or "")
                log(f"[enrich {processed + 1}/{total}] OK label={row['label']} type={row['type']} score={row['relevance_score']}")
            except Exception as e:
                # Minimal failure recording without adding new columns.
                row["reason"] = f"enrichment_error: {type(e).__name__}"
                log(f"[enrich {processed + 1}/{total}] ERROR {type(e).__name__}")
        else:
            raise SystemExit(f"Unsupported provider: {provider}")

        processed += 1
        out.append(row)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Pipeline helpers: export search results, extract text, and enrich rows.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_search = sub.add_parser("search", help="Export Google CSE results to a pipeline-ready CSV.")
    sp_search.add_argument("--query", required=True, help="Search query")
    sp_search.add_argument("--num", type=int, default=20, help="Number of results to export (default: 20)")
    sp_search.add_argument("--out", default="results.csv", help="Output CSV path (default: results.csv)")
    sp_search.add_argument("--run-id", default=str(date_type.today()), help="Run id to embed in rows (default: today)")

    sp_extract = sub.add_parser("extract", help="Fetch each URL and populate extracted_text in a CSV.")
    sp_extract.add_argument("--in", dest="in_path", required=True, help="Input CSV path")
    sp_extract.add_argument("--out", dest="out_path", default="extracted.csv", help="Output CSV path (default: extracted.csv)")
    sp_extract.add_argument("--max-rows", type=int, default=None, help="Max number of rows to extract (default: no limit)")
    sp_extract.add_argument("--overwrite", action="store_true", help="Overwrite extracted_text even if already present")
    sp_extract.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds (default: 20)")
    sp_extract.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (compatible; buildingaipipelines.com/1.0; +https://buildingaipipelines.com)",
        help="User-Agent header (default: a simple browser-like UA)",
    )
    sp_extract.add_argument("--max-chars", type=int, default=8000, help="Max chars to keep in extracted_text (default: 8000)")

    sp_enrich = sub.add_parser("enrich", help="Enrich an existing CSV by filling label/type/score/reason from extracted_text.")
    sp_enrich.add_argument("--in", dest="in_path", required=True, help="Input CSV path")
    sp_enrich.add_argument("--out", dest="out_path", default="enriched.csv", help="Output CSV path (default: enriched.csv)")
    sp_enrich.add_argument("--provider", choices=["openai"], default="openai", help="LLM provider (default: openai)")
    sp_enrich.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), help="Model name")
    sp_enrich.add_argument("--topic", default="UFO sightings (UAP reports)", help="Topic string used in the prompt")
    sp_enrich.add_argument("--only-missing", action="store_true", help="Only enrich rows missing label/type/score/reason")
    sp_enrich.add_argument("--max-rows", type=int, default=None, help="Max number of rows to enrich (default: no limit)")

    args = p.parse_args()

    if args.cmd == "search":
        api_key = os.getenv("GOOGLE_CSE_API_KEY")
        cx = os.getenv("GOOGLE_CSE_CX")
        if not api_key or not cx:
            raise SystemExit("Missing env vars: GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX")

        items = google_search_results(api_key=api_key, cx=cx, q=args.query, total=max(1, args.num))

        rows: list[dict] = []
        for item in items:
            url = item.get("link") or ""
            rows.append(
                {
                    "run_id": args.run_id,
                    "query": args.query,
                    "title": item.get("title") or "",
                    "source": item.get("displayLink") or "",
                    "date": extract_published_date(item),
                    "url": url,
                    "dedupe_key": normalize_dedupe_key(url),
                    "snippet": item.get("snippet") or "",
                    # columns for later steps (left blank intentionally)
                    "extracted_text": "",
                    "extraction_status": "",
                    "extraction_error": "",
                    "label": "",
                    "type": "",
                    "relevance_score": "",
                    "reason": "",
                }
            )

        write_csv(args.out, rows)
        log(f"[search] wrote {len(rows)} rows to {args.out}")
        return

    if args.cmd == "extract":
        rows = read_csv(args.in_path)
        log(f"[extract] reading {len(rows)} rows from {args.in_path}")
        extracted = extract_rows(
            rows,
            max_rows=args.max_rows,
            overwrite=bool(args.overwrite),
            timeout_s=args.timeout,
            user_agent=args.user_agent,
            max_chars=args.max_chars,
        )
        normalized = []
        for r in extracted:
            normalized.append({k: (r.get(k, "") if r.get(k, "") is not None else "") for k in CSV_COLUMNS})
        write_csv(args.out_path, normalized)
        log(f"[extract] wrote {len(normalized)} rows to {args.out_path}")
        return

    if args.cmd == "enrich":
        rows = read_csv(args.in_path)
        log(f"[enrich] reading {len(rows)} rows from {args.in_path}")
        enriched = enrich_rows(
            rows,
            provider=args.provider,
            model=args.model,
            topic=args.topic,
            only_missing=bool(args.only_missing),
            max_rows=args.max_rows,
        )
        # Preserve the standard column order even if input CSV differs.
        normalized = []
        for r in enriched:
            normalized.append({k: (r.get(k, "") if r.get(k, "") is not None else "") for k in CSV_COLUMNS})
        write_csv(args.out_path, normalized)
        log(f"[enrich] wrote {len(normalized)} rows to {args.out_path}")
        return


if __name__ == "__main__":
    main()


