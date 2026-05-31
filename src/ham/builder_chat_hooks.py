"""Chat turn hooks for workspace builder happy-path (project + scaffold).

Conductor ownership boundary (see AGENTS.md → "HAM bet"):

- This module is the **canonical user-facing path for Builder turns**
  (``classify_builder_chat_intent`` → ``build_or_create`` /
  ``answer_question`` / ``plan_only``). Builder ack copy, clarification
  prompts, and verification-failure copy are produced here.
- The chat dispatcher in ``src/api/chat.py`` runs this hook first per
  turn; when ``builder_intent == "build_or_create"`` (or the hook
  short-circuits with clarification / verification failure) the operator
  path in ``src/ham/chat_operator.py`` is gated off, so the two paths
  never both emit user copy on the same turn.
- Builder intent classification is in
  ``src/ham/builder_chat_intent.classify_builder_chat_intent`` (structured
  signal only).
- The CodingPlanCard preview contract (``src/api/coding_conductor.py``)
  is a separate frontend-driven surface; this module does not invoke it.
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE, STEP_VERIFICATION_FAILED
from src.ham.clerk_auth import HamActor

from src.ham.builder_chat_intent import (
    classify_builder_chat_intent,
    is_builder_edit_like_followup,
    is_builder_status_diagnostic_turn,
    looks_like_explicit_no_build,
)
from src.ham.builder_mutation_router import classify_builder_project_action, resolve_snapshot_project_template


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
        r"\bchange\b.{0,48}\b(the|it|this|those|these|colors?|styles?|buttons?|layout|spacing)\b",
        r"\bupdate\b.{0,48}\b(the|it|this|colors?|styles?|buttons?|layout|ui|code)\b",
        r"\badd\b.{0,64}\b(border|shadow|styles?|animations?|sounds?|buttons?|features?|more)\b",
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


def _model_access_required_message(*, operation: str) -> str:
    if operation == "update_existing_project":
        return (
            "I cannot apply that edit without model access. "
            "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
        )
    return (
        "I cannot build this without model access. "
        "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
    )


def _llm_scaffold_failure_message(
    *,
    operation: str,
    error_code: str,
    model_slug: str | None = None,
) -> str:
    is_edit = operation == "update_existing_project"
    model_label = str(model_slug or "").strip()
    if error_code == STEP_VERIFICATION_FAILED:
        if is_edit:
            return (
                "I couldn't apply that edit yet because the model response wasn't valid "
                "scaffold JSON. Try again or pick a different chat model.\n\n"
            )
        return (
            "I couldn't build this yet because the model response wasn't valid scaffold JSON. "
            "Try again or pick a different chat model.\n\n"
        )
    if model_label:
        display = model_label.replace("openrouter/", "", 1) if model_label.startswith("openrouter/") else model_label
        if is_edit:
            return (
                f"I couldn't apply that edit yet because the selected scaffold model ({display}) "
                "is unavailable or the model call failed. Check Connected Tools (OpenRouter key) "
                "or pick a different model in Settings, then try again.\n\n"
            )
        return (
            f"I couldn't build this yet because the selected scaffold model ({display}) "
            "is unavailable or the model call failed. Check Connected Tools (OpenRouter key) "
            "or pick a different model in Settings, then try again.\n\n"
        )
    if is_edit:
        return (
            "I couldn't apply that edit yet because the OpenRouter model call failed. "
            "Check Connected Tools (OpenRouter key) and your selected chat model, then try again.\n\n"
        )
    return (
        "I couldn't build this yet because the OpenRouter model call failed. "
        "Check Connected Tools (OpenRouter key) and your selected chat model, then try again.\n\n"
    )


def _artifact_verification_failure_message(*, operation: str, detail: str) -> str:
    tail = f" ({detail})" if detail else ""
    if operation == "update_existing_project":
        return (
            "I tried to apply that edit, but the generated files did not include "
            f"what you asked for yet{tail}.\n\n"
        )
    return f"I couldn't build that yet{tail}.\n\n"


# ---------------------------------------------------------------------------
# Harness-first guard (Phase 2 of HARNESS_FIRST_ARCHITECTURE_PLAN.md)
#
# Premium coding/build harnesses (Cursor / Claude / OpenCode / Factory Droid)
# own normal product builds. The internal chat scaffold is Quick Preview /
# fallback only and must not silently replace an available harness build path.
# ---------------------------------------------------------------------------

# coding_router ProviderKind values for the premium build harnesses.
# ``claude_code`` is intentionally excluded — it has no active launch route in
# HAM and is always blocked (planned candidate).
_PREMIUM_BUILD_HARNESS_PROVIDERS: frozenset[str] = frozenset(
    {"cursor_cloud", "claude_agent", "opencode_cli", "factory_droid_build"}
)

# Quick Preview acknowledgement — the internal scaffold runs here as a preview
# tool, explicitly NOT the product builder.
_QUICK_PREVIEW_ACK = (
    "Generating a quick preview (a lightweight mockup, not a full build). "
    "It'll appear in the workbench on the right.\n\n"
)


def _looks_like_quick_preview_request(last_user_plain: str) -> bool:
    """True when the user explicitly asked for a quick preview / mockup / scaffold.

    Explicit preview intent keeps the internal scaffold path available even when
    a premium harness is eligible (Quick Preview is an allowed scaffold use).
    """
    text = (last_user_plain or "").strip().lower()
    if not text:
        return False
    return bool(
        re.search(
            r"\b(quick preview|preview only|just a (quick )?preview|mock[\s-]?up|"
            r"wireframe|rough draft|throwaway|scaffold only|just scaffold)\b",
            text,
        )
    )


def premium_harness_available_for_build(
    *,
    workspace_id: str | None,
    project_id: str | None,
    ham_actor: HamActor | None,
) -> bool:
    """Return True when at least one premium build harness is eligible.

    Uses the existing readiness/policy primitives only: ``collate_readiness``
    (platform availability) combined with the workspace ``WorkspaceAgentPolicy``
    allow flags. Never inspects or returns secret values, env names, or runner
    URLs. A harness counts as eligible when it is ``available`` and carries no
    blockers. Best-effort: any failure resolves to ``False`` so the internal
    scaffold fallback is preserved.
    """
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid:
        return False
    try:
        from src.api.coding_agent_access_settings import load_workspace_agent_policy
        from src.ham.coding_router import collate_readiness

        policy = load_workspace_agent_policy(ws)
        readiness = collate_readiness(
            actor=ham_actor,
            project_id=pid,
            include_operator_details=False,
            workspace_policy=policy,
        )
    except Exception:  # noqa: BLE001 — never block the build turn on readiness errors
        return False
    return any(
        p.provider in _PREMIUM_BUILD_HARNESS_PROVIDERS and p.available and not p.blockers
        for p in readiness.providers
    )


# ---------------------------------------------------------------------------
# User-selected builder model (Phase 3 of HARNESS_FIRST_ARCHITECTURE_PLAN.md)
#
# A normal new-build prompt routes to the builder the user selected — no hidden
# fallback chain. With no selection, HAM applies a product-configured default
# (if any) or asks the user to choose. The internal scaffold is NOT a builder;
# it runs only for an explicit Quick Preview request.
# ---------------------------------------------------------------------------

# Product-facing builder display labels (used in user copy + safe metadata).
# These are intentionally NOT the snake_case provider ids, so they never collide
# with provider-internal tokens.
_BUILDER_DISPLAY_LABEL: dict[str, str] = {
    "cursor": "Cursor",
    "claude": "Claude",
    "opencode": "OpenCode",
    "factory_droid": "Factory Droid",
    "hermes_agent": "Hermes Agent",
}

# Selectable builder id -> coding_router ProviderKind used only for readiness.
# ``hermes_agent`` is intentionally absent: its new-build entry point is not
# wired yet, so it can never be "ready" for a new build (honest, never faked).
# TODO(harness-first §9): add a hermes_agent readiness probe + new-build entry
# point, then map it here.
_BUILDER_READINESS_PROVIDER: dict[str, str] = {
    "cursor": "cursor_cloud",
    "claude": "claude_agent",
    "opencode": "opencode_cli",
    "factory_droid": "factory_droid_build",
}

_DEFAULT_BUILDER_ENV = "HAM_DEFAULT_BUILDER"

_BUILDER_CHOOSE_MESSAGE = (
    "Which builder should I use for this build? Choose Cursor, Claude, OpenCode, "
    "Factory Droid, or Hermes Agent in Settings (coding agents). If you just want "
    'a fast mockup, say "quick preview".'
    "\n\n"
)

_HERMES_AGENT_NEW_BUILD_UNAVAILABLE_MESSAGE = (
    "Hermes Agent is not available for new builds yet. Pick another builder "
    "(Cursor, Claude, OpenCode, or Factory Droid) in Settings, or say "
    '"quick preview" for a fast mockup.'
    "\n\n"
)


def configured_default_builder() -> str | None:
    """Return the product-configured default builder id, or ``None``.

    Read from ``HAM_DEFAULT_BUILDER`` (e.g. ``opencode``). Only an explicit,
    valid configuration takes effect; otherwise there is no default and HAM asks
    the user to choose. Per product law, OpenCode is the default *only if* the
    product configures it here.
    """
    raw = (os.environ.get(_DEFAULT_BUILDER_ENV) or "").strip().lower()
    return raw if raw in _BUILDER_DISPLAY_LABEL else None


def _selected_builder_for_workspace(workspace_id: str) -> str | None:
    """Return the workspace's persisted selected builder id, or ``None``."""
    try:
        from src.api.coding_agent_access_settings import load_workspace_agent_policy

        policy = load_workspace_agent_policy(workspace_id)
    except Exception:  # noqa: BLE001
        return None
    if policy is None:
        return None
    sel = getattr(policy, "selected_builder", None)
    return sel if sel in _BUILDER_DISPLAY_LABEL else None


