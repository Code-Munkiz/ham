"""Tests for ~/.ham cursor API key persistence."""
from __future__ import annotations

import json
import pathlib
from pathlib import Path

from src.persistence import cursor_credentials as cc


def _patch_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(
        pathlib.Path,
        "home",
        classmethod(lambda cls: home),
    )


def test_mask_api_key_preview_short() -> None:
    assert cc.mask_api_key_preview("short") == "***"


def test_mask_api_key_preview_long() -> None:
    s = "crsr_" + "a" * 40 + "7a8"
    m = cc.mask_api_key_preview(s)
    assert m.startswith("crsr_aaa")
    assert m.endswith("7a8")
    assert "…" in m


def test_key_source_none(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _patch_home(monkeypatch, home)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    assert cc.key_source() == "none"


def test_save_and_effective_roundtrip(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _patch_home(monkeypatch, home)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    cc.save_cursor_api_key("  test-key-123  ")
    assert cc.get_effective_cursor_api_key() == "test-key-123"
    assert cc.key_source() == "ui"
    raw = json.loads((home / ".ham" / "cursor_credentials.json").read_text(encoding="utf-8"))
    assert raw["cursor_api_key"] == "test-key-123"


def test_env_fallback_when_no_file(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _patch_home(monkeypatch, home)
    monkeypatch.setenv("CURSOR_API_KEY", "from-env")
    assert cc.get_effective_cursor_api_key() == "from-env"
    assert cc.key_source() == "env"


def test_ham_cursor_credentials_file_override(tmp_path: Path, monkeypatch) -> None:
    """Cloud Run: optional absolute path via env (mounted volume)."""
    creds = tmp_path / "mounted" / "cursor_credentials.json"
    creds.parent.mkdir(parents=True)
    creds.write_text(json.dumps({"cursor_api_key": "from-override"}), encoding="utf-8")
    monkeypatch.setenv("HAM_CURSOR_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CURSOR_API_KEY", "from-env")
    assert cc.get_effective_cursor_api_key() == "from-override"
    assert cc.key_source() == "ui"
    assert "mounted" in cc.credentials_path_for_display()
