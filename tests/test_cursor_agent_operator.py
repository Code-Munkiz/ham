"""Cursor Cloud Agent operator: preview, launch, status, audit, Bearer adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.ham.chat_operator import ChatOperatorPayload, process_operator_turn
from src.persistence.project_store import ProjectStore
from src.registry.projects import ProjectRecord


@pytest.fixture
def central_audit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "central_cursor_audit.jsonl"
    monkeypatch.setenv("HAM_CURSOR_AGENT_AUDIT_FILE", str(p))
    return p


@pytest.fixture
def launch_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "launch-secret")


def _make_store(tmp_path: Path, *, root: str, metadata: dict | None = None) -> tuple[ProjectStore, ProjectRecord]:
    store = ProjectStore(tmp_path / "projects.json")
    rec = ProjectRecord(
        id="project.test-abc123",
        name="t",
        root=root,
        metadata=metadata or {},
    )
    store.register(rec)
    return store, rec


def test_preview_blocked_without_repository(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_CURSOR_DEFAULT_REPOSITORY", raising=False)
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(tmp_path, root=str(tmp_path / "repo"))
    (tmp_path / "repo").mkdir()
    op = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="do something",
        cursor_repository=None,
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out is not None
    assert not out.ok
    assert out.blocking_reason and "repository" in out.blocking_reason.lower()
    lines = central_audit.read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[-1])
    assert row["action"] == "preview"
    assert row["ok"] is False


def test_cloud_launch_heuristic_missing_repo_has_stable_reason_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    monkeypatch.delenv("HAM_CURSOR_DEFAULT_REPOSITORY", raising=False)
    store, rec = _make_store(tmp_path, root=str(tmp_path / "repo"), metadata={})
    (tmp_path / "repo").mkdir()
    out = process_operator_turn(
        user_text="fire up a cloud agent to patch flaky tests",
        project_store=store,
        default_project_id=rec.id,
        operator_payload=None,
        ham_operator_authorization=None,
    )
    assert out is not None and out.handled and not out.ok
    assert (out.data or {}).get("reason_code") == "missing_repo_context"


def test_preview_blocked_without_cursor_key(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pathlib

    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    op = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="task",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out is not None and not out.ok
    assert "Cursor API key" in (out.blocking_reason or "")


def test_preview_managed_mission_uses_different_digest_than_direct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed missions digest the full managed prompt; direct digests the raw user task + deliverable."""
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    op_direct = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="fix bug",
        cursor_mission_handling="direct",
    )
    out_d = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op_direct,
        ham_operator_authorization=None,
    )
    op_managed = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="fix bug",
        cursor_mission_handling="managed",
    )
    out_m = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op_managed,
        ham_operator_authorization=None,
    )
    assert out_d and out_d.ok
    assert out_m and out_m.ok
    d_d = (out_d.data or {}).get("proposal_digest")
    d_m = (out_m.data or {}).get("proposal_digest")
    assert isinstance(d_d, str) and isinstance(d_m, str)
    assert d_d != d_m
    pd = out_m.pending_cursor_agent or {}
    assert pd.get("cursor_mission_handling") == "managed"


def test_digest_mismatch_blocks_launch(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_token: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="task",
        cursor_proposal_digest="0" * 64,
        cursor_base_revision="cursor-agent-v1",
        cursor_auto_create_pr=False,
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer launch-secret",
    )
    assert out is not None and not out.ok
    assert "mismatch" in (out.blocking_reason or "").lower()


def test_launch_blocked_without_ham_bearer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    monkeypatch.delenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", raising=False)
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    op = ChatOperatorPayload(
        phase="cursor_agent_launch",
        confirmed=True,
        project_id=rec.id,
        cursor_task_prompt="task",
        cursor_proposal_digest="a" * 64,
        cursor_base_revision="cursor-agent-v1",
    )
    with pytest.raises(HTTPException) as ei:
        process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization=None,
        )
    assert ei.value.status_code in (401, 403)


def test_successful_launch_writes_central_audit_and_normalizes_summary(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_token: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()

    from src.ham import cursor_agent_workflow as caw

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
    fake = {"id": "bc_xyz", "status": "CREATING", "summary": "started", "source": {"repository": "https://github.com/o/r"}}
    with patch.object(caw, "cursor_api_launch_agent", return_value=fake):
        op = ChatOperatorPayload(
            phase="cursor_agent_launch",
            confirmed=True,
            project_id=rec.id,
            cursor_task_prompt="fix tests",
            cursor_proposal_digest=digest,
            cursor_base_revision="cursor-agent-v1",
            cursor_auto_create_pr=False,
        )
        out = process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
        )
    assert out is not None and out.ok
    assert out.data.get("agent_id") == "bc_xyz"
    assert out.data.get("provider") == "cursor_cloud_agent"
    assert out.data.get("mission_checkpoint") == "queued"
    lines = central_audit.read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[-1])
    assert row["action"] == "launch"
    assert row["ok"] is True
    assert row["agent_id"] == "bc_xyz"


