"""Hermes HTTP JSON payload budgeting for dashboard chat upstream calls."""
from __future__ import annotations

import pytest

from src.ham.hermes_http_context_budget import apply_hermes_http_context_budget
from src.integrations.nous_gateway_client import GatewayCallError, format_gateway_error_user_message


@pytest.fixture(autouse=True)
def _budget_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_HERMES_HTTP_CONTEXT_MAX_CHARS", raising=False)


def test_drops_gateway_rejection_boilerplate_assistant_roles() -> None:
    msgs = [
        {"role": "system", "content": "stay helpful"},
        {
            "role": "assistant",
            "content": "The model gateway rejected the request. Try again or contact support if it continues.",
        },
        {"role": "user", "content": "fresh question"},
        {
            "role": "assistant",
            "content": "The model gateway rejected the request. Try again or contact support if it continues.",
        },
        {"role": "user", "content": "keep me"},
    ]
    trimmed, meta = apply_hermes_http_context_budget(msgs, max_wire_chars=1_000_000)
    assert meta.dropped_error_message_count == 2
    assistants = [m for m in trimmed if m.get("role") == "assistant"]
    assert assistants == []
    assert trimmed[-1]["content"] == "keep me"


def test_keeps_last_user_through_aggressive_budget() -> None:
    base = [{"role": "system", "content": "(sys)"}]
    fillers = [{"role": "user", "content": "o" * 400}, {"role": "assistant", "content": "a" * 400}]
    msgs = [*base, *fillers * 40, {"role": "user", "content": "FINAL_UNIQUE"}]

    trimmed, meta = apply_hermes_http_context_budget(msgs, max_wire_chars=2500)

    users = [m for m in trimmed if m.get("role") == "user"]
    assert users[-1]["content"] == "FINAL_UNIQUE"
    assert meta.truncated_for_gateway_budget


def test_format_upstream_413_mentions_context_overload() -> None:
    exc = GatewayCallError("UPSTREAM_REJECTED", "Gateway HTTP 413", http_status=413)
    text = format_gateway_error_user_message(exc)
    lowered = text.lower()
    assert "too large" in lowered
    assert "new chat" in lowered
