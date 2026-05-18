"""Cross-area conversational-lane invariants (VAL-CROSS-001..013, VAL-SAFETY-005).

All scenarios run with the FastAPI TestClient and either mock mode, openrouter mode
with `litellm.completion` mocked, or http mode with `httpx.Client` mocked.
No live LLM / gateway calls; all env state is set via monkeypatch.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import chat as chat_mod
from src.api.server import app
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


CONV_SLUG = "openrouter/anthropic/claude-3.5-haiku"
OR_TEST_KEY = "sk-or-v1-hamtests-only-fake-key-000000000"


@pytest.fixture(autouse=True)
def _reset_conversational_notice_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the one-time notice flag/lock between tests."""
    monkeypatch.setattr(
        chat_mod, "_chat_conversational_model_notice_emitted", False, raising=True
    )
    monkeypatch.setattr(
        chat_mod,
        "_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK",
        threading.Lock(),
        raising=True,
    )


@pytest.fixture
def or_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", OR_TEST_KEY)
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_MODEL", raising=False)
    monkeypatch.delenv("HAM_CHAT_PREMIUM_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _stub_litellm_chunk(text: str) -> Any:
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = text
    return chunk


def _stub_completion_factory(seen: list[dict[str, Any]], reply: str = "ok"):
    def _stub(*_args: Any, **kwargs: Any):
        seen.append(dict(kwargs))
        yield _stub_litellm_chunk(reply)

    return _stub


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_val_cross_001_env_toggle_roundtrip_preserves_unset_behavior(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-001 — unset → set → unset; unset baseline is byte-identical at both ends."""
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o-mini")

    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        r1 = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "unset turn 1"}]},
        )
    assert r1.status_code == 200, r1.text
    first_model = seen[0].get("model")
    assert first_model == "openrouter/openai/gpt-4o-mini"

    seen.clear()
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        r2 = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "set turn"}]},
        )
    assert r2.status_code == 200, r2.text
    assert seen[0].get("model") == CONV_SLUG

    seen.clear()
    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        r3 = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "unset turn 2"}]},
        )
    assert r3.status_code == 200, r3.text
    assert seen[0].get("model") == first_model


def test_val_cross_002_explicit_model_id_wins_across_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CROSS-002 — explicit body.model_id always wins (mock 422; openrouter wins over env)."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    res_mock = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "model_id": "openrouter:default",
        },
    )
    assert res_mock.status_code == 422, res_mock.text
    assert (
        res_mock.json()["detail"]["error"]["code"]
        == "MODEL_SELECTION_REQUIRES_OPENROUTER"
    )

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", OR_TEST_KEY)
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        res_or = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "openrouter:default",
            },
        )
    assert res_or.status_code == 200, res_or.text
    assert seen and seen[0].get("model") != CONV_SLUG
    assert seen[0].get("model") == "openrouter/minimax/minimax-m2.5:free"


def test_val_cross_003_multi_turn_stability_with_env_set(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-003 — env slug is reused on turn 2 of a two-turn conversation."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    seen: list[dict[str, Any]] = []
    with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
        r1 = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "turn one"}]},
        )
        assert r1.status_code == 200, r1.text
        sid = r1.json()["session_id"]

        r2 = client.post(
            "/api/chat",
            json={
                "session_id": sid,
                "messages": [{"role": "user", "content": "turn two"}],
            },
        )
        assert r2.status_code == 200, r2.text
    assert len(seen) == 2
    assert seen[0].get("model") == CONV_SLUG
    assert seen[1].get("model") == CONV_SLUG


def test_val_cross_004_builder_stream_early_handoff_bypasses_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-004 — build_or_create + scaffolded=True stream short-circuits with no LLM."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)

    def _builder_hook(**_kwargs):
        return (
            "I'll create the initial project source and prepare the Workbench.\n\n",
            {"builder_intent": "build_or_create", "scaffolded": True},
        )

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for early-handoff lane")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a Tetris clone"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assistant = done["messages"][-1]["content"]
    assert "prepare the Workbench" in assistant
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant
    assert CONV_SLUG not in assistant


def test_val_cross_005_builder_rest_env_mix_preserves_ack_dedupe(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-005 — REST build_or_create still calls LLM (not the ack template) once, no double-emit."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    builder_prefix = "I'll create the initial project source and prepare the Workbench.\n\n"

    def _builder_hook(**_kwargs):
        return (
            builder_prefix,
            {"builder_intent": "build_or_create", "scaffolded": True},
        )

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    captured: dict[str, Any] = {}

    def _stub_complete(_messages, **kwargs) -> str:
        captured.update(kwargs)
        return "Builder reply body."

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _stub_complete)

    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "build me a Tetris clone"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    builder_meta = body.get("builder") or {}
    assert builder_meta.get("builder_intent") == "build_or_create"
    assert builder_meta.get("acknowledgement_template") == builder_prefix
    assistant_visible = body["messages"][-1]["content"]
    assert assistant_visible == "Builder reply body."
    assert assistant_visible.count(builder_prefix) == 0


def test_val_cross_006_operator_handled_turn_bypasses_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-006 — operator-handled lane never invokes the LLM under env set."""
    from src.ham.chat_operator import OperatorTurnResult

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    op_result = OperatorTurnResult(
        handled=True,
        intent="bridge_run",
        ok=True,
        data={"reason_code": "test_handled"},
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError("complete_chat_turn must not run when operator handles the turn")

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "trigger operator path"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    op_payload = body.get("operator_result")
    assert isinstance(op_payload, dict)
    assert op_payload.get("handled") is True
    assistant_text = body["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert CONV_SLUG not in assistant_text


def test_val_cross_007_http_fallback_unaffected_by_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CROSS-007 — HTTP 429 → HAM_CHAT_FALLBACK_MODEL retry; conv env never reaches HTTP body."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "primary-m")
    monkeypatch.setenv("HAM_CHAT_FALLBACK_MODEL", "fallback-m")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)

    captured_models: list[str] = []
    responses_idx = {"i": 0}

    def _sse(text: str) -> str:
        payload = json.dumps({"choices": [{"delta": {"content": text}}]})
        return f"data: {payload}"

    sequence = [
        (429, []),
        (200, [_sse("fb-ok"), "data: [DONE]"]),
    ]

    class _FakeResp:
        def __init__(self, status: int, lines: list[str]) -> None:
            self.status_code = status
            self._lines = lines

        def __enter__(self) -> "_FakeResp":
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def iter_lines(self) -> list[str]:
            return self._lines

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def stream(
            self,
            _method: str,
            _url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
        ) -> _FakeResp:
            assert json is not None
            captured_models.append(str(json["model"]))
            i = responses_idx["i"]
            responses_idx["i"] += 1
            status, lines = sequence[i]
            return _FakeResp(status, lines)

    with patch(
        "src.integrations.nous_gateway_client.httpx.Client",
        return_value=_FakeClient(),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 200, res.text
    assert captured_models == ["primary-m", "fallback-m"]
    assert CONV_SLUG not in captured_models
    assert "anthropic/claude-3.5-haiku" not in captured_models


def test_val_cross_008_vision_text_fallback_reuses_env_slug(
    or_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-008 — vision text-fallback retry reuses the same env slug."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_VISION_UPSTREAM_TEXT_FALLBACK", "1")

    overrides_seen: list[str | None] = []
    call_count = {"n": 0}

    def fake_stream(_messages, **kwargs):
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
    assert overrides_seen and overrides_seen[0] == CONV_SLUG
    if len(overrides_seen) >= 2:
        assert overrides_seen[1] == CONV_SLUG


def test_val_cross_009_startup_notice_emitted_once_per_process(
    or_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-CROSS-009 — multiple chat requests do not produce duplicate notice log lines."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    seen: list[dict[str, Any]] = []
    with caplog.at_level(logging.INFO, logger=chat_mod._LOG.name):
        with patch("litellm.completion", side_effect=_stub_completion_factory(seen)):
            for _ in range(3):
                res = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                )
                assert res.status_code == 200, res.text
    notice_records = [
        r for r in caplog.records if "chat_conversational_model" in r.getMessage()
    ]
    assert len(notice_records) == 1, [r.getMessage() for r in notice_records]


def test_val_cross_010_ui_actions_shape_preserved_under_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-010 — `actions` array byte-identical under env-unset vs env-set."""
    def _fixture_turn(_msgs: list, **_kwargs) -> str:
        return (
            "Opening settings.\n"
            'HAM_UI_ACTIONS_JSON: {"actions":[{"type":"toast","level":"success","message":"ok"},'
            '{"type":"navigate","path":"/workspace/settings"}]}'
        )

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _fixture_turn)

    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    baseline = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "open settings"}],
            "enable_ui_actions": True,
        },
    )
    assert baseline.status_code == 200, baseline.text
    baseline_actions = baseline.json()["actions"]

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    env_set = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "open settings"}],
            "enable_ui_actions": True,
        },
    )
    assert env_set.status_code == 200, env_set.text
    env_set_actions = env_set.json()["actions"]

    assert baseline_actions == env_set_actions
    assert baseline_actions, "fixture should produce at least one action"


def test_val_cross_011_agent_router_turn_bypasses_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VAL-CROSS-011 — operator-disabled agent-router turn never streams LLM under env set."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")

    def _no_stream(*_a: object, **_k: object):
        raise AssertionError("stream_chat_turn must not run for agent-router short-circuit")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Launch a Cursor Cloud Agent for repo Unmapped-Org/unmapped-repo on branch main. Task: update docs only.",
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert [e for e in events if e["type"] == "delta"] == []
    done = [e for e in events if e["type"] == "done"][0]
    op_result = done.get("operator_result") or {}
    assert op_result.get("handled") is True
    assert op_result.get("intent") == "cursor_agent_launch"
    assistant_text = done["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert CONV_SLUG not in assistant_text


def _clarification_hook(**_kwargs):
    return (
        "Which area should I change?\n\n",
        {
            "builder_intent": "answer_question",
            "builder_clarification": True,
            "builder_action_decision": {"kind": "ask_clarification", "reason": "vague"},
        },
    )


def _verification_failed_hook(**_kwargs):
    return (
        "Verification did not pass.\n\n",
        {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "artifact_verification_failed": True,
            "artifact_verification": {"verified": False, "reason": "missing"},
        },
    )


def _edit_worker_blocked_hook(**_kwargs):
    return (
        "Structured builder edits require Hermes.\n\n",
        {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": "hermes_gateway", "blocked_reason": "gateway_mock"},
        },
    )


@pytest.mark.parametrize(
    ("lane_id", "hook", "meta_key"),
    [
        ("clarification", _clarification_hook, "builder_clarification"),
        ("verification_failed", _verification_failed_hook, "artifact_verification_failed"),
        ("edit_worker_blocked", _edit_worker_blocked_hook, "builder_edit_worker_blocked"),
    ],
)
def test_val_cross_012_short_circuit_builder_lanes_ignore_env(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    lane_id: str,
    hook: object,
    meta_key: str,
) -> None:
    """VAL-CROSS-012 — short-circuit builder lanes emit pre-formed text with no LLM under env set."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", hook)

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError(f"complete_chat_turn must not run for short-circuit lane {lane_id}")

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": f"trigger {lane_id}"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    builder_meta = body.get("builder") or {}
    assert builder_meta.get(meta_key) is True
    assistant_text = body["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert CONV_SLUG not in assistant_text


def test_val_cross_013_active_agent_guidance_unchanged_under_env(
    mock_mode: None,
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CROSS-013 — Active Agent guidance block and `active_agent` meta unchanged under env."""
    root = tmp_path / "proj_cross013"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "CrossAgent",
                            "description": "Cross-area lane test",
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
        json={"name": "crossproj013", "root": str(root), "description": ""},
    )
    assert reg.status_code == 201, reg.text
    pid = reg.json()["id"]

    captured: dict[str, list] = {}

    def _capture(messages: list, **_kwargs) -> str:
        captured["messages"] = list(messages)
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _capture)

    monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    res_unset = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "project_id": pid,
        },
    )
    assert res_unset.status_code == 200, res_unset.text
    sys_prompt_unset = (captured.get("messages") or [{}])[0].get("content") or ""
    meta_unset = res_unset.json().get("active_agent")
    assert "HAM active agent guidance" in sys_prompt_unset
    assert meta_unset is not None

    captured.clear()
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    res_set = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "project_id": pid,
        },
    )
    assert res_set.status_code == 200, res_set.text
    sys_prompt_set = (captured.get("messages") or [{}])[0].get("content") or ""
    meta_set = res_set.json().get("active_agent")

    assert sys_prompt_unset == sys_prompt_set
    assert meta_unset == meta_set
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in sys_prompt_set


def test_conversational_lane_startup_notice_no_secret_leak(
    or_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-SAFETY-005 — startup notice never embeds Bearer / sk-or- / BYOK plaintext."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", CONV_SLUG)
    monkeypatch.setenv("HERMES_GATEWAY_API_KEY", "sk-bearer-xyz-not-in-logs")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-deadbeef-not-in-logs")
    monkeypatch.setenv(
        "HAM_BYOK_FAKE_PLAINTEXT_KEY",
        "supersecret_byok_plaintext_key_3456789abcdef0",
    )

    with caplog.at_level(logging.INFO, logger=chat_mod._LOG.name):
        chat_mod._chat_conversational_model_default()
        chat_mod._chat_conversational_model_default()

    records = [
        r for r in caplog.records if "chat_conversational_model" in r.getMessage()
    ]
    assert len(records) == 1
    record = records[0]
    payload = (
        record.getMessage()
        + " "
        + str(getattr(record, "chat_conversational_model", ""))
    )
    assert "sk-bearer-xyz-not-in-logs" not in payload
    assert "sk-or-test-deadbeef-not-in-logs" not in payload
    assert "supersecret_byok_plaintext_key_3456789abcdef0" not in payload
    assert "Bearer " not in payload
    assert not re.search(r"sk-or-[A-Za-z0-9_-]{8,}", payload)
    assert not re.search(r"sk-[A-Za-z0-9_-]{20,}", payload)
