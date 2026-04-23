"""Hermes runtime inventory: sanitization + GET /api/hermes-runtime/inventory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham import hermes_runtime_inventory as inv

client = TestClient(app)


def test_redact_secrets_strips_bearer_and_api_key() -> None:
    raw = "Authorization: Bearer supersecret\ntoken: abc123\nAPI_KEY=sk-test-123456789012"
    out = inv.redact_secrets(raw)
    assert "supersecret" not in out
    assert "sk-test" not in out


def test_sanitize_mcp_server_entry_redacts_env_presence_only() -> None:
    row = inv.sanitize_mcp_server_entry(
        "srv",
        {
            "command": "npx",
            "env": {"API_KEY": "secret"},
            "headers": {"Authorization": "Bearer x"},
            "tools_include": ["a"],
        },
    )
    assert row["name"] == "srv"
    assert row["transport"] == "stdio"
    assert row["has_env"] is True
    assert row["has_headers"] is True
    assert row["tools_include"] == ["a"]
    assert "secret" not in str(row)
    assert "Bearer" not in str(row)


def test_parse_sanitized_config_dict_mcp_and_skills() -> None:
    doc = yaml.safe_load(
        """
skills:
  external_dirs:
    - /secret/path
  toolsets: [core]
plugins:
  enabled: [p1]
  disabled: [p2]
mcp:
  servers:
    one:
      command: mcporter
      env: {TOKEN: x}
      headers: {Authorization: Bearer z}
memory:
  provider: sqlite
"""
    )
    assert isinstance(doc, dict)
    out = inv.parse_sanitized_config_dict(doc)
    assert out["external_skill_dirs_count"] == 1
    assert out["toolsets"] == ["core"]
    assert out["plugins_enabled"] == ["p1"]
    assert out["plugins_disabled"] == ["p2"]
    assert len(out["mcp_servers"]) == 1
    assert out["mcp_servers"][0]["name"] == "one"
    assert out["mcp_servers"][0]["has_env"] is True
    assert out["mcp_servers"][0]["has_headers"] is True
    assert out["memory_provider"] == "sqlite"


def test_load_sanitized_config_from_file(tmp_path: Path) -> None:
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    cfg = hermes / "config.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "mcp": {
                    "servers": {
                        "s": {"url": "http://127.0.0.1:9", "headers": {"X": "y"}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    out = inv.load_sanitized_config(hermes)
    assert out["status"] == "ok"
    assert out["mcp_servers"][0]["transport"] == "http"
    assert out["mcp_servers"][0]["has_headers"] is True


def test_inventory_remote_only_skips_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    called: list[str] = []

    def fake_run(*_a, **_k):
        called.append("run")
        raise AssertionError("subprocess should not run in remote_only")

    monkeypatch.setattr("src.ham.hermes_runtime_inventory.subprocess.run", fake_run)
    body = inv.build_runtime_inventory()
    assert body["kind"] == "ham_hermes_runtime_inventory"
    assert body["available"] is False
    assert body["tools"]["status"] == "unavailable"
    assert called == []
    assert body["skills"]["static_catalog"] is True
    assert body["skills"]["catalog_count"] >= 1


def test_inventory_no_hermes_binary_partial_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    monkeypatch.delenv("HAM_HERMES_CLI_PATH", raising=False)
    monkeypatch.setattr(inv.shutil, "which", lambda _x: None)
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "config.yaml").write_text(
        "skills:\n  toolsets: [a]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    body = inv.build_runtime_inventory()
    assert body["available"] is False
    assert body["config"]["toolsets"] == ["a"]


def test_inventory_mock_subprocess_partial_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    fake_bin = tmp_path / "hermes"
    fake_bin.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake_bin))
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))

    def fake_run(cmd, **_kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "line1\n"
        m.stderr = ""
        if "tools" in cmd:
            m.stdout = "Tool summary OK\n- builtin\n"
        elif "plugins" in cmd:
            m.returncode = 1
            m.stderr = "plugins failed"
        elif "mcp" in cmd:
            m.stdout = "mcp-a\n"
        elif "status" in cmd:
            m.stdout = "status ok"
        elif "dump" in cmd and cmd[-1] == "dump":
            m.stdout = "dump: ok"
        return m

    monkeypatch.setattr("src.ham.hermes_runtime_inventory.subprocess.run", fake_run)
    body = inv.build_runtime_inventory()
    assert body["available"] is True
    assert body["tools"]["status"] == "ok"
    assert body["plugins"]["status"] == "error"
    assert body["mcp"]["status"] == "ok"
    assert any("failed" in w.lower() or "subcommands" in w.lower() for w in body["warnings"])


def test_get_api_inventory_remote_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    res = client.get("/api/hermes-runtime/inventory")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "ham_hermes_runtime_inventory"
    assert data["available"] is False
