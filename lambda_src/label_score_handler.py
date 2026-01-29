from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from common import get_api_keys, s3_get_text, s3_put_text

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


def _extract_first_json_object(text: str) -> dict[str, Any]:
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


def _openai_enrich(*, api_key: str, model: str, topic: str, text: str) -> dict[str, Any]:
    prompt = ENRICH_PROMPT_TEMPLATE.format(topic=topic, text=text)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise assistant that returns only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return _extract_first_json_object(content)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Input:
      {
        "run_id": "...",
        "extracted_s3_key": "runs/<run_id>/extracted.jsonl",
        "enriched_s3_key": "runs/<run_id>/enriched.jsonl",     # optional
        "topic": "UFO sightings (UAP reports)",                # optional
        "model": "gpt-4o-mini"                                 # optional
      }

    Output:
      { "run_id": "...", "extracted_s3_key": "...", "enriched_s3_key": "..." }
    """
    run_id = str((event or {}).get("run_id") or "").strip()
    extracted_s3_key = str((event or {}).get("extracted_s3_key") or "").strip()
    enriched_s3_key = str((event or {}).get("enriched_s3_key") or "").strip() or f"runs/{run_id}/enriched.jsonl"
    topic = str((event or {}).get("topic") or "UFO sightings (UAP reports)")

    if not run_id:
        raise RuntimeError("Missing required field: run_id")
    if not extracted_s3_key:
        raise RuntimeError("Missing required field: extracted_s3_key")

    bucket = str((event or {}).get("artifacts_bucket") or "").strip() or os.environ["ARTIFACTS_BUCKET"]

    keys = get_api_keys()
    api_key = str(keys.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in Secrets Manager JSON secret")

    model = str((event or {}).get("model") or "").strip() or str(keys.get("OPENAI_MODEL") or "").strip() or "gpt-4o-mini"

    raw = s3_get_text(bucket, extracted_s3_key)
    lines = [ln for ln in raw.splitlines() if ln.strip()]

    out_lines: list[str] = []
    for ln in lines:
        row = json.loads(ln)
        extracted_text = str(row.get("extracted_text") or "").strip()
        extraction_status = str(row.get("extraction_status") or "").strip().lower()

        if not extracted_text or (extraction_status and extraction_status != "ok"):
            # pass-through (skip enrichment)
            out_lines.append(json.dumps(row, ensure_ascii=False))
            continue

        try:
            result = _openai_enrich(api_key=api_key, model=model, topic=topic, text=extracted_text)
            row["label"] = str(result.get("label", "") or "")
            row["type"] = str(result.get("type", "") or "")
            row["relevance_score"] = result.get("relevance_score", "")
            row["reason"] = str(result.get("reason", "") or "")
        except Exception as e:
            row["reason"] = f"enrichment_error:{type(e).__name__}"

        out_lines.append(json.dumps(row, ensure_ascii=False))

    s3_put_text(bucket, enriched_s3_key, "\n".join(out_lines) + ("\n" if out_lines else ""), content_type="application/x-ndjson")
    return {"run_id": run_id, "extracted_s3_key": extracted_s3_key, "enriched_s3_key": enriched_s3_key}

