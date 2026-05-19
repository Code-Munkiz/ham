"""POST /api/chat/stream NDJSON streaming."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _parse_ndjson(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def test_chat_stream_rejects_multiple_messages_in_one_request(mock_mode: None) -> None:
    """Data minimization: each turn sends one user message; prior context is session-backed."""
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
            ],
        },
    )
    assert res.status_code == 422


def test_chat_stream_rejects_non_user_single_message(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "assistant", "content": "hello"}]},
    )
    assert res.status_code == 422


def test_chat_stream_mock_yields_session_delta_done(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello stream"}]},
    )
    assert res.status_code == 200, res.text
    assert "ndjson" in res.headers.get("content-type", "").lower()
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    assert events[0]["session_id"]
    deltas = [e for e in events if e["type"] == "delta"]
    assert deltas
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["session_id"] == events[0]["session_id"]
    msgs = done[0]["messages"]
    assert msgs[-1]["role"] == "assistant"
    assert "Mock assistant reply" in msgs[-1]["content"]


def test_chat_stream_releases_lock_when_execution_mode_raises(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: _claim_stream_session must not stick if setup after claim raises."""

    seed = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "seed session for lock test"}]},
    )
    assert seed.status_code == 200, seed.text
    sid = str(_parse_ndjson(seed.text)[0]["session_id"])

    calls = {"n": 0}

    def _boom_once(**kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated post-claim execution-mode failure")
        return kwargs["execution_mode"]

    monkeypatch.setattr("src.api.chat._apply_browser_bridge_for_turn", _boom_once)

    with pytest.raises(RuntimeError, match="simulated post-claim execution-mode failure"):
        client.post(
            "/api/chat/stream",
            json={"session_id": sid, "messages": [{"role": "user", "content": "hello"}]},
        )

    res_ok = client.post(
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "hello again"}]},
    )
    assert res_ok.status_code == 200, res_ok.text
    events = _parse_ndjson(res_ok.text)
    assert events[0]["type"] == "session"