def _selected_builder_ready(
    builder_id: str,
    *,
    workspace_id: str,
    project_id: str,
    ham_actor: HamActor | None,
) -> bool:
    """True when the selected builder's underlying provider is ready.

    Uses `collate_readiness` + `WorkspaceAgentPolicy` (no secret values). Returns
    ``False`` for builders with no wired new-build provider (e.g. Hermes Agent).
    """
    provider = _BUILDER_READINESS_PROVIDER.get(builder_id)
    if provider is None:
        return False
    try:
        from src.api.coding_agent_access_settings import load_workspace_agent_policy
        from src.ham.coding_router import collate_readiness

        policy = load_workspace_agent_policy(workspace_id)
        readiness = collate_readiness(
            actor=ham_actor,
            project_id=project_id,
            include_operator_details=False,
            workspace_policy=policy,
        )
    except Exception:  # noqa: BLE001
        return False
    return any(
        p.provider == provider and p.available and not p.blockers for p in readiness.providers
    )


def _builder_ready_handoff_message(label: str) -> str:
    return (
        f"{label} is your selected builder, so I'll route this build to it. "
        "Open the build panel on the right to review and start the build.\n\n"
    )


def _builder_setup_required_message(label: str) -> str:
    return (
        f"{label} is your selected builder, but it isn't set up on this workspace "
        "yet. Enable it in Settings (coding agents), then try again. If you just "
        'want a fast mockup, say "quick preview".\n\n'
    )


