"""Hermes gateway broker: snapshot shape, redaction, TTL, adapters."""

from __future__ import annotations

from typing import Any

import pytest

import src.ham.hermes_gateway.broker as broker_mod
from src.ham.hermes_gateway.broker import HermesGatewayBroker
from src.ham.hermes_gateway.dto import GATEWAY_SNAPSHOT_SCHEMA_VERSION


def _minimal_runtime_inventory(warning: str) -> dict[str, Any]:
    """Minimal valid shape for broker snapshot path (sanitization + warnings merge)."""
    return {
        "kind": "ham_hermes_runtime_inventory",
        "mode": "local_inventory",
        "available": True,
        "source": {"hermes_binary": "bin", "hermes_home": "", "colocated": True},
        "tools": {
            "status": "ok",
            "summary_text": "",
            "toolsets": [],
            "raw_redacted": "raw",
        },
        "plugins": {"status": "ok", "items": [], "raw_redacted": "raw"},
        "mcp": {"status": "ok", "servers": [], "raw_redacted": "raw"},
        "config": {
            "status": "ok",
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        },
        "skills": {"status": "ok", "catalog_count": 0, "static_catalog": True},
        "status": {"status_all": {"status": "ok", "raw_redacted": "raw"}},
        "warnings": [warning],
    }


def test_gateway_snapshot_schema_and_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    b = HermesGatewayBroker()
    snap = b.build_snapshot(project_id=None, force_refresh=True)
    assert snap["kind"] == "ham_hermes_gateway_snapshot"
    assert snap["schema_version"] == GATEWAY_SNAPSHOT_SCHEMA_VERSION
    assert "captured_at" in snap
    assert "hermes_hub" in snap
    assert snap["hermes_hub"]["gateway_mode"] == "mock"
    ph = snap["future_adapter_placeholders"]
    assert any(p.get("id") == "hermes_json_rpc" for p in ph)
    assert any(p.get("id") == "hermes_websocket_control" for p in ph)
    runners = snap["external_runners"]
    ids = {r["id"] for r in runners}
    assert "cursor_cloud_agent" in ids
    assert "factory_droid" in ids
    assert "opencode" in ids


def test_snapshot_omits_raw_redacted_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    b = HermesGatewayBroker()
    snap = b.build_snapshot(project_id=None, force_refresh=True)
    inv = snap["runtime_inventory"]
    tools = inv.get("tools") or {}
    assert tools.get("raw_redacted", "").startswith("[omitted")
    sk = snap["skills_installed"]
    assert isinstance(sk, dict)
    assert str(sk.get("raw_redacted", "")).startswith("[omitted")
    src = inv.get("source") or {}
    assert src.get("hermes_binary") == "[configured]" or src.get("hermes_binary") == ""


def test_snapshot_ttl_cache_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.setenv("HAM_HERMES_GATEWAY_CACHE_TTL_S", "60")
    b = HermesGatewayBroker()
    a = b.build_snapshot(project_id=None, force_refresh=False)
    b2 = b.build_snapshot(project_id=None, force_refresh=False)
    fr = a["freshness"]
    assert fr["inventory_cached"] is False
    assert b2["freshness"]["inventory_cached"] is True


def test_force_refresh_repopulates_cache_for_next_unforced_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After refresh=true, cache must store new fragments; refresh=false must not read pre-refresh TTL data."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    monkeypatch.setenv("HAM_HERMES_GATEWAY_CACHE_TTL_S", "300")
    b = HermesGatewayBroker()
    n = 0

    def fake_inv() -> dict[str, Any]:
        nonlocal n
        n += 1
        if n == 1:
            return _minimal_runtime_inventory("__INV_V1__")
        return _minimal_runtime_inventory("__INV_V2__")

    monkeypatch.setattr(broker_mod, "build_runtime_inventory", fake_inv)
    s1 = b.build_snapshot(project_id=None, force_refresh=False)
    assert "__INV_V1__" in s1["warnings"]
    s2 = b.build_snapshot(project_id=None, force_refresh=False)
    assert "__INV_V1__" in s2["warnings"]
    s3 = b.build_snapshot(project_id=None, force_refresh=True)
    assert "__INV_V2__" in s3["warnings"]
    s4 = b.build_snapshot(project_id=None, force_refresh=False)
    assert "__INV_V2__" in s4["warnings"]
    assert "__INV_V1__" not in s4["warnings"]


def test_unknown_project_id_activity_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    b = HermesGatewayBroker()
    snap = b.build_snapshot(project_id="not-a-real-project-id-xyz", force_refresh=True)
    assert snap["activity"].get("control_plane_error") == "unknown_project_id"