@pytest.mark.parametrize(
    ("prompt", "expected_intent", "expected_reason_code"),
    [
        (
            "Launch a Cursor Cloud Agent for repo Unmapped-Org/unmapped-repo on branch main. Task: update docs only.",
            "cursor_agent_launch",
            "missing_project_mapping",
        ),
        (
            "have Cursor implement the SDK adapter fix",
            "cursor_agent_launch",
            "missing_project_context",
        ),
        (
            "fire up an agent to update the SDK adapter",
            "cursor_agent_launch",
            "missing_project_context",
        ),
    ],
)
@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_routes_agent_intents_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    expected_intent: str,
    expected_reason_code: str,
    conv_env: str | None,
) -> None:
    """VAL-LANE-007 — agent-router lane short-circuits without LLM under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for agent-router short-circuit")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": prompt}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    # Routed intents should short-circuit before model streaming.
    assert [e for e in events if e["type"] == "delta"] == []
    done = [e for e in events if e["type"] == "done"][0]
    operator_result = done.get("operator_result")
    assert isinstance(operator_result, dict)
    assert operator_result.get("intent") == expected_intent
    assert operator_result.get("handled") is True
    assert operator_result.get("data", {}).get("reason_code") == expected_reason_code


@pytest.mark.parametrize(
    "prompt",
    [
        "send this to Factory Droid to update the SDK adapter",
        "use Claude to implement this change",
        "launch Claude Cloud Agent to edit this repo",
    ],
)
def test_chat_stream_non_cursor_agent_mention_streams_without_operator_block(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": prompt}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert any(e.get("type") == "delta" for e in events)
    done = [e for e in events if e["type"] == "done"][0]
    assert not done.get("operator_result")


def test_chat_stream_non_cursor_turn_persists_streamed_assistant_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "send this to Factory Droid to update the SDK adapter"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    done = [e for e in _parse_ndjson(res.text) if e["type"] == "done"][0]
    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert msgs[-1]["role"] == "assistant"
    assert "provider_not_implemented" not in msgs[-1]["content"]
    assert "Blocked:" not in msgs[-1]["content"]


def test_chat_stream_build_intent_bypasses_operator_fallback(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            "I'll create the initial project source and prepare the Workbench.\n\n",
            {"builder_intent": "build_or_create", "scaffolded": True},
        )

    def _unexpected_operator(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("operator fallback must not run for build_or_create intent")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.process_operator_turn", _unexpected_operator)
    monkeypatch.setattr("src.api.chat.process_agent_router_turn", _unexpected_operator)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a game like Tetris"}], "enable_operator": True},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assert done.get("operator_result") is None
    assert done.get("builder", {}).get("builder_intent") == "build_or_create"
    assert "prepare the Workbench" in done["messages"][-1]["content"]


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_build_intent_handoffs_without_long_llm_stream(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-002 — early-handoff lane never invokes stream_chat_turn under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)

    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            "I'll create the initial project source and prepare the Workbench.\n\n",
            {"builder_intent": "build_or_create", "scaffolded": True},
        )

    def _should_not_stream(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("stream_chat_turn should not run for builder handoff")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _should_not_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a game like Tetris"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assistant = done["messages"][-1]["content"]
    assert "prepare the Workbench" in assistant
    assert "started the live preview handoff" in assistant
    assert "Connection interrupted. Ask me to continue." not in assistant


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_artifact_verification_failure_skips_llm_stream(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-004 — verification-failure lane skips LLM under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    honest = (
        "I tried to apply that edit, but the generated files did not include what you asked for yet "
        "(missing yellow border styling on digit keys).\n\n"
    )

    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            honest,
            {
                "builder_intent": "build_or_create",
                "scaffolded": False,
                "artifact_verification_failed": True,
                "artifact_verification": {
                    "verified": False,
                    "reason": "missing yellow border styling on digit keys",
                },
            },
        )

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run when artifact verification failed")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "yellow border please"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert [e.get("type") for e in events] == ["session", "delta", "done"]
    done = events[-1]
    assert done.get("artifact_verification", {}).get("verified") is False
    assert done["messages"][-1]["content"] == honest
    assert "live preview handoff" not in done["messages"][-1]["content"]


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_builder_edit_worker_blocked_skips_llm_stream(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-005 — edit-worker-blocked lane skips LLM under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    honest = (
        "Structured builder edits require a live Hermes gateway on the API host "
        "(mock gateway mode cannot produce patches). Configure the gateway or try again later.\n\n"
    )

    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            honest,
            {
                "builder_intent": "build_or_create",
                "scaffolded": False,
                "builder_edit_worker_blocked": True,
                "builder_edit_worker": {"worker": "hermes_gateway", "blocked_reason": "gateway_mock_or_unconfigured"},
                "source_snapshot_id": "ssnp_existing",
            },
        )

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run when builder edit worker blocked")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "change + and - buttons"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert [e.get("type") for e in events] == ["session", "delta", "done"]
    done = events[-1]
    assert done["messages"][-1]["content"] == honest
    b = done.get("builder") or {}
    assert b.get("builder_edit_worker_blocked") is True
    assert (b.get("builder_edit_worker") or {}).get("blocked_reason") == "gateway_mock_or_unconfigured"
    low = done["messages"][-1]["content"].lower()
    assert "updated" not in low
    assert "preview refreshed" not in low
    assert "live preview handoff" not in done["messages"][-1]["content"]
    assert "I've generated" not in done["messages"][-1]["content"]
    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    persisted = detail.json()["messages"][-1]
    assert persisted["role"] == "assistant"
    assert persisted["content"] == honest


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_builder_clarification_skips_llm_stream(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-003 — builder clarification lane skips LLM under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    clar = "Which part should I edit?\n\n"

    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            clar,
            {
                "builder_intent": "answer_question",
                "builder_clarification": True,
                "builder_action_decision": {"kind": "ask_clarification", "reason": "vague_improvement"},
            },
        )

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for builder clarification")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "make it better"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert [e.get("type") for e in events] == ["session", "delta", "done"]
    assert events[1].get("type") == "delta"
    assert events[1].get("text") == clar.strip()
    done = events[-1]
    assert done["messages"][-1]["content"] == clar.strip()
    low = done["messages"][-1]["content"].lower()
    assert "updated" not in low
    assert "preview refreshed" not in low
    assert "generated project files" not in low
    assert "live preview handoff" not in done["messages"][-1]["content"]
    assert "I've generated" not in done["messages"][-1]["content"]
    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    assert detail.json()["messages"][-1]["content"] == clar.strip()


def test_chat_stream_local_repo_ops_not_forced_into_mission_route_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "gh auth status"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert any(e.get("type") == "delta" for e in events), "should remain normal chat stream"
    done = [e for e in events if e["type"] == "done"][0]
    operator_result = done.get("operator_result")
    assert not operator_result


def test_chat_stream_gateway_failure_done_with_safe_assistant_and_signal(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_stream(*_a, **_k):
        raise GatewayCallError(
            "UPSTREAM_REJECTED",
            "secret-upstream-body-do-not-show-users",
            http_status=503,
        )

    monkeypatch.setattr("src.api.chat.stream_chat_turn", failing_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done.get("gateway_error") == {"code": "UPSTREAM_REJECTED", "upstream_http_status": 503}
    msgs = done["messages"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert msgs[-1]["role"] == "assistant"
    body = msgs[-1]["content"]
    assert "secret-upstream" not in body.lower()
    assert "try again" in body.lower() or "settings" in body.lower()


def test_chat_stream_openrouter_model_rejected_done_with_safe_assistant_and_signal(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_stream(*_a, **_k):
        raise GatewayCallError(
            "OPENROUTER_MODEL_REJECTED",
            "secret-provider-body-do-not-show-users",
            http_status=400,
        )

    monkeypatch.setattr("src.api.chat.stream_chat_turn", failing_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done.get("gateway_error") == {"code": "OPENROUTER_MODEL_REJECTED", "upstream_http_status": 400}
    msgs = done["messages"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    body = msgs[-1]["content"]
    assert "secret-provider" not in body.lower()


def test_chat_stream_vision_text_fallback_preserves_conversational_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-FALLBACK-006 — the vision text-fallback retry reuses the same env-derived override."""
    from src.api import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_chat_conversational_model_notice_emitted", False, raising=True)
    monkeypatch.setattr(
        chat_mod, "_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK", threading.Lock(), raising=True,
    )

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setenv(
        "HAM_CHAT_CONVERSATIONAL_MODEL",
        "openrouter/anthropic/claude-3.5-haiku",
    )
    monkeypatch.setenv("HAM_CHAT_VISION_UPSTREAM_TEXT_FALLBACK", "1")

    overrides_seen: list[str | None] = []
    call_count = {"n": 0}

    def fake_stream(messages, **kwargs):  # type: ignore[no-untyped-def]
        overrides_seen.append(kwargs.get("openrouter_model_override"))
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise GatewayCallError("UPSTREAM_REJECTED", "vision rejected", http_status=400)
        yield "ok"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", fake_stream)

    image_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "describe this",
                        "images": [
                            {
                                "name": "tiny.png",
                                "mime": "image/png",
                                "data_url": image_data_url,
                            }
                        ],
                    },
                }
            ]
        },
    )
    assert res.status_code == 200, res.text
    expected = "openrouter/anthropic/claude-3.5-haiku"
    assert len(overrides_seen) == 2, overrides_seen
    assert call_count["n"] == 2
    assert overrides_seen == [expected, expected]


