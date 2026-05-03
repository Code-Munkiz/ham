"""Workspace tool/worker discovery — status + safe connect contracts (MVP).

Returns a safe list of tools/workers with discovery status.
No secrets, no env dumps, no auto-install, no real execution from this module.
Cloud Run must never pretend it scanned the user's local computer.

Connect: Cursor API keys may be persisted via the existing file-backed store
(``src.persistence.cursor_credentials``). Other tools return a blocked response until
secure storage exists — the UI must not fake success.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.models_catalog import build_catalog_payload
from src.ham.worker_adapters.claude_agent_adapter import (
    check_claude_agent_readiness,
    reset_claude_agent_readiness_cache,
)
from src.ham.worker_adapters.cursor_adapter import check_cursor_readiness
from src.llm_client import normalized_openrouter_api_key, openrouter_api_key_is_plausible
from src.persistence.cursor_credentials import (
    clear_saved_cursor_api_key,
    get_effective_cursor_api_key,
    mask_api_key_preview,
    save_cursor_api_key,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class ToolStatus(str, Enum):
    ready = "ready"
    needs_sign_in = "needs_sign_in"
    not_found = "not_found"
    off = "off"
    error = "error"
    unknown = "unknown"


class ToolSource(str, Enum):
    cloud = "cloud"
    this_computer = "this_computer"
    built_in = "built_in"
    unknown = "unknown"


class ToolCategory(str, Enum):
    coding = "coding"
    cloud = "cloud"
    local_tool = "local_tool"
    media = "media"
    repo = "repo"
    deploy = "deploy"
    model = "model"


class ConnectKind(str, Enum):
    none = "none"
    api_key = "api_key"
    access_token = "access_token"
    local_scan = "local_scan"
    coming_soon = "coming_soon"


class ToolEntry(BaseModel):
    id: str
    label: str
    category: ToolCategory
    status: ToolStatus
    enabled: bool = False
    source: ToolSource
    capabilities: list[str] = Field(default_factory=list)
    setup_hint: Optional[str] = None
    connect_kind: ConnectKind = ConnectKind.none
    connected_account_label: Optional[str] = None
    credential_preview: Optional[str] = None
    last_checked_at: Optional[str] = None
    safe_actions: list[str] = Field(default_factory=list)
    version: Optional[str] = None


class ToolDiscoveryResponse(BaseModel):
    tools: list[ToolEntry]
    scan_available: bool = False
    scan_hint: Optional[str] = None


class ToolConnectBody(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=8192)
    access_token: Optional[str] = Field(default=None, max_length=8192)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_cloud_mode() -> bool:
    return bool(
        os.environ.get("K_SERVICE")
        or os.environ.get("CLOUD_RUN_JOB")
        or os.environ.get("GAE_APPLICATION")
    )


def _openrouter_chat_ready_from_catalog() -> bool:
    try:
        catalog = build_catalog_payload()
        return bool(catalog.get("openrouter_chat_ready"))
    except Exception:
        return False


def _openrouter_status() -> ToolStatus:
    if _openrouter_chat_ready_from_catalog():
        return ToolStatus.ready
    raw = normalized_openrouter_api_key()
    if raw and openrouter_api_key_is_plausible(raw):
        return ToolStatus.ready
    return ToolStatus.needs_sign_in


def _openrouter_credential_preview() -> Optional[str]:
    raw = normalized_openrouter_api_key()
    if not raw or not openrouter_api_key_is_plausible(raw):
        return None
    return mask_api_key_preview(raw)


def _cursor_status() -> ToolStatus:
    readiness = check_cursor_readiness()
    if readiness.status == "ready":
        return ToolStatus.ready
    if readiness.status == "unavailable":
        return ToolStatus.needs_sign_in
    return ToolStatus.needs_sign_in


def _cursor_credential_preview() -> Optional[str]:
    key = get_effective_cursor_api_key()
    if not key:
        return None
    return mask_api_key_preview(key)


def _factory_droid_status() -> ToolStatus:
    token = (os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip()
    if token:
        return ToolStatus.ready
    return ToolStatus.unknown


def _github_status(cloud: bool) -> ToolStatus:
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        return ToolStatus.ready
    if cloud:
        return ToolStatus.unknown
    return ToolStatus.not_found


_CLAUDE_AGENT_HINTS: dict[ToolStatus, str] = {
    ToolStatus.not_found: "Claude isn't installed on this server yet.",
    ToolStatus.needs_sign_in: (
        "Set ANTHROPIC_API_KEY, or configure Bedrock/Vertex credentials "
        "on the server, to enable Claude."
    ),
    ToolStatus.ready: "Connected. Execution stays disabled in this release.",
    ToolStatus.error: "Claude detection hit an unexpected error.",
}


def _claude_agent_status_and_meta() -> tuple[ToolStatus, Optional[str], Optional[str]]:
    """Map adapter readiness → (ToolStatus, setup_hint, sdk_version).

    Never returns auth values. Swallows unexpected exceptions and reports
    them as ToolStatus.error so the registry never fails to build.
    """
    try:
        readiness = check_claude_agent_readiness()
    except Exception:
        return ToolStatus.error, _CLAUDE_AGENT_HINTS[ToolStatus.error], None

    if readiness.status == "ready":
        status = ToolStatus.ready
    elif readiness.status == "needs_sign_in":
        status = ToolStatus.needs_sign_in
    else:
        status = ToolStatus.not_found

    return status, _CLAUDE_AGENT_HINTS.get(status), readiness.sdk_version


def _comfyui_status(cloud: bool) -> ToolStatus:
    try:
        from src.ham.comfyui_provider_adapter import (
            comfyui_base_url_configured,
            comfyui_image_generation_ready,
        )
    except Exception:
        return ToolStatus.unknown

    if comfyui_image_generation_ready():
        return ToolStatus.ready
    if comfyui_base_url_configured():
        return ToolStatus.needs_sign_in
    if cloud:
        return ToolStatus.unknown
    return ToolStatus.not_found


def _tool_enabled_for_status(status: ToolStatus) -> bool:
    """Default toggle: only clearly ready tools start On for HAM preferences."""
    return status == ToolStatus.ready


def _build_tool_registry() -> list[ToolEntry]:
    """Build the canonical tool list with safe status detection."""
    now = _now_iso()
    cloud = _is_cloud_mode()

    or_status = _openrouter_status()
    cur_status = _cursor_status()
    fd_status = _factory_droid_status()
    gh_status = _github_status(cloud)
    cf_status = _comfyui_status(cloud)
    claude_agent_status, claude_agent_hint, claude_agent_version = (
        _claude_agent_status_and_meta()
    )

    tools: list[ToolEntry] = [
        ToolEntry(
            id="openrouter",
            label="OpenRouter",
            category=ToolCategory.model,
            status=or_status,
            enabled=_tool_enabled_for_status(or_status),
            source=ToolSource.cloud,
            capabilities=["chat", "completions"],
            setup_hint="Add your key in Settings or connect here when storage is available.",
            connect_kind=ConnectKind.api_key,
            credential_preview=_openrouter_credential_preview(),
            last_checked_at=now,
            safe_actions=["check_status", "connect"],
        ),
        ToolEntry(
            id="cursor",
            label="Cursor",
            category=ToolCategory.coding,
            status=cur_status,
            enabled=_tool_enabled_for_status(cur_status),
            source=ToolSource.cloud,
            capabilities=["plan", "edit_code", "run_tests", "open_pr"],
            setup_hint="Sign-in checks your saved key. Automated runs stay off in this release.",
            connect_kind=ConnectKind.api_key,
            credential_preview=_cursor_credential_preview(),
            last_checked_at=now,
            safe_actions=["check_status", "connect", "disconnect"],
        ),
        ToolEntry(
            id="factory_droid",
            label="Factory Droid",
            category=ToolCategory.coding,
            status=fd_status,
            enabled=_tool_enabled_for_status(fd_status),
            source=ToolSource.cloud,
            capabilities=["edit_code", "run_tests"],
            setup_hint="Configure a Droid execution token to enable.",
            connect_kind=ConnectKind.api_key,
            last_checked_at=now,
            safe_actions=["check_status", "connect"],
        ),
        ToolEntry(
            id="claude_code",
            label="Claude Code",
            category=ToolCategory.coding,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["plan", "edit_code", "run_tests"],
            setup_hint="Install Claude Code on this computer to connect.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="claude_agent_sdk",
            label="Claude Agent",
            category=ToolCategory.coding,
            status=claude_agent_status,
            enabled=_tool_enabled_for_status(claude_agent_status),
            source=ToolSource.cloud,
            capabilities=["plan", "edit_code", "run_tests"],
            setup_hint=claude_agent_hint,
            connect_kind=ConnectKind.api_key,
            version=claude_agent_version,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="openclaw",
            label="OpenClaw",
            category=ToolCategory.coding,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["plan", "edit_code"],
            setup_hint="Install OpenClaw on this computer to connect.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="ai_studio",
            label="AI Studio",
            category=ToolCategory.model,
            status=ToolStatus.unknown,
            enabled=False,
            source=ToolSource.cloud,
            capabilities=[],
            setup_hint="Discovery only in this release.",
            connect_kind=ConnectKind.coming_soon,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="antigravity",
            label="Antigravity",
            category=ToolCategory.coding,
            status=ToolStatus.unknown,
            enabled=False,
            source=ToolSource.unknown,
            capabilities=[],
            setup_hint="Discovery only in this release.",
            connect_kind=ConnectKind.coming_soon,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="github",
            label="GitHub",
            category=ToolCategory.repo,
            status=gh_status,
            enabled=_tool_enabled_for_status(gh_status),
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["pull_requests", "issues", "actions"],
            setup_hint="Connect with an access token when storage is available.",
            connect_kind=ConnectKind.access_token,
            last_checked_at=now,
            safe_actions=["check_status", "connect"],
        ),
        ToolEntry(
            id="git",
            label="Git",
            category=ToolCategory.repo,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["version_control"],
            setup_hint="Not found on this computer. Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="node",
            label="Node",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["run_scripts", "package_management"],
            setup_hint="Not found on this computer. Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="python",
            label="Python",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["run_scripts", "package_management"],
            setup_hint="Not found on this computer. Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="docker",
            label="Docker",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["containers", "images"],
            setup_hint="Not found on this computer. Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="vercel",
            label="Vercel",
            category=ToolCategory.deploy,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.cloud,
            capabilities=["deploy", "preview"],
            setup_hint="Connect with a token when storage is available.",
            connect_kind=ConnectKind.api_key,
            last_checked_at=now,
            safe_actions=["check_status", "connect"],
        ),
        ToolEntry(
            id="google_cloud",
            label="Google Cloud",
            category=ToolCategory.cloud,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.cloud,
            capabilities=["deploy", "storage", "compute"],
            setup_hint="Connect coming later.",
            connect_kind=ConnectKind.coming_soon,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="comfyui",
            label="ComfyUI",
            category=ToolCategory.media,
            status=cf_status,
            enabled=_tool_enabled_for_status(cf_status),
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["image_generation", "workflows"],
            setup_hint="Point HAM at your Comfy service in Settings, or connect this computer.",
            connect_kind=ConnectKind.api_key,
            last_checked_at=now,
            safe_actions=["check_status", "connect"],
        ),
    ]

    return tools


@router.get("/tools")
def workspace_tools(
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    """Tool/worker discovery and safe status."""
    cloud = _is_cloud_mode()
    tools = _build_tool_registry()
    return ToolDiscoveryResponse(
        tools=tools,
        scan_available=not cloud,
        scan_hint="Connect this computer to scan local tools." if cloud else None,
    )


@router.post("/tools/scan")
def workspace_tools_scan(
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    """Refresh discovery snapshot (no local exec).

    Invalidates per-adapter detection caches so a freshly installed SDK
    or a new env var becomes visible without a server restart.
    """
    reset_claude_agent_readiness_cache()
    return workspace_tools(_actor)  # type: ignore[arg-type]


@router.post("/tools/{tool_id}/connect")
def workspace_tool_connect(
    tool_id: str,
    body: ToolConnectBody,
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    """Persist credentials only where a safe store exists; otherwise return a clear error."""
    known = {t.id for t in _build_tool_registry()}
    if tool_id not in known:
        raise HTTPException(status_code=404, detail="Unknown tool.")

    secret = (body.api_key or body.access_token or "").strip()
    if tool_id == "cursor":
        if not secret:
            raise HTTPException(status_code=400, detail="Missing API key.")
        try:
            save_cursor_api_key(secret)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        _LOG.info("cursor tool connect: saved credentials (key not logged)")
        return workspace_tools(_actor)  # type: ignore[arg-type]

    raise HTTPException(
        status_code=501,
        detail={
            "code": "SECURE_STORAGE_NOT_READY",
            "message": "Secure key storage is coming next.",
        },
    )


@router.post("/tools/{tool_id}/disconnect")
def workspace_tool_disconnect(
    tool_id: str,
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    """Remove saved credentials where supported."""
    known = {t.id for t in _build_tool_registry()}
    if tool_id not in known:
        raise HTTPException(status_code=404, detail="Unknown tool.")

    if tool_id == "cursor":
        clear_saved_cursor_api_key()
        _LOG.info("cursor tool disconnect: cleared saved file if present")
        return workspace_tools(_actor)  # type: ignore[arg-type]

    raise HTTPException(
        status_code=501,
        detail={
            "code": "SECURE_STORAGE_NOT_READY",
            "message": "Disconnect for this tool is not available yet.",
        },
    )
