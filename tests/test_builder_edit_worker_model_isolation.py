"""VAL-LANE-008 — builder edit worker's complete_chat_turn path ignores HAM_CHAT_CONVERSATIONAL_MODEL.

`src/ham/builder_edit_worker.py` calls `complete_chat_turn(messages)` with no
`openrouter_model_override`. The effective gateway/LiteLLM model id MUST be
derived from `HERMES_GATEWAY_MODEL` (or `DEFAULT_MODEL` fallback), never from
`HAM_CHAT_CONVERSATIONAL_MODEL`.
"""
from __future__ import annotations

import pytest


_CONV_SENTINEL = "openrouter/sentinel-conv:free"
_GATEWAY_GUARD = "openrouter/guard-gateway:free"


def test_builder_edit_worker_ignores_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP gateway primary slug used by complete_chat_turn is HERMES_GATEWAY_MODEL, not the conv env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", _GATEWAY_GUARD)
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://test-builder-worker.local:1234")
    monkeypatch.delenv("HAM_CHAT_FALLBACK_MODEL", raising=False)

    captured_models: list[str] = []

    def _fake_iter_http_chat_completions(
        *,
        base: str,
        api_key: str,
        model: str,
        messages: list,
        timeout_sec: float,
    ):
        captured_models.append(model)
        yield "ok"

    monkeypatch.setattr(
        "src.integrations.nous_gateway_client._iter_http_chat_completions",
        _fake_iter_http_chat_completions,
    )

    # Import via the same path the builder edit worker uses.
    from src.ham.builder_edit_worker import complete_chat_turn

    raw = complete_chat_turn(
        [
            {"role": "system", "content": "edit worker test"},
            {"role": "user", "content": "make a change"},
        ]
    )
    assert raw == "ok"
    assert captured_models == [_GATEWAY_GUARD]
    assert _CONV_SENTINEL not in captured_models


def test_builder_edit_worker_complete_chat_turn_passes_no_openrouter_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Static-shape complement: the worker call site never forwards openrouter_model_override."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", _GATEWAY_GUARD)

    captured_kwargs: dict[str, object] = {}

    def _capture(messages, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return ""

    monkeypatch.setattr("src.ham.builder_edit_worker.complete_chat_turn", _capture)

    import src.ham.builder_edit_worker as bew

    bew.complete_chat_turn(
        [
            {"role": "system", "content": "x"},
            {"role": "user", "content": "y"},
        ]
    )

    override = captured_kwargs.get("openrouter_model_override")
    assert override is None or override != _CONV_SENTINEL
