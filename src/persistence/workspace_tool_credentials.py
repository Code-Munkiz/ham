"""Server-side workspace tool API keys (admin / shared HAM instance).

File-backed JSON — same durability pattern as ``cursor_credentials``.
Keys are never logged by callers; use ``HAM_WORKSPACE_TOOL_CREDENTIALS_FILE`` on Cloud Run
when mounting a writable path.

This is an MVP store (not a multi-user vault).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.persistence.cursor_credentials import mask_api_key_preview


def _credentials_path() -> Path:
    override = (os.environ.get("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".ham" / "workspace_tool_credentials.json"


def _load_raw() -> dict[str, Any]:
    path = _credentials_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _atomic_write(data: dict[str, Any]) -> None:
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def get_stored_openrouter_api_key() -> str | None:
    k = (_load_raw().get("openrouter_api_key") or "").strip()
    return k or None


def get_stored_github_token() -> str | None:
    k = (_load_raw().get("github_token") or "").strip()
    return k or None


def get_stored_anthropic_api_key() -> str | None:
    k = (_load_raw().get("anthropic_api_key") or "").strip()
    return k or None


def get_stored_openai_transcription_api_key() -> str | None:
    k = (_load_raw().get("openai_transcription_api_key") or "").strip()
    return k or None


def resolve_claude_agent_anthropic_api_key() -> str | None:
    """Anthropic API key — **without** per-user Clerk context (legacy / tests).

    Product routes should call
    :func:`resolve_claude_agent_anthropic_api_key_for_actor` instead.
    """
    # Late import avoids circular bootstrap with Firebase-backed facade.
    from src.persistence.connected_tool_credentials import (
        resolve_claude_agent_anthropic_api_key_for_actor,
    )

    return resolve_claude_agent_anthropic_api_key_for_actor(None)


def get_effective_openrouter_api_key() -> str:
    s = get_stored_openrouter_api_key()
    if s:
        return s
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def get_effective_github_token() -> str:
    s = get_stored_github_token()
    if s:
        return s
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def save_openrouter_api_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        raise ValueError("api_key must be non-empty")
    data = _load_raw()
    data["openrouter_api_key"] = key
    _atomic_write(data)


def save_github_token(token: str) -> None:
    tok = token.strip()
    if not tok:
        raise ValueError("token must be non-empty")
    data = _load_raw()
    data["github_token"] = tok
    _atomic_write(data)


def save_anthropic_api_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        raise ValueError("api_key must be non-empty")
    data = _load_raw()
    data["anthropic_api_key"] = key
    _atomic_write(data)


def save_openai_transcription_api_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        raise ValueError("api_key must be non-empty")
    data = _load_raw()
    data["openai_transcription_api_key"] = key
    _atomic_write(data)


def clear_openrouter_api_key() -> bool:
    data = _load_raw()
    if "openrouter_api_key" not in data:
        return False
    del data["openrouter_api_key"]
    _atomic_write(data)
    return True


def clear_github_token() -> bool:
    data = _load_raw()
    if "github_token" not in data:
        return False
    del data["github_token"]
    _atomic_write(data)
    return True


def clear_anthropic_api_key() -> bool:
    data = _load_raw()
    if "anthropic_api_key" not in data:
        return False
    del data["anthropic_api_key"]
    _atomic_write(data)
    return True


def clear_openai_transcription_api_key() -> bool:
    data = _load_raw()
    if "openai_transcription_api_key" not in data:
        return False
    del data["openai_transcription_api_key"]
    _atomic_write(data)
    return True


def preview_openrouter() -> str | None:
    k = get_stored_openrouter_api_key()
    return mask_api_key_preview(k) if k else None


def preview_github() -> str | None:
    k = get_stored_github_token()
    return mask_api_key_preview(k) if k else None


def preview_anthropic() -> str | None:
    k = get_stored_anthropic_api_key()
    return mask_api_key_preview(k) if k else None
