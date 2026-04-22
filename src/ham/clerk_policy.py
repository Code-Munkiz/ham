"""Map HAM operator phases/intents to required Clerk-derived permissions."""

from __future__ import annotations

from fastapi import HTTPException

from src.ham.clerk_auth import HamActor, clerk_operator_require_auth_enabled

# Minimal HAM permission strings (Clerk custom permissions or org_role fallback).
HAM_PREVIEW = "ham:preview"
HAM_STATUS = "ham:status"
HAM_LAUNCH = "ham:launch"
HAM_ADMIN = "ham:admin"


def actor_has_permission(actor: HamActor, required: str) -> bool:
    if HAM_ADMIN in actor.permissions:
        return True
    return required in actor.permissions


def enforce_operator_permission(actor: HamActor | None, required: str | None) -> None:
    if not clerk_operator_require_auth_enabled():
        return
    if required is None:
        return
    if actor is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "OPERATOR_AUTH_REQUIRED",
                    "message": "Clerk session required for this operator action.",
                }
            },
        )
    if not actor_has_permission(actor, required):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "OPERATOR_FORBIDDEN",
                    "message": f"Missing required permission: {required}",
                }
            },
        )


def permission_for_phase(phase: str | None) -> str | None:
    if phase is None:
        return None
    p = str(phase)
    if p in (
        "cursor_agent_preview",
        "droid_preview",
    ):
        return HAM_PREVIEW
    if p in ("cursor_agent_status",):
        return HAM_STATUS
    if p in (
        "cursor_agent_launch",
        "droid_launch",
        "launch_run",
        "apply_settings",
        "register_project",
    ):
        return HAM_LAUNCH
    return HAM_STATUS


def permission_for_intent(intent: str | None) -> str | None:
    if not intent:
        return None
    if intent in ("cursor_agent_preview", "droid_preview", "update_agents_preview"):
        return HAM_PREVIEW
    if intent in (
        "list_projects",
        "inspect_project",
        "inspect_agents",
        "list_runs",
        "inspect_run",
        "cursor_agent_status",
    ):
        return HAM_STATUS
    if intent in (
        "cursor_agent_launch",
        "droid_launch",
        "launch_run",
        "apply_settings",
        "register_project",
    ):
        return HAM_LAUNCH
    return HAM_STATUS