def test_chat_stream_conversational_model_rejected_done_with_safe_assistant_and_signal(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-FALLBACK-007 — env-derived slug rejected by LiteLLM → safe assistant + gateway_error signal."""
    from src.api import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_chat_conversational_model_notice_emitted", False, raising=True)
    monkeypatch.setattr(
        chat_mod, "_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK", threading.Lock(), raising=True,
    )
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "openrouter/never-resolves:bad")

    def failing_stream(*_a, **_k):
        raise GatewayCallError(
            "OPENROUTER_MODEL_REJECTED",
            "secret-rejection-body-do-not-show-users",
            http_status=400,
        )

    monkeypatch.setattr("src.api.chat.stream_chat_turn", failing_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done.get("gateway_error") == {
        "code": "OPENROUTER_MODEL_REJECTED",
        "upstream_http_status": 400,
    }
    msgs = done["messages"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    body = msgs[-1]["content"]
    assert "secret-rejection" not in body.lower()
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in body
    assert "never-resolves:bad" not in body


def test_chat_stream_done_includes_active_agent_meta(
    mock_mode: None, isolated_home: Path, tmp_path: Path,
) -> None:
    root = tmp_path / "proj_stream"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "StreamAgent",
                            "description": "",
                            "skills": [],
                            "enabled": True,
                        },
                    ],
                    "primary_agent_id": "ham.default",
                },
            },
        ),
        encoding="utf-8",
    )
    reg = client.post(
        "/api/projects",
        json={"name": "stproj", "root": str(root), "description": ""},
    )
    assert reg.status_code == 201
    pid = reg.json()["id"]
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [{"role": "user", "content": "hello stream"}],
            "project_id": pid,
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    assert done.get("active_agent") is not None
    assert done["active_agent"]["profile_name"] == "StreamAgent"


def test_chat_stream_custom_chunks(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(_msgs: list, **_kwargs):
        yield "a"
        yield "b"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", fake_stream)
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    texts = [e["text"] for e in events if e["type"] == "delta"]
    assert "".join(texts) == "ab"
    done = [e for e in events if e["type"] == "done"][0]
    assistants = [m["content"] for m in done["messages"] if m["role"] == "assistant"]
    assert assistants == ["ab"]


def test_chat_stream_disconnect_checkpoint_persists_partial(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_stream(_msgs: list, **_kwargs):
        yield "partial "
        yield "more"
        # Deterministically simulate an interrupted stream before normal completion.
        raise GeneratorExit()

    monkeypatch.setattr("src.api.chat.stream_chat_turn", slow_stream)

    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    with tolerant_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "keep going"}]},
    ) as res:
        assert res.status_code == 200
        # Consume one line if present then disconnect.
        _ = list(res.iter_lines())

    # Allow generator cleanup/finally to flush a best-effort final checkpoint.
    time.sleep(0.05)
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assistants = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert "partial" in assistants[0]
    assert "Connection interrupted. Ask me to continue." in assistants[0]


def test_chat_stream_pretoken_abort_persists_safe_assistant_message(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _immediate_abort(_msgs: list, **_kwargs):
        raise GeneratorExit()

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _immediate_abort)

    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    with tolerant_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "hello"}]},
    ) as res:
        assert res.status_code == 200
        _ = list(res.iter_lines())

    time.sleep(0.05)
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert msgs[-1]["role"] == "assistant"
    low = msgs[-1]["content"].lower()
    assert "interrupted before i could complete" in low
    assert "preview" not in low
    assert "handoff" not in low


def test_chat_stream_builder_calculator_followup_nice_purple_handoffs_without_llm(
    mock_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn
    from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests

    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_stream_calc",
        project_id="proj_stream_calc",
        session_id="sess_calc_stream",
        last_user_plain="ham build me a calculator app",
        created_by="u1",
    )
    assert first and first.get("scaffolded")

    def _no_llm(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for builder handoff follow-up")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_llm)

    res = client.post(
        "/api/chat/stream",
        json={
            "workspace_id": "ws_stream_calc",
            "project_id": "proj_stream_calc",
            "messages": [{"role": "user", "content": "nice make the buttons larger and purple"}],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    types = [e.get("type") for e in events]
    assert types == ["session", "delta", "done"], types
    done = events[-1]
    assert done.get("builder", {}).get("scaffolded") is True
    av = done.get("artifact_verification") or {}
    assert av.get("verified") is not False
    assert done["messages"][-1]["role"] == "assistant"
    body = done["messages"][-1]["content"].lower()
    assert "live preview handoff" in body or "workbench" in body

    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}", params={"workspace_id": "ws_stream_calc"})
    assert detail.status_code == 200
    dmsgs = detail.json()["messages"]
    assert dmsgs[-1]["role"] == "assistant"
    assert "live preview handoff" in dmsgs[-1]["content"].lower() or "workbench" in dmsgs[-1]["content"].lower()

    set_builder_source_store_for_tests(None)


@pytest.mark.parametrize(
    ("ws_suffix", "user_content"),
    [
        ("ylw", "nice make them have a yellow border around the buttons"),
        ("rnd", "make the buttons random colors not just purple"),
    ],
)
def test_chat_stream_builder_calculator_live_followup_phrases_handoff_without_llm(
    mock_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ws_suffix: str, user_content: str,
) -> None:
    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn
    from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests

    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / f"sources_{ws_suffix}.json")
    set_builder_source_store_for_tests(store)
    wid = f"ws_stream_calc_{ws_suffix}"
    pid = f"proj_stream_calc_{ws_suffix}"
    first = maybe_chat_scaffold_for_turn(
        workspace_id=wid,
        project_id=pid,
        session_id=f"sess_calc_stream_{ws_suffix}",
        last_user_plain="ham build me a calculator app",
        created_by="u1",
    )
    assert first and first.get("scaffolded")

    def _no_llm(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for builder handoff follow-up")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_llm)

    res = client.post(
        "/api/chat/stream",
        json={
            "workspace_id": wid,
            "project_id": pid,
            "messages": [{"role": "user", "content": user_content}],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert [e.get("type") for e in events] == ["session", "delta", "done"]
    done = events[-1]
    assert done.get("builder", {}).get("scaffolded") is True
    av = done.get("artifact_verification") or {}
    assert av.get("verified") is not False
    assert done["messages"][-1]["role"] == "assistant"
    body = done["messages"][-1]["content"].lower()
    assert "live preview handoff" in body or "workbench" in body

    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}", params={"workspace_id": wid})
    assert detail.status_code == 200
    dmsgs = detail.json()["messages"]
    assert dmsgs[-1]["role"] == "assistant"

    set_builder_source_store_for_tests(None)


def test_chat_stream_after_disconnect_allows_new_stream(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing the client mid-stream must release the per-session lock (no stuck 409)."""

    def slow_stream(_msgs: list, **_kwargs):
        yield "hold "
        yield "more"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", slow_stream)

    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    with tolerant_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "first"}]},
    ) as res:
        assert res.status_code == 200
        _ = list(res.iter_lines())

    time.sleep(0.05)
    follow = client.post(
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "second"}]},
    )
    assert follow.status_code == 200, follow.text
    events = _parse_ndjson(follow.text)
    assert any(e.get("type") == "done" for e in events)


