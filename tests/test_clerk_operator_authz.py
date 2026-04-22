"""Clerk identity + HAM operator authorization (server-enforced)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.chat_operator import ChatOperatorPayload, process_operator_turn
from src.ham.clerk_auth import HamActor
from src.ham.clerk_policy import HAM_LAUNCH, HAM_PREVIEW, HAM_STATUS
from src.persistence.project_store import ProjectStore

client = TestClient(app)


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _actor(*, perms: frozenset[str], email: str | None = "user_test@example.com") -> HamActor:
    return HamActor(
        user_id="user_test",
        org_id="org_test",
        session_id="sess_1",
        email=email.lower().strip() if email else None,
        permissions=perms,
        org_role="org:member",
        raw_permission_claim="test",
    )


def test_process_operator_turn_requires_actor_when_clerk_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    store_path = tmp_path / "proj.json"
    store = ProjectStore(store_path=store_path)
    rec = store.make_record(name="t", root=str(tmp_path), description="")
    store.register(rec)
    with pytest.raises(HTTPException) as ei:
        process_operator_turn(
            user_text="list all projects",
            project_store=store,
            default_project_id=None,
            operator_payload=None,
            ham_operator_authorization=None,
            ham_actor=None,
        )
    assert ei.value.status_code == 401


def test_launch_forbidden_without_ham_launch_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "launch-secret")
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    root = tmp_path / "repo"
    root.mkdir()
    rec = store.make_record(name="n", root=str(root), metadata={"cursor_cloud_repository": "https://github.com/o/r"})
    store.register(rec)
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="task",
        cursor_proposal_digest="a" * 64,
        cursor_base_revision="cursor-agent-v1",
    )
    actor = _actor(perms=frozenset({HAM_PREVIEW, HAM_STATUS}))
    with pytest.raises(HTTPException) as ei:
        process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
            ham_actor=actor,
        )
    assert ei.value.status_code == 403


def test_preview_allowed_with_preview_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store = ProjectStore(tmp_path / "p.json")
    root = tmp_path / "repo"
    root.mkdir()
    rec = store.make_record(name="n", root=str(root), metadata={"cursor_cloud_repository": "https://github.com/o/r"})
    store.register(rec)
    op = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="do something",
    )
    actor = _actor(perms=frozenset({HAM_PREVIEW}))
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
        ham_actor=actor,
    )
    assert out is not None and out.handled
    assert out.intent == "cursor_agent_preview"


def test_chat_api_401_when_clerk_required_and_no_authorization(
    mock_gateway: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "please list projects"}]},
    )
    assert res.status_code == 401
    detail = res.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("error", {}).get("code") == "CLERK_SESSION_REQUIRED"


def test_chat_api_operator_audit_includes_clerk_attribution(
    mock_gateway: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audit = tmp_path / "operator_audit.jsonl"
    monkeypatch.setenv("HAM_OPERATOR_AUDIT_FILE", str(audit))
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    fake_actor = _actor(perms=frozenset({HAM_STATUS}))
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=fake_actor):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "please list projects"}]},
            headers={"Authorization": "Bearer fake.jwt"},
        )
    assert res.status_code == 200
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    row = json.loads(lines[-1])
    assert row["clerk_user_id"] == "user_test"
    assert row["clerk_org_id"] == "org_test"
    assert row["audit_sink"] == "ham_local_jsonl"
    assert row["required_permission"] == HAM_STATUS


def test_launch_succeeds_with_clerk_launch_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "launch-secret")
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    from src.ham import cursor_agent_workflow as caw

    store = ProjectStore(tmp_path / "p.json")
    root = tmp_path / "repo"
    root.mkdir()
    rec = store.make_record(name="n", root=str(root), metadata={"cursor_cloud_repository": "https://github.com/o/r"})
    store.register(rec)
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="fix tests",
    )
    fake = {"id": "bc_ok", "status": "CREATING", "summary": "started", "source": {"repository": "https://github.com/o/r"}}
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="fix tests",
        cursor_proposal_digest=digest,
        cursor_base_revision="cursor-agent-v1",
        cursor_auto_create_pr=False,
    )
    actor = _actor(perms=frozenset({HAM_LAUNCH}))
    with patch.object(caw, "cursor_api_launch_agent", return_value=fake):
        out = process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
            ham_actor=actor,
        )
    assert out is not None and out.ok
    assert out.data.get("agent_id") == "bc_ok"


def test_cursor_api_key_still_separate_from_clerk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Launch path still requires Cursor team key via get_effective_cursor_api_key (not Clerk)."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "launch-secret")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    import pathlib

    from src.ham import cursor_agent_workflow as caw

    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    store = ProjectStore(tmp_path / "p.json")
    root = tmp_path / "repo"
    root.mkdir()
    rec = store.make_record(name="n", root=str(root), metadata={"cursor_cloud_repository": "https://github.com/o/r"})
    store.register(rec)
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="task",
    )
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="task",
        cursor_proposal_digest=digest,
        cursor_base_revision="cursor-agent-v1",
    )
    actor = _actor(perms=frozenset({HAM_LAUNCH}))
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer launch-secret",
        ham_actor=actor,
    )
    assert out is not None and out.handled and not out.ok
    assert out.blocking_reason and "Cursor API key" in out.blocking_reason
