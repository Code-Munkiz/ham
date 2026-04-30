"""Unit tests for Cursor → HAM managed-mission feed projection helpers."""

from __future__ import annotations

from src.ham.cursor_provider_adapter import (
    map_cursor_conversation_to_feed_events,
    provider_projection_envelope,
)


def test_map_cursor_sorts_by_observed_time() -> None:
    payload = {
        "events": [
            {"id": "b", "createdAt": "2026-01-02T00:00:02Z", "role": "assistant", "message": "second"},
            {"id": "a", "createdAt": "2026-01-02T00:00:01Z", "role": "assistant", "message": "first"},
        ]
    }
    out = map_cursor_conversation_to_feed_events(agent_id="ag_test", payload=payload)
    assert len(out) == 2
    assert out[0]["message"] == "first"
    assert out[1]["message"] == "second"


def test_map_cursor_dedupes_by_provider_stable_id() -> None:
    payload = {
        "events": [
            {
                "id": "same-row",
                "createdAt": "2026-01-02T00:00:01Z",
                "type": "tool_progress",
                "message": "first",
            },
            {
                "id": "same-row",
                "createdAt": "2026-01-02T00:00:05Z",
                "type": "tool_progress",
                "message": "last wins same id",
            },
        ]
    }
    out = map_cursor_conversation_to_feed_events(agent_id="ag_test", payload=payload)
    assert len(out) == 1
    assert out[0]["message"] == "last wins same id"


def test_map_cursor_redacts_secrets_in_message() -> None:
    payload = {
        "events": [
            {
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "log",
                "message": "token is crsr_ABCDEF1234567890 here",
            }
        ]
    }
    out = map_cursor_conversation_to_feed_events(agent_id="ag_test", payload=payload)
    assert len(out) == 1
    assert "crsr_" not in out[0]["message"]
    assert "[REDACTED]" in out[0]["message"]


def test_provider_projection_envelope_ok_and_unavailable() -> None:
    ok = provider_projection_envelope(provider_error=None)
    assert ok["mode"] == "rest_projection"
    assert ok["native_realtime_stream"] is False
    assert ok["status"] == "ok"
    assert ok["reason"] is None

    miss = provider_projection_envelope(provider_error="provider_key_missing")
    assert miss["status"] == "unavailable"

    u404 = provider_projection_envelope(provider_error="provider_conversation_unavailable:404")
    assert u404["status"] == "unavailable"

    e500 = provider_projection_envelope(provider_error="provider_conversation_unavailable:502")
    assert e500["status"] == "error"


def test_map_cursor_normalizes_tool_progress_to_status_kind() -> None:
    payload = {
        "events": [
            {
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "tool_progress",
                "role": "tool",
                "message": "step",
            }
        ]
    }
    out = map_cursor_conversation_to_feed_events(agent_id="ag_test", payload=payload)
    assert out[0]["kind"] == "status"
    assert "tool_progress" in (out[0].get("reason_code") or "")
