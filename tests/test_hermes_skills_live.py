"""Hermes skills live overlay — CLI allowlist, join, redaction, remote_only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham import hermes_skills_live as live
from src.ham.hermes_runtime_inventory import redact_secrets
from src.ham.hermes_skills_catalog import list_catalog_entries

client = TestClient(app)


def test_parse_skills_table_success() -> None:
    text = """
                                Installed Skills
┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ Name    ┃ Category ┃ Source  ┃ Trust   ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ dogfood │          │ builtin │ builtin │
│ custom-skill │ x   │ local   │ local   │
""".strip()
    rows, w = live._parse_skills_list_output(text)
    assert len(rows) == 2
    assert rows[0]["name"] == "dogfood"
    assert rows[0]["hermes_source"] == "builtin"
    assert rows[1]["name"] == "custom-skill"
    assert not w


def test_join_linked_by_display_name() -> None:
    entries = [
        {"catalog_id": "bundled.dogfood", "display_name": "dogfood"},
        {"catalog_id": "bundled.other", "display_name": "other"},
    ]
    bd, bs = live._build_catalog_indexes(entries)
    cid, res = live._resolve_live_row_to_catalog_id("dogfood", by_display=bd, by_segment=bs)
    assert res == "linked"
    assert cid == "bundled.dogfood"


def test_join_linked_by_final_segment_unique() -> None:
    entries = [
        {"catalog_id": "bundled.apple.apple-notes", "display_name": "Notes App"},
    ]
    bd, bs = live._build_catalog_indexes(entries)
    cid, res = live._resolve_live_row_to_catalog_id(
        "apple-notes",
        by_display=bd,
        by_segment=bs,
    )
    assert res == "linked"
    assert cid == "bundled.apple.apple-notes"


def test_join_live_only() -> None:
    entries = [{"catalog_id": "bundled.x", "display_name": "only-in-catalog"}]
    bd, bs = live._build_catalog_indexes(entries)
    cid, res = live._resolve_live_row_to_catalog_id(
        "not-in-catalog",
        by_display=bd,
        by_segment=bs,
    )
    assert res == "live_only"
    assert cid is None


def test_join_unknown_ambiguous_display() -> None:
    entries = [
        {"catalog_id": "bundled.a", "display_name": "dup"},
        {"catalog_id": "official.b", "display_name": "dup"},
    ]
    bd, bs = live._build_catalog_indexes(entries)
    cid, res = live._resolve_live_row_to_catalog_id("dup", by_display=bd, by_segment=bs)
    assert res == "unknown"
    assert cid is None


def test_overlay_remote_only_skips_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    called: list[str] = []

    def fake_run(*_a, **_k):
        called.append("run")
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr("src.ham.hermes_skills_live.subprocess.run", fake_run)
    body = live.build_skills_installed_overlay()
    assert body["kind"] == "hermes_skills_live_overlay"
    assert body["status"] == "remote_only"
    assert body["live_count"] == 0
    assert called == []


def test_overlay_missing_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    monkeypatch.delenv("HAM_HERMES_CLI_PATH", raising=False)
    monkeypatch.setattr(live, "resolve_hermes_cli_binary", lambda: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.delenv("HERMES_HOME", raising=False)
    body = live.build_skills_installed_overlay()
    assert body["status"] == "unavailable"
    assert body["live_count"] == 0


def test_overlay_cli_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    fake_bin = tmp_path / "hermes"
    fake_bin.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake_bin))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    def fake_run(cmd, **_kwargs):
        assert cmd[:4] == [str(fake_bin), "skills", "list", "--source"]
        assert cmd[4] == "all"
        m = MagicMock()
        m.returncode = 2
        m.stdout = ""
        m.stderr = "boom"
        return m

    monkeypatch.setattr("src.ham.hermes_skills_live.subprocess.run", fake_run)
    body = live.build_skills_installed_overlay()
    assert body["status"] == "error"
    assert body["live_count"] == 0
    assert "exited with code 2" in " ".join(body["warnings"])


def test_overlay_parse_degraded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    fake_bin = tmp_path / "hermes"
    fake_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake_bin))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    def fake_run(_cmd, **_kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "Installed Skills\n(no table here)\n"
        m.stderr = ""
        return m

    monkeypatch.setattr("src.ham.hermes_skills_live.subprocess.run", fake_run)
    body = live.build_skills_installed_overlay()
    assert body["status"] == "parse_degraded"
    assert body["live_count"] == 0


def test_overlay_redaction_in_raw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    fake_bin = tmp_path / "hermes"
    fake_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake_bin))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    secret = "sk-or-v1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def fake_run(_cmd, **_kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = f"│ x │ │ │ │\nstderr leaked {secret}\n"
        m.stderr = ""
        return m

    monkeypatch.setattr("src.ham.hermes_skills_live.subprocess.run", fake_run)
    body = live.build_skills_installed_overlay()
    assert secret not in body["raw_redacted"]


def test_overlay_counts_linked_and_catalog_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    fake_bin = tmp_path / "hermes"
    fake_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake_bin))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    table = """
│ dogfood │  │ builtin │ builtin │
│ only-live │  │ local │ local │
""".strip()

    def fake_run(_cmd, **_kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = table
        m.stderr = ""
        return m

    monkeypatch.setattr("src.ham.hermes_skills_live.subprocess.run", fake_run)
    body = live.build_skills_installed_overlay()
    assert body["status"] == "ok"
    assert body["live_count"] == 2
    assert body["linked_count"] >= 1
    assert body["live_only_count"] >= 1
    assert body["catalog_only_count"] >= 1
    catalog_n = len(list_catalog_entries())
    assert body["catalog_only_count"] == catalog_n - 1
    assert body["linked_count"] == 1


def test_get_api_installed_remote_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    res = client.get("/api/hermes-skills/installed")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "hermes_skills_live_overlay"
    assert data["status"] == "remote_only"


def test_redact_secrets_skills_live_uses_inventory_patterns() -> None:
    raw = "token sk-or-v1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
    assert "sk-or-v1" not in redact_secrets(raw)
