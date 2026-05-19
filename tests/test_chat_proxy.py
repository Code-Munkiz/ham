"""HAM /api/chat proxy and session behavior (gateway mocked)."""
from __future__ import annotations

import json
import uuid
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
from src.ham.clerk_auth import HamActor
from src.ham.chat_attachment_store import (
    AttachmentRecord,
    LocalDiskAttachmentStore,
    set_chat_attachment_store_for_tests,
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


def test_post_chat_build_intent_bypasses_operator_fallback(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "build me a game like Tetris"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("operator_result") is None
    builder = body.get("builder") or {}
    assert builder.get("builder_intent") == "build_or_create"
    assert builder.get("acknowledgement_template") == (
        "I'll create the initial project source and prepare the Workbench.\n\n"
    )
    visible = body["messages"][-1]["content"]
    assert "prepare the Workbench" not in visible


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_post_chat_artifact_verification_failure_skips_llm_and_is_final_message(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-004 — REST verification-failure lane skips LLM under env set/unset."""
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
                    "skipped": False,
                    "status": "failed",
                    "requested_checks": ["yellow_digit_border"],
                    "passed_checks": [],
                    "failed_checks": ["yellow_digit_border"],
                    "reason": "missing yellow border styling on digit keys",
                },
            },
        )

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError("complete_chat_turn must not run when artifact verification failed")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "add yellow border"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    av = body.get("artifact_verification")
    assert isinstance(av, dict)
    assert av.get("verified") is False
    assert body["messages"][-1]["content"] == honest
    assert "I've generated" not in body["messages"][-1]["content"]
    assert "live preview handoff" not in body["messages"][-1]["content"]


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_post_chat_builder_edit_worker_blocked_skips_llm_and_is_final_message(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-005 — REST edit-worker-blocked lane skips LLM under env set/unset."""
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

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError("complete_chat_turn must not run when builder edit worker blocked")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "change + and - buttons"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["messages"][-1]["content"] == honest
    b = body.get("builder") or {}
    assert b.get("builder_edit_worker_blocked") is True
    assert (b.get("builder_edit_worker") or {}).get("blocked_reason") == "gateway_mock_or_unconfigured"
    low = body["messages"][-1]["content"].lower()
    assert "updated" not in low
    assert "preview refreshed" not in low
    assert "I've generated" not in body["messages"][-1]["content"]
    assert "live preview handoff" not in body["messages"][-1]["content"]


@pytest.mark.parametrize("conv_env", [None, "openrouter/sentinel-conv:free"])
def test_post_chat_builder_clarification_skips_llm_and_is_final_message(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-003 — REST builder clarification lane skips LLM under env set/unset."""
    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)
    clar = "Which area should I change—the layout, the logic, or copy?\n\n"

    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            clar,
            {
                "builder_intent": "answer_question",
                "builder_clarification": True,
                "builder_action_decision": {"kind": "ask_clarification", "reason": "vague_improvement"},
            },
        )

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError("complete_chat_turn must not run for builder clarification")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "clean this up"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["messages"][-1]["content"] == clar.strip()
    low = body["messages"][-1]["content"].lower()
    assert "updated" not in low
    assert "preview refreshed" not in low
    assert "generated project files" not in low
    assert "live preview handoff" not in low


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


def test_chat_session_create_and_append_turns() -> None:
    created = client.post("/api/chat/sessions")
    assert created.status_code == 200, created.text
    sid = created.json()["session_id"]
    assert sid

    appended = client.post(
        f"/api/chat/sessions/{sid}/turns",
        json={
            "turns": [
                {"role": "user", "content": "open https://example.com"},
                {"role": "assistant", "content": "Opening that locally."},
            ]
        },
    )
    assert appended.status_code == 200, appended.text
    body = appended.json()
    assert body["session_id"] == sid
    assert len(body["messages"]) == 2
    assert body["messages"][0] == {"role": "user", "content": "open https://example.com"}
    assert body["messages"][1] == {"role": "assistant", "content": "Opening that locally."}

    fetched = client.get(f"/api/chat/sessions/{sid}")
    assert fetched.status_code == 200, fetched.text
    f = fetched.json()
    assert f["session_id"] == sid
    assert len(f["messages"]) == 2


def test_chat_session_delete_removes_turns() -> None:
    created = client.post("/api/chat/sessions")
    assert created.status_code == 200
    sid = created.json()["session_id"]
    appended = client.post(
        f"/api/chat/sessions/{sid}/turns",
        json={"turns": [{"role": "user", "content": "tmp"}]},
    )
    assert appended.status_code == 200
    deleted = client.delete(f"/api/chat/sessions/{sid}")
    assert deleted.status_code == 204
    fetched = client.get(f"/api/chat/sessions/{sid}")
    assert fetched.status_code == 404
    assert fetched.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_chat_session_delete_unknown_returns_404() -> None:
    missing_id = str(uuid.uuid4())
    deleted = client.delete(f"/api/chat/sessions/{missing_id}")
    assert deleted.status_code == 404
    assert deleted.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_chat_session_append_turns_unknown_session() -> None:
    res = client.post(
        "/api/chat/sessions/00000000-0000-4000-8000-000000000001/turns",
        json={"turns": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


def test_chat_session_append_turns_rejects_empty_content() -> None:
    created = client.post("/api/chat/sessions")
    sid = created.json()["session_id"]
    res = client.post(
        f"/api/chat/sessions/{sid}/turns",
        json={"turns": [{"role": "assistant", "content": "   "}]},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "INVALID_MESSAGE"


def test_append_turns_v2_rejects_foreign_user_attachment_with_clerk(
    tmp_path: Path,
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ham_chat_user_v2 appended via /turns must re-validate attachment ownership (Clerk on)."""
    _ = mock_mode
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "good.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")

    att_dir = tmp_path / "att"
    att_dir.mkdir()
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    victim = HamActor(
        user_id="user_victim",
        org_id="o1",
        session_id="s1",
        email="v@good.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )
    attacker = HamActor(
        user_id="user_attacker",
        org_id="o1",
        session_id="s2",
        email="a@good.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )

    def _jwt_actor(token: str) -> HamActor:
        t = (token or "").strip()
        if t.startswith("victim"):
            return victim
        return attacker

    with patch("src.api.clerk_gate.verify_clerk_session_jwt", side_effect=_jwt_actor):
        up = client.post(
            "/api/chat/attachments",
            files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"x" * 20, "image/png")},
            headers={"Authorization": "Bearer victim.jwt"},
        )
        assert up.status_code == 200, up.text
        aid = up.json()["attachment_id"]

        created = client.post("/api/chat/sessions", headers={"Authorization": "Bearer attacker.jwt"})
        assert created.status_code == 200
        sid = created.json()["session_id"]

        v2 = {
            "h": "ham_chat_user_v2",
            "text": "stolen",
            "attachments": [
                {"id": aid, "name": "x.png", "mime": "image/png", "kind": "image"},
            ],
        }
        res = client.post(
            f"/api/chat/sessions/{sid}/turns",
            headers={"Authorization": "Bearer attacker.jwt"},
            json={"turns": [{"role": "user", "content": json.dumps(v2)}]},
        )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "INVALID_USER_MESSAGE"


def test_post_chat_validation_empty_messages(mock_mode: None) -> None:
    res = client.post("/api/chat", json={"messages": []})
    assert res.status_code == 422


def test_post_chat_rejects_multiple_messages_in_one_request(mock_mode: None) -> None:
    res = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
            ],
        },
    )
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


