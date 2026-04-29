"""Helpers for safe transcription runtime configuration checks."""
from __future__ import annotations

import os


_PLACEHOLDER_TOKENS = (
    "placeholder",
    "placehol",
    "changeme",
    "dummy",
    "test",
    "example",
    "fake",
    "your_",
    "your-",
)


def transcription_provider() -> str:
    return (os.environ.get("HAM_TRANSCRIPTION_PROVIDER") or "").strip().lower()


def transcription_api_key() -> str:
    return (os.environ.get("HAM_TRANSCRIPTION_API_KEY") or "").strip()


def is_placeholder_transcription_key(raw: str) -> bool:
    key = (raw or "").strip()
    if not key:
        return True
    lower = key.lower()
    if any(token in lower for token in _PLACEHOLDER_TOKENS):
        return True
    # Obvious fake mask-like values and snippets.
    if "*" in key or "..." in key:
        return True
    # Common fake OpenAI-style examples used in docs/tests.
    if lower.startswith("sk-test") or lower.startswith("sk-fake"):
        return True
    return False


def transcription_runtime_configured() -> tuple[bool, str | None]:
    provider = transcription_provider()
    key = transcription_api_key()
    if provider != "openai":
        return False, "not_configured"
    if is_placeholder_transcription_key(key):
        return False, "not_configured"
    return True, None
