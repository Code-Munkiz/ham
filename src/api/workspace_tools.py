"""Workspace tool/worker discovery — read-only status endpoint.

Returns a safe list of tools/workers with discovery status.
No secrets, no env dumps, no auto-install, no execution.
Cloud Run must never pretend it scanned the user's local computer.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor

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


class ToolEntry(BaseModel):
    id: str
    label: str
    category: ToolCategory
    status: ToolStatus
    enabled: bool = False
    source: ToolSource
    capabilities: list[str] = Field(default_factory=list)
    setup_hint: Optional[str] = None
    last_checked_at: Optional[str] = None
    safe_actions: list[str] = Field(default_factory=list)


class ToolDiscoveryResponse(BaseModel):
    tools: list[ToolEntry]
    scan_available: bool = False
    scan_hint: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _detect_openrouter_status() -> ToolStatus:
    """Check if OpenRouter is configured (key present) without leaking the key."""
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if key:
        return ToolStatus.ready
    return ToolStatus.needs_sign_in


def _detect_cursor_status() -> ToolStatus:
    """Check if Cursor credentials are available without leaking them."""
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if key:
        return ToolStatus.ready
    try:
        from src.persistence.cursor_credentials import get_effective_cursor_api_key
        saved = get_effective_cursor_api_key()
        if saved:
            return ToolStatus.ready
    except Exception:
        pass
    return ToolStatus.needs_sign_in


def _detect_factory_droid_status() -> ToolStatus:
    """Check if Factory Droid is configured."""
    token = (os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip()
    if token:
        return ToolStatus.ready
    return ToolStatus.unknown


def _detect_comfyui_status() -> ToolStatus:
    """ComfyUI requires local detection; return unknown in cloud mode."""
    return ToolStatus.unknown


def _is_cloud_mode() -> bool:
    """Heuristic: running on Cloud Run or similar hosted environment."""
    return bool(
        os.environ.get("K_SERVICE")
        or os.environ.get("CLOUD_RUN_JOB")
        or os.environ.get("GAE_APPLICATION")
    )


def _build_tool_registry() -> list[ToolEntry]:
    """Build the canonical tool list with safe status detection."""
    now = _now_iso()
    cloud = _is_cloud_mode()

    tools: list[ToolEntry] = [
        ToolEntry(
            id="openrouter",
            label="OpenRouter",
            category=ToolCategory.model,
            status=_detect_openrouter_status(),
            enabled=_detect_openrouter_status() == ToolStatus.ready,
            source=ToolSource.cloud,
            capabilities=["chat", "completions"],
            setup_hint="Add your OpenRouter API key in Settings to enable model access.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="cursor",
            label="Cursor",
            category=ToolCategory.coding,
            status=_detect_cursor_status(),
            enabled=_detect_cursor_status() == ToolStatus.ready,
            source=ToolSource.cloud,
            capabilities=["plan", "edit_code", "run_tests", "open_pr"],
            setup_hint="Add your Cursor API key in Settings to connect.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="factory_droid",
            label="Factory Droid",
            category=ToolCategory.coding,
            status=_detect_factory_droid_status(),
            enabled=_detect_factory_droid_status() == ToolStatus.ready,
            source=ToolSource.cloud,
            capabilities=["edit_code", "run_tests"],
            setup_hint="Configure a Droid execution token to enable.",
            last_checked_at=now,
            safe_actions=["check_status"],
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
            setup_hint="AI Studio integration is not yet available.",
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
            setup_hint="Antigravity integration is not yet available.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="github",
            label="GitHub",
            category=ToolCategory.repo,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["pull_requests", "issues", "actions"],
            setup_hint="Connect this computer to detect GitHub access.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="git",
            label="Git",
            category=ToolCategory.repo,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["version_control"],
            setup_hint="Connect this computer to detect Git.",
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
            setup_hint="Connect this computer to detect Node.",
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
            setup_hint="Connect this computer to detect Python.",
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
            setup_hint="Connect this computer to detect Docker.",
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
            setup_hint="Connect your Vercel account to enable deployments.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="google_cloud",
            label="Google Cloud",
            category=ToolCategory.cloud,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            enabled=False,
            source=ToolSource.cloud,
            capabilities=["deploy", "storage", "compute"],
            setup_hint="Connect your Google Cloud project to enable.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="comfyui",
            label="ComfyUI",
            category=ToolCategory.media,
            status=_detect_comfyui_status(),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["image_generation", "workflows"],
            setup_hint="Connect this computer to detect ComfyUI.",
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
    ]

    return tools


@router.get("/tools")
def workspace_tools(
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    """Read-only tool/worker discovery endpoint.

    Returns status of known tools without leaking secrets or scanning
    the local machine from a cloud context.
    """
    cloud = _is_cloud_mode()
    tools = _build_tool_registry()
    return ToolDiscoveryResponse(
        tools=tools,
        scan_available=not cloud,
        scan_hint="Connect this computer to scan local tools." if cloud else None,
    )
