"""Native Builder v2 chat stream short-circuit: when start_native_build_job
returns "started", the stream must close immediately — no Hermes gateway
streaming, no worker execution awaited, no internals exposed."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)

client = TestClient(app)

_FORBIDDEN_TOKENS = (
    "registry_v2",
    "proposal_digest",
    "base_revision",
    "inline_files",
    "hermes-builder",
    "hermes_gateway",
    "openrouter",
    "upstream_timeout",
    "import_job_id",
    "native_build_job_id",
    "cloud_tasks",
)


def _parse_ndjson(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _native_started_meta() -> dict:
    return {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": False,
        "ham_native_builder": {"status": "started"},
        "import_job_id": "ijob_short_circuit",
        "native_build_job_id": "ijob_short_circuit",
        "selected_builder_state": "native",
        "builder_harness_first": True,
    }


def _native_failed_meta(reason: str = "gateway") -> dict:
    return {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": False,
        "ham_native_builder": {"status": "failed", "failure_reason": reason},
        "import_job_id": "ijob_fail",
        "selected_builder_state": "native",
        "builder_harness_first": True,
    }


@pytest.fixture
def _empty_store(tmp_path):
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_source_store_for_tests(None)


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


# ---------------------------------------------------------------------------
# Stream short-circuit
# ---------------------------------------------------------------------------


def test_native_build_started_closes_stream_immediately(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """When native builder v2 returns "started", the stream emits safe copy
    and terminates immediately — no Hermes gateway streaming."""
    prefix = "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"

    def _builder_hook(**kwargs):
        return prefix, _native_started_meta()

    def _must_not_stream(*_a, **_k):
        raise AssertionError("stream_chat_turn must not run after native build started")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _must_not_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    types = [e["type"] for e in events]
    assert types[0] == "session"
    assert "delta" in types
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    # Safe copy in the final messages.
    assistant = done[0]["messages"][-1]["content"]
    assert "HAM started the native build" in assistant
    # No LLM streamed tokens beyond the builder ack.
    delta_text = "".join(e.get("text", "") for e in events if e["type"] == "delta")
    assert delta_text.strip() == prefix.strip()


def test_native_build_started_no_hermes_gateway_call_after_started(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """No Hermes conversational gateway streaming call happens after native job started."""
    stream_calls = {"n": 0}

    def _must_not_stream(*_a, **_k):
        stream_calls["n"] += 1
        raise AssertionError("stream_chat_turn must not be called after native build started")

    complete_calls = {"n": 0}

    def _must_not_complete(*_a, **_k):
        complete_calls["n"] += 1
        raise AssertionError("complete_chat_turn must not be called after native build started")

    prefix = "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"

    def _builder_hook(**kwargs):
        return prefix, _native_started_meta()

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _must_not_stream)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", _must_not_complete)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text
    assert stream_calls["n"] == 0
    assert complete_calls["n"] == 0


def test_native_build_started_rest_post_chat_returns_immediately(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """POST /api/chat also short-circuits immediately for native build started."""
    prefix = "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"

    def _builder_hook(**kwargs):
        return prefix, _native_started_meta()

    def _must_not_complete(*_a, **_k):
        raise AssertionError("complete_chat_turn must not be called after native build started")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", _must_not_complete)

    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assistant = body["messages"][-1]["content"]
    assert "HAM started the native build" in assistant


# ---------------------------------------------------------------------------
# Other builder paths unchanged
# ---------------------------------------------------------------------------


def test_opencode_handoff_still_works(mock_mode, _empty_store, monkeypatch) -> None:
    """OpenCode/Factory Droid handoff paths are not affected by the native short-circuit."""
    prefix = "OpenCode is your selected builder. I've prepared the build on the right.\n\n"
    meta = {
        "builder_intent": "build_or_create",
        "scaffolded": False,
        "builder_harness_first": True,
        "selected_builder_state": "ready",
        "selected_builder_label": "OpenCode",
        "builder_handoff_required": True,
        "selected_builder_key": "opencode",
    }

    def _builder_hook(**kwargs):
        return prefix, meta

    def _must_not_stream(*_a, **_k):
        raise AssertionError("stream_chat_turn must not run for builder handoff")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _must_not_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a tetris game"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assistant = done[0]["messages"][-1]["content"]
    assert "OpenCode" in assistant


def test_native_build_failure_does_not_short_circuit_to_ndjson(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """When native build fails (not started), the harness-first path handles it
    — it does NOT fall through to ndjson_gen."""

    def _builder_hook(**kwargs):
        return (
            "HAM Native Builder could not reach the Hermes runtime.\n\n",
            _native_failed_meta("gateway"),
        )

    def _must_not_stream(*_a, **_k):
        raise AssertionError("stream_chat_turn must not run for harness-first failure")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _must_not_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assistant = done[0]["messages"][-1]["content"]
    assert "could not reach" in assistant


# ---------------------------------------------------------------------------
# Old scaffold not called
# ---------------------------------------------------------------------------


def test_native_build_started_does_not_call_old_scaffold(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """The old scaffold must not run when native build starts."""

    def _scaffold_raise(*_a, **_k):
        raise AssertionError("maybe_chat_scaffold_for_turn must not run for native build started")

    prefix = "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"

    def _builder_hook(**kwargs):
        return prefix, _native_started_meta()

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn", _scaffold_raise)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# No internals exposed
# ---------------------------------------------------------------------------


def test_native_build_started_exposes_no_internals(
    mock_mode, _empty_store, monkeypatch
) -> None:
    """The NDJSON stream and session messages must not leak build-kit internals,
    job ids, provider names, or secrets."""
    prefix = "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"
    # Use meta that includes job ids — these must not appear in user-facing copy.
    meta = {
        **_native_started_meta(),
        "import_job_id": "ijob_internal_test",
        "native_build_job_id": "ijob_internal_test",
    }

    def _builder_hook(**kwargs):
        return prefix, meta

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a calculator"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    # Check assistant message text (user-visible copy).
    assistant = done["messages"][-1]["content"].lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in assistant, f"forbidden token {token!r} leaked into assistant copy"
    # The builder metadata dict is included in the done payload for frontend
    # routing, so we only check user-facing copy above. Ensure the assistant
    # message (the only user-visible text) is clean.
