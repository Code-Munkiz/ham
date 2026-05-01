"""Redact sensitive patterns from text before PDF export (server-side only)."""
from __future__ import annotations

import re

_RE_GS = re.compile(r"gs://[^\s\)\"\'>]+", re.IGNORECASE)
_RE_S3 = re.compile(r"\bs3://[^\s\)\"\'>]+", re.IGNORECASE)
# Windows absolute paths
_RE_WIN_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\(?:[^\\/:*?\"<>\|\r\n]+\\?)+", re.IGNORECASE)
# Unix-ish home or obvious绝对 paths (conservative)
_RE_UNIX_PATH = re.compile(
    r"(?:(?:/usr/|/var/|/home/|/Users/|/tmp/|/etc/)[^\s]+)",
    re.IGNORECASE,
)
# Provider-style API keys (OpenAI-style sk-, long alnum)
_RE_SK_OPENAI = re.compile(r"\bsk-[A-Za-z0-9]{24,}\b")
# Bearer tokens in prose
_RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b", re.IGNORECASE)

_REDACT = "[redacted]"


def redact_for_pdf_export(text: str) -> str:
    """
    Best-effort redaction for audit-safe PDFs. Conservative: may redact rare false
    positives; avoids emitting storage URIs, obvious secrets, and filesystem paths.
    """
    if not text:
        return text
    s = text
    s = _RE_GS.sub(_REDACT, s)
    s = _RE_S3.sub(_REDACT, s)
    s = _RE_WIN_PATH.sub(_REDACT, s)
    s = _RE_UNIX_PATH.sub(_REDACT, s)
    s = _RE_SK_OPENAI.sub(_REDACT, s)
    s = _RE_BEARER.sub(f"Bearer {_REDACT}", s)
    return s


def safe_export_filename_fragment(session_id: str) -> str:
    """ASCII filename fragment from session id (first 8 hex-ish chars safe)."""
    raw = (session_id or "").strip()
    safe = "".join(c for c in raw[:36] if c.isalnum() or c in "-_")
    return (safe[:8] or "session") if safe else "session"
