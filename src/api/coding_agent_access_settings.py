"""Workspace coding-agent access settings — GET + PATCH.

GET  /api/workspaces/{workspace_id}/coding-agent-access-settings
PATCH /api/workspaces/{workspace_id}/coding-agent-access-settings

Returns (or updates) which coding-agent builders the workspace has enabled
and what preference mode HAM should use when choosing among them.

Hard guarantees:
- No secret values, env variable names, runner URLs, or provider internals
  in request or response bodies.
- Workspace-scoped: one settings document per workspace, readable by any
  workspace member, writable by any workspace member (workspace-level policy,
  not per-user).
- When no settings exist the GET response returns safe defaults.
- PATCH only mutates fields that are explicitly supplied; omitted fields keep
  their stored (or default) values.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from src.api.dependencies.workspace import get_workspace_store, require_perm
from src.ham.coding_router.types import (
    ModelSourcePreference,
    PreferenceMode,
    WorkspaceAgentPolicy,
)
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_perms import PERM_WORKSPACE_READ
from src.persistence.coding_agent_access_settings_store import (
    build_coding_agent_access_settings_store,
    workspace_settings_scope_key,
)
from src.persistence.workspace_store import WorkspaceStore

_LOG = logging.getLogger(__name__)

router = APIRouter(tags=["coding-agent-settings"])

_SETTINGS_STORE = build_coding_agent_access_settings_store()
_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Default values (must match WorkspaceAgentPolicy defaults)
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "allow_factory_droid": True,
    "allow_claude_agent": True,
    "allow_opencode": False,
    "allow_cursor": True,
    "preference_mode": "recommended",
    "model_source_preference": "ham_default",
}

_VALID_PREFERENCE_MODES: frozenset[str] = frozenset(
    ["recommended", "prefer_open_custom", "prefer_premium_reasoning", "prefer_connected_repo"]
)
_VALID_MODEL_SOURCE_PREFS: frozenset[str] = frozenset(
    ["ham_default", "connected_tools_byok", "workspace_default"]
)


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CodingAgentAccessSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_factory_droid: bool | None = None
    allow_claude_agent: bool | None = None
    allow_opencode: bool | None = None
    allow_cursor: bool | None = None
    preference_mode: PreferenceMode | None = None
    model_source_preference: ModelSourcePreference | None = None


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------


def _load_raw(workspace_id: str) -> dict[str, Any]:
    key = workspace_settings_scope_key(workspace_id)
    stored = _SETTINGS_STORE.get_raw(key)
    if not stored:
        return dict(_DEFAULTS)
    merged = dict(_DEFAULTS)
    for field in _DEFAULTS:
        if field in stored:
            merged[field] = stored[field]
    return merged


def _save_raw(workspace_id: str, data: dict[str, Any]) -> None:
    key = workspace_settings_scope_key(workspace_id)
    _SETTINGS_STORE.put_raw(key, data)


def _raw_to_policy(raw: dict[str, Any]) -> WorkspaceAgentPolicy:
    pm = raw.get("preference_mode", "recommended")
    if pm not in _VALID_PREFERENCE_MODES:
        pm = "recommended"
    ms = raw.get("model_source_preference", "ham_default")
    if ms not in _VALID_MODEL_SOURCE_PREFS:
        ms = "ham_default"
    return WorkspaceAgentPolicy(
        allow_factory_droid=bool(raw.get("allow_factory_droid", True)),
        allow_claude_agent=bool(raw.get("allow_claude_agent", True)),
        allow_opencode=bool(raw.get("allow_opencode", False)),
        allow_cursor=bool(raw.get("allow_cursor", True)),
        preference_mode=pm,  # type: ignore[arg-type]
        model_source_preference=ms,  # type: ignore[arg-type]
        updated_at=raw.get("updated_at"),
        updated_by=raw.get("updated_by"),
    )


def _policy_to_response(workspace_id: str, policy: WorkspaceAgentPolicy) -> dict[str, Any]:
    return {
        "kind": "ham_coding_agent_access_settings",
        "workspace_id": workspace_id,
        "allow_factory_droid": policy.allow_factory_droid,
        "allow_claude_agent": policy.allow_claude_agent,
        "allow_opencode": policy.allow_opencode,
        "allow_cursor": policy.allow_cursor,
        "preference_mode": policy.preference_mode,
        "model_source_preference": policy.model_source_preference,
        "updated_at": policy.updated_at,
        "updated_by": policy.updated_by,
    }


def load_workspace_agent_policy(workspace_id: str | None) -> WorkspaceAgentPolicy | None:
    """Load workspace policy for conductor integration.

    Returns ``None`` when ``workspace_id`` is not provided so callers can
    treat absent policy as "use safe defaults" without an extra branch.
    """
    if not workspace_id or not workspace_id.strip():
        return None
    try:
        raw = _load_raw(workspace_id.strip())
        return _raw_to_policy(raw)
    except Exception:  # noqa: BLE001
        _LOG.warning("coding_agent_access_settings load failed for workspace %r", workspace_id)
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/workspaces/{workspace_id}/coding-agent-access-settings")
async def get_coding_agent_access_settings(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Return current (or default) coding-agent access settings for the workspace."""
    _ = store
    raw = _load_raw(ctx.workspace_id)
    policy = _raw_to_policy(raw)
    return _policy_to_response(ctx.workspace_id, policy)


@router.patch("/api/workspaces/{workspace_id}/coding-agent-access-settings")
async def patch_coding_agent_access_settings(
    body: CodingAgentAccessSettingsPatch,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Partially update coding-agent access settings for the workspace.

    Only explicitly supplied fields are mutated; omitted fields keep their
    current values. Returns the complete updated settings.
    """
    _ = store
    raw = _load_raw(ctx.workspace_id)

    patch_data = body.model_dump(exclude_none=True)
    for field_name, value in patch_data.items():
        raw[field_name] = value

    now = datetime.now(tz=UTC).isoformat()
    raw["updated_at"] = now
    raw["updated_by"] = ctx.actor_user_id or "unknown"
    raw["schema_version"] = _SCHEMA_VERSION

    _save_raw(ctx.workspace_id, raw)
    policy = _raw_to_policy(raw)

    _LOG.info(
        "coding_agent_access_settings patched: workspace=%s allow_factory_droid=%s "
        "allow_claude_agent=%s allow_opencode=%s allow_cursor=%s preference_mode=%s",
        ctx.workspace_id,
        policy.allow_factory_droid,
        policy.allow_claude_agent,
        policy.allow_opencode,
        policy.allow_cursor,
        policy.preference_mode,
    )

    return _policy_to_response(ctx.workspace_id, policy)


__all__ = [
    "load_workspace_agent_policy",
    "router",
]
