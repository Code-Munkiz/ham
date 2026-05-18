"""Unit tests for the HAM_CHAT_CONVERSATIONAL_MODEL env-reader helper (VAL-ENV-003..013)."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.api import chat as chat_mod


@pytest.fixture(autouse=True)
def _reset_conversational_notice_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the one-time notice flag between tests so VAL-ENV-006/011 stay independent."""
    monkeypatch.setattr(chat_mod, "_chat_conversational_model_notice_emitted", False, raising=True)
    monkeypatch.setattr(
        chat_mod,
        "_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK",
        threading.Lock(),
        raising=True,
    )


def test_unset_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-ENV-003 — helper returns None when env var is unset."""
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_MODE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    assert chat_mod._chat_conversational_model_default() is None


@pytest.mark.parametrize("value", ["", "   ", "\t", "\n  \n"])
def test_blank_returns_none(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """VAL-ENV-004 — helper returns None for whitespace-only values."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", value)
    assert chat_mod._chat_conversational_model_default() is None


def test_valid_slug_is_trimmed_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-ENV-005 — bare slug is trimmed and prefixed with openrouter/; double-prefix avoided."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "  minimax/minimax-m2.5:free  ")
    result = chat_mod._chat_conversational_model_default()
    assert result == "openrouter/minimax/minimax-m2.5:free"

    monkeypatch.setenv(
        "HAM_CHAT_CONVERSATIONAL_MODEL",
        "openrouter/minimax/minimax-m2.5:free",
    )
    result_prefixed = chat_mod._chat_conversational_model_default()
    assert result_prefixed == "openrouter/minimax/minimax-m2.5:free"


def test_lane_enabled_notice_emitted_once_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-ENV-006 — INFO notice fires exactly once and never contains API keys / Bearer tokens."""
    monkeypatch.setenv(
        "HAM_CHAT_CONVERSATIONAL_MODEL",
        "openrouter/anthropic/claude-3.5-haiku",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-deadbeef")
    monkeypatch.setenv("HERMES_GATEWAY_API_KEY", "bearer-test-deadbeef")

    with caplog.at_level(logging.INFO, logger=chat_mod._LOG.name):
        chat_mod._chat_conversational_model_default()
        chat_mod._chat_conversational_model_default()
        chat_mod._chat_conversational_model_default()

    records = [
        r
        for r in caplog.records
        if "chat_conversational_model" in (r.getMessage() or "")
        or "chat_conversational_model" in (getattr(r, "chat_conversational_model", "") or "")
    ]
    assert len(records) == 1, [r.getMessage() for r in records]
    record = records[0]
    full = record.getMessage() + " " + str(getattr(record, "chat_conversational_model", ""))
    assert "sk-or-test-deadbeef" not in full
    assert "bearer-test-deadbeef" not in full
    assert "Bearer " not in full
    assert "sk-" not in full
    assert "openrouter/anthropic/claude-3.5-haiku" in full


def test_lane_disabled_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-ENV-007 — when env var is unset/blank, helper emits no log line."""
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    with caplog.at_level(logging.DEBUG, logger=chat_mod._LOG.name):
        chat_mod._chat_conversational_model_default()
        chat_mod._chat_conversational_model_default()
    matches = [r for r in caplog.records if "chat_conversational_model" in r.getMessage()]
    assert matches == []


@pytest.mark.parametrize(
    "gateway_mode,gateway_model,openrouter_key",
    [
        ("openrouter", "", ""),
        ("openrouter", "minimax/minimax-m2.5:free", "sk-or-deadbeefdeadbeefdeadbeefdeadbeef"),
        ("http", "hermes-agent", ""),
        ("mock", "", ""),
        ("", "", ""),
    ],
)
def test_helper_is_independent_of_gateway_env(
    monkeypatch: pytest.MonkeyPatch,
    gateway_mode: str,
    gateway_model: str,
    openrouter_key: str,
) -> None:
    """VAL-ENV-009 — return value depends only on HAM_CHAT_CONVERSATIONAL_MODEL, not gateway state."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", gateway_mode)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", gateway_model)
    monkeypatch.setenv("OPENROUTER_API_KEY", openrouter_key)
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "anthropic/claude-3.5-haiku")
    assert (
        chat_mod._chat_conversational_model_default()
        == "openrouter/anthropic/claude-3.5-haiku"
    )

    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    assert chat_mod._chat_conversational_model_default() is None


def test_lane_notice_thread_safe_first_invocation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-ENV-011 — concurrent first invocations emit exactly one notice."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "minimax/minimax-m2.5:free")
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        chat_mod._chat_conversational_model_default()

    with caplog.at_level(logging.INFO, logger=chat_mod._LOG.name):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(worker) for _ in range(8)]
            for f in futures:
                f.result()

    records = [
        r
        for r in caplog.records
        if "chat_conversational_model" in r.getMessage()
    ]
    assert len(records) == 1


def test_helper_rereads_env_on_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-ENV-012 — helper re-reads os.environ on every call; no caching."""
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    assert chat_mod._chat_conversational_model_default() is None

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "model-a/slug:free")
    assert chat_mod._chat_conversational_model_default() == "openrouter/model-a/slug:free"

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "model-b/slug:free")
    assert chat_mod._chat_conversational_model_default() == "openrouter/model-b/slug:free"

    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    assert chat_mod._chat_conversational_model_default() is None


@pytest.mark.parametrize(
    "raw",
    [
        "slug with spaces",
        "slug;rm -rf /",
        "../../etc/passwd",
        "openrouter/openrouter/double-prefix",
        "slug\nBearer xyz",
        "slug\r\nInject: yes",
    ],
)
def test_helper_handles_malformed_values_safely(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """VAL-ENV-013 — malformed inputs never raise, never embed CR/LF, never mutate other chars."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", raw)
    result = chat_mod._chat_conversational_model_default()
    assert result is None or ("\n" not in result and "\r" not in result)
    if result is not None:
        if raw.strip().startswith("openrouter/"):
            assert result == raw.strip()
        else:
            assert result == f"openrouter/{raw.strip()}"