def test_cloud_launch_heuristic_creates_managed_mission_id_without_launch_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    monkeypatch.delenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", raising=False)
    missions_dir = tmp_path / "missions"
    monkeypatch.setenv("HAM_MANAGED_MISSIONS_DIR", str(missions_dir))
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    from src.ham import cursor_agent_workflow as caw

    fake = {"id": "bc_heuristic", "status": "CREATING", "summary": "started"}
    with patch.object(caw, "cursor_api_launch_agent", return_value=fake):
        out = process_operator_turn(
            user_text="launch a cloud agent to update the sdk adapter",
            project_store=store,
            default_project_id=rec.id,
            operator_payload=None,
            ham_operator_authorization=None,
        )
    assert out is not None and out.handled and out.ok
    assert (out.data or {}).get("agent_id") == "bc_heuristic"
    assert (out.data or {}).get("mission_registry_id")
    assert (out.data or {}).get("reason_code") == "mission_launched"


def test_managed_launch_calls_mission_registry(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_token: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "repo"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    (tmp_path / "repo").mkdir()
    from src.ham import cursor_agent_workflow as caw

    managed_prompt = caw.build_managed_cloud_agent_prompt_py(
        user_prompt="fix tests",
        repository="https://github.com/o/r",
        ref=None,
    )
    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt=managed_prompt,
    )
    fake = {"id": "bc_managed", "status": "CREATING", "summary": "started"}
    with (
        patch.object(caw, "cursor_api_launch_agent", return_value=fake),
        patch("src.ham.managed_mission_wiring.create_mission_after_managed_launch") as m_mission,
    ):
        op = ChatOperatorPayload(
            phase="cursor_agent_launch",
            confirmed=True,
            project_id=rec.id,
            cursor_task_prompt="fix tests",
            cursor_proposal_digest=digest,
            cursor_base_revision="cursor-agent-v1",
            cursor_auto_create_pr=False,
            cursor_mission_handling="managed",
        )
        out = process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
        )
    assert out is not None and out.ok
    m_mission.assert_called_once()
    kw = m_mission.call_args.kwargs
    assert kw["mission_handling"] == "managed"
    assert kw["launch_response"] == fake
    assert kw["project_id"] == rec.id
    assert (out.data or {}).get("mission_handling") == "managed"


def test_status_returns_normalized_summary(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(tmp_path, root=str(tmp_path / "repo"))
    (tmp_path / "repo").mkdir()
    from src.ham import cursor_agent_workflow as caw

    fake = {
        "id": "bc_ab",
        "status": "FINISHED",
        "summary": "done",
        "source": {"repository": "https://github.com/o/r", "ref": "main"},
    }
    with patch.object(caw, "cursor_api_get_agent", return_value=fake):
        op = ChatOperatorPayload(
            phase="cursor_agent_status",
            project_id=rec.id,
            cursor_agent_id="bc_ab",
        )
        out = process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization=None,
        )
    assert out is not None and out.ok
    assert out.data.get("status") == "FINISHED"
    assert out.data.get("mission_checkpoint") == "completed"
    lines = central_audit.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["action"] == "status"


def test_launch_succeeds_central_audit_when_project_root_missing(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_token: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    bad_root = str(tmp_path / "nope")
    store, rec = _make_store(
        tmp_path,
        root=bad_root,
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    from src.ham import cursor_agent_workflow as caw

    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="x",
    )
    fake = {"id": "bc_1", "status": "CREATING"}
    with patch.object(caw, "cursor_api_launch_agent", return_value=fake):
        op = ChatOperatorPayload(
            phase="cursor_agent_launch",
            confirmed=True,
            project_id=rec.id,
            cursor_task_prompt="x",
            cursor_proposal_digest=digest,
            cursor_base_revision="cursor-agent-v1",
        )
        out = process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
        )
    assert out is not None and out.ok
    assert central_audit.is_file()
    assert "launch" in central_audit.read_text(encoding="utf-8")


def test_project_mirror_skipped_when_root_not_dir(
    central_audit: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launch_token: None,
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    store, rec = _make_store(
        tmp_path,
        root=str(tmp_path / "ghost"),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    from src.ham import cursor_agent_workflow as caw

    digest = caw.compute_cursor_proposal_digest(
        project_id=rec.id,
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="x",
    )
    fake = {"id": "bc_2", "status": "CREATING"}
    with patch.object(caw, "cursor_api_launch_agent", return_value=fake):
        op = ChatOperatorPayload(
            phase="cursor_agent_launch",
            confirmed=True,
            project_id=rec.id,
            cursor_task_prompt="x",
            cursor_proposal_digest=digest,
            cursor_base_revision="cursor-agent-v1",
        )
        process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization="Bearer launch-secret",
        )
    mirror = tmp_path / "ghost" / ".ham" / "_audit" / "cursor_cloud_agent.jsonl"
    assert not mirror.is_file()


def test_cursor_cloud_client_uses_bearer_not_basic() -> None:
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"id": "bc_t", "status": "X"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}
            return FakeResp()

        def get(self, url, **kwargs):
            captured["headers_get"] = kwargs.get("headers") or {}
            return FakeResp()

    with patch("src.integrations.cursor_cloud_client.httpx.Client", FakeClient):
        from src.integrations.cursor_cloud_client import cursor_api_get_agent, cursor_api_launch_agent

        cursor_api_launch_agent(
            api_key="secret-key",
            prompt_text="hi",
            repository="https://github.com/o/r",
            ref=None,
            model="default",
            auto_create_pr=False,
            branch_name=None,
        )
        assert captured["headers"].get("Authorization") == "Bearer secret-key"

        cursor_api_get_agent(api_key="secret-key", agent_id="bc_t")
        assert captured["headers_get"].get("Authorization") == "Bearer secret-key"