def _resolve_selected_builder_turn(
    *,
    workspace_id: str,
    project_id: str,
    ham_actor: HamActor | None,
    meta: dict[str, Any],
    directive_prefix: str,
) -> tuple[str, dict[str, Any]]:
    """Terminal (prefix, meta) for a normal build prompt under the user-selected
    builder model. Never runs the internal scaffold; never fakes a builder."""
    selected = _selected_builder_for_workspace(workspace_id)
    source = "selected"
    if selected is None:
        selected = configured_default_builder()
        source = "default" if selected else "none"

    base: dict[str, Any] = {
        **meta,
        "builder_intent": "answer_question",
        "builder_harness_first": True,
        "scaffolded": False,
    }

    if selected is None:
        base["selected_builder_state"] = "choose"
        return f"{directive_prefix}{_BUILDER_CHOOSE_MESSAGE}", base

    label = _BUILDER_DISPLAY_LABEL[selected]
    base["selected_builder_label"] = label
    base["selected_builder_source"] = source

    if selected == "hermes_agent":
        # Selectable HAM-native builder, but new-build path not wired yet.
        base["selected_builder_state"] = "unavailable"
        return f"{directive_prefix}{_HERMES_AGENT_NEW_BUILD_UNAVAILABLE_MESSAGE}", base

    if _selected_builder_ready(
        selected, workspace_id=workspace_id, project_id=project_id, ham_actor=ham_actor
    ):
        base["selected_builder_state"] = "ready"
        return f"{directive_prefix}{_builder_ready_handoff_message(label)}", base

    base["selected_builder_state"] = "setup_required"
    return f"{directive_prefix}{_builder_setup_required_message(label)}", base