# ---------------------------------------------------------------------------
# Conversational env-isolation: operator-handled / structured-actions /
# non-conversational lanes (VAL-LANE-006 / VAL-LANE-012 / VAL-SAFETY-010)
# ---------------------------------------------------------------------------


_CONV_SENTINEL = "openrouter/sentinel-conv:free"


@pytest.mark.parametrize("conv_env", [None, _CONV_SENTINEL])
def test_post_chat_operator_handled_skips_llm_under_conversational_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, conv_env: str | None,
) -> None:
    """VAL-LANE-006 — operator-handled lane never invokes the LLM, regardless of conv env."""
    from src.ham.chat_operator import OperatorTurnResult

    if conv_env is None:
        monkeypatch.delenv("HAM_CHAT_CONVERSATIONAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", conv_env)

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
    data = res.json()
    op_payload = data.get("operator_result")
    assert isinstance(op_payload, dict)
    assert op_payload.get("handled") is True
    assert op_payload.get("intent") == "bridge_run"
    assistant_text = data["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert _CONV_SENTINEL not in assistant_text


def test_post_chat_structured_actions_shape_invariant_under_conversational_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-LANE-012 — structured `actions` array is byte-identical under env-unset and env-set."""

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
        json={"messages": [{"role": "user", "content": "open settings"}], "enable_ui_actions": True},
    )
    assert baseline.status_code == 200, baseline.text
    baseline_actions = baseline.json()["actions"]

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    env_set = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "open settings"}], "enable_ui_actions": True},
    )
    assert env_set.status_code == 200, env_set.text
    env_set_actions = env_set.json()["actions"]

    assert baseline_actions == env_set_actions
    assert baseline_actions, "fixture should produce at least one action"


def _build_or_create_hook(**_kwargs):  # type: ignore[no-untyped-def]
    return (
        "I'll create the initial project source and prepare the Workbench.\n\n",
        {"builder_intent": "build_or_create", "scaffolded": True},
    )


def _clarification_hook(**_kwargs):  # type: ignore[no-untyped-def]
    return (
        "Which area should I change?\n\n",
        {
            "builder_intent": "answer_question",
            "builder_clarification": True,
            "builder_action_decision": {"kind": "ask_clarification", "reason": "vague_improvement"},
        },
    )


def _verification_failed_hook(**_kwargs):  # type: ignore[no-untyped-def]
    return (
        "I tried to apply that edit, but verification failed.\n\n",
        {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "artifact_verification_failed": True,
            "artifact_verification": {"verified": False, "reason": "missing border"},
        },
    )


def _edit_worker_blocked_hook(**_kwargs):  # type: ignore[no-untyped-def]
    return (
        "Structured builder edits require a live Hermes gateway.\n\n",
        {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": "hermes_gateway", "blocked_reason": "gateway_mock"},
        },
    )


@pytest.mark.parametrize(
    ("lane_id", "hook"),
    [
        ("build_or_create", _build_or_create_hook),
        ("clarification", _clarification_hook),
        ("verification_failed", _verification_failed_hook),
        ("edit_worker_blocked", _edit_worker_blocked_hook),
    ],
)
def test_non_conversational_lanes_ignore_conversational_env(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch, lane_id: str, hook: object,
) -> None:
    """VAL-SAFETY-010 — non-conversational lanes never leak the conversational env."""
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", hook)

    if lane_id == "build_or_create":
        captured: dict[str, object] = {}

        def _capture(_msgs: list, **kwargs) -> str:
            captured.update(kwargs)
            return "Builder reply."

        monkeypatch.setattr("src.api.chat.complete_chat_turn", _capture)
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "build me a Tetris clone"}]},
        )
        assert res.status_code == 200, res.text
        assistant_text = res.json()["messages"][-1]["content"]
        assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
        assert _CONV_SENTINEL not in assistant_text
        return

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError(
            f"complete_chat_turn must not run for non-conversational lane {lane_id}"
        )

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)

    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": f"trigger lane {lane_id}"}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assistant_text = body["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert _CONV_SENTINEL not in assistant_text
    builder_meta = body.get("builder") or {}
    if lane_id == "clarification":
        assert builder_meta.get("builder_clarification") is True
    elif lane_id == "verification_failed":
        assert builder_meta.get("artifact_verification_failed") is True
    elif lane_id == "edit_worker_blocked":
        assert builder_meta.get("builder_edit_worker_blocked") is True


_BYOK_OR_KEY = "sk-or-v1-byok-fake-key-only-for-tests-000000000"


def _byok_test_actor() -> HamActor:
    return HamActor(
        user_id="user_byok",
        org_id="o1",
        session_id="s_byok",
        email="byok@good.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def test_chat_byok_explicit_model_id_wins_over_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-SAFETY-008 — BYOK + explicit model_id always wins over the conversational env."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://10.0.0.1:8642")
    monkeypatch.setenv("HERMES_GATEWAY_MODEL", "minimax/minimax-m2.5:free")
    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", "openrouter/sentinel-conv:free")

    actor = _byok_test_actor()
    monkeypatch.setattr(
        "src.api.chat._resolve_chat_clerk_context",
        lambda *_a, **_k: (actor, None),
    )
    monkeypatch.setattr(
        "src.api.chat.resolve_connected_tool_secret_plaintext",
        lambda _actor, tool_id: _BYOK_OR_KEY if tool_id == "openrouter" else None,
    )
    monkeypatch.setattr(
        "src.api.models_catalog.has_connected_tool_credential_record",
        lambda _actor, tool_id: tool_id == "openrouter",
    )

    seen: list[dict[str, object]] = []

    def _stub_completion(*_a, **kwargs):
        seen.append(dict(kwargs))

        class _Choice:
            def __init__(self) -> None:
                self.delta = type("D", (), {"content": "ok"})()

        class _Chunk:
            def __init__(self) -> None:
                self.choices = [_Choice()]

        yield _Chunk()

    with patch("litellm.completion", side_effect=_stub_completion):
        res = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "openrouter:default",
            },
        )

    assert res.status_code == 200, res.text
    assert seen, "litellm.completion was not invoked via BYOK route"
    model_used = seen[0].get("model")
    api_key_used = seen[0].get("api_key")
    assert model_used != "openrouter/sentinel-conv:free"
    assert "sentinel-conv" not in str(model_used)
    assert api_key_used == _BYOK_OR_KEY


_BRAND_INVENTORY_FORBIDDEN_TOKENS = (
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


def _stub_inventory_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make catalog renderers return easy-to-detect inventory text for casual gating tests."""
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


def test_rest_casual_space_monkey_identity_prompt_includes_brand_canon(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-BRAND-004 — REST default prompt for casual identity includes HAM brand canon + no-denial guidance."""
    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "Are you really the first code monkey launched into space?"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    low = sys_content.lower()
    assert "first code monkey launched into space" in low
    assert "never deny" in low
    assert "embrace" in low


def test_rest_casual_checkin_omits_internal_tool_inventory(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-001 / VAL-CROSS-001 — casual REST check-in suppresses internal tool/provider inventory."""
    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    _stub_inventory_render(monkeypatch)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "hey HAM, what you been up to lately?"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    for tok in _BRAND_INVENTORY_FORBIDDEN_TOKENS:
        assert tok not in sys_content, f"casual REST leaked inventory token: {tok!r}"
    assert "first code monkey launched into space" in sys_content.lower()


def test_rest_who_are_you_uses_ham_brand_without_inventory(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-003 / VAL-BRAND-009 — "who are you" returns brand canon without inventory dump."""
    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    _stub_inventory_render(monkeypatch)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Who are you?"}]},
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    low = sys_content.lower()
    assert "first code monkey launched into space" in low
    assert "casual voice" in low
    for tok in _BRAND_INVENTORY_FORBIDDEN_TOKENS:
        assert tok not in sys_content, f"who-are-you leaked inventory token: {tok!r}"


def test_rest_explicit_tool_inventory_prompt_allows_friendly_capability_context(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-004 — explicit tool-inventory prompts unlock friendly capability context."""
    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    friendly_skills_block = (
        "**Operator skills (Ham repo `.cursor/skills`):**\n"
        "- `cloud-agent-starter` — **Cloud Agent Starter**: how to launch agents.\n"
        "- `triage-issues` — **Triage**: route incoming issues.\n"
    )
    monkeypatch.setattr("src.api.chat.render_skills_for_system_prompt", lambda _items: friendly_skills_block)
    monkeypatch.setattr("src.api.chat.render_subagents_for_system_prompt", lambda _items: "")
    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "What tools do you have available?"}]},
    )
    assert res.status_code == 200, res.text
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
        assert tok not in sys_content, f"explicit-inventory leaked raw token: {tok!r}"


