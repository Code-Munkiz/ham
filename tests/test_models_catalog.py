"""Tests for unified GET /api/models catalog and chat model resolution."""
from __future__ import annotations

import json

import pytest

from src.api import models_catalog as mc
from src.llm_client import get_default_model, resolve_openrouter_model_name_for_chat


@pytest.fixture(autouse=True)
def _openrouter_catalog_test_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real OpenRouter HTTP; individual tests may override the fetch stub."""
    mc.reset_openrouter_catalog_cache_for_tests()
    monkeypatch.setattr(mc, "_fetch_openrouter_public_models_from_network", lambda: ([], False))
    yield
    mc.reset_openrouter_catalog_cache_for_tests()


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
    assert payload.get("openrouter_catalog", {}).get("remote_models_fetched") is True
    assert payload.get("openrouter_catalog", {}).get("remote_fetch_failed") is False


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
    oc = payload.get("openrouter_catalog") or {}
    assert oc.get("remote_models_fetched") is False


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


def test_get_default_model_fallback_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    assert get_default_model() == "minimax/minimax-m2.5:free"


def test_auto_tier_tracks_get_default_model_not_gateway_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """tier:auto uses get_default_model() only; HERMES_GATEWAY_MODEL must not change Auto row."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "anthropic/claude-3-haiku")
    payload = mc.build_catalog_payload()
    auto = next(x for x in payload["items"] if x["id"] == "tier:auto")
    default_row = next(x for x in payload["items"] if x["id"] == "openrouter:default")
    assert auto["openrouter_model"] == f"openrouter/{get_default_model()}"
    assert auto["openrouter_model"] == "openrouter/minimax/minimax-m2.5:free"
    assert default_row["openrouter_model"] == "openrouter/anthropic/claude-3-haiku"


def test_hermes_gateway_model_overrides_default_for_chat_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_MODEL", "minimax/minimax-m2.5:free")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "openai/gpt-4o-mini")
    assert resolve_openrouter_model_name_for_chat() == "openrouter/openai/gpt-4o-mini"


_HAM_PHASE1_ROW: list[dict] = [
    {
        "id": "openai/ham-phase1-test",
        "label": "Ham Phase1",
        "tag": "API",
        "tier": None,
        "provider": "openai",
        "description": "unit test placeholder",
        "supports_chat": True,
        "disabled_reason": None,
        "openrouter_model": "openrouter/openai/ham-phase1-test",
        "context_length": 8000,
        "pricing_display": None,
    },
]


def test_openrouter_remote_rows_merge_into_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mc,
        "_fetch_openrouter_public_models_from_network",
        lambda: (_HAM_PHASE1_ROW, False),
    )
    mc.reset_openrouter_catalog_cache_for_tests()
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    ids = {x["id"] for x in payload["items"]}
    assert "openai/ham-phase1-test" in ids
    row = next(x for x in payload["items"] if x["id"] == "openai/ham-phase1-test")
    assert row["openrouter_model"] == "openrouter/openai/ham-phase1-test"
    assert payload["openrouter_catalog"]["remote_model_count"] == 1


def test_resolve_remote_openrouter_slug_from_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mc,
        "_fetch_openrouter_public_models_from_network",
        lambda: (_HAM_PHASE1_ROW, False),
    )
    mc.reset_openrouter_catalog_cache_for_tests()
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    assert mc.resolve_model_id_for_chat("openai/ham-phase1-test") == "openrouter/openai/ham-phase1-test"


def test_catalog_payload_never_contains_openrouter_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-or-v1-hamtests-json-leak-check-abcdef012345"
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    blob = json.dumps(payload)
    assert secret not in blob
    assert "Authorization" not in blob


def test_openrouter_catalog_marks_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc, "_fetch_openrouter_public_models_from_network", lambda: ([], True))
    mc.reset_openrouter_catalog_cache_for_tests()
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    payload = mc.build_catalog_payload()
    assert payload["openrouter_catalog"]["remote_fetch_failed"] is True
    assert payload["openrouter_catalog"]["remote_model_count"] == 0


def test_openrouter_public_fetch_hits_network_at_most_once_per_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fetch() -> tuple[list[dict], bool]:
        calls["n"] += 1
        row = {
            **_HAM_PHASE1_ROW[0],
            "id": f'openai/ham-fetch-{calls["n"]}',
            "openrouter_model": f'openrouter/openai/ham-fetch-{calls["n"]}',
        }
        return [row], False

    monkeypatch.setattr(mc, "_fetch_openrouter_public_models_from_network", fetch)
    mc.reset_openrouter_catalog_cache_for_tests()
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", _FAKE_OR_KEY)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    first = mc.build_catalog_payload()
    second = mc.build_catalog_payload()
    assert calls["n"] == 1
    first_ids = {x["id"] for x in first["items"]}
    second_ids = {x["id"] for x in second["items"]}
    assert first_ids == second_ids
    assert "openai/ham-fetch-1" in first_ids