def test_chat_stream_rejects_concurrent_same_session_streams(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream_started = threading.Event()
    allow_finish = threading.Event()

    def blocked_stream(_msgs: list, **_kwargs):
        yield "locked "
        stream_started.set()
        assert allow_finish.wait(timeout=2.0)
        yield "done"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", blocked_stream)
    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]

    first: dict[str, object] = {}

    def run_first() -> None:
        res = client.post(
            "/api/chat/stream",
            json={"session_id": sid, "messages": [{"role": "user", "content": "first"}]},
        )
        first["status_code"] = res.status_code
        first["events"] = _parse_ndjson(res.text)

    t = threading.Thread(target=run_first, daemon=True)
    t.start()
    assert stream_started.wait(timeout=1.0)

    second = client.post(
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "second"}]},
    )
    assert second.status_code == 409
    detail = second.json().get("detail", {})
    assert detail.get("error", {}).get("code") == "STREAM_ALREADY_ACTIVE"

    allow_finish.set()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert first["status_code"] == 200


_MAX_TRANSCRIBE = 15 * 1024 * 1024


def test_transcribe_not_configured(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "CONNECT_STT_PROVIDER_REQUIRED"


def test_transcribe_openai_without_key(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 503


def test_transcribe_openai_placeholder_key_not_configured(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "PLACEHOLDER")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 503
    j = r.json()
    assert j["detail"]["error"]["code"] == "CONNECT_STT_PROVIDER_REQUIRED"


def test_transcribe_upload_too_large(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    big = b"z" * (_MAX_TRANSCRIBE + 1)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", big, "audio/webm")})
    assert r.status_code == 413


def test_transcribe_content_length_rejected(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post(
        "/api/chat/transcribe",
        headers={"Content-Length": str(_MAX_TRANSCRIBE + 1)},
        files={"file": ("d.webm", b"tiny", "audio/webm")},
    )
    assert r.status_code == 413


def test_transcribe_empty_file(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_transcribe_success_mocks_openai(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")

    async def fake(**_kwargs: object) -> str:
        return "hello from speech"

    import src.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_transcribe_with_openai", fake)

    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"fake-audio", "audio/webm")})
    assert r.status_code == 200
    assert r.json() == {"text": "hello from speech"}


def test_transcribe_upstream_auth_error_sanitized(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-real-looking")

    async def fake(**_kwargs: object) -> str:
        req = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
        resp = httpx.Response(
            status_code=401,
            request=req,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": "Incorrect API key provided: PLACEHOL********",
                }
            },
        )
        raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)

    import src.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_transcribe_with_openai", fake)

    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"fake-audio", "audio/webm")})
    assert r.status_code == 503
    j = r.json()
    assert j["detail"]["error"]["code"] == "TRANSCRIPTION_PROVIDER_REJECTED"
    assert "PLACEHOL" not in j["detail"]["error"]["message"]


