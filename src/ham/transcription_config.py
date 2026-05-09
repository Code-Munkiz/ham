"""Helpers for safe transcription runtime configuration checks."""
from __future__ import annotations

import os

from src.ham.clerk_auth import HamActor
from src.persistence.connected_tool_credentials import resolve_connected_tool_secret_plaintext


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


def resolve_transcription_openai_api_key_for_actor(actor: HamActor | None) -> str | None:
    """User BYOK Connected Tool first; else platform ``HAM_TRANSCRIPTION_*`` when configured."""
    if actor is not None:
        u = resolve_connected_tool_secret_plaintext(actor, "openai_transcription")
        if u and not is_placeholder_transcription_key(u):
            return u.strip()
    if transcription_provider() != "openai":
        return None
    pk = transcription_api_key()
    if is_placeholder_transcription_key(pk):
        return None
    return pk.strip()


def transcription_runtime_configured(
    actor: HamActor | None = None,
) -> tuple[bool, str | None]:
    key = resolve_transcription_openai_api_key_for_actor(actor)
    if key:
        return True, None
    return False, "not_configured"
