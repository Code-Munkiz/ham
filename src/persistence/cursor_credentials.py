"""File-backed Cursor API key for shared HAM deployments (~/.ham/cursor_credentials.json)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _credentials_path() -> Path:
    """
    Path to UI-saved Cursor key.

    Set ``HAM_CURSOR_CREDENTIALS_FILE`` to an absolute path on Cloud Run / Docker when you mount
    a volume so the same key survives restarts (optional).
    """
    override = (os.environ.get("HAM_CURSOR_CREDENTIALS_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".ham" / "cursor_credentials.json"


def credentials_path_for_display() -> str:
    """Safe to show in API responses (path only, no secret)."""
    return str(_credentials_path())


def get_effective_cursor_api_key() -> str | None:
    """
    Key saved via Settings UI (file) takes precedence over CURSOR_API_KEY env,
    so a team can swap subscriptions without redeploying.
    """
    path = _credentials_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            key = (raw.get("cursor_api_key") or "").strip()
            if key:
                return key
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    env = (os.environ.get("CURSOR_API_KEY") or "").strip()
    return env or None


def save_cursor_api_key(api_key: str) -> None:
    key = api_key.strip()
    if not key:
        raise ValueError("cursor_api_key must be non-empty")
    fp = _credentials_path()
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps({"cursor_api_key": key}, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_saved_cursor_api_key() -> bool:
    """Remove UI-saved key so process falls back to CURSOR_API_KEY env."""
    path = _credentials_path()
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def key_source() -> str:
    """'ui' | 'env' | 'none' — where the effective key comes from."""
    path = _credentials_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if (raw.get("cursor_api_key") or "").strip():
                return "ui"
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    if (os.environ.get("CURSOR_API_KEY") or "").strip():
        return "env"
    return "none"


def mask_api_key_preview(key: str) -> str:
    k = key.strip()
    if len(k) <= 12:
        return "***"
    # Fine-grained / classic PATs: do not echo the recognizable prefix in UI.
    if k.startswith("ghp_") or k.startswith("github_pat_"):
        return f"github…{k[-4:]}"
    return f"{k[:8]}…{k[-4:]}"