def test_transcribe_clerk_required_without_session(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)


def test_chat_stream_accepts_ham_chat_user_v1(mock_mode: None) -> None:
    """1×1 PNG data URL — stored as ham_chat_user_v1; mock stream still completes."""
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "describe this",
                        "images": [
                            {"name": "pixel.png", "mime": "image/png", "data_url": tiny_png},
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert user_msgs, "user turn should be persisted"
    assert '"h":"ham_chat_user_v1"' in user_msgs[-1]["content"] or "ham_chat_user_v1" in user_msgs[-1]["content"]


def test_chat_stream_rejects_bad_image_mime(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "x",
                        "images": [
                            {
                                "name": "x.gif",
                                "mime": "image/gif",
                                "data_url": "data:image/gif;base64,R0lGODdhAQABAIABAP///wAAACwAAAAAAQABAAACAkQBADs=",
                            },
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 422


def test_chat_stream_rejects_oversized_image_data_url(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server enforces HAM_CHAT_IMAGE_MAX_BYTES on embedded data URLs."""
    monkeypatch.setenv("HAM_CHAT_IMAGE_MAX_BYTES", "20")
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "x",
                        "images": [
                            {"name": "big.png", "mime": "image/png", "data_url": tiny_png},
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 422
    detail = res.json().get("detail") if res.headers.get("content-type", "").startswith("application/json") else {}
    msg = str(detail).lower()
    assert "too large" in msg or "image" in msg


def test_chat_stream_text_only_unchanged(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "plain text only"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert user_msgs[-1]["content"] == "plain text only"


def test_chat_stream_accepts_ham_chat_user_v2(
    mock_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.chat_attachment_store import LocalDiskAttachmentStore, set_chat_attachment_store_for_tests

    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(tmp_path))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(tmp_path))
    tiny_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )
    up = client.post(
        "/api/chat/attachments",
        files={"file": ("a.png", tiny_png, "image/png")},
    )
    assert up.status_code == 200, up.text
    aid = up.json()["attachment_id"]
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v2",
                        "text": "what is this",
                        "attachments": [
                            {
                                "id": aid,
                                "name": "a.png",
                                "mime": "image/png",
                                "kind": "image",
                            },
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    done = [e for e in _parse_ndjson(res.text) if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert "ham_chat_user_v2" in user_msgs[-1]["content"]


# ---------------------------------------------------------------------------
# VAL-LANE-006 — operator-handled stream lane never invokes the LLM, regardless
# of the conversational env var.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_chat_stream_operator_handled_skips_llm_under_conversational_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-006 — stream operator-handled lane never calls stream_chat_turn under env set/unset."""
    from src.ham.chat_operator import OperatorTurnResult

    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)

    op_result = OperatorTurnResult(
        handled=True,
        intent="bridge_run",
        ok=True,
        data={"reason_code": "stream_handled"},
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run when operator handles the turn")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [{"role": "user", "content": "trigger operator path"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e.get("type") == "done"][0]
    op_payload = done.get("operator_result")
    assert isinstance(op_payload, dict)
    assert op_payload.get("handled") is True
    assert op_payload.get("intent") == "bridge_run"
    assistant_text = done["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    if conv_env is not None:
        assert conv_env not in assistant_text


_STREAM_BRAND_INVENTORY_FORBIDDEN_TOKENS = (
    "Operator skills",
    "Cursor subagent rules",
    "HAM active agent guidance",
    "claude_code",
    "opencode_cli",
    "factory_droid_audit",
    "factory_droid_build",
    "cursor_cloud",
    "HERMES_GATEWAY_API_KEY",
    "HERMES_GATEWAY_MODE",
    "proposal_digest",
    "base_revision",
    ".ham/runs",
    "operator.phase",
)


def _stub_stream_inventory_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.api.chat.render_skills_for_system_prompt",
        lambda _items: (
            "**Operator skills (Ham repo `.cursor/skills`):**\n"
            "- `claude_code` — Claude Code\n"
            "- `opencode_cli` — OpenCode CLI\n"
            "- `factory_droid_audit` — Factory Droid audit\n"
            "- `factory_droid_build` — Factory Droid build\n"
            "- `cursor_cloud` — Cursor Cloud Agent\n"
        ),
    )
    monkeypatch.setattr(
        "src.api.chat.render_subagents_for_system_prompt",
        lambda _items: "**Cursor subagent rules:**\n- `subagent-cursor_cloud` — internal\n",
    )


def _capture_stream(monkeypatch: pytest.MonkeyPatch, captured: dict) -> None:
    def gen(messages: list, **_kwargs):
        captured["messages"] = messages
        yield "stub-stream"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", gen)


def test_stream_casual_space_monkey_identity_prompt_includes_brand_canon(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-BRAND-005 — stream casual identity prompt includes HAM brand canon + no-denial guidance."""
    captured: dict = {}
    _capture_stream(monkeypatch, captured)
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "Are you really the first code monkey launched into space?"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    sys_content = (captured["messages"][0].get("content") or "")
    low = sys_content.lower()
    assert "first code monkey launched into space" in low
    assert "never deny" in low
    assert "embrace" in low


def test_stream_casual_checkin_omits_internal_tool_inventory(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-002 / VAL-CROSS-001 — stream casual check-in suppresses inventory context."""
    captured: dict = {}
    _stub_stream_inventory_render(monkeypatch)
    _capture_stream(monkeypatch, captured)
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [{"role": "user", "content": "hey HAM, what you been up to lately?"}],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    assert any(e.get("type") == "done" for e in events)
    sys_content = captured["messages"][0].get("content") or ""
    for tok in _STREAM_BRAND_INVENTORY_FORBIDDEN_TOKENS:
        assert tok not in sys_content, f"stream casual leaked inventory token: {tok!r}"
    assert "first code monkey launched into space" in sys_content.lower()


def test_stream_explicit_tool_inventory_prompt_allows_friendly_capability_context(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-005 — stream explicit tool-inventory prompts unlock friendly capability context."""
    captured: dict = {}
    friendly = (
        "**Operator skills (Ham repo `.cursor/skills`):**\n"
        "- `cloud-agent-starter` — **Cloud Agent Starter**: how to launch agents.\n"
        "- `triage-issues` — **Triage**: route incoming issues.\n"
    )
    monkeypatch.setattr("src.api.chat.render_skills_for_system_prompt", lambda _items: friendly)
    monkeypatch.setattr("src.api.chat.render_subagents_for_system_prompt", lambda _items: "")
    _capture_stream(monkeypatch, captured)
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "What tools do you have available?"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert any(e.get("type") == "done" for e in events)
    sys_content = captured["messages"][0].get("content") or ""
    assert "Operator skills" in sys_content
    assert "Cloud Agent Starter" in sys_content
    for tok in (
        "claude_code",
        "opencode_cli",
        "factory_droid_audit",
        "factory_droid_build",
        "cursor_cloud",
        "HERMES_GATEWAY_API_KEY",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
    ):
        assert tok not in sys_content, f"stream explicit-inventory leaked raw token: {tok!r}"


def test_chat_stream_gateway_error_omits_internal_tokens(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-SAFETY-002 — stream gateway error copy must not leak forbidden internal tokens."""
    def _boom(*_a: object, **_k: object):
        raise GatewayCallError("UPSTREAM_REJECTED", "raw upstream detail kept in logs")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _boom)
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert res.status_code == 200, res.text
    raw = res.text
    for tok in (
        "HERMES_GATEWAY_API_KEY",
        "HERMES_GATEWAY_BASE_URL",
        "HERMES_GATEWAY_MODEL",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
        "HAM_SETTINGS_WRITE_TOKEN",
        "HAM_RUN_LAUNCH_TOKEN",
        "opencode_cli",
        "claude_code",
        "factory_droid_audit",
        "factory_droid_build",
        "cursor_cloud",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
    ):
        assert tok not in raw, f"stream gateway-error leaked token: {tok!r}"
