"""Harness advisory (preview-only, rule-based, separate from control-plane truth)."""

from __future__ import annotations

import copy
import json

import pytest

from src.ham.chat_operator import ChatOperatorPayload, process_operator_turn
from src.ham.harness_advisory import (
    HarnessAdvisory,
    build_harness_advisory_for_cursor_preview,
    build_harness_advisory_for_droid_preview,
    format_harness_advisory_for_operator_message,
    harness_advisory_enabled,
    build_harness_advisory_for_preview,
)
from src.ham.chat_operator import format_operator_assistant_message
from src.persistence.project_store import ProjectStore


def test_harness_advisory_enabled_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_HARNESS_ADVISORY", raising=False)
    assert harness_advisory_enabled() is False
    monkeypatch.setenv("HAM_HARNESS_ADVISORY", "1")
    assert harness_advisory_enabled() is True


def test_schema_rejects_long_rationale() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        HarnessAdvisory(
            suggested_harness="factory_droid",
            confidence="high",
            rationale="x" * 900,
        )


def test_rationale_capped_by_validator() -> None:
    long_r = "y" * 900
    adv = build_harness_advisory_for_droid_preview(
        workflow_id="readonly_repo_audit",
        mutates=False,
        tier="readonly",
        requires_launch_token=False,
        droid_exec_token_configured=True,
        user_prompt=long_r,
    )
    assert len(adv.rationale) <= 800


def test_list_items_capped() -> None:
    adv = HarnessAdvisory(
        suggested_harness="factory_droid",
        confidence="high",
        rationale="ok",
        risks=["a" * 300, "b" * 300],
        missing_prerequisites=["c" * 300],
    )
    assert all(len(x) <= 200 for x in adv.risks)
    assert len(adv.risks) <= 5


def test_droid_pr_signal_unclear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_DROID_EXEC_TOKEN", raising=False)
    adv = build_harness_advisory_for_droid_preview(
        workflow_id="readonly_repo_audit",
        mutates=False,
        tier="readonly",
        requires_launch_token=False,
        droid_exec_token_configured=False,
        user_prompt="Please open a pull request on github.com/foo/bar for the change",
    )
    assert adv.suggested_harness == "unclear"
    assert adv.confidence == "limited"
    assert adv.risks


def test_cursor_no_repo_unclear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    adv = build_harness_advisory_for_cursor_preview(
        repository_resolved=False,
        mutates=None,
        auto_create_pr=False,
        cursor_launch_token_configured=False,
        task_prompt="do work",
    )
    assert adv.suggested_harness == "unclear"
    assert adv.confidence == "limited"
    assert any("repository" in m.lower() for m in adv.missing_prerequisites)


def test_preview_dispatch_cursor() -> None:
    adv = build_harness_advisory_for_preview(
        preview_kind="cursor_agent_preview",
        repository_resolved=True,
        mutates=False,
        auto_create_pr=False,
        cursor_launch_token_configured=True,
        task_prompt="fix tests",
    )
    assert adv.suggested_harness == "cursor_cloud_agent"


def test_droid_inputs_hash_stable() -> None:
    a = build_harness_advisory_for_droid_preview(
        workflow_id="readonly_repo_audit",
        mutates=False,
        tier="readonly",
        requires_launch_token=False,
        droid_exec_token_configured=True,
        user_prompt="audit",
    )
    b = build_harness_advisory_for_droid_preview(
        workflow_id="readonly_repo_audit",
        mutates=False,
        tier="readonly",
        requires_launch_token=False,
        droid_exec_token_configured=True,
        user_prompt="audit",
    )
    assert a.inputs_hash == b.inputs_hash
    assert a.inputs_hash and len(a.inputs_hash) == 16


def test_format_operator_message_contains_advisory_block() -> None:
    from src.ham.chat_operator import OperatorTurnResult

    adv = build_harness_advisory_for_droid_preview(
        workflow_id="readonly_repo_audit",
        mutates=False,
        tier="readonly",
        requires_launch_token=False,
        droid_exec_token_configured=True,
        user_prompt="audit",
    )
    op = OperatorTurnResult(
        handled=True,
        intent="droid_preview",
        ok=True,
        pending_droid={"project_id": "p", "workflow_id": "readonly_repo_audit", "summary_preview": "s"},
        harness_advisory=adv,
    )
    msg = format_operator_assistant_message(op)
    assert "Advisory (Hermes)" in msg
    assert "not a launch decision" in msg
    assert "factory_droid" in msg
    assert format_harness_advisory_for_operator_message(adv) in msg


