"""User-facing Plan toggle flow for builder workspace chat (markdown plan, no approval cards)."""

from __future__ import annotations

import logging
from typing import Any

from src.ham.builder_plan import Plan, PlanApprovalRecord, Step
from src.ham.builder_plan_approval import transition
from src.ham.builder_planner import PlannerOutputInvalidError, produce_plan
from src.persistence.builder_plan_store import BuilderPlanStoreProtocol, get_builder_plan_store

_LOG = logging.getLogger(__name__)

CHAT_PLAN_MODE_META_KEY = "chat_plan_mode"


def find_pending_chat_plan(
    *,
    workspace_id: str,
    project_id: str,
    store: BuilderPlanStoreProtocol | None = None,
) -> tuple[Plan | None, PlanApprovalRecord | None]:
    """Return the newest chat Plan-toggle proposal awaiting user affirmation."""
    st = store or get_builder_plan_store()
    for plan in st.list_plans(workspace_id=workspace_id, project_id=project_id):
        if not plan.metadata.get(CHAT_PLAN_MODE_META_KEY):
            continue
        rec = st.get_approval_record(plan_id=plan.plan_id)
        if rec is not None and rec.state == "proposed":
            return plan, rec
    return None, None


def approve_pending_chat_plan(
    *,
    plan: Plan,
    record: PlanApprovalRecord,
    store: BuilderPlanStoreProtocol | None = None,
) -> PlanApprovalRecord:
    st = store or get_builder_plan_store()
    approved = transition(record, "approve")
    st.upsert_approval_record(approved)
    return approved


def _deterministic_fallback_steps(user_message: str, *, is_edit: bool) -> list[Step]:
    summary = " ".join(str(user_message or "").split()).strip()
    if len(summary) > 140:
        summary = f"{summary[:137]}..."
    if is_edit:
        return [
            Step(
                title="Review the current app",
                description="Check the active preview and source snapshot.",
            ),
            Step(
                title="Apply your requested changes",
                description=summary or "Implement the edits you described.",
            ),
            Step(
                title="Refresh the preview",
                description="Update the preview so you can verify the result.",
            ),
        ]
    return [
        Step(
            title="Scaffold the project",
            description="Create starter source files for your app.",
        ),
        Step(
            title="Implement the core experience",
            description=summary or "Build the UI and behavior you asked for.",
        ),
        Step(
            title="Connect the preview",
            description="Wire the preview so you can interact with the app.",
        ),
    ]


def render_chat_plan_markdown(plan: Plan) -> str:
    lines = ["Here's a concise plan:", ""]
    for index, step in enumerate(plan.steps, start=1):
        title = str(step.title or "").strip()
        desc = str(step.description or "").strip()
        if desc:
            lines.append(f"{index}. **{title}** — {desc}")
        else:
            lines.append(f"{index}. **{title}**")
    lines.extend(["", "Want me to proceed?"])
    return "\n".join(lines)


def _persist_chat_plan(
    plan: Plan,
    *,
    session_id: str,
    store: BuilderPlanStoreProtocol,
) -> Plan:
    tagged = plan.model_copy(
        update={
            "metadata": {
                **plan.metadata,
                CHAT_PLAN_MODE_META_KEY: True,
                "session_id": session_id,
            }
        }
    )
    store.upsert_plan(tagged)
    store.upsert_approval_record(PlanApprovalRecord(plan_id=tagged.plan_id, state="proposed"))
    return tagged


def create_chat_plan_proposal(
    *,
    user_message: str,
    workspace_id: str,
    project_id: str,
    session_id: str,
    requested_by: str,
    ham_actor: Any | None,
    model_override: str | None,
    conversation_history: list[Any] | None,
    is_edit: bool,
    store: BuilderPlanStoreProtocol | None = None,
) -> tuple[str, Plan]:
    """Create a pending plan for Plan-toggle UX; never raises to callers."""
    st = store or get_builder_plan_store()
    history = list(conversation_history or [])
    plan: Plan | None = None
    try:
        plan = produce_plan(
            user_message=user_message,
            project_id=project_id,
            workspace_id=workspace_id,
            requested_by=requested_by,
            conversation_history=history,
            ham_actor=ham_actor,
            model_override=model_override,
            store=st,
        )
    except PlannerOutputInvalidError:
        _LOG.info(
            "Chat plan toggle: planner invalid output; using deterministic fallback",
            extra={"workspace_id": workspace_id, "project_id": project_id},
        )
        plan = None

    if plan is not None:
        if not plan.steps:
            plan = plan.model_copy(
                update={"steps": _deterministic_fallback_steps(user_message, is_edit=is_edit)}
            )
        persisted = _persist_chat_plan(plan, session_id=session_id, store=st)
        return render_chat_plan_markdown(persisted), persisted

    fallback = Plan(
        workspace_id=workspace_id,
        project_id=project_id,
        user_message=user_message,
        steps=_deterministic_fallback_steps(user_message, is_edit=is_edit),
        destructive=False,
        planner_confidence="medium",
        metadata={"fallback": True},
    )
    persisted = _persist_chat_plan(fallback, session_id=session_id, store=st)
    return render_chat_plan_markdown(persisted), persisted
