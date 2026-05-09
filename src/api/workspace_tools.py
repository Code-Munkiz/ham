"""Workspace tool/worker discovery — status + connect/disconnect (MVP).

Returns a safe list of tools/workers with discovery status.
No secrets, no env dumps, no auto-install.

API keys for selected tools are persisted **server-side only**. When workspace
Firestore is enabled, Connected Tools secrets are encrypted (Fernet) in the
``connected_tool_credentials`` collection keyed by Clerk user id — never in
plaintext in Firestore, never returned by the HTTP API.

Local dev fallback (``HAM_CONNECTED_TOOLS_CREDENTIAL_BACKEND=file``) continues
plain file-backed storage under ``~/.ham/workspace_tool_credentials.json``.

**Cursor Connected Tool** stores the Cursor API key in the server/instance ``cursor_credentials``
file (platform-scoped); it is **not** partitioned per Clerk user. Per-user SaaS isolation
claims apply to Firestore-backed tools (OpenRouter, GitHub, Claude Agent, OpenAI transcription),
not Cursor, until migrated.

Internal-only (optional): gated ``POST /api/workspace/tools/claude_agent_sdk/smoke``
when ``HAM_CLAUDE_AGENT_SMOKE_ENABLED`` is on; not linked from the default
dashboard UI.

Product path: ``POST /api/workspace/tools/claude_agent_sdk/mission`` requires
Clerk session (when Clerk auth is enabled for this deployment), plus Clerk-scoped
Connected Tools / runtime Anthropic auth (Firestore encrypted credential, legacy
local file credential, Bedrock / Vertex routing, or bootstrap env). Does not use
``X-HAM-SMOKE-TOKEN`` or smoke flags for this route.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.models_catalog import build_catalog_payload
from src.ham.clerk_auth import HamActor, clerk_authorization_is_clerk_session
from src.ham.workspace_tool_key_validation import (
    validate_anthropic_api_key,
    validate_cursor_api_key,
    validate_github_token,
    validate_openai_transcription_api_key,
    validate_openrouter_api_key,
)
from src.ham.worker_adapters.claude_agent_adapter import (
    check_claude_agent_readiness,
    claude_agent_mission_auth_configured,
    claude_agent_smoke_feature_enabled,
    claude_agent_smoke_route_armed,
    reset_claude_agent_readiness_cache,
    run_claude_agent_sdk_mission,
    run_claude_agent_sdk_smoke,
)
from src.ham.worker_adapters.cursor_adapter import check_cursor_readiness
from src.llm_client import normalized_openrouter_api_key, openrouter_api_key_is_plausible
from src.persistence.connected_tool_credentials import (
    ConnectedCredentialSaveFailed,
    connected_tools_credentials_use_firestore,
    delete_connected_tool_secret,
    get_connected_tool_masked_preview,
    has_connected_tool_credential_record,
    save_connected_tool_secret,
)
from src.persistence.cursor_credentials import (
    clear_saved_cursor_api_key,
    get_effective_cursor_api_key,
    mask_api_key_preview,
    save_cursor_api_key,
)
from src.persistence.workspace_tool_credentials import get_effective_github_token


def _credential_store_requires_clerk(actor: HamActor | None) -> bool:
    if not connected_tools_credentials_use_firestore():
        return False
    return actor is None

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

TOOL_CONNECT_HELP: dict[str, dict[str, str]] = {
    "openrouter": {
        "label": "Get your OpenRouter API key",
        "url": "https://openrouter.ai/keys",
    },
    "claude_agent_sdk": {
        "label": "Get your Anthropic API key",
        "url": "https://console.anthropic.com/settings/keys",
    },
    "github": {
        "label": "Create a GitHub fine-grained token",
        "url": (
            "https://docs.github.com/en/authentication/"
            "keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
            "#creating-a-fine-grained-personal-access-token"
        ),
    },
    "cursor": {
        "label": "Get your Cursor API key",
        "url": "https://cursor.com/docs/cloud-agent/api",
    },
    "openai_transcription": {
        "label": "Create an OpenAI API key",
        "url": "https://platform.openai.com/api-keys",
    },
}

INVALID_KEY_MESSAGE = (
    "That key did not work. Check that it is copied correctly and has the "
    "required permissions."
)


class ToolStatus(str, Enum):
    ready = "ready"
    needs_sign_in = "needs_sign_in"
    not_found = "not_found"
    off = "off"
    error = "error"
    unknown = "unknown"


class ToolConnection(str, Enum):
    on = "on"
    off = "off"
    error = "error"


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
    connection: ToolConnection
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


class ToolConnectHelpModel(BaseModel):
    label: str
    url: str


class ToolConnectSuccessResponse(BaseModel):
    ok: Literal[True] = True
    status: Literal["on"] = "on"
    credential_preview: str
    message: str = "Connected"


class ToolConnectFailResponse(BaseModel):
    ok: Literal[False] = False
    status: Literal["off"] = "off"
    error_code: str
    message: str
    help: Optional[ToolConnectHelpModel] = None


class ToolDisconnectSuccessResponse(BaseModel):
    ok: Literal[True] = True
    status: Literal["off"] = "off"
    message: str = "Disconnected"


class ClaudeAgentSmokeHttpResponse(BaseModel):
    """Internal smoke outcome — no env dumps, keys, or user-supplied secrets."""

    status: Literal["ok", "error"]
    provider: str
    sdk_available: bool
    authenticated: bool
    smoke_ok: bool
    response_text: str
    blocker: Optional[str] = None


class ClaudeAgentMissionHttpResponse(BaseModel):
    """Bounded mission outcome — fixed prompt only; no arbitrary user input."""

    ok: bool
    mission_ok: bool
    worker: str
    mission_type: str
    result_text: str
    parsed_result: Optional[dict[str, Any]] = None
    duration_ms: int
    safety_mode: str
    blocker: Optional[str] = None


def _connection_for_status(status: ToolStatus) -> ToolConnection:
    if status == ToolStatus.error:
        return ToolConnection.error
    if status == ToolStatus.ready:
        return ToolConnection.on
    return ToolConnection.off


def _help(tool_id: str) -> ToolConnectHelpModel | None:
    h = TOOL_CONNECT_HELP.get(tool_id)
    if not h:
        return None
    return ToolConnectHelpModel(label=h["label"], url=h["url"])


def _invalid_key_response(tool_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ToolConnectFailResponse(
            error_code="INVALID_KEY",
            message=INVALID_KEY_MESSAGE,
            help=_help(tool_id),
        ).model_dump(),
    )


def _authorize_claude_agent_smoke(actor: HamActor | None, x_ham_smoke_token: str | None) -> None:
    if not claude_agent_smoke_feature_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    if not claude_agent_smoke_route_armed():
        raise HTTPException(
            status_code=404,
            detail="Claude Agent internal check is not configured.",
        )
    if clerk_authorization_is_clerk_session():
        if actor is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "CLERK_SESSION_REQUIRED",
                    "message": (
                        "Authorization: Bearer <Clerk session JWT> required when "
                        "Clerk session auth is enabled for this deployment."
                    ),
                },
            )
        return
    expected = (os.environ.get("HAM_CLAUDE_AGENT_SMOKE_TOKEN") or "").strip()
    got = (x_ham_smoke_token or "").strip()
    if not got or not expected or len(got) != len(expected):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INTERNAL_CHECK_AUTH_REQUIRED",
                "message": (
                    "Valid X-HAM-SMOKE-TOKEN required when Clerk session auth is not enabled."
                ),
            },
        )
    if not secrets.compare_digest(got, expected):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INTERNAL_CHECK_AUTH_REQUIRED",
                "message": (
                    "Valid X-HAM-SMOKE-TOKEN required when Clerk session auth is not enabled."
                ),
            },
        )


def _authorize_claude_agent_mission(actor: HamActor | None) -> None:
    """Clerk session + Anthropic auth signal (Connected Tools SSOT, optional legacy env / cloud)."""
    if not clerk_authorization_is_clerk_session():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CLERK_AUTH_NOT_CONFIGURED_FOR_MISSION",
                "message": (
                    "Enable HAM_CLERK_REQUIRE_AUTH or HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS so "
                    "Claude Agent missions can require a signed-in user."
                ),
            },
        )
    if actor is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CLERK_SESSION_REQUIRED",
                    "message": (
                        "Authorization: Bearer <Clerk session JWT> required for "
                        "Claude Agent missions."
                    ),
                },
            },
        )
    if not claude_agent_mission_auth_configured(actor):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONNECT_CLAUDE_AGENT_REQUIRED",
                "message": "Connect Claude Agent first.",
            },
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_cloud_mode() -> bool:
    return bool(
        os.environ.get("K_SERVICE")
        or os.environ.get("CLOUD_RUN_JOB")
        or os.environ.get("GAE_APPLICATION")
    )


def _openrouter_chat_ready_from_catalog(actor: HamActor | None = None) -> bool:
    try:
        catalog = build_catalog_payload(ham_actor=actor)
        if bool(catalog.get("openrouter_chat_ready")):
            return True
        return bool(catalog.get("openrouter_user_byok_connected"))
    except Exception:
        return False


def _openrouter_status(actor: HamActor | None = None) -> ToolStatus:
    if actor and has_connected_tool_credential_record(actor, "openrouter"):
        return ToolStatus.ready
    if _openrouter_chat_ready_from_catalog(actor):
        return ToolStatus.ready
    raw = normalized_openrouter_api_key()
    if raw and openrouter_api_key_is_plausible(raw):
        return ToolStatus.ready
    return ToolStatus.needs_sign_in


def _openrouter_credential_preview(actor: HamActor | None) -> Optional[str]:
    prev = get_connected_tool_masked_preview(actor, "openrouter")
    if prev:
        return prev
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


def _github_status(cloud: bool, actor: HamActor | None = None) -> ToolStatus:
    if actor and has_connected_tool_credential_record(actor, "github"):
        return ToolStatus.ready
    token = get_effective_github_token()
    if token.strip():
        return ToolStatus.ready
    if cloud:
        return ToolStatus.unknown
    return ToolStatus.not_found


def _github_credential_preview(actor: HamActor | None) -> Optional[str]:
    t = get_connected_tool_masked_preview(actor, "github")
    if t:
        return t
    raw = get_effective_github_token()
    if not raw:
        return None
    return mask_api_key_preview(raw)


def _claude_agent_status_and_meta(actor: HamActor | None) -> tuple[ToolStatus, Optional[str], Optional[str]]:
    """Map adapter readiness + workspace-stored user key → (ToolStatus, setup_hint, sdk_version)."""
    try:
        readiness = check_claude_agent_readiness(actor)
    except Exception:
        return (
            ToolStatus.error,
            "Something went wrong while checking Claude Agent.",
            None,
        )

    has_user_cred = has_connected_tool_credential_record(actor, "claude_agent_sdk")

    if not readiness.sdk_available:
        return (
            ToolStatus.not_found,
            "Install Claude Agent on this server, then paste your API key to connect.",
            readiness.sdk_version,
        )

    if has_user_cred:
        return (
            ToolStatus.ready,
            "Claude Agent is connected.",
            readiness.sdk_version,
        )

    if readiness.status == "ready":
        return (
            ToolStatus.ready,
            "Claude Agent is connected.",
            readiness.sdk_version,
        )
    if readiness.status == "needs_sign_in":
        return (
            ToolStatus.needs_sign_in,
            "Paste your Anthropic API key to connect.",
            readiness.sdk_version,
        )
    return (
        ToolStatus.not_found,
        "Install Claude Agent on this server, then paste your API key to connect.",
        readiness.sdk_version,
    )


def _comfyui_status(cloud: bool) -> ToolStatus:
    try:
        from src.ham.comfyui_provider_adapter import (  # noqa: PLC0415
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


def _openai_transcription_tool_status(actor: HamActor | None = None) -> ToolStatus:
    """User BYOK ``openai_transcription`` credential (``/api/chat/transcribe``)."""
    if actor and has_connected_tool_credential_record(actor, "openai_transcription"):
        return ToolStatus.ready
    return ToolStatus.needs_sign_in


def _tool_enabled_for_status(status: ToolStatus) -> bool:
    return status == ToolStatus.ready


def _build_tool_registry(actor: HamActor | None = None) -> list[ToolEntry]:
    now = _now_iso()
    cloud = _is_cloud_mode()

    or_status = _openrouter_status(actor)
    cur_status = _cursor_status()
    fd_status = _factory_droid_status()
    gh_status = _github_status(cloud, actor)
    cf_status = _comfyui_status(cloud)
    claude_agent_status, claude_agent_hint, claude_agent_version = _claude_agent_status_and_meta(
        actor,
    )
    oai_stt_status = _openai_transcription_tool_status(actor)

    tools: list[ToolEntry] = [
        ToolEntry(
            id="openrouter",
            label="OpenRouter",
            category=ToolCategory.model,
            status=or_status,
            connection=_connection_for_status(or_status),
            enabled=_tool_enabled_for_status(or_status),
            source=ToolSource.cloud,
            capabilities=["chat", "completions"],
            setup_hint="Cloud models for chat when this is connected.",
            connect_kind=ConnectKind.api_key,
            credential_preview=_openrouter_credential_preview(actor),
            last_checked_at=now,
            safe_actions=["check_status", "connect", "disconnect"],
        ),
        ToolEntry(
            id="cursor",
            label="Cursor",
            category=ToolCategory.coding,
            status=cur_status,
            connection=_connection_for_status(cur_status),
            enabled=_tool_enabled_for_status(cur_status),
            source=ToolSource.cloud,
            capabilities=["plan", "edit_code", "run_tests", "open_pr"],
            setup_hint="Cursor Cloud Agents from HAM when connected.",
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
            connection=_connection_for_status(fd_status),
            enabled=_tool_enabled_for_status(fd_status),
            source=ToolSource.cloud,
            capabilities=["edit_code", "run_tests"],
            setup_hint="Uses server configuration. If it stays off, ask your admin.",
            connect_kind=ConnectKind.none,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="claude_code",
            label="Claude Code",
            category=ToolCategory.coding,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["plan", "edit_code", "run_tests"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="claude_agent_sdk",
            label="Claude Agent",
            category=ToolCategory.coding,
            status=claude_agent_status,
            connection=_connection_for_status(claude_agent_status),
            enabled=_tool_enabled_for_status(claude_agent_status),
            source=ToolSource.cloud,
            capabilities=["plan", "edit_code", "run_tests"],
            setup_hint=claude_agent_hint,
            connect_kind=ConnectKind.api_key,
            version=claude_agent_version,
            credential_preview=get_connected_tool_masked_preview(actor, "claude_agent_sdk"),
            last_checked_at=now,
            safe_actions=["check_status", "connect", "disconnect"],
        ),
        ToolEntry(
            id="openai_transcription",
            label="OpenAI (transcription)",
            category=ToolCategory.media,
            status=oai_stt_status,
            connection=_connection_for_status(oai_stt_status),
            enabled=_tool_enabled_for_status(oai_stt_status),
            source=ToolSource.cloud,
            capabilities=["speech_to_text"],
            setup_hint="Paste an OpenAI API key for server-side speech-to-text.",
            connect_kind=ConnectKind.api_key,
            credential_preview=get_connected_tool_masked_preview(actor, "openai_transcription"),
            last_checked_at=now,
            safe_actions=["check_status", "connect", "disconnect"],
        ),
        ToolEntry(
            id="openclaw",
            label="OpenClaw",
            category=ToolCategory.coding,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["plan", "edit_code"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="ai_studio",
            label="AI Studio",
            category=ToolCategory.model,
            status=ToolStatus.unknown,
            connection=ToolConnection.off,
            enabled=False,
            source=ToolSource.cloud,
            capabilities=[],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="antigravity",
            label="Antigravity",
            category=ToolCategory.coding,
            status=ToolStatus.unknown,
            connection=ToolConnection.off,
            enabled=False,
            source=ToolSource.unknown,
            capabilities=[],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="github",
            label="GitHub",
            category=ToolCategory.repo,
            status=gh_status,
            connection=_connection_for_status(gh_status),
            enabled=_tool_enabled_for_status(gh_status),
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["pull_requests", "issues", "actions"],
            setup_hint="Paste a token so HAM can reach your GitHub repositories.",
            connect_kind=ConnectKind.access_token,
            credential_preview=_github_credential_preview(actor),
            last_checked_at=now,
            safe_actions=["check_status", "connect", "disconnect"],
        ),
        ToolEntry(
            id="git",
            label="Git",
            category=ToolCategory.repo,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["version_control"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="node",
            label="Node",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["run_scripts", "package_management"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="python",
            label="Python",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["run_scripts", "package_management"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="docker",
            label="Docker",
            category=ToolCategory.local_tool,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["containers", "images"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="vercel",
            label="Vercel",
            category=ToolCategory.deploy,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.cloud,
            capabilities=["deploy", "preview"],
            setup_hint="Connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="google_cloud",
            label="Google Cloud",
            category=ToolCategory.cloud,
            status=ToolStatus.unknown if cloud else ToolStatus.not_found,
            connection=_connection_for_status(
                ToolStatus.unknown if cloud else ToolStatus.not_found,
            ),
            enabled=False,
            source=ToolSource.cloud,
            capabilities=["deploy", "storage", "compute"],
            setup_hint="Connect later from settings when available.",
            connect_kind=ConnectKind.coming_soon,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
        ToolEntry(
            id="comfyui",
            label="ComfyUI",
            category=ToolCategory.media,
            status=cf_status,
            connection=_connection_for_status(cf_status),
            enabled=_tool_enabled_for_status(cf_status),
            source=ToolSource.this_computer if not cloud else ToolSource.unknown,
            capabilities=["image_generation", "workflows"],
            setup_hint="Configure ComfyUI in settings, or connect this computer and scan again.",
            connect_kind=ConnectKind.local_scan,
            last_checked_at=now,
            safe_actions=["check_status"],
        ),
    ]

    return tools


@router.get("/tools")
def workspace_tools(
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    actor = _actor if isinstance(_actor, HamActor) else None
    cloud = _is_cloud_mode()
    tools = _build_tool_registry(actor)
    return ToolDiscoveryResponse(
        tools=tools,
        scan_available=not cloud,
        scan_hint="Cloud workspaces cannot scan this computer. Use a local HAM install to detect local tools."
        if cloud
        else None,
    )


@router.post("/tools/scan")
def workspace_tools_scan(
    _actor: object = Depends(get_ham_clerk_actor),
) -> ToolDiscoveryResponse:
    reset_claude_agent_readiness_cache()
    return workspace_tools(_actor)  # type: ignore[arg-type]


@router.post("/tools/claude_agent_sdk/smoke", response_model=ClaudeAgentSmokeHttpResponse)
async def workspace_claude_agent_smoke(
    actor: HamActor | None = Depends(get_ham_clerk_actor),
    x_ham_smoke_token: str | None = Header(default=None, alias="X-HAM-SMOKE-TOKEN"),
) -> ClaudeAgentSmokeHttpResponse:
    """Internal server-side Claude Agent check (feature-flag + auth gated)."""
    _authorize_claude_agent_smoke(actor, x_ham_smoke_token)
    result = await run_claude_agent_sdk_smoke(actor)
    return ClaudeAgentSmokeHttpResponse(
        status=result.status,
        provider=result.provider,
        sdk_available=result.sdk_available,
        authenticated=result.authenticated,
        smoke_ok=result.smoke_ok,
        response_text=result.response_text,
        blocker=result.blocker,
    )


@router.post("/tools/claude_agent_sdk/mission", response_model=ClaudeAgentMissionHttpResponse)
async def workspace_claude_agent_mission(
    actor: HamActor | None = Depends(get_ham_clerk_actor),
) -> ClaudeAgentMissionHttpResponse:
    """Fixed bounded mission — Clerk + Connected Tools auth; not user-prompt driven."""
    _authorize_claude_agent_mission(actor)
    result = await run_claude_agent_sdk_mission(actor)
    return ClaudeAgentMissionHttpResponse(
        ok=result.ok,
        mission_ok=result.mission_ok,
        worker=result.worker,
        mission_type=result.mission_type,
        result_text=result.result_text,
        parsed_result=result.parsed_result,
        duration_ms=result.duration_ms,
        safety_mode=result.safety_mode,
        blocker=result.blocker,
    )


def _connect_not_supported_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ToolConnectFailResponse(
            error_code="NOT_SUPPORTED",
            message="This tool cannot be connected here yet.",
            help=None,
        ).model_dump(),
    )


@router.post("/tools/{tool_id}/connect")
def workspace_tool_connect(
    tool_id: str,
    body: ToolConnectBody,
    _actor: object = Depends(get_ham_clerk_actor),
) -> Any:
    actor = _actor if isinstance(_actor, HamActor) else None
    known = {t.id for t in _build_tool_registry(None)}
    if tool_id not in known:
        raise HTTPException(status_code=404, detail="Unknown tool.")

    secret = (body.api_key or body.access_token or "").strip()
    supported = {"openrouter", "github", "claude_agent_sdk", "cursor", "openai_transcription"}

    if tool_id not in supported:
        return _connect_not_supported_response()

    if not secret:
        return JSONResponse(
            status_code=400,
            content=ToolConnectFailResponse(
                error_code="MISSING_KEY",
                message="Paste your key, then try Connect.",
                help=_help(tool_id),
            ).model_dump(),
        )

    if _credential_store_requires_clerk(actor):
        return JSONResponse(
            status_code=401,
            content=ToolConnectFailResponse(
                error_code="CLERK_SESSION_REQUIRED",
                message="Sign in again, then reconnect this tool.",
                help=_help(tool_id),
            ).model_dump(),
        )

    if tool_id == "openrouter":
        if not validate_openrouter_api_key(secret):
            _LOG.info("openrouter tool connect: validation failed (key not logged)")
            return _invalid_key_response(tool_id)
        try:
            prev = save_connected_tool_secret(actor, "openrouter", secret)
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not save this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("openrouter tool connect: saved (key not logged)")
        return ToolConnectSuccessResponse(credential_preview=prev)

    if tool_id == "github":
        if not validate_github_token(secret):
            _LOG.info("github tool connect: validation failed (token not logged)")
            return _invalid_key_response(tool_id)
        try:
            prev = save_connected_tool_secret(actor, "github", secret)
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not save this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("github tool connect: saved (token not logged)")
        return ToolConnectSuccessResponse(credential_preview=prev)

    if tool_id == "claude_agent_sdk":
        readiness = check_claude_agent_readiness(actor)
        if not readiness.sdk_available:
            return JSONResponse(
                status_code=400,
                content=ToolConnectFailResponse(
                    error_code="SETUP_REQUIRED",
                    message=(
                        "Claude Agent is not installed on this server yet. "
                        "Ask your admin to install it, then try again."
                    ),
                    help=_help(tool_id),
                ).model_dump(),
            )
        if not validate_anthropic_api_key(secret):
            _LOG.info("claude_agent_sdk connect: validation failed (key not logged)")
            return _invalid_key_response(tool_id)
        try:
            prev = save_connected_tool_secret(actor, "claude_agent_sdk", secret)
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not save this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        reset_claude_agent_readiness_cache()
        _LOG.info("claude_agent_sdk connect: saved (key not logged)")
        return ToolConnectSuccessResponse(credential_preview=prev)

    if tool_id == "openai_transcription":
        if not validate_openai_transcription_api_key(secret):
            _LOG.info("openai_transcription connect: validation failed (key not logged)")
            return _invalid_key_response(tool_id)
        try:
            prev = save_connected_tool_secret(actor, "openai_transcription", secret)
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not save this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("openai_transcription connect: saved (key not logged)")
        return ToolConnectSuccessResponse(credential_preview=prev)

    if tool_id == "cursor":
        if not validate_cursor_api_key(secret):
            _LOG.info("cursor tool connect: validation failed (key not logged)")
            return _invalid_key_response(tool_id)
        try:
            save_cursor_api_key(secret)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        prev = mask_api_key_preview(secret)
        _LOG.info("cursor tool connect: saved (key not logged)")
        return ToolConnectSuccessResponse(credential_preview=prev)

    return _connect_not_supported_response()


@router.post("/tools/{tool_id}/disconnect")
def workspace_tool_disconnect(
    tool_id: str,
    _actor: object = Depends(get_ham_clerk_actor),
) -> Any:
    actor = _actor if isinstance(_actor, HamActor) else None
    known = {t.id for t in _build_tool_registry(None)}
    if tool_id not in known:
        raise HTTPException(status_code=404, detail="Unknown tool.")

    if tool_id == "cursor":
        clear_saved_cursor_api_key()
        _LOG.info("cursor tool disconnect: cleared saved file if present")
        return ToolDisconnectSuccessResponse()

    if tool_id == "openrouter":
        try:
            delete_connected_tool_secret(actor, "openrouter")
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not remove this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("openrouter tool disconnect: cleared stored credential if present")
        return ToolDisconnectSuccessResponse()

    if tool_id == "github":
        try:
            delete_connected_tool_secret(actor, "github")
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not remove this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("github tool disconnect: cleared stored credential if present")
        return ToolDisconnectSuccessResponse()

    if tool_id == "claude_agent_sdk":
        try:
            delete_connected_tool_secret(actor, "claude_agent_sdk")
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not remove this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        reset_claude_agent_readiness_cache()
        _LOG.info("claude_agent_sdk disconnect: cleared stored credential if present")
        return ToolDisconnectSuccessResponse()

    if tool_id == "openai_transcription":
        try:
            delete_connected_tool_secret(actor, "openai_transcription")
        except ConnectedCredentialSaveFailed:
            return JSONResponse(
                status_code=503,
                content=ToolConnectFailResponse(
                    error_code="CREDENTIAL_STORE_FAILED",
                    message="Could not remove this credential on the server. Ask your operator.",
                    help=_help(tool_id),
                ).model_dump(),
            )
        _LOG.info("openai_transcription disconnect: cleared stored credential if present")
        return ToolDisconnectSuccessResponse()

    return JSONResponse(
        status_code=400,
        content=ToolConnectFailResponse(
            error_code="NOT_SUPPORTED",
            message="Disconnect is not available for this tool.",
            help=None,
        ).model_dump(),
    )
