"""Chat turn hooks for workspace builder happy-path (project + scaffold)."""

from __future__ import annotations

import re
from typing import Any

from src.ham.clerk_auth import HamActor


def _looks_like_followup_edit(last_user_plain: str) -> bool:
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    patterns = (
        r"\bmake it\b",
        r"\bmore like\b",
        r"\bchange\b",
        r"\bupdate\b",
        r"\badd\b",
        r"\bremove\b",
        r"\btry again\b",
        r"\bi do not see\b",
        r"\bi don't see\b",
        r"\bi dont see\b",
        r"\bboard smaller\b",
    )
    if any(re.search(p, text) for p in patterns):
        return True
    return bool(re.search(r"\b(colors?|layout|style|sidebar|sound|leaderboard)\b", text))


def _looks_like_visual_reference_request(last_user_plain: str) -> bool:
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    if "image" not in text:
        return False
    return bool(
        re.search(r"\b(like|similar to|more like|style|look)\b.{0,48}\b(image|reference)\b", text)
    )


def _builder_ack_prefix(
    last_user_plain: str,
    *,
    operation: str = "build_or_create",
) -> str:
    """Generate prompt-specific builder acknowledgement copy."""
    text = (last_user_plain or "").strip().lower()
    if operation == "update_existing_project":
        if _looks_like_visual_reference_request(last_user_plain):
            return "I'll update the existing project and apply the visual style from your reference as closely as I can.\n\n"
        return "I'll update the existing project source and refresh the Workbench preview.\n\n"
    product = ""
    m = re.search(
        r"\b(?:build|create|make|generate|scaffold)\b.{0,60}\b"
        r"(game|app|application|website|site|dashboard|landing\s*page|tracker|portal|saas|tool|clone)\b",
        text,
    )
    if m:
        noun = m.group(1).strip()
        qualifier = ""
        qm = re.search(r"\b(like|similar to|clone of|style)\s+(\w[\w\s]{0,30})", text)
        if qm:
            qualifier = f"{qm.group(2).strip().title()}-style "
        elif re.search(r"\b(tetris|snake|pong|chess|sudoku|wordle)\b", text):
            found = re.search(r"\b(tetris|snake|pong|chess|sudoku|wordle)\b", text)
            if found:
                qualifier = f"{found.group(1).title()}-style "
        product = f"a {qualifier}browser {noun}" if noun == "game" else f"a {qualifier}{noun}"
    if product:
        return f"I'll create {product} project and prepare the Workbench.\n\n"
    return "I'll create the initial project source and prepare the Workbench.\n\n"


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
    from src.persistence.builder_source_store import get_builder_source_store

    source_rows = get_builder_source_store().list_project_sources(workspace_id=ws, project_id=pid)
    has_active_snapshot = any(bool(row.active_snapshot_id) for row in source_rows)
    operation = "build_or_create"
    if (
        intent != "build_or_create"
        and has_active_snapshot
        and _looks_like_followup_edit(last_user_plain)
    ):
        operation = "update_existing_project"
        meta["builder_intent"] = "build_or_create"
    elif intent != "build_or_create":
        return None, meta
    summary = maybe_chat_scaffold_for_turn(
        workspace_id=ws,
        project_id=pid,
        session_id=session_id,
        last_user_plain=last_user_plain,
        created_by=created_by,
        operation=operation,
    )
    if not summary:
        return None, meta
    meta.update(summary)
    sid = str(summary.get("source_snapshot_id") or "").strip()
    if summary.get("scaffolded"):
        from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job

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
            _builder_ack_prefix(last_user_plain, operation=operation),
            meta,
        )
    if summary.get("deduplicated"):
        if sid:
            from src.ham.builder_chat_cloud_runtime import (
                maybe_enqueue_chat_scaffold_cloud_runtime_job,
            )

            enqueue_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
                workspace_id=ws,
                project_id=pid,
                source_snapshot_id=sid,
                session_id=session_id,
                requested_by=created_by,
            )
            if enqueue_meta:
                meta.update(enqueue_meta)
        if operation == "update_existing_project":
            return (
                "I already applied that update for the active project source and will keep the Workbench in sync.\n\n",
                meta,
            )
        return (
            "I already prepared this builder project source from your recent prompt and will keep the Workbench in sync.\n\n",
            meta,
        )
    return None, meta
