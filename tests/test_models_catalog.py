"""Tests for unified GET /api/models catalog and chat model resolution."""
from __future__ import annotations

import pytest

from src.api import models_catalog as mc


def test_resolve_none_uses_default() -> None:
    assert mc.resolve_model_id_for_chat(None) is None
    assert mc.resolve_model_id_for_chat("") is None
    assert mc.resolve_model_id_for_chat("   ") is None


def test_resolve_cursor_rejected() -> None:
    with pytest.raises(ValueError, match="CURSOR_MODEL_NOT_CHAT_ENABLED"):
        mc.resolve_model_id_for_chat("cursor:composer-2")


def test_resolve_unknown() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_MODEL_ID"):
        mc.resolve_model_id_for_chat("not-a-real-id")


_FAKE_OR_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


def test_resolve_openrouter_default_id(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")
    m = mc.resolve_model_id_for_chat("openrouter:default")
    assert m is not None
    assert "openrouter" in m


def test_build_catalog_has_openrouter_and_cursor_shape(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)

    payload = mc.build_catalog_payload()
    assert payload["openrouter_chat_ready"] is True
    assert payload.get("dashboard_chat_ready") is True
    assert payload.get("http_chat_ready") is False
    ids = {x["id"] for x in payload["items"]}
    assert "openrouter:default" in ids
    assert "tier:auto" in ids
    assert "tier:premium" in ids
    cursor_like = [x for x in payload["items"] if x["id"].startswith("cursor:")]
    assert len(cursor_like) >= 1
    assert all(x["supports_chat"] is False for x in cursor_like)


def test_build_catalog_openrouter_not_ready_when_key_poisoned(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "Bearer echo sk-or-v1-not-a-real-key-000000000")
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    assert payload["openrouter_chat_ready"] is False
    row = next(x for x in payload["items"] if x["id"] == "openrouter:default")
    assert row["supports_chat"] is False
    assert row["disabled_reason"] and "OPENROUTER_API_KEY" in row["disabled_reason"]


def test_build_catalog_http_mode_openrouter_tiers_inactive(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    assert payload["gateway_mode"] == "http"
    assert payload["openrouter_chat_ready"] is False
    assert payload.get("http_chat_ready") is True
    assert payload.get("dashboard_chat_ready") is True
    row = next(x for x in payload["items"] if x["id"] == "openrouter:default")
    assert row["supports_chat"] is False
    assert row["disabled_reason"] and "HERMES_GATEWAY_MODE=http" in row["disabled_reason"]
    assert "OPENROUTER_API_KEY" not in (row["disabled_reason"] or "")


def test_build_catalog_http_mode_missing_base_url_not_ready(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    assert payload["gateway_mode"] == "http"
    assert payload.get("http_chat_ready") is False
    assert payload.get("dashboard_chat_ready") is False