def test_rest_project_casual_chat_preserves_ham_brand_persona(
    mock_mode: None,
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-BRAND-010 — project casual chat keeps brand canon but omits casual active-agent inventory."""
    root = tmp_path / "proj_brand_casual"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "CasualBrandProfile",
                            "description": "Bench casual",
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
        json={"name": "casualbrand", "root": str(root), "description": ""},
    )
    assert reg.status_code == 201, reg.text
    pid = reg.json()["id"]

    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "tell me about yourself"}],
            "project_id": pid,
        },
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    low = sys_content.lower()
    assert "first code monkey launched into space" in low
    assert "never deny" in low
    assert "HAM active agent guidance" not in sys_content
    assert "CasualBrandProfile" not in sys_content
    assert "bundled.apple.apple-notes" not in sys_content


def test_rest_project_casual_chat_gates_active_agent_inventory(
    mock_mode: None,
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-CASUAL-006 — casual project chat omits attached active-agent catalog skills from system prompt."""
    root = tmp_path / "proj_brand_gate"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "GatedProfile",
                            "description": "Gated bench",
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
        json={"name": "gatedcasual", "root": str(root), "description": ""},
    )
    pid = reg.json()["id"]

    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "what you been up to lately?"}],
            "project_id": pid,
        },
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    assert "HAM active agent guidance" not in sys_content
    assert "GatedProfile" not in sys_content
    assert "bundled.apple.apple-notes" not in sys_content
    body = res.json()
    assert body.get("active_agent") is None


