"""Chat turn hooks for workspace builder happy-path (project + scaffold)."""

from __future__ import annotations

import re
from typing import Any

from src.ham.clerk_auth import HamActor


def _looks_like_followup_edit(last_user_plain: str) -> bool:
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    # Explicit UI/chrome polish ("make the buttons larger and blue").
    if re.search(
        r"\b(make|change|update|adjust)\b.{0,60}\b"
        r"(buttons?|digits?|numbers?|keys?|keyboard|controls?|pad)\b",
        text,
    ):
        return True
    if re.search(r"\blarger\b.{0,32}\band\b.{0,32}\bblue\b", text):
        return True
    if re.search(r"\bborder\b|\boutline\b", text) and (
        re.search(r"\byellow\b|\bgold\b|\bamber\b|#\s*facc15\b", text)
        or re.search(r"\b(them|those|these|the\s+buttons?|digits?|keys?)\b", text)
    ):
        return True
    if re.search(
        r"\b(easier\s+to\s+read|readability|readable|legible|bigger\s+font|more\s+contrast)\b", text,
    ):
        return True
    patterns = (
        r"\bmake it\b",
        r"\bi want\b",
        r"\bi'd like\b",
        r"\bi need\b",
        r"\binstead\b",
        r"\bas well\b",
        r"\bmore like\b",
        r"\bchange\b",
        r"\bupdate\b",
        r"\badd\b",
        r"\bremove\b",
        r"\btry again\b",
        r"\benhance\b",
        r"\bboring\b",
        r"\bpolish\b",
        r"\brefine\b",
        r"\biterate\b",
        r"\bmake it better\b",
        r"\bmake it more\b",
        r"\bnot how\b.{0,32}\bimage\b.{0,24}\blooked\b",
        r"\bi do not see\b",
        r"\bi don't see\b",
        r"\bi dont see\b",
        r"\bboard smaller\b",
    )
    if any(re.search(p, text) for p in patterns):
        return True
    return bool(
        re.search(
            r"\b(colors?|layout|style|spacing|sidebar|sound|leaderboard|particles?|glow|neon|image|reference|border|outline)\b",
            text,
        )
    )


def _looks_like_literal_explain_only(last_user_plain: str) -> bool:
    """Pure Q&A phrasing that should not drive builder updates when mis-detected."""
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    return bool(
        re.search(
            r"^\s*(what is|what are|what's|explain|describe|define|why is|why does|how does|how do)\b",
            text,
        )
    )


def _looks_like_active_app_iteration(last_user_plain: str) -> bool:
    """Feature / polish requests on an existing Workbench app (not a brand-new product build)."""
    text = (last_user_plain or "").strip().lower()
    if not text or _looks_like_literal_explain_only(last_user_plain):
        return False
    if re.search(
        r"\b(i want|i'd like|i need|please)\b.{0,160}\b(show|see|display|keep|make|add|change|update|improve|fix)\b",
        text,
    ):
        return True
    if re.search(
        r"^\s*(nice\s+job|looks\s+great|great\s+job|love\s+it|perfect|thanks|thank\s+you)\b",
        text,
    ) and re.search(r"\b(make|show|add|change|update|keep|improve|try)\b", text):
        return True
    if re.search(
        r"\b(show|display|visible|stay|persist|reflect|mirror|equation|expression|formula|digits?|numbers?|typing|typed|history|tape|flow)\b",
        text,
    ) and (
        re.search(
            r"\b(the|this|my)\s+(app|calculator|buttons?|preview|screen|ui|equation|numbers|keyboard|controls)\b",
            text,
        )
        or re.search(r"\bas i type\b", text)
        or re.search(r"\b(calculator|calc)\b", text)
    ):
        return True
    # "Yeah just keep working on this current app…" iteration phrasing.
    if re.search(
        r"\b(keep\s+working|keep\s+going)\b.{0,100}\b(this|current|the)\s+(app|preview|calculator)",
        text,
    ):
        return True
    return False


def _looks_like_discrete_new_product_request(last_user_plain: str) -> bool:
    """User is asking for a different standalone product/build (respect even if one exists)."""
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    if re.search(r"\banother\s+(app|project|dashboard|site|saas|clone|tracker|portal|tool|game)\b", text):
        return True
    if re.search(
        r"\b(new|brand[- ]new|fresh)\s+(app|project|dashboard|site|saas|landing|clone|tracker|portal|tool|game)\b",
        text,
    ):
        return True
    if re.search(r"\b(from scratch|start over|scratch project|new project)\b", text):
        return True
    if re.search(
        r"\b(build|create|make|generate|scaffold|spin up)\b.{0,120}\b(app|dashboard|saas|landing|website|site|tracker|portal|clone|tool|game|calculator)\b",
        text,
    ):
        return True
    return False


def _looks_like_visual_reference_request(last_user_plain: str) -> bool:
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    if "image" in text and re.search(
        r"\b(like|similar to|more like|style|look)\b.{0,48}\b(image|reference)\b", text
    ):
        return True
    # Messages can include only "like this" while dashboard metadata appends:
    # [User attached N image(s) in the dashboard.]
    if "user attached" in text and "image" in text:
        return bool(re.search(r"\b(like this|similar to this|more like this|look like this)\b", text))
    return bool(
        re.search(r"\b(one in the image|the image|reference style|reference look)\b", text)
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
        if _looks_like_visual_reference_request(last_user_plain):
            qualifier = "Reference-style "
        qm = re.search(r"\b(like|similar to|clone of|style)\s+(\w[\w\s]{0,30})", text)
        if qm:
            candidate = qm.group(2).strip()
            # Avoid awkward acknowledgements like "One In The Image I Gave You-style".
            if not re.search(r"\b(image|reference|this|that|one)\b", candidate):
                qualifier = f"{candidate.title()}-style "
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

    base_intent = classify_builder_chat_intent(last_user_plain)
    meta: dict[str, Any] = {"builder_intent": base_intent}
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid or not str(last_user_plain or "").strip():
        return None, meta
    created_by = ham_actor.user_id if ham_actor is not None else ""
    from src.persistence.builder_source_store import get_builder_source_store

    source_rows = get_builder_source_store().list_project_sources(workspace_id=ws, project_id=pid)
    has_active_snapshot = any(bool(row.active_snapshot_id) for row in source_rows)
    wants_update = _looks_like_followup_edit(last_user_plain) or _looks_like_active_app_iteration(
        last_user_plain
    )
    discrete_new = base_intent == "build_or_create" and _looks_like_discrete_new_product_request(
        last_user_plain
    )
    forced_update = bool(has_active_snapshot and wants_update and not discrete_new)
    operation = "update_existing_project" if forced_update else "build_or_create"
    intent_out: str = (
        "build_or_create"
        if forced_update or base_intent == "build_or_create"
        else str(base_intent)
    )
    meta["builder_intent"] = intent_out
    if not forced_update and intent_out != "build_or_create":
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
