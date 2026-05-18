"""Tests for src/ham/sentry_wiring.py — Phase 1 #9 (ADR-0008).

Covers: no-op when DSN unset, is_active() state, idempotent init.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.sentry_wiring import init, is_active, reset_for_tests

# Obviously-fake DSN placeholder — sentry_sdk.init is mocked so format does not matter.
_FAKE_DSN = "sentry-dsn-placeholder-for-tests"
_FAKE_DSN2 = "sentry-dsn-placeholder-for-tests-2"


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


class TestInitNoDsn:
    def test_is_active_false_before_init(self):
        assert is_active() is False

    def test_init_with_no_dsn_is_noop(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        init()
        assert is_active() is False

    def test_init_with_empty_dsn_is_noop(self):
        init(dsn="")
        assert is_active() is False

    def test_init_with_whitespace_dsn_is_noop(self):
        init(dsn="   ")
        assert is_active() is False

    def test_init_with_env_dsn_empty_is_noop(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "")
        init()
        assert is_active() is False


class TestInitWithDsn:
    def test_is_active_true_after_init_with_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with patch("sentry_sdk.init"):
            init(dsn=_FAKE_DSN)
        assert is_active() is True

    def test_sentry_sdk_init_called_with_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with patch("sentry_sdk.init") as mock_sdk_init:
            init(dsn=_FAKE_DSN)
        mock_sdk_init.assert_called_once()
        call_kwargs = mock_sdk_init.call_args.kwargs
        assert call_kwargs["dsn"] == _FAKE_DSN
        assert call_kwargs["traces_sample_rate"] == 0.0
        assert call_kwargs["send_default_pii"] is False

    def test_init_is_idempotent(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with patch("sentry_sdk.init") as mock_sdk_init:
            init(dsn=_FAKE_DSN)
            init(dsn=_FAKE_DSN2)
        assert is_active() is True
        assert mock_sdk_init.call_count == 1  # second call was no-op

    def test_reset_for_tests_clears_state(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with patch("sentry_sdk.init"):
            init(dsn=_FAKE_DSN)
        assert is_active() is True
        reset_for_tests()
        assert is_active() is False

    def test_env_dsn_activates_sdk(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init"):
            init()
        assert is_active() is True