def test_casual_prompt_context_excludes_forbidden_internal_tokens(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-SAFETY-001 — casual prompt assembled context strips all forbidden raw internal tokens."""
    captured: dict[str, list] = {}

    def cap(messages: list, **_kwargs) -> str:
        captured["messages"] = messages
        return "stub"

    _stub_inventory_render(monkeypatch)
    monkeypatch.setattr("src.api.chat.complete_chat_turn", cap)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "introduce yourself"}]},
    )
    assert res.status_code == 200, res.text
    sys_content = captured["messages"][0].get("content") or ""
    for tok in _BRAND_INVENTORY_FORBIDDEN_TOKENS:
        assert tok not in sys_content, f"casual context leaked forbidden token: {tok!r}"


def test_non_conversational_lanes_ignore_conversational_env_operator_handled(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-SAFETY-010 (operator subcase) — operator-handled never leaks conv env."""
    from src.ham.chat_operator import OperatorTurnResult

    monkeypatch.setenv("HAM_CHAT_CONVERSATIONAL_MODEL", _CONV_SENTINEL)
    op_result = OperatorTurnResult(
        handled=True,
        intent="bridge_run",
        ok=True,
        data={"reason_code": "lane_isolation"},
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)

    def _no_llm(*_a: object, **_k: object) -> str:
        raise AssertionError("complete_chat_turn must not run for operator-handled lane")

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "trigger operator"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    op_payload = body.get("operator_result") or {}
    assert op_payload.get("handled") is True
    assistant_text = body["messages"][-1]["content"]
    assert "HAM_CHAT_CONVERSATIONAL_MODEL" not in assistant_text
    assert _CONV_SENTINEL not in assistant_text


def test_rest_model_selection_error_uses_friendly_copy(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-OPERATOR-006 — model_id in wrong gateway mode returns friendly error copy without env names."""
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "model_id": "openrouter:default",
        },
    )
    assert res.status_code == 422, res.text
    body = res.json()
    err = body.get("detail", {}).get("error", {}) or {}
    assert err.get("code") == "MODEL_SELECTION_REQUIRES_OPENROUTER"
    msg = err.get("message") or ""
    assert msg
    for tok in (
        "HERMES_GATEWAY_MODE",
        "HERMES_GATEWAY_BASE_URL",
        "HERMES_GATEWAY_MODEL",
        "HERMES_GATEWAY_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        assert tok not in msg, f"user-visible error leaked env name: {tok!r}"


def test_rest_operator_handled_assistant_text_quarantines_internal_tokens(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-OPERATOR-007 — REST operator-handled assistant content avoids env/protocol/raw IDs.

    The full payload may keep `operator_result` metadata with raw structured fields;
    only the visible assistant message is sanitized.
    """
    from src.ham.chat_operator import OperatorTurnResult

    op_result = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_launch",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_test",
            "external_id": "bc_test",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "status": "running",
            "mission_checkpoint": "launched",
            "reason_code": "mission_launched",
        },
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "have Cursor launch the agent"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    op_payload = body.get("operator_result") or {}
    # Metadata still carries the raw provider id for routing/compatibility.
    assert (op_payload.get("data") or {}).get("provider") == "cursor_cloud_agent"
    assistant_text = body["messages"][-1]["content"]
    for tok in (
        "HERMES_GATEWAY",
        "HAM_RUN_LAUNCH_TOKEN",
        "HAM_DROID_EXEC_TOKEN",
        "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
        "HAM_SETTINGS_WRITE_TOKEN",
        "proposal_digest",
        "base_revision",
        ".ham/runs",
        "operator.phase",
        "cursor_cloud_agent",
        "Cloud Agent",
        "Cursor Cloud Agent",
    ):
        assert tok not in assistant_text, f"operator visible text leaked: {tok!r}"
    assert "Cursor mission launched" in assistant_text


# ---------------------------------------------------------------------------
# VAL-OPERATOR-014 / VAL-OPERATOR-015 — recursive visible-payload scans for
# REST operator-handled responses, error envelopes, and persisted history.
# ---------------------------------------------------------------------------


def test_rest_operator_handled_full_response_has_no_visible_leaks(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-OPERATOR-014 — every user-visible string in the REST envelope is sanitized.

    The recursive scan walks ``messages``, ``actions``, displayable
    ``operator_result`` strings (``data.summary``, ``data.message``,
    pending preview summaries, ``blocking_reason``), and any other text the
    UI may render. Machine-metadata keys (``provider``, ``proposal_digest``,
    ``base_revision``, persistence paths, raw identifiers) are exempted so
    that internal transport fields stay available where required.
    """
    from src.ham.chat_operator import OperatorTurnResult

    from tests._helpers.visible_text import (
        assert_no_visible_leaks,
        iter_visible_strings,
    )

    op_result = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_launch",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_test",
            "external_id": "bc_test",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "status": "running",
            "mission_checkpoint": "launched",
            "reason_code": "mission_launched",
            "summary": "Cursor mission kicked off; awaiting first checkpoint.",
        },
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "have Cursor launch the agent"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert_no_visible_leaks(body, label="POST /api/chat envelope")

    visible_strings = [v for _, v in iter_visible_strings(body)]
    assert any(s for s in visible_strings), "scan must find at least one visible string"
    assert any("Cursor mission launched" in s for s in visible_strings)

    op_payload = body.get("operator_result") or {}
    data = op_payload.get("data") or {}
    assert data.get("provider") == "cursor_cloud_agent"
    assert data.get("mission_registry_id") == "mission-1"
    assert data.get("agent_id") == "bc_test"

    full_text = json.dumps(body)
    for tok in ("HERMES_GATEWAY", "HAM_RUN_LAUNCH_TOKEN"):
        assert tok not in full_text, f"unexpected env token in full envelope: {tok!r}"
    assert "cursor_cloud_agent" in full_text


def test_rest_operator_handled_blocking_reason_payload_scan(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-OPERATOR-014 — blocking-reason path: visible card-facing strings stay
    friendly while metadata retains the diagnostic ``blocking_reason``.
    """
    from src.ham.chat_operator import OperatorTurnResult

    from tests._helpers.visible_text import assert_no_visible_leaks

    raw_reason = (
        "HAM_RUN_LAUNCH_TOKEN missing on this API host; check HERMES_GATEWAY_MODE and "
        "provide proposal_digest plus base_revision; see .ham/runs and operator.phase."
    )
    op_result = OperatorTurnResult(
        handled=True,
        intent="launch_run",
        ok=False,
        blocking_reason=raw_reason,
        data={
            "summary": "Launch is gated until approval and configuration are in place.",
        },
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "launch the run"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    blocking_metadata_keys = frozenset({"blocking_reason"})
    assert_no_visible_leaks(
        body,
        extra_metadata_keys=blocking_metadata_keys,
        label="POST /api/chat blocked envelope",
    )

    op_payload = body.get("operator_result") or {}
    assert op_payload.get("blocking_reason") == raw_reason


def test_rest_model_selection_error_detail_payload_scan(
    mock_mode: None,
) -> None:
    """VAL-OPERATOR-014 — ``detail.error.message`` and adjacent visible strings
    in error envelopes are sanitized; the machine ``error.code`` may keep its
    raw form because it is not rendered as product copy.
    """
    from tests._helpers.visible_text import assert_no_visible_leaks

    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "model_id": "openrouter:default",
        },
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert_no_visible_leaks(body, label="POST /api/chat 422 envelope")
    err = body.get("detail", {}).get("error", {}) or {}
    assert err.get("code") == "MODEL_SELECTION_REQUIRES_OPENROUTER"


def test_rest_operator_handled_session_history_replay_is_sanitized(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VAL-OPERATOR-015 — sanitized operator transcript stays sanitized after
    persistence and replay via ``GET /api/chat/sessions/{sid}`` and the
    sessions listing.
    """
    from src.ham.chat_operator import OperatorTurnResult

    from tests._helpers.visible_text import (
        FORBIDDEN_VISIBLE_TOKENS,
        assert_no_visible_leaks,
    )

    op_result = OperatorTurnResult(
        handled=True,
        intent="cursor_agent_launch",
        ok=True,
        data={
            "provider": "cursor_cloud_agent",
            "mission_registry_id": "mission-1",
            "agent_id": "bc_test",
            "external_id": "bc_test",
            "repository": "Code-Munkiz/ham",
            "ref": "main",
            "status": "running",
            "mission_checkpoint": "launched",
            "reason_code": "mission_launched",
        },
    )
    monkeypatch.setattr("src.api.chat.process_operator_turn", lambda **_kw: op_result)
    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "have Cursor launch the agent"}],
            "enable_operator": True,
        },
    )
    assert res.status_code == 200, res.text
    sid = res.json()["session_id"]

    history = client.get(f"/api/chat/sessions/{sid}")
    assert history.status_code == 200, history.text
    persisted = history.json()
    messages = persisted.get("messages") or []
    assert messages, "session history must include the operator-handled turn"
    assistant_persisted = messages[-1]
    assert assistant_persisted["role"] == "assistant"
    assert "Cursor mission launched" in assistant_persisted["content"]
    for tok in FORBIDDEN_VISIBLE_TOKENS:
        assert tok not in assistant_persisted["content"], (
            f"persisted operator transcript leaked {tok!r}"
        )
    assert_no_visible_leaks(persisted, label="GET /api/chat/sessions/{sid} replay")

    listing = client.get("/api/chat/sessions")
    assert listing.status_code == 200, listing.text
    listing_body = listing.json()
    own_entries = [
        entry
        for entry in (listing_body.get("sessions") or [])
        if entry.get("session_id") == sid
    ]
    assert own_entries, "session listing must surface the operator-handled session"
    # The listing aggregates other in-process tests' user-typed prompts; only
    # scan the operator-handled session's own row, whose preview comes from the
    # newly typed user prompt and whose summary should not regress.
    assert_no_visible_leaks(
        {"sessions": own_entries},
        label="GET /api/chat/sessions listing (own session row)",
    )
