"""HAM /api/chat proxy and session behavior (gateway mocked)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import chat as chat_mod
from src.api.server import app
from src.bridge.contracts import (
    BrowserAction,
    BrowserIntent,
    BrowserPolicySpec,
    BrowserResult,
    BrowserRunStatus,
    BrowserStepSpec,
    PolicyDecision,
)
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_root_is_not_404_json() -> None:
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data.get("service") == "HAM API"
    assert data.get("status") == "/api/status"


def test_post_chat_prepends_system_prompt_for_llm(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list] = {}

    def capture(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub-assistant"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", capture)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200, res.text
    msgs = captured.get("messages") or []
    assert msgs and msgs[0].get("role") == "system"
    assert "Ham" in (msgs[0].get("content") or "")
    assert msgs[1] == {"role": "user", "content": "hi"}
    # Client-visible transcript has no system row
    body = res.json()["messages"]
    assert all(m["role"] != "system" for m in body)


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_post_chat_creates_session_and_assistant_roundtrip(mock_mode: None) -> None:
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["session_id"]
    assert len(data["messages"]) == 2
    assert data["messages"][0] == {"role": "user", "content": "hello"}
    assert data["messages"][1]["role"] == "assistant"
    assert "Mock assistant reply" in data["messages"][1]["content"]


def test_post_chat_continues_session(mock_mode: None) -> None:
    r1 = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "first"}]},
    )
    assert r1.status_code == 200
    sid = r1.json()["session_id"]

    r2 = client.post(
        "/api/chat",
        json={
            "session_id": sid,
            "messages": [{"role": "user", "content": "second"}],
        },
    )
    assert r2.status_code == 200
    msgs = r2.json()["messages"]
    assert len(msgs) == 4
    assert msgs[0]["content"] == "first"
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["content"] == "second"
    assert msgs[3]["role"] == "assistant"


def test_post_chat_unknown_session() -> None:
    res = client.post(
        "/api/chat",
        json={
            "session_id": "00000000-0000-4000-8000-000000000001",
            "messages": [{"role": "user", "content": "x"}],
        },
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_post_chat_validation_empty_messages(mock_mode: None) -> None:
    res = client.post("/api/chat", json={"messages": []})
    assert res.status_code == 422


def test_post_chat_gateway_error_mapped(mock_mode: None) -> None:
    with patch(
        "src.api.chat.complete_chat_turn",
        side_effect=GatewayCallError("UPSTREAM_REJECTED", "gateway said no"),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail["error"]["code"] == "UPSTREAM_REJECTED"
    assert "gateway" in detail["error"]["message"].lower()


def test_post_chat_invalid_request_from_gateway(mock_mode: None) -> None:
    with patch(
        "src.api.chat.complete_chat_turn",
        side_effect=GatewayCallError("INVALID_REQUEST", "empty history"),
    ):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert res.status_code == 400


def test_post_chat_no_project_id_skips_active_agent_guidance(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list] = {}

    def capture(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", capture)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200
    assert "HAM active agent guidance" not in (captured["messages"][0].get("content") or "")
    assert res.json().get("active_agent") is None


def test_post_chat_project_id_injects_guidance_and_meta(
    mock_mode: None, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj_chat"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "BenchProfile",
                            "description": "For tests",
                            "skills": ["bundled.apple.apple-notes"],
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
        json={"name": "chatproj", "root": str(root), "description": ""},
    )
    assert reg.status_code == 201, reg.text
    pid = reg.json()["id"]

    captured: dict[str, list] = {}

    def capture(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", capture)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "project_id": pid,
        },
    )
    assert res.status_code == 200
    sys_content = captured["messages"][0].get("content") or ""
    assert "HAM active agent guidance" in sys_content
    assert "BenchProfile" in sys_content
    assert "context only" in sys_content.lower() or "Context only" in sys_content
    body = res.json()
    aa = body.get("active_agent")
    assert aa is not None
    assert aa["profile_id"] == "ham.default"
    assert aa["profile_name"] == "BenchProfile"
    assert aa["skills_requested"] == 1
    assert aa["skills_resolved"] == 1
    assert aa["skills_skipped_catalog_miss"] == 0
    assert aa["guidance_applied"] is True


def test_post_chat_include_active_agent_guidance_false(
    mock_mode: None, isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj_chat2"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "X",
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
        json={"name": "p2", "root": str(root), "description": ""},
    )
    pid = reg.json()["id"]
    captured: dict[str, list] = {}

    def capture(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", capture)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "project_id": pid,
            "include_active_agent_guidance": False,
        },
    )
    assert res.status_code == 200
    assert "HAM active agent guidance" not in (captured["messages"][0].get("content") or "")
    assert res.json().get("active_agent") is None


def test_phase3_browser_bridge_skips_when_no_url() -> None:
    body = chat_mod.ChatRequest(messages=[chat_mod.ChatMessageIn(role="user", content="hello world")])
    mode = {
        "requested_mode": "browser",
        "selected_mode": "browser",
        "auto_selected": True,
        "environment": "web",
        "browser_available": True,
        "local_machine_available": False,
        "browser_adapter": "playwright",
        "reason": "test",
    }
    out = chat_mod._apply_browser_bridge_for_turn(
        execution_mode=mode,
        body=body,
        last_user_plain="hello world",
    )
    assert out["selected_mode"] == "browser"
    assert out["browser_bridge"]["status"] == "skipped"


def test_phase3_browser_bridge_escalates_to_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    body = chat_mod.ChatRequest(messages=[chat_mod.ChatMessageIn(role="user", content="open https://example.com")])
    mode = {
        "requested_mode": "auto",
        "selected_mode": "browser",
        "auto_selected": True,
        "environment": "desktop",
        "browser_available": True,
        "local_machine_available": True,
        "browser_adapter": "playwright",
        "reason": "test",
    }
    intent = BrowserIntent(
        intent_id="i1",
        request_id="r1",
        run_id="run1",
        start_url="https://example.com",
        steps=[
            BrowserStepSpec(step_id="s1", action=BrowserAction.NAVIGATE, args={"url": "https://example.com"}),
        ],
        policy=BrowserPolicySpec(
            max_steps=1,
            step_timeout_ms=1000,
            max_dom_chars=256,
            max_console_chars=128,
            max_network_events=1,
        ),
        reason="test",
    )
    monkeypatch.setattr(chat_mod, "_build_browser_intent_for_turn", lambda **_kw: intent)
    monkeypatch.setattr(chat_mod, "_build_browser_assembly_for_turn", lambda *_a, **_kw: object())
    monkeypatch.setattr(
        chat_mod,
        "run_browser_v0",
        lambda *_a, **_kw: BrowserResult(
            intent_id="i1",
            request_id="r1",
            run_id="run1",
            status=BrowserRunStatus.BLOCKED,
            policy_decision=PolicyDecision(accepted=True, reasons=[], policy_version="browser-v0"),
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:01+00:00",
            duration_ms=1,
            steps=[],
            summary="blocked",
        ),
    )
    out = chat_mod._apply_browser_bridge_for_turn(
        execution_mode=mode,
        body=body,
        last_user_plain="open https://example.com",
    )
    assert out["selected_mode"] == "machine"
    assert out["escalated_from"] == "browser"
    assert out["escalation_trigger"] == "blocked"


def test_phase3_browser_bridge_escalates_to_machine_on_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    body = chat_mod.ChatRequest(messages=[chat_mod.ChatMessageIn(role="user", content="open https://example.com")])
    mode = {
        "requested_mode": "auto",
        "selected_mode": "browser",
        "auto_selected": True,
        "environment": "desktop",
        "browser_available": True,
        "local_machine_available": True,
        "browser_adapter": "playwright",
        "reason": "test",
    }
    intent = BrowserIntent(
        intent_id="i2",
        request_id="r2",
        run_id="run2",
        start_url="https://example.com",
        steps=[
            BrowserStepSpec(step_id="s1", action=BrowserAction.NAVIGATE, args={"url": "https://example.com"}),
        ],
        policy=BrowserPolicySpec(
            max_steps=1,
            step_timeout_ms=1000,
            max_dom_chars=256,
            max_console_chars=128,
            max_network_events=1,
        ),
        reason="test",
    )
    monkeypatch.setattr(chat_mod, "_build_browser_intent_for_turn", lambda **_kw: intent)
    monkeypatch.setattr(chat_mod, "_build_browser_assembly_for_turn", lambda *_a, **_kw: object())
    monkeypatch.setattr(
        chat_mod,
        "run_browser_v0",
        lambda *_a, **_kw: BrowserResult(
            intent_id="i2",
            request_id="r2",
            run_id="run2",
            status=BrowserRunStatus.PARTIAL,
            policy_decision=PolicyDecision(accepted=True, reasons=[], policy_version="browser-v0"),
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:01+00:00",
            duration_ms=1,
            steps=[],
            summary="partial",
        ),
    )
    out = chat_mod._apply_browser_bridge_for_turn(
        execution_mode=mode,
        body=body,
        last_user_plain="open https://example.com",
    )
    assert out["selected_mode"] == "machine"
    assert out["escalated_from"] == "browser"
    assert out["escalation_trigger"] == "partial"
