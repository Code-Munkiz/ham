"""Builder chat Plan toggle — plan_mode request field and hook behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.builder_chat_hooks import run_builder_happy_path_hook
from src.ham.builder_chat_plan_mode import (
    CHAT_PLAN_MODE_META_KEY,
    create_chat_plan_proposal,
    find_pending_chat_plan,
    render_chat_plan_markdown,
)
from src.ham.builder_plan import Plan, PlanApprovalRecord, Step
from src.ham.clerk_auth import HamActor
from src.persistence.builder_plan_store import BuilderPlanStore, set_builder_plan_store_for_tests
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    SourceSnapshot,
    set_builder_source_store_for_tests,
)

_FORBIDDEN_USER_PHRASES = (
    "System B",
    "worker",
    "dispatcher",
    "Cloud Tasks",
    "GKE",
    "Approve below",
    "approval card",
)


def _actor(uid: str = "user_plan") -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _raise_if_scaffold(**_kw: object) -> object:
    raise AssertionError("maybe_chat_scaffold_for_turn must not run")


@pytest.fixture
def plan_store(tmp_path):
    store = BuilderPlanStore(store_path=tmp_path / "plans.json")
    set_builder_plan_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_plan_store_for_tests(None)


@pytest.fixture
def empty_source_store(tmp_path):
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_source_store_for_tests(None)


def test_plan_mode_false_build_intent_scaffolds_directly(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    sentinel = {"scaffolded": True, "source_snapshot_id": "snap_x", "builder_operation": "build_or_create"}
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        return_value=sentinel,
    ) as scaffold_mock:
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_plan_off",
            project_id="proj_plan_off",
            session_id="sess_plan_off",
            last_user_plain="build me a todo app",
            ham_actor=_actor(),
            plan_mode=False,
        )
    scaffold_mock.assert_called_once()
    assert meta.get("builder_intent") == "build_or_create"
    assert meta.get("builder_plan_pending") is not True
    assert prefix is not None


def test_plan_mode_true_net_new_build_returns_plan_not_scaffold(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_if_scaffold,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_plan_on",
            project_id="proj_plan_on",
            session_id="sess_plan_on",
            last_user_plain="build me a landing page",
            ham_actor=_actor(),
            plan_mode=True,
        )
    assert meta.get("builder_plan_pending") is True
    assert meta.get("builder_intent") == "build_or_create"
    assert prefix is not None
    assert "Want me to proceed?" in prefix
    assert "Here's a concise plan:" in prefix
    pending, rec = find_pending_chat_plan(workspace_id="ws_plan_on", project_id="proj_plan_on")
    assert pending is not None
    assert rec is not None and rec.state == "proposed"
    assert pending.metadata.get(CHAT_PLAN_MODE_META_KEY) is True
    for token in _FORBIDDEN_USER_PHRASES:
        assert token.lower() not in prefix.lower()


def test_plan_mode_true_edit_intent_returns_plan_not_scaffold(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    ws, pid = "ws_edit", "proj_edit"
    src = ProjectSource(
        workspace_id=ws,
        project_id=pid,
        kind="chat_scaffold",
        active_snapshot_id="snap_edit",
    )
    empty_source_store.upsert_project_source(src)
    empty_source_store.upsert_source_snapshot(
        SourceSnapshot(
            id="snap_edit",
            workspace_id=ws,
            project_id=pid,
            project_source_id=src.id,
            manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": {}},
        )
    )
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_if_scaffold,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess_edit",
            last_user_plain="change the header color to blue",
            ham_actor=_actor(),
            plan_mode=True,
        )
    assert meta.get("builder_plan_pending") is True
    assert prefix is not None
    assert "Want me to proceed?" in prefix
    pending, _ = find_pending_chat_plan(workspace_id=ws, project_id=pid)
    assert pending is not None
    assert pending.user_message == "change the header color to blue"


def test_plan_mode_true_affirmation_continues_into_scaffold(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    ws, pid = "ws_cont", "proj_cont"
    plan = Plan(
        workspace_id=ws,
        project_id=pid,
        user_message="build me a calculator",
        steps=[Step(title="Scaffold", description="Create files.")],
        destructive=False,
        planner_confidence="high",
        metadata={CHAT_PLAN_MODE_META_KEY: True},
    )
    plan_store.upsert_plan(plan)
    plan_store.upsert_approval_record(PlanApprovalRecord(plan_id=plan.plan_id, state="proposed"))
    sentinel = {"scaffolded": True, "source_snapshot_id": "snap_y", "builder_operation": "build_or_create"}
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        return_value=sentinel,
    ) as scaffold_mock:
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess_cont",
            last_user_plain="build it",
            ham_actor=_actor(),
            plan_mode=True,
        )
    scaffold_mock.assert_called_once()
    assert meta.get("builder_plan_continuation") is True
    assert meta.get("builder_plan_id") == plan.plan_id
    assert meta.get("builder_intent") == "build_or_create"
    assert prefix is not None


def test_plan_mode_true_yes_without_pending_plan_does_not_scaffold(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_if_scaffold,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_bare_yes",
            project_id="proj_bare_yes",
            session_id="sess_bare_yes",
            last_user_plain="yes",
            ham_actor=_actor(),
            plan_mode=True,
        )
    assert prefix is None
    assert meta.get("builder_affirmation_without_plan") is True
    assert meta.get("builder_intent") == "answer_question"


def test_plan_mode_true_non_build_qa_does_not_create_plan(
    empty_source_store: BuilderSourceStore,
    plan_store: BuilderPlanStore,
) -> None:
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_if_scaffold,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_qa",
            project_id="proj_qa",
            session_id="sess_qa",
            last_user_plain="what is a React component?",
            ham_actor=_actor(),
            plan_mode=True,
        )
    assert prefix is None
    assert meta.get("builder_plan_pending") is not True
    assert meta.get("builder_intent") == "answer_question"
    assert find_pending_chat_plan(workspace_id="ws_qa", project_id="proj_qa") == (None, None)


def test_fallback_plan_markdown_has_no_forbidden_language(
    plan_store: BuilderPlanStore,
) -> None:
    text, plan = create_chat_plan_proposal(
        user_message="build a weather dashboard",
        workspace_id="ws_fb",
        project_id="proj_fb",
        session_id="sess_fb",
        requested_by="user_fb",
        ham_actor=None,
        model_override=None,
        conversation_history=[],
        is_edit=False,
        store=plan_store,
    )
    assert plan.steps
    assert "Want me to proceed?" in text
    for token in _FORBIDDEN_USER_PHRASES:
        assert token.lower() not in text.lower()


def test_render_chat_plan_markdown_format() -> None:
    plan = Plan(
        workspace_id="w",
        project_id="p",
        user_message="build x",
        steps=[
            Step(title="One", description="First step."),
            Step(title="Two", description="Second step."),
        ],
        destructive=False,
        planner_confidence="high",
    )
    md = render_chat_plan_markdown(plan)
    assert "**One**" in md
    assert "Want me to proceed?" in md
