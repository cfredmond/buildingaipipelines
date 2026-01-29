from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
import urllib.request
from typing import Any

import boto3

_secrets_cache: dict[str, Any] | None = None


def _required_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def get_api_keys() -> dict[str, str]:
    """
    Reads a single JSON secret from Secrets Manager and returns it as a dict.
    Expected keys (per our Terraform secret_string JSON):
      - GOOGLE_CSE_API_KEY
      - GOOGLE_CSE_CX
      - OPENAI_API_KEY
      - OPENAI_MODEL (optional)
    """
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache  # type: ignore[return-value]

    secret_arn = _required_env("API_KEYS_SECRET_ARN")
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=secret_arn)
    secret_str = resp.get("SecretString") or ""
    data = json.loads(secret_str) if secret_str else {}
    _secrets_cache = data
    return data


def s3_put_text(bucket: str, key: str, text: str, *, content_type: str) -> None:
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType=content_type,
    )


def s3_get_text(bucket: str, key: str) -> str:
    obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    return body.decode("utf-8")


def normalize_dedupe_key(raw_url: str) -> str:
    """
    Copied (lightly) from pipeline.py: stable key to dedupe across runs.
    Output is "host/path" (no scheme) to stay compact.
    """
    raw = (raw_url or "").strip()
    if not raw:
        return ""

    try:
        u = urllib.parse.urlparse(raw)
    except Exception:
        return raw.lower()

    drop_prefixes = ("utm_",)
    drop_keys = {"gclid", "fbclid", "yclid", "mc_cid", "mc_eid"}

    kept: list[tuple[str, str]] = []
    for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True):
        kl = (k or "").lower()
        if any(kl.startswith(p) for p in drop_prefixes):
            continue
        if kl in drop_keys:
            continue
        kept.append((k, v))

    query = urllib.parse.urlencode(kept, doseq=True)
    cleaned = urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, query, ""))  # strip fragment

    cu = urllib.parse.urlparse(cleaned)
    host = (cu.netloc or "").lower()
    path = re.sub(r"/+$", "", cu.path or "/")  # remove trailing slashes
    return f"{host}{path}"


def http_get(url: str, *, timeout_s: int, user_agent: str, max_bytes: int = 2_000_000) -> tuple[bytes, str]:
    """
    Fetch a URL with a hard wall-clock timeout.

    Note: urllib's timeout is per-socket operation. Some servers can "trickle" data and
    keep a request alive indefinitely. To avoid Lambda timeouts, we enforce an overall
    deadline using a background thread and join().
    """

    out: dict[str, Any] = {}

    def _run() -> None:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent} if user_agent else {})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            out["content_type"] = (resp.headers.get("Content-Type") or "").lower()
            out["body"] = resp.read(max_bytes)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        raise TimeoutError("wall_clock_timeout")
    if "body" not in out:
        raise RuntimeError("http_get_failed")
    return out["body"], out["content_type"]


_script_style_re = re.compile(r"(?is)<(script|style|noscript).*?>.*?</\\1>")
_tag_re = re.compile(r"(?s)<[^>]+>")


def html_to_text(html: str) -> str:
    """
    Minimal HTML -> text conversion using regex (stdlib-only).
    Not as accurate as BeautifulSoup, but keeps the Lambda package simple.
    """
    s = html or ""
    s = _script_style_re.sub(" ", s)
    s = _tag_re.sub(" ", s)
    s = s.replace("&nbsp;", " ")
    s = re.sub(r"[ \\t\\r\\f\\v]+", " ", s)
    s = re.sub(r"\\n+", "\\n", s)
    return s.strip()


def chunks(lines: list[str]) -> str:
    return "\n".join(lines).rstrip("\n") + "\n"