def test_advisory_absent_when_flag_off(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_HARNESS_ADVISORY", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    op = ChatOperatorPayload(
        phase="droid_preview",
        project_id=rec.id,
        droid_workflow_id="readonly_repo_audit",
        droid_user_prompt="check layout",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out and out.ok
    assert out.harness_advisory is None
    assert "Advisory (Hermes)" not in format_operator_assistant_message(out)


def test_advisory_on_droid_preview_when_flag_on(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_HARNESS_ADVISORY", "1")
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    op = ChatOperatorPayload(
        phase="droid_preview",
        project_id=rec.id,
        droid_workflow_id="readonly_repo_audit",
        droid_user_prompt="check layout",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out and out.ok
    assert out.harness_advisory is not None
    assert out.harness_advisory.suggested_harness in ("factory_droid", "unclear", "cursor_cloud_agent")
    assert out.pending_droid
    d = out.pending_droid or {}
    before_digest = d.get("proposal_digest")
    out.harness_advisory.model_dump(mode="json")
    d2 = out.pending_droid or {}
    assert d2.get("proposal_digest") == before_digest
    assert d2.get("base_revision") == d.get("base_revision")
    msg = format_operator_assistant_message(out)
    assert "Advisory (Hermes)" in msg
    assert "not a launch decision" in msg


def test_advisory_does_not_mutate_pending_reference(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_HARNESS_ADVISORY", "1")
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(name="p", root=str(repo))
    store.register(rec)
    op = ChatOperatorPayload(
        phase="droid_preview",
        project_id=rec.id,
        droid_workflow_id="readonly_repo_audit",
        droid_user_prompt="x",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization=None,
    )
    assert out and out.pending_droid
    snap = copy.deepcopy(out.pending_droid)
    _ = out.harness_advisory.model_dump() if out.harness_advisory else None
    assert out.pending_droid == snap


def test_cursor_preview_advisory_when_flag_on(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_HARNESS_ADVISORY", "1")
    monkeypatch.setenv("HAM_CURSOR_AGENT_LAUNCH_TOKEN", "x")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-api-key-for-preview")
    repo = tmp_path / "repo"
    repo.mkdir()
    store = ProjectStore(tmp_path / "store.json")
    rec = store.make_record(
        name="p",
        root=str(repo),
        metadata={"cursor_cloud_repository": "https://github.com/o/r"},
    )
    store.register(rec)
    op = ChatOperatorPayload(
        phase="cursor_agent_preview",
        project_id=rec.id,
        cursor_task_prompt="fix bug",
    )
    out = process_operator_turn(
        user_text="",
        project_store=store,
        default_project_id=None,
        operator_payload=op,
        ham_operator_authorization="Bearer x",
    )
    assert out and out.ok
    assert out.harness_advisory is not None
    assert out.pending_cursor_agent
    p0 = (out.pending_cursor_agent or {}).get("proposal_digest")
    assert p0
    # advisory must not change digest
    hdump = out.harness_advisory.model_dump(mode="json")
    assert "control_plane" not in json.dumps(hdump)
    assert (out.pending_cursor_agent or {}).get("proposal_digest") == p0
    assert "Advisory (Hermes)" in format_operator_assistant_message(out)


def test_limited_confidence_cursor_when_no_api_key_monkeypatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful preview path always has a Cursor key; test rule output via stubbed key lookup."""
    monkeypatch.setattr(
        "src.ham.harness_advisory.get_effective_cursor_api_key",
        lambda: None,
    )
    adv = build_harness_advisory_for_cursor_preview(
        repository_resolved=True,
        mutates=False,
        auto_create_pr=False,
        cursor_launch_token_configured=True,
        task_prompt="fix bug",
    )
    assert adv.confidence == "limited"
    assert any("CURSOR_API_KEY" in m or "cursor key" in m.lower() for m in adv.missing_prerequisites)
