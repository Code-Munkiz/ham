"""Shared redaction helpers for HAM-on-X records."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "access_token_secret",
    "auth",
    "authorization",
    "bearer",
    "client_secret",
    "key",
    "password",
    "secret",
    "token",
    "x-api-key",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I)
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token(?:[_-]?secret)?|bearer[_-]?token|"
    r"authorization|client[_-]?secret|x-api-key)\s*[:=]\s*['\"]?[^'\"\s,;]+"
)
_OPAQUE_RE = re.compile(r"\b[A-Za-z0-9_./+=-]{32,}\b")


def _mask_query_secrets(text: str) -> str:
    def replace_url(match: re.Match[str]) -> str:
        raw = match.group(0)
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw
        params = []
        changed = False
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in SECRET_KEYS or any(part in key.lower() for part in ("token", "secret", "key")):
                params.append((key, "[REDACTED]"))
                changed = True
            else:
                params.append((key, value))
        if not changed:
            return raw
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(params),
                parsed.fragment,
            )
        )

    return re.sub(r"https?://[^\s)>\]\"']+", replace_url, text)


def redact_text(value: str) -> str:
    """Mask common credential shapes without preserving secret values."""
    text = _mask_query_secrets(value)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)

    def redact_opaque(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.startswith("http"):
            return token
        return "[REDACTED_TOKEN]"

    return _OPAQUE_RE.sub(redact_opaque, text)


def redact(value: Any) -> Any:
    """Recursively redact strings, mapping keys, and nested JSON-like data."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            skey = str(key)
            lowered = skey.lower()
            if lowered in SECRET_KEYS or any(part in lowered for part in ("token", "secret", "api_key", "apikey")):
                out[skey] = "[REDACTED]"
            else:
                out[skey] = redact(item)
        return out
    return value