def compose_builder_grounded_status_reply(*, workspace_id: str, project_id: str) -> str:
    """Deterministic Workbench status copy from source + preview job records (never raises)."""
    from src.persistence.builder_runtime_job_store import get_builder_runtime_job_store
    from src.persistence.builder_source_store import get_builder_source_store

    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid:
        return (
            "I don't have workspace builder records for this turn yet. "
            "Open the project in the Workbench and try again.\n\n"
        )

    source_store = get_builder_source_store()
    job_store = get_builder_runtime_job_store()
    source_rows = source_store.list_project_sources(workspace_id=ws, project_id=pid)
    has_active_source = any(bool(str(row.active_snapshot_id or "").strip()) for row in source_rows)
    snapshots = source_store.list_source_snapshots(workspace_id=ws, project_id=pid)
    latest_snapshot_id = str(snapshots[0].id or "").strip() if snapshots else ""
    jobs = job_store.list_cloud_runtime_jobs(workspace_id=ws, project_id=pid)
    latest_job = jobs[0] if jobs else None

    if not has_active_source:
        return (
            "There isn't any committed project source in this workspace yet, so the preview has "
            "nothing to show. Tell me what you'd like to build and I can create the first version "
            "in the Workbench.\n\n"
        )

    job_status = str(getattr(latest_job, "status", "") or "").strip().lower()
    job_phase = str(getattr(latest_job, "phase", "") or "").strip().lower()
    failed = job_status in {"failed", "cancelled", "unsupported"} or job_phase in {"failed", "error"}

    if failed:
        detail_bits: list[str] = []
        if job_status:
            detail_bits.append(f"status {job_status}")
        if job_phase:
            detail_bits.append(f"phase {job_phase}")
        detail = f" ({', '.join(detail_bits)})" if detail_bits else ""
        snap_hint = f" Latest snapshot: {latest_snapshot_id}." if latest_snapshot_id else ""
        return (
            "Project source exists in this workspace, but the latest preview run did not succeed"
            f"{detail}.{snap_hint} Retry the preview from the Workbench or ask me to rebuild.\n\n"
        )

    if job_status in {"queued", "running", "cancelling"}:
        return (
            "Project source exists and a preview run is still in progress. "
            "Check the Workbench preview panel — it should update when the job finishes.\n\n"
        )

    return (
        "Project source exists in this workspace. If the preview still looks empty, refresh the "
        "Workbench preview or ask me to rebuild.\n\n"
    )


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
    model_id: str | None = None,
    plan_mode: bool = False,
    conversation_history: list[Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Returns optional stream prefix and metadata for /api/chat responses."""
    from src.ham.builder_chat_scaffold import maybe_chat_scaffold_for_turn

    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid or not str(last_user_plain or "").strip():
        base_intent = classify_builder_chat_intent(last_user_plain)
        return None, {"builder_intent": base_intent}

    from src.ham.builder_edit_worker import (
        apply_builder_worker_chat_directives,
        run_builder_edit_worker_maybe,
    )
    from src.persistence.builder_source_store import get_builder_source_store

    store = get_builder_source_store()
    source_rows = store.list_project_sources(workspace_id=ws, project_id=pid)
    preferred_for_directive = next(
        (row for row in source_rows if str(row.kind or "").strip().lower() == "chat_scaffold"),
        source_rows[0] if source_rows else None,
    )
    directive = apply_builder_worker_chat_directives(
        last_user_plain=last_user_plain,
        project_source=preferred_for_directive,
        store=store,
    )
    effective_plain = directive.cleaned_prompt
    if directive.updated_source is not None:
        source_rows = store.list_project_sources(workspace_id=ws, project_id=pid)
    has_active_snapshot = any(bool(row.active_snapshot_id) for row in source_rows)
    active_template: str | None = None
    if has_active_snapshot:
        _pref = next(
            (row for row in source_rows if str(row.kind or "").strip().lower() == "chat_scaffold"),
            source_rows[0] if source_rows else None,
        )
        _aid = str(getattr(_pref, "active_snapshot_id", "") or "").strip() if _pref else ""
        if _aid:
            for _sn in store.list_source_snapshots(workspace_id=ws, project_id=pid):
                if str(_sn.id or "").strip() == _aid:
                    active_template = resolve_snapshot_project_template(_sn)
                    break
    if directive.assistant_note and not str(effective_plain or "").strip():
        meta_d: dict[str, Any] = {
            "builder_intent": "build_or_create",
            "builder_worker_directive_only": True,
        }
        if directive.blocked_reason:
            meta_d["builder_worker_override_rejected"] = directive.blocked_reason
        return directive.assistant_note, meta_d
    # Prefix directive ack when present alongside an edit (preference saved first).
    directive_prefix = directive.assistant_note or ""

    if looks_like_explicit_no_build(effective_plain):
        meta = {"builder_intent": "plan_only"}
        return None, meta

    base_intent = classify_builder_chat_intent(effective_plain)
    action_decision = classify_builder_project_action(
        effective_plain,
        has_active_snapshot=has_active_snapshot,
        active_template=active_template,
    )
    meta: dict[str, Any] = {"builder_intent": base_intent, "builder_action_decision": action_decision.to_safe_dict()}
    if action_decision.kind == "ask_clarification":
        clar = action_decision.clarification_prompt or "What should I change?\n\n"
        return f"{directive_prefix}{clar}", {
            **meta,
            "builder_clarification": True,
            "builder_intent": "answer_question",
        }

    advice_only = action_decision.kind == "answer_only"

    created_by = ham_actor.user_id if ham_actor is not None else ""

    wants_update = (not advice_only) and (
        is_builder_edit_like_followup(effective_plain)
        or _looks_like_followup_edit(effective_plain)
        or _looks_like_active_app_iteration(effective_plain)
    )
    discrete_new = base_intent == "build_or_create" and _looks_like_discrete_new_product_request(
        effective_plain
    )
    forced_update = bool(has_active_snapshot and wants_update and not discrete_new)
    operation = "update_existing_project" if forced_update else "build_or_create"
    intent_out: str = (
        "build_or_create"
        if forced_update or base_intent == "build_or_create"
        else str(base_intent)
    )
    meta["builder_intent"] = intent_out
    if is_builder_status_diagnostic_turn(effective_plain):
        grounded = compose_builder_grounded_status_reply(workspace_id=ws, project_id=pid)
        return f"{directive_prefix}{grounded}", {
            **meta,
            "builder_intent": "answer_question",
            "builder_grounded_status": True,
        }

    plan_mode_on = bool(plan_mode)
    plan_continuation = False
    if plan_mode_on:
        from src.ham.builder_chat_intent import is_affirmation_continuation
        from src.ham.builder_chat_plan_mode import (
            approve_pending_chat_plan,
            create_chat_plan_proposal,
            find_pending_chat_plan,
        )

        if is_affirmation_continuation(effective_plain):
            pending_plan, pending_rec = find_pending_chat_plan(
                workspace_id=ws,
                project_id=pid,
            )
            if pending_plan is None or pending_rec is None:
                return None, {
                    **meta,
                    "builder_intent": "answer_question",
                    "builder_affirmation_without_plan": True,
                }
            approve_pending_chat_plan(plan=pending_plan, record=pending_rec)
            effective_plain = pending_plan.user_message
            base_intent = classify_builder_chat_intent(effective_plain)
            action_decision = classify_builder_project_action(
                effective_plain,
                has_active_snapshot=has_active_snapshot,
                active_template=active_template,
            )
            meta = {
                "builder_intent": base_intent,
                "builder_action_decision": action_decision.to_safe_dict(),
            }
            advice_only = action_decision.kind == "answer_only"
            wants_update = (not advice_only) and (
                is_builder_edit_like_followup(effective_plain)
                or _looks_like_followup_edit(effective_plain)
                or _looks_like_active_app_iteration(effective_plain)
            )
            discrete_new = base_intent == "build_or_create" and _looks_like_discrete_new_product_request(
                effective_plain
            )
            forced_update = bool(has_active_snapshot and wants_update and not discrete_new)
            operation = "update_existing_project" if forced_update else "build_or_create"
            intent_out = (
                "build_or_create"
                if forced_update or base_intent == "build_or_create"
                else str(base_intent)
            )
            meta["builder_intent"] = intent_out
            meta["builder_plan_continuation"] = True
            meta["builder_plan_id"] = pending_plan.plan_id
            plan_continuation = True
        elif intent_out == "build_or_create":
            plan_text, plan = create_chat_plan_proposal(
                user_message=effective_plain,
                workspace_id=ws,
                project_id=pid,
                session_id=session_id,
                requested_by=created_by,
                ham_actor=ham_actor,
                model_override=model_id,
                conversation_history=conversation_history,
                is_edit=operation == "update_existing_project",
            )
            return f"{directive_prefix}{plan_text}", {
                **meta,
                "builder_plan_pending": True,
                "builder_plan_id": plan.plan_id,
                "builder_intent": "build_or_create",
            }

    if not plan_continuation and not forced_update and intent_out != "build_or_create":
        return None, meta

    if operation == "update_existing_project" and has_active_snapshot:
        preferred = next(
            (row for row in source_rows if str(row.kind or "").strip().lower() == "chat_scaffold"),
            source_rows[0] if source_rows else None,
        )
        active_id = str(getattr(preferred, "active_snapshot_id", "") or "").strip() if preferred else ""
        if preferred and active_id:
            active_snap = next(
                (
                    sn
                    for sn in store.list_source_snapshots(workspace_id=ws, project_id=pid)
                    if str(sn.id or "").strip() == active_id
                ),
                None,
            )
            if active_snap is not None:
                edit_try = run_builder_edit_worker_maybe(
                    workspace_id=ws,
                    project_id=pid,
                    session_id=session_id,
                    last_user_plain=effective_plain,
                    created_by=created_by,
                    operation=operation,
                    preferred_source=preferred,
                    active_snapshot=active_snap,
                    action_decision=action_decision,
                )
                if edit_try is not None:
                    meta.update(edit_try)
                    sid_e = str(edit_try.get("source_snapshot_id") or "").strip()
                    if edit_try.get("builder_edit_worker_blocked"):
                        reason = str((edit_try.get("builder_edit_worker") or {}).get("blocked_reason") or "").strip()
                        human = "I could not apply that edit via the Hermes gateway yet."
                        if reason == "gateway_mock_or_unconfigured":
                            human = (
                                "Structured builder edits require a live Hermes gateway on the API host "
                                "(mock gateway mode cannot produce patches). Configure the gateway or try again later.\n\n"
                            )
                        elif reason == "unsupported_worker":
                            human = "That builder worker is not available for this edit path yet.\n\n"
                        elif reason in {"invalid_json", "gateway_error"}:
                            human = (
                                "The Hermes gateway did not return a usable structured patch for this request.\n\n"
                            )
                        elif reason == "verification_failed":
                            human = (
                                "The Hermes gateway patch did not verify against your calculator project "
                                "(+/− styling or preserved theme).\n\n"
                            )
                        elif reason == "no_op":
                            human = "The Hermes gateway returned a no-op patch (no file changes).\n\n"
                        elif reason:
                            human = f"I could not complete that builder edit ({reason}).\n\n"
                        return f"{directive_prefix}{human}", meta
                    if edit_try.get("scaffolded") and sid_e:
                        return (
                            f"{directive_prefix}{_builder_ack_prefix(effective_plain, operation=operation)}",
                            meta,
                        )

    # User-selected builder model: a normal new-build prompt routes to the
    # builder the user selected (or asks them to choose / use a configured
    # default). The internal scaffold is NOT a builder and is reached only on an
    # explicit Quick Preview request. The update_existing_project edit path is
    # unaffected. See docs/build-kit-registry-v2/HARNESS_FIRST_ARCHITECTURE_PLAN.md
    # (Phase 3).
    quick_preview = _looks_like_quick_preview_request(effective_plain)
    if operation == "build_or_create" and not quick_preview:
        return _resolve_selected_builder_turn(
            workspace_id=ws,
            project_id=pid,
            ham_actor=ham_actor,
            meta=meta,
            directive_prefix=directive_prefix,
        )
    if operation == "build_or_create" and quick_preview:
        # Explicit Quick Preview: the internal scaffold runs, but as a preview
        # tool — not the product builder.
        meta["builder_quick_preview"] = True

    summary = maybe_chat_scaffold_for_turn(
        workspace_id=ws,
        project_id=pid,
        session_id=session_id,
        last_user_plain=effective_plain,
        created_by=created_by,
        operation=operation,
        ham_actor=ham_actor,
        model_id=model_id,
    )
    if not summary:
        return None, meta
    meta.update(summary)
    sid = str(summary.get("source_snapshot_id") or "").strip()
    builder_operation = str(summary.get("builder_operation") or operation).strip()
    if summary.get("model_access_required"):
        return (
            f"{directive_prefix}{_model_access_required_message(operation=builder_operation)}",
            meta,
        )
    if summary.get("llm_scaffold_failed"):
        error_code = str(summary.get("llm_scaffold_error_code") or STEP_MODEL_UNAVAILABLE).strip()
        failed_model = str(summary.get("llm_scaffold_failed_model") or "").strip() or None
        return (
            f"{directive_prefix}{_llm_scaffold_failure_message(operation=builder_operation, error_code=error_code, model_slug=failed_model)}",
            meta,
        )
    if summary.get("artifact_verification_failed"):
        ver = summary.get("artifact_verification") or {}
        detail = str(ver.get("reason") or "").strip()
        return (
            f"{directive_prefix}{_artifact_verification_failure_message(operation=builder_operation, detail=detail)}",
            meta,
        )
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
        if meta.get("builder_quick_preview"):
            return (
                f"{directive_prefix}{_QUICK_PREVIEW_ACK}",
                meta,
            )
        return (
            f"{directive_prefix}{_builder_ack_prefix(effective_plain, operation=operation)}",
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
                f"{directive_prefix}"
                "I already applied that update for the active project source and will keep the Workbench in sync.\n\n",
                meta,
            )
        return (
            f"{directive_prefix}"
            "I already prepared this builder project source from your recent prompt and will keep the Workbench in sync.\n\n",
            meta,
        )
    return None, meta
