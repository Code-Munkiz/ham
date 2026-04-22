"""Tests for allowlisted Factory droid workflows (registry, preview, launch, audit)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.ham.chat_operator import (
    ChatOperatorPayload,
    process_operator_turn,
    try_heuristic_intent,
)
from src.ham.droid_workflows.preview_launch import (
    DroidLaunchResult,
    append_droid_audit,
    build_droid_preview,
    compute_proposal_digest,
    execute_droid_workflow,
    parse_droid_json_stdout,
    verify_launch_against_preview,
)
from src.ham.droid_workflows.registry import (
    REGISTRY_REVISION,
    DroidWorkflowDefinition,
    get_workflow,
    list_workflow_ids,
)
from src.persistence.project_store import ProjectStore
from src.tools.droid_executor import DroidExecutionRecord


def test_registry_allowlists_two_workflows() -> None:
    ids = list_workflow_ids()
    assert ids == ["readonly_repo_audit", "safe_edit_low"]
    ro = get_workflow("readonly_repo_audit")
    assert ro is not None
    assert ro.mutates is False
    assert ro.requires_launch_token is False
    assert ro.requires_confirmation is True
    se = get_workflow("safe_edit_low")
    assert se is not None
    assert se.mutates is True
    assert se.requires_launch_token is True


def test_build_preview_unknown_workflow(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pr = build_droid_preview(
        workflow_id="evil_workflow",
        project_id="p",
        project_root=root,
        user_prompt="x",
    )
    assert not pr.ok
    assert pr.blocking_reason and "Unknown workflow_id" in pr.blocking_reason


def test_build_preview_invalid_root(tmp_path) -> None:
    missing = tmp_path / "nope"
    pr = build_droid_preview(
        workflow_id="readonly_repo_audit",
        project_id="p",
        project_root=missing,
        user_prompt="audit",
    )
    assert not pr.ok
    assert "not a directory" in (pr.blocking_reason or "").lower()


def test_build_preview_missing_custom_droid(tmp_path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    wf = DroidWorkflowDefinition(
        workflow_id="readonly_repo_audit",
        description="x",
        tier="readonly",
        mutates=False,
        requires_confirmation=True,
        requires_launch_token=False,
        prompt_template="Do:\n{user_focus}\n.",
        custom_droid_name="ghost-droid",
    )
    monkeypatch.setattr("src.ham.droid_workflows.preview_launch.get_workflow", lambda _id: wf)
    pr = build_droid_preview(
        workflow_id="readonly_repo_audit",
        project_id="p1",
        project_root=root,
        user_prompt="check",
    )
    assert not pr.ok
    assert pr.blocking_reason and "Custom Droid" in pr.blocking_reason


def test_verify_launch_digest_mismatch(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    err = verify_launch_against_preview(
        workflow_id="readonly_repo_audit",
        project_id="proj",
        project_root=root,
        user_prompt="focus",
        proposal_digest="0" * 64,
        base_revision=REGISTRY_REVISION,
    )
    assert err and "mismatch" in err


def test_verify_stale_base_revision(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    d = compute_proposal_digest(
        workflow_id="readonly_repo_audit",
        project_id="proj",
        cwd=str(root.resolve()),
        user_prompt="focus",
    )
    err = verify_launch_against_preview(
        workflow_id="readonly_repo_audit",
        project_id="proj",
        project_root=root,
        user_prompt="focus",
        proposal_digest=d,
        base_revision="old",
    )
    assert err and "Stale" in err


def test_parse_droid_json_stdout() -> None:
    payload = {"result": "ok", "session_id": "s-1"}
    data, text, sid = parse_droid_json_stdout(json.dumps(payload))
    assert data == payload
    assert text == "ok"
    assert sid == "s-1"


def test_append_droid_audit_writes_jsonl(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    aid = append_droid_audit(
        root,
        {"workflow_id": "readonly_repo_audit", "runner_id": "local", "ok": True},
    )
    path = root / ".ham" / "_audit" / "droid_exec.jsonl"
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["audit_id"] == aid
    assert row["workflow_id"] == "readonly_repo_audit"


@patch("src.ham.droid_workflows.preview_launch.run_droid_argv")
def test_execute_workflow_honest_failure(mock_run, tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    mock_run.return_value = DroidExecutionRecord(
        argv=["droid", "exec"],
        working_dir=str(root),
        exit_code=7,
        timed_out=False,
        stdout="",
        stderr="boom",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="",
        ended_at="",
        duration_ms=10,
    )
    out = execute_droid_workflow(
        workflow_id="readonly_repo_audit",
        project_root=root,
        user_prompt="audit security",
    )
    assert not out.ok
    assert out.exit_code == 7
    assert out.audit_id
    assert "failed" in (out.blocking_reason or "").lower()


@patch("src.ham.chat_operator.execute_droid_workflow")
def test_operator_droid_launch_readonly_no_bearer(mock_ex, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HAM_DROID_EXEC_TOKEN", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    prev = build_droid_preview(
        workflow_id="readonly_repo_audit",
        project_id=rec.id,
        project_root=repo,
        user_prompt="audit layout",
    )
    assert prev.ok
    mock_ex.return_value = DroidLaunchResult(
        ok=True,
        blocking_reason=None,
        workflow_id="readonly_repo_audit",
        audit_id="audit-1",
        runner_id="local",
        cwd=str(repo.resolve()),
        exit_code=0,
        duration_ms=100,
        summary="done",
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        parsed_json={},
        session_id=None,
        timed_out=False,
    )
    op = ChatOperatorPayload(
        phase="droid_launch",
        confirmed=True,
        project_id=rec.id,
        droid_workflow_id="readonly_repo_audit",
        droid_user_prompt=prev.user_prompt,
        droid_proposal_digest=prev.proposal_digest,
        droid_base_revision=prev.base_revision,
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out is not None
    assert out.ok
    assert out.data.get("audit_id") == "audit-1"


@patch("src.ham.chat_operator.execute_droid_workflow")
def test_operator_safe_edit_requires_bearer(mock_ex, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HAM_DROID_EXEC_TOKEN", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    prev = build_droid_preview(
        workflow_id="safe_edit_low",
        project_id=rec.id,
        project_root=repo,
        user_prompt="fix typo in README",
    )
    assert prev.ok
    op = ChatOperatorPayload(
        phase="droid_launch",
        confirmed=True,
        project_id=rec.id,
        droid_workflow_id="safe_edit_low",
        droid_user_prompt=prev.user_prompt,
        droid_proposal_digest=prev.proposal_digest,
        droid_base_revision=prev.base_revision,
    )
    with pytest.raises(HTTPException) as excinfo:
        process_operator_turn(
            user_text="",
            project_store=store,
            default_project_id=None,
            operator_payload=op,
            ham_operator_authorization=None,
        )
    assert excinfo.value.status_code in (401, 403)
    mock_ex.assert_not_called()


def test_heuristic_droid_preview_extracts_workflow_and_focus(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    text = f"preview factory droid readonly_repo_audit: check tests in {rec.id}"
    out = try_heuristic_intent(text, default_project_id=None)
    assert out is not None
    intent, params = out
    assert intent == "droid_preview"
    assert params["workflow_id"] == "readonly_repo_audit"
    assert params["project_id"] == rec.id
    assert "tests" in params["user_prompt"]


@patch("src.ham.chat_operator.execute_droid_workflow")
def test_operator_safe_edit_with_bearer_calls_execute(mock_ex, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "tok")
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    prev = build_droid_preview(
        workflow_id="safe_edit_low",
        project_id=rec.id,
        project_root=repo,
        user_prompt="docs only",
    )
    assert prev.ok
    mock_ex.return_value = DroidLaunchResult(
        ok=True,
        blocking_reason=None,
        workflow_id="safe_edit_low",
        audit_id="a2",
        runner_id="local",
        cwd=str(repo.resolve()),
        exit_code=0,
        duration_ms=50,
        summary="ok",
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        parsed_json={},
        session_id="s",
        timed_out=False,
    )
    op = ChatOperatorPayload(
        phase="droid_launch",
        confirmed=True,
        project_id=rec.id,
        droid_workflow_id="safe_edit_low",
        droid_user_prompt=prev.user_prompt,
        droid_proposal_digest=prev.proposal_digest,
        droid_base_revision=prev.base_revision,
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer tok",
    )
    assert out is not None and out.ok
    mock_ex.assert_called_once()
