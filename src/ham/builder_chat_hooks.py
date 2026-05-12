"""Chat turn hooks for workspace builder happy-path (project + scaffold)."""

from __future__ import annotations

from typing import Any

from src.ham.clerk_auth import HamActor


def resolve_effective_chat_project_id(
    *,
    workspace_id: str | None,
    project_id: str | None,
    ham_actor: HamActor | None,
) -> str | None:
    """Return backend-known project id, creating default builder project if needed."""
    pid = (project_id or "").strip()
    if pid:
        return pid
    ws = (workspace_id or "").strip()
    if not ws or ham_actor is None:
        return None
    from src.ham.workspace_perms import PERM_WORKSPACE_WRITE
    from src.ham.workspace_resolver import (
        WorkspaceForbidden,
        WorkspaceNotFound,
        resolve_workspace_context,
    )
    from src.persistence.workspace_store import build_workspace_store

    try:
        ctx = resolve_workspace_context(ham_actor, ws, build_workspace_store())
    except (WorkspaceNotFound, WorkspaceForbidden):
        return None
    if PERM_WORKSPACE_WRITE not in ctx.perms:
        return None
    from src.ham.builder_default_project import ensure_default_builder_project

    return ensure_default_builder_project(ws).id


def run_builder_happy_path_hook(
    *,
    workspace_id: str | None,
    project_id: str | None,
    session_id: str,
    last_user_plain: str,
    ham_actor: HamActor | None,
) -> tuple[str | None, dict[str, Any]]:
    """Returns optional stream prefix and metadata for /api/chat responses."""
    from src.ham.builder_chat_intent import classify_builder_chat_intent
    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn

    intent = classify_builder_chat_intent(last_user_plain)
    meta: dict[str, Any] = {"builder_intent": intent}
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid or not str(last_user_plain or "").strip():
        return None, meta
    created_by = ham_actor.user_id if ham_actor is not None else ""
    summary = maybe_chat_scaffold_for_turn(
        workspace_id=ws,
        project_id=pid,
        session_id=session_id,
        last_user_plain=last_user_plain,
        created_by=created_by,
    )
    if not summary:
        return None, meta
    meta.update(summary)
    if summary.get("scaffolded"):
        from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job

        sid = str(summary.get("source_snapshot_id") or "").strip()
        if sid:
            enqueue_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
                workspace_id=ws,
                project_id=pid,
                source_snapshot_id=sid,
                session_id=session_id,
                requested_by=created_by,
            )
            if enqueue_meta:
                meta.update(enqueue_meta)
        return (
            "I'll create the initial project source and prepare the Workbench.\n\n",
            meta,
        )
    return None, meta
