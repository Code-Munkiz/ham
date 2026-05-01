"""Read-only Social workspace API facade.

Phase 1: read-only endpoints only. The user-facing workspace section is
**Social**; the first active provider is **X**. The existing backend
implementation continues to live under :mod:`src.ham.ham_x` and continues to
read ``HAM_X_*`` environment variables; this facade does not rename anything.

Safety rules enforced by this module:

- Every endpoint is ``GET`` and read-only. No live X writes, no GoHAM actions,
  no shell commands, no provider mutation calls, no audit appends.
- Secrets, tokens, auth headers, raw credentials, and ``.env`` values are
  never returned. Only presence booleans are surfaced.
- Journal and audit summaries are bounded and redacted.
- Live apply is **not** available in Phase 1 (``live_apply_available=False``).
"""
from __future__ import annotations

import json
import hashlib
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor, resolve_ham_operator_authorization_header
from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_governor import GohamGovernorCandidate, evaluate_goham_governor
from src.ham.ham_x.goham_live_controller import run_live_controller_once
from src.ham.ham_x.goham_ops import dry_preflight_goham_candidate, show_goham_status
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.goham_reactive_batch import run_reactive_batch_once
from src.ham.ham_x.goham_reactive_inbox import discover_reactive_inbox_once, state_from_journal
from src.ham.ham_x.goham_reactive_live import run_reactive_live_once
from src.ham.ham_x.inbound_client import ReactiveInboundItem
from src.ham.ham_x.reactive_governor import (
    GOHAM_REACTIVE_EXECUTION_KIND,
    ReactiveGovernorState,
    evaluate_reactive_governor,
)
from src.ham.ham_x.reactive_policy import evaluate_reactive_policy
from src.ham.ham_x.redaction import redact
from src.ham.social_persona import load_social_persona, persona_digest
from src.ham.social_telegram_send import (
    TELEGRAM_EXECUTION_KIND,
    TelegramSendRequest,
    send_confirmed_telegram_message,
)

router = APIRouter(prefix="/api/social", tags=["social"])

# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_RECENT_ITEMS = 10
MAX_RECENT_EVENTS = 10
MAX_ROWS_SCANNED = 500
MAX_BYTES_SCANNED = 1_048_576
MAX_STRING_CHARS = 1_000
MAX_DICT_KEYS = 50
MAX_LIST_ITEMS = 25

ProviderStatus = Literal["active", "setup_required", "blocked", "coming_soon"]
OverallReadiness = Literal["ready", "limited", "blocked", "setup_required"]
PreviewStatus = Literal["completed", "blocked", "failed"]
PreviewKind = Literal["reactive_inbox", "reactive_batch_dry_run", "broadcast_preflight"]
TelegramMessageIntent = Literal["greeting", "announcement", "test_message"]
SocialApplyStatus = Literal["blocked", "executed", "failed"]
SocialApplyKind = Literal["reactive_reply", "reactive_batch", "broadcast_post"]
LIVE_REPLY_CONFIRMATION_PHRASE = "SEND ONE LIVE REPLY"
LIVE_BATCH_CONFIRMATION_PHRASE = "SEND LIVE REACTIVE BATCH"
LIVE_BROADCAST_CONFIRMATION_PHRASE = "SEND ONE LIVE POST"
LIVE_TELEGRAM_CONFIRMATION_PHRASE = "SEND ONE TELEGRAM MESSAGE"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class SocialProviderDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    status: ProviderStatus
    configured: bool
    coming_soon: bool = False
    enabled_lanes: list[str] = Field(default_factory=list)


class SocialProvidersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[SocialProviderDto]


class EmergencyStopDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DryRunDefaultsDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_dry_run: bool
    controller_dry_run: bool
    reactive_dry_run: bool
    reactive_batch_dry_run: bool


class BroadcastLaneStatusDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    controller_enabled: bool
    live_controller_enabled: bool
    dry_run_available: bool
    live_configured: bool
    execution_allowed_now: bool
    reasons: list[str] = Field(default_factory=list)


class ReactiveLaneStatusDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    inbox_discovery_enabled: bool
    dry_run_enabled: bool
    live_canary_enabled: bool
    batch_enabled: bool
    reasons: list[str] = Field(default_factory=list)


class CapCooldownSummaryDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broadcast_daily_cap: int
    broadcast_daily_used: int
    broadcast_daily_remaining: int
    broadcast_per_run_cap: int
    broadcast_min_spacing_minutes: int
    reactive_max_replies_per_15m: int
    reactive_max_replies_per_hour: int
    reactive_max_replies_per_user_per_day: int
    reactive_max_replies_per_thread_per_day: int
    reactive_min_seconds_between_replies: int
    reactive_batch_max_replies_per_run: int


class SafePathsDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_journal_path: str
    audit_log_path: str


class XProviderStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    label: Literal["X"] = "X"
    overall_readiness: OverallReadiness
    readiness_reasons: list[str] = Field(default_factory=list)
    emergency_stop: EmergencyStopDto
    dry_run_defaults: DryRunDefaultsDto
    broadcast_lane: BroadcastLaneStatusDto
    reactive_lane: ReactiveLaneStatusDto
    last_autonomous_post: dict[str, Any] | None = None
    last_reactive_reply: dict[str, Any] | None = None
    cap_cooldown_summary: CapCooldownSummaryDto
    paths: SafePathsDto
    read_only: bool = True
    mutation_attempted: bool = False


class XCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    live_read_available: bool
    live_model_available: bool
    broadcast_dry_run_available: bool
    broadcast_live_available: bool
    broadcast_apply_available: bool = False
    reactive_inbox_discovery_available: bool
    reactive_dry_run_available: bool
    reactive_reply_canary_available: bool
    reactive_batch_available: bool
    reactive_reply_apply_available: bool = False
    reactive_batch_apply_available: bool = False
    live_apply_available: bool = False
    read_only: bool = True


class SetupChecklistItemDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    ok: bool


class XSetupChecklistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    items: list[SetupChecklistItemDto]
    feature_flags: dict[str, bool]
    read_only: bool = True


class JournalSummaryBoundsDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_recent_items: int = MAX_RECENT_ITEMS
    max_rows_scanned: int = MAX_ROWS_SCANNED
    max_bytes_scanned: int = MAX_BYTES_SCANNED


class XJournalSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    journal_path: str
    total_count_scanned: int
    malformed_count: int
    counts_by_execution_kind: dict[str, int]
    latest_broadcast_post: dict[str, Any] | None = None
    latest_reactive_reply: dict[str, Any] | None = None
    recent_items: list[dict[str, Any]] = Field(default_factory=list)
    bounds: JournalSummaryBoundsDto = Field(default_factory=JournalSummaryBoundsDto)
    read_only: bool = True
    mutation_attempted: bool = False


class AuditSummaryBoundsDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_recent_events: int = MAX_RECENT_EVENTS
    max_rows_scanned: int = MAX_ROWS_SCANNED
    max_bytes_scanned: int = MAX_BYTES_SCANNED


class XAuditSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    audit_path: str
    total_count_scanned: int
    malformed_count: int
    counts_by_event_type: dict[str, int]
    latest_audit_ids: list[str] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    bounds: AuditSummaryBoundsDto = Field(default_factory=AuditSummaryBoundsDto)
    read_only: bool = True
    mutation_attempted: bool = False


class SocialPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str | None = Field(default=None, max_length=128)
    max_candidates: int | None = Field(default=None, ge=1, le=25)
    candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=25)
    preflight_candidate: dict[str, Any] | None = None


class SocialPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    persona_id: str
    persona_version: int
    persona_digest: str
    preview_kind: PreviewKind
    status: PreviewStatus
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    proposal_digest: str | None = None
    read_only: bool = True


class TelegramMessagePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str | None = Field(default=None, max_length=128)
    message_intent: TelegramMessageIntent = "test_message"


class TelegramPreviewTargetDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["home_channel", "test_group"]
    configured: bool
    masked_id: str


class TelegramMessagePreviewDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    char_count: int


class TelegramMessagePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    preview_kind: Literal["telegram_message"] = "telegram_message"
    status: PreviewStatus
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    proposal_digest: str | None = None
    target: TelegramPreviewTargetDto
    message_preview: TelegramMessagePreviewDto
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    read_only: bool = True


class TelegramMessageApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_digest: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(default="", max_length=64)
    message_intent: TelegramMessageIntent = "test_message"
    client_request_id: str | None = Field(default=None, max_length=128)


class TelegramMessageApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    apply_kind: Literal["telegram_message"] = "telegram_message"
    status: Literal["blocked", "sent", "failed", "duplicate"]
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    provider_message_id: str | None = None
    target: TelegramPreviewTargetDto
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class SocialReactiveReplyApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_digest: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=128)


class SocialReactiveReplyApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    persona_id: str
    persona_version: int
    persona_digest: str
    apply_kind: SocialApplyKind = "reactive_reply"
    status: SocialApplyStatus
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    provider_status_code: int | None = None
    provider_post_id: str | None = None
    execution_kind: str = GOHAM_REACTIVE_EXECUTION_KIND
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class SocialReactiveBatchApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_digest: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=128)


class SocialReactiveBatchApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    persona_id: str
    persona_version: int
    persona_digest: str
    apply_kind: SocialApplyKind = "reactive_batch"
    status: Literal["blocked", "completed", "stopped", "failed"]
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    attempted_count: int = 0
    executed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    provider_post_ids: list[str] = Field(default_factory=list)
    execution_kind: str = GOHAM_REACTIVE_EXECUTION_KIND
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class SocialBroadcastApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_digest: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=128)


class SocialBroadcastApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    persona_id: str
    persona_version: int
    persona_digest: str
    apply_kind: SocialApplyKind = "broadcast_post"
    status: Literal["blocked", "executed", "failed"]
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    provider_status_code: int | None = None
    provider_post_id: str | None = None
    execution_kind: str = GOHAM_EXECUTION_KIND
    audit_ids: list[str] = Field(default_factory=list)
    journal_path: str
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class XSetupSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
    provider_configured: bool
    overall_readiness: OverallReadiness
    missing_requirement_ids: list[str] = Field(default_factory=list)
    ready_for_dry_run: bool
    ready_for_confirmed_live_reply: bool
    ready_for_reactive_batch: bool
    ready_for_broadcast: bool
    required_connections: dict[str, bool]
    lane_readiness: dict[str, dict[str, Any]]
    safe_identifiers: dict[str, str]
    caps_cooldowns: dict[str, int]
    feature_flags: dict[str, bool]
    recommended_next_steps: list[str] = Field(default_factory=list)
    read_only: bool = True
    mutation_attempted: bool = False


SocialMessagingProviderId = Literal["telegram", "discord"]
HermesRuntimeState = Literal["connected", "connecting", "retrying", "fatal", "stopped", "unknown"]
TelegramMode = Literal["polling", "polling_default", "webhook", "unset"]
TelegramPlatformState = Literal["connected", "retrying", "fatal", "stopped", "unknown", "not_reported"]


class HermesGatewayRuntimeStatusDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    base_url_configured: bool
    status_path_configured: bool = False
    status_file_available: bool
    source: Literal["status_file", "env", "unknown"]
    gateway_state: str = "unknown"
    provider_runtime_state: HermesRuntimeState = "unknown"
    active_agents: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class SocialMessagingProviderStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: SocialMessagingProviderId
    label: Literal["Telegram", "Discord"]
    overall_readiness: OverallReadiness
    readiness_reasons: list[str] = Field(default_factory=list)
    hermes_gateway: HermesGatewayRuntimeStatusDto
    required_connections: dict[str, bool]
    safe_identifiers: dict[str, str] = Field(default_factory=dict)
    readiness: OverallReadiness | None = None
    missing_requirements: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    telegram_bot_token_present: bool | None = None
    telegram_allowed_users_present: bool | None = None
    telegram_home_channel_configured: bool | None = None
    telegram_test_group_configured: bool | None = None
    telegram_mode: TelegramMode | None = None
    hermes_gateway_base_url_present: bool | None = None
    hermes_gateway_status_path_present: bool | None = None
    hermes_gateway_runtime_state: HermesRuntimeState | None = None
    telegram_platform_state: TelegramPlatformState | None = None
    read_only: bool = True
    mutation_attempted: bool = False
    live_apply_available: bool = False


class TelegramCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    bot_token_present: bool
    allowed_users_configured: bool
    home_channel_configured: bool
    test_group_configured: bool = False
    telegram_mode: TelegramMode = "unset"
    hermes_gateway_base_url_present: bool = False
    hermes_gateway_status_path_present: bool = False
    hermes_gateway_runtime_state: HermesRuntimeState = "unknown"
    telegram_platform_state: TelegramPlatformState = "not_reported"
    readiness: OverallReadiness = "setup_required"
    missing_requirements: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    polling_supported: bool = True
    webhook_supported: bool = True
    groups_supported: bool = True
    topics_supported: bool = True
    media_supported: bool = True
    voice_supported: bool = True
    inbound_available: bool = False
    preview_available: bool = False
    live_message_available: bool = False
    live_apply_available: bool = False
    read_only: bool = True
    mutation_attempted: bool = False


class DiscordCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["discord"] = "discord"
    bot_token_present: bool
    allowed_users_or_roles_configured: bool
    guild_or_channel_configured: bool
    dms_supported: bool = True
    channels_supported: bool = True
    threads_supported: bool = True
    slash_commands_supported: bool = True
    media_supported: bool = True
    voice_supported: bool = True
    inbound_available: bool = False
    preview_available: bool = False
    live_message_available: bool = False
    live_apply_available: bool = False
    read_only: bool = True
    mutation_attempted: bool = False


class SocialMessagingSetupChecklistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: SocialMessagingProviderId
    items: list[SetupChecklistItemDto]
    recommended_next_steps: list[str] = Field(default_factory=list)
    read_only: bool = True
    mutation_attempted: bool = False


class SocialPersonaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: str
    version: int
    display_name: str
    short_bio: str
    mission: str
    values: list[str]
    tone_rules: list[str]
    platform_adaptations: dict[str, dict[str, Any]]
    prohibited_content: list[str]
    safety_boundaries: list[str]
    example_replies: list[dict[str, str]]
    example_announcements: list[str]
    refusal_examples: list[dict[str, str]]
    persona_digest: str
    read_only: bool = True
    mutation_attempted: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bound_string(value: Any) -> Any:
    if isinstance(value, str):
        return value[: MAX_STRING_CHARS - 3] + "..." if len(value) > MAX_STRING_CHARS else value
    return value


def _bound_value(value: Any) -> Any:
    if isinstance(value, str):
        return _bound_string(value)
    if isinstance(value, list):
        return [_bound_value(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:MAX_DICT_KEYS]:
            out[str(key)[:128]] = _bound_value(item)
        return out
    return value


def _safe_dict(value: Any) -> dict[str, Any]:
    """Bound + redact a JSON-loaded record so secrets cannot leak through."""
    if not isinstance(value, dict):
        return {}
    return redact(_bound_value(value))


def _safe_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "redacted_dump"):
        try:
            dumped = value.redacted_dump()
        except Exception:
            dumped = {}
        return _safe_dict(dumped)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
        except Exception:
            dumped = {}
        return _safe_dict(dumped)
    return _safe_dict(value)


def _bounded_string_list(items: list[Any], *, max_items: int = 12, max_chars: int = 240) -> list[str]:
    out: list[str] = []
    for item in items[:max_items]:
        text = str(redact(str(item or "").strip()))
        if text:
            out.append(text[:max_chars])
    return out


def _bounded_examples(items: list[Any], *, max_items: int = 3) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items[:max_items]:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(data, dict):
            continue
        raw_input = str(data.get("input") or "").strip()
        raw_output = str(data.get("output") or "").strip()
        if raw_input and raw_output:
            out.append(
                {
                    "input": str(redact(raw_input))[:300],
                    "output": str(redact(raw_output))[:500],
                }
            )
    return out


def _social_persona_response() -> SocialPersonaResponse:
    persona = load_social_persona("ham-canonical", 1)
    adaptations: dict[str, dict[str, Any]] = {}
    for key, adaptation in persona.platform_adaptations.items():
        data = adaptation.model_dump(mode="json")
        adaptations[key] = _safe_dict(
            {
                "label": data.get("label"),
                "style": data.get("style"),
                "max_chars": data.get("max_chars"),
                "guidance": _bounded_string_list(list(data.get("guidance") or []), max_items=8),
            }
        )
    return SocialPersonaResponse(
        persona_id=persona.persona_id,
        version=persona.version,
        display_name=persona.display_name,
        short_bio=str(redact(persona.short_bio))[:500],
        mission=str(redact(persona.mission))[:700],
        values=_bounded_string_list(persona.values),
        tone_rules=_bounded_string_list(persona.tone_rules),
        platform_adaptations=adaptations,
        prohibited_content=_bounded_string_list(persona.prohibited_content),
        safety_boundaries=_bounded_string_list(persona.safety_boundaries),
        example_replies=_bounded_examples(persona.example_replies),
        example_announcements=_bounded_string_list(persona.example_announcements, max_items=3, max_chars=500),
        refusal_examples=_bounded_examples(persona.refusal_examples),
        persona_digest=persona_digest(persona),
    )


def _persona_ref() -> dict[str, Any]:
    persona = load_social_persona("ham-canonical", 1)
    return {
        "persona_id": persona.persona_id,
        "persona_version": int(persona.version),
        "persona_digest": persona_digest(persona),
    }


def _persona_ref_fields() -> dict[str, Any]:
    # Persona digests are integrity hashes, not credentials. Do not run them
    # through the generic social redactor, which intentionally masks opaque
    # token-shaped strings.
    ref = _persona_ref()
    return {
        "persona_id": str(ref["persona_id"])[:128],
        "persona_version": int(ref["persona_version"]),
        "persona_digest": str(ref["persona_digest"])[:64],
    }


def _safe_id(value: str) -> str:
    return str(redact((value or "").strip()))[:128]


def _env_present(*names: str) -> bool:
    return any((os.environ.get(name) or "").strip() for name in names)


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_config_ref(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"configured:{digest}"


def _hermes_gateway_status_path() -> Path | None:
    explicit = (os.environ.get("HAM_HERMES_GATEWAY_STATUS_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    home = (os.environ.get("HAM_HERMES_HOME") or os.environ.get("HERMES_HOME") or "").strip()
    if not home:
        return None
    return Path(home).expanduser() / "gateway_state.json"


def _runtime_state(value: Any) -> HermesRuntimeState:
    raw = str(value or "").strip().lower()
    if raw in {"connected", "connecting", "retrying", "fatal", "stopped"}:
        return raw  # type: ignore[return-value]
    if raw in {"healthy", "running", "ready", "active"}:
        return "connected"
    if raw in {"startup_failed", "failed", "error"}:
        return "fatal"
    return "unknown"


def _telegram_platform_state(runtime: HermesGatewayRuntimeStatusDto) -> TelegramPlatformState:
    if runtime.source == "status_file" and runtime.provider_runtime_state == "unknown":
        return "not_reported"
    if runtime.provider_runtime_state == "connecting":
        return "retrying"
    if runtime.provider_runtime_state in {"connected", "retrying", "fatal", "stopped", "unknown"}:
        return runtime.provider_runtime_state  # type: ignore[return-value]
    return "unknown"


def _telegram_mode() -> TelegramMode:
    if _env_present("TELEGRAM_WEBHOOK_URL", "TELEGRAM_WEBHOOK_BASE_URL"):
        return "webhook"
    explicit = (
        os.environ.get("TELEGRAM_MODE")
        or os.environ.get("HERMES_TELEGRAM_MODE")
        or os.environ.get("TELEGRAM_GATEWAY_MODE")
        or ""
    ).strip().lower()
    if explicit in {"polling", "polling_default", "webhook"}:
        return explicit  # type: ignore[return-value]
    if _env_present("TELEGRAM_BOT_TOKEN"):
        return "polling_default"
    return "unset"


def _bounded_json_file(path: Path) -> dict[str, Any] | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_BYTES_SCANNED:
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _hermes_runtime_status(provider_id: SocialMessagingProviderId) -> HermesGatewayRuntimeStatusDto:
    base_url_configured = bool((os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip())
    path = _hermes_gateway_status_path()
    if path is not None and path.is_file():
        payload = _safe_dict(_bounded_json_file(path) or {})
        platforms = payload.get("platforms")
        provider_payload = platforms.get(provider_id) if isinstance(platforms, dict) else {}
        provider_payload = provider_payload if isinstance(provider_payload, dict) else {}
        return HermesGatewayRuntimeStatusDto(
            configured=True,
            base_url_configured=base_url_configured,
            status_path_configured=True,
            status_file_available=True,
            source="status_file",
            gateway_state=str(payload.get("gateway_state") or "unknown")[:64],
            provider_runtime_state=_runtime_state(provider_payload.get("state")),
            active_agents=int(payload["active_agents"]) if isinstance(payload.get("active_agents"), int) else None,
            error_code=str(provider_payload.get("error_code"))[:128] if provider_payload.get("error_code") else None,
            error_message="Provider error [REDACTED]." if provider_payload.get("error_message") else None,
        )
    return HermesGatewayRuntimeStatusDto(
        configured=base_url_configured,
        base_url_configured=base_url_configured,
        status_path_configured=path is not None,
        status_file_available=False,
        source="env" if base_url_configured else "unknown",
        gateway_state="unknown",
        provider_runtime_state="unknown",
    )


def _telegram_connections() -> dict[str, bool]:
    return {
        "bot_token_present": _env_present("TELEGRAM_BOT_TOKEN"),
        "allowed_users_configured": _env_present("TELEGRAM_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS")
        or _env_bool("TELEGRAM_ALLOW_ALL_USERS")
        or _env_bool("GATEWAY_ALLOW_ALL_USERS"),
        "home_channel_configured": _env_present("TELEGRAM_HOME_CHANNEL"),
        "test_group_configured": _env_present(
            "TELEGRAM_TEST_GROUP",
            "TELEGRAM_TEST_GROUP_ID",
            "TELEGRAM_TEST_CHAT_ID",
        ),
    }


def _discord_connections() -> dict[str, bool]:
    return {
        "bot_token_present": _env_present("DISCORD_BOT_TOKEN"),
        "allowed_users_or_roles_configured": _env_present(
            "DISCORD_ALLOWED_USERS",
            "DISCORD_ALLOWED_ROLES",
            "GATEWAY_ALLOWED_USERS",
        )
        or _env_bool("DISCORD_ALLOW_ALL_USERS")
        or _env_bool("GATEWAY_ALLOW_ALL_USERS"),
        "guild_or_channel_configured": _env_present(
            "DISCORD_HOME_CHANNEL",
            "DISCORD_ALLOWED_CHANNELS",
            "DISCORD_FREE_RESPONSE_CHANNELS",
        ),
    }


def _messaging_readiness(
    provider_id: SocialMessagingProviderId,
    connections: dict[str, bool],
    runtime: HermesGatewayRuntimeStatusDto,
) -> tuple[OverallReadiness, list[str]]:
    reasons: list[str] = []
    if runtime.provider_runtime_state == "fatal":
        reasons.append("hermes_gateway_provider_fatal")
        return "blocked", reasons
    for key, ok in connections.items():
        if not ok and key != "home_channel_configured" and key != "guild_or_channel_configured":
            reasons.append(f"{key}_missing")
    if provider_id == "discord" and not connections.get("guild_or_channel_configured", False):
        reasons.append("guild_or_channel_not_configured")
    if provider_id == "telegram" and not connections.get("home_channel_configured", False):
        reasons.append("home_channel_not_configured")
    if runtime.provider_runtime_state == "connected":
        return ("ready" if not reasons else "limited"), reasons
    reasons.append("hermes_gateway_runtime_unknown" if runtime.provider_runtime_state == "unknown" else "hermes_gateway_not_connected")
    return ("limited" if connections.get("bot_token_present") else "setup_required"), _dedupe(reasons)


def _telegram_status_response() -> SocialMessagingProviderStatusResponse:
    runtime = _hermes_runtime_status("telegram")
    connections = _telegram_connections()
    readiness, reasons = _messaging_readiness("telegram", connections, runtime)
    missing = _telegram_missing_requirements(connections, runtime)
    next_steps = _telegram_setup_steps(connections, runtime)
    safe_identifiers = {
        "home_channel": _safe_config_ref(os.environ.get("TELEGRAM_HOME_CHANNEL") or ""),
        "test_group": _safe_config_ref(
            os.environ.get("TELEGRAM_TEST_GROUP")
            or os.environ.get("TELEGRAM_TEST_GROUP_ID")
            or os.environ.get("TELEGRAM_TEST_CHAT_ID")
            or ""
        ),
    }
    return SocialMessagingProviderStatusResponse(
        provider_id="telegram",
        label="Telegram",
        overall_readiness=readiness,
        readiness_reasons=reasons,
        hermes_gateway=runtime,
        required_connections=connections,
        safe_identifiers={key: value for key, value in safe_identifiers.items() if value},
        readiness=readiness,
        missing_requirements=missing,
        recommended_next_steps=next_steps,
        telegram_bot_token_present=connections["bot_token_present"],
        telegram_allowed_users_present=connections["allowed_users_configured"],
        telegram_home_channel_configured=connections["home_channel_configured"],
        telegram_test_group_configured=connections["test_group_configured"],
        telegram_mode=_telegram_mode(),
        hermes_gateway_base_url_present=runtime.base_url_configured,
        hermes_gateway_status_path_present=runtime.status_path_configured,
        hermes_gateway_runtime_state=runtime.provider_runtime_state,
        telegram_platform_state=_telegram_platform_state(runtime),
    )


def _discord_status_response() -> SocialMessagingProviderStatusResponse:
    runtime = _hermes_runtime_status("discord")
    connections = _discord_connections()
    readiness, reasons = _messaging_readiness("discord", connections, runtime)
    safe_identifiers = {
        "home_channel": _safe_config_ref(os.environ.get("DISCORD_HOME_CHANNEL") or ""),
    }
    return SocialMessagingProviderStatusResponse(
        provider_id="discord",
        label="Discord",
        overall_readiness=readiness,
        readiness_reasons=reasons,
        hermes_gateway=runtime,
        required_connections=connections,
        safe_identifiers={key: value for key, value in safe_identifiers.items() if value},
    )


def _messaging_provider_dto(provider_id: SocialMessagingProviderId) -> SocialProviderDto:
    status_response = _telegram_status_response() if provider_id == "telegram" else _discord_status_response()
    if status_response.overall_readiness == "blocked":
        status: ProviderStatus = "blocked"
    elif status_response.overall_readiness == "ready":
        status = "active"
    else:
        status = "setup_required"
    enabled_lanes = ["readiness"]
    if provider_id == "telegram" and status_response.hermes_gateway.provider_runtime_state == "connected":
        enabled_lanes.append("preview")
    return SocialProviderDto(
        id=provider_id,
        label=status_response.label,
        status=status,
        configured=bool(status_response.required_connections.get("bot_token_present")),
        coming_soon=False,
        enabled_lanes=enabled_lanes,
    )


def _telegram_setup_steps(connections: dict[str, bool], runtime: HermesGatewayRuntimeStatusDto) -> list[str]:
    steps: list[str] = []
    if not connections["bot_token_present"]:
        steps.append("Store the Telegram bot token securely on the Hermes runtime host.")
    if not connections["allowed_users_configured"]:
        steps.append("Configure allowed Telegram users or chats before enabling Telegram access.")
    if not connections["home_channel_configured"]:
        steps.append("Configure the Telegram home channel for proactive delivery after runtime validation.")
    if not connections.get("test_group_configured", False):
        steps.append("Configure a private Telegram test group before dry-run preview work begins.")
    if _telegram_mode() == "unset":
        steps.append("Choose Telegram gateway mode: polling or webhook.")
    if not runtime.base_url_configured and not runtime.status_path_configured:
        steps.append("Configure Hermes gateway status discovery through HERMES_GATEWAY_BASE_URL or a safe status file path.")
    if runtime.provider_runtime_state != "connected":
        steps.append("Validate the Hermes gateway outside HAM; this Social surface does not start or stop it.")
    if not steps:
        steps.append("Telegram readiness looks configured. Keep using this panel as read-only status until Social live controls are added.")
    return steps


def _telegram_missing_requirements(connections: dict[str, bool], runtime: HermesGatewayRuntimeStatusDto) -> list[str]:
    missing: list[str] = []
    if not connections["bot_token_present"]:
        missing.append("telegram_bot_token")
    if not connections["allowed_users_configured"]:
        missing.append("telegram_allowed_users")
    if not connections["home_channel_configured"]:
        missing.append("telegram_home_channel")
    if not connections.get("test_group_configured", False):
        missing.append("telegram_test_group")
    if _telegram_mode() == "unset":
        missing.append("telegram_mode")
    if not runtime.base_url_configured:
        missing.append("hermes_gateway_base_url")
    if not runtime.status_path_configured:
        missing.append("hermes_gateway_status_path")
    if runtime.provider_runtime_state != "connected":
        missing.append("hermes_gateway_runtime")
    return _dedupe(missing)


def _discord_setup_steps(connections: dict[str, bool], runtime: HermesGatewayRuntimeStatusDto) -> list[str]:
    steps: list[str] = []
    if not connections["bot_token_present"]:
        steps.append("Configure DISCORD_BOT_TOKEN on the Hermes gateway host using `hermes gateway setup`.")
    if not connections["allowed_users_or_roles_configured"]:
        steps.append("Configure DISCORD_ALLOWED_USERS or DISCORD_ALLOWED_ROLES before enabling Discord access.")
    if not connections["guild_or_channel_configured"]:
        steps.append("Configure a Discord home, allowed, or free-response channel for controlled routing.")
    if runtime.provider_runtime_state != "connected":
        steps.append("Verify the Hermes gateway service outside HAM; this Social surface does not start or stop it.")
    if not steps:
        steps.append("Discord readiness looks configured. Keep using this panel as read-only status until Social live controls are added.")
    return steps


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _proposal_digest(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(_safe_dict(payload), sort_keys=True, default=str)
    return hashlib.sha256(f"{kind}:{raw}".encode("utf-8")).hexdigest()


def _proposal_payload_with_persona(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    out = _safe_dict(payload)
    out["persona"] = _persona_ref_fields()
    return out


def _telegram_preview_target() -> TelegramPreviewTargetDto:
    test_group = (
        os.environ.get("TELEGRAM_TEST_GROUP")
        or os.environ.get("TELEGRAM_TEST_GROUP_ID")
        or os.environ.get("TELEGRAM_TEST_CHAT_ID")
        or ""
    )
    if (test_group or "").strip():
        return TelegramPreviewTargetDto(
            kind="test_group",
            configured=True,
            masked_id=_safe_config_ref(test_group),
        )
    home_channel = os.environ.get("TELEGRAM_HOME_CHANNEL") or ""
    return TelegramPreviewTargetDto(
        kind="home_channel",
        configured=bool(home_channel.strip()),
        masked_id=_safe_config_ref(home_channel),
    )


def _telegram_preview_text(intent: TelegramMessageIntent) -> str:
    persona = load_social_persona("ham-canonical", 1)
    if intent == "greeting":
        text = (
            f"Hey, this is {persona.display_name}. Telegram preview is connected, persona-protected, "
            "and still dry-run only from HAM Social."
        )
    elif intent == "announcement":
        text = (
            f"{persona.display_name} Telegram readiness is connected. Next step: keep previews bounded, "
            "masked, and confirmation-gated before any live send exists."
        )
    else:
        text = (
            f"{persona.display_name} Telegram preview check: persona is locked, target is masked, "
            "and no Telegram message will be sent."
        )
    return str(redact(text)).strip()[:700]


def _telegram_preview_response(body: TelegramMessagePreviewRequest) -> TelegramMessagePreviewResponse:
    runtime = _hermes_runtime_status("telegram")
    connections = _telegram_connections()
    readiness, readiness_reasons = _messaging_readiness("telegram", connections, runtime)
    missing = _telegram_missing_requirements(connections, runtime)
    persona = _persona_ref_fields()
    target = _telegram_preview_target()
    reasons: list[str] = []
    warnings: list[str] = []
    status: PreviewStatus = "completed"
    text = _telegram_preview_text(body.message_intent)
    proposal_digest: str | None = None

    if runtime.provider_runtime_state != "connected":
        reasons.append("telegram_gateway_not_connected")
    if not target.configured:
        reasons.append("telegram_target_not_configured")
    if readiness == "blocked":
        reasons.append("telegram_readiness_blocked")
    elif readiness != "ready":
        warnings.extend(missing)
        warnings.extend(readiness_reasons)

    if reasons:
        status = "blocked"
    else:
        payload = {
            "provider_id": "telegram",
            "preview_kind": "telegram_message",
            "target": target.model_dump(),
            "message_preview": {"text": text, "char_count": len(text)},
            "readiness": {
                "overall_readiness": readiness,
                "telegram_mode": _telegram_mode(),
                "hermes_gateway_runtime_state": runtime.provider_runtime_state,
                "telegram_platform_state": _telegram_platform_state(runtime),
            },
            "safety_gates": {
                "execution_allowed": False,
                "mutation_attempted": False,
                "live_apply_available": False,
            },
        }
        proposal_digest = _proposal_digest("telegram_message", _proposal_payload_with_persona(payload) or payload)

    return TelegramMessagePreviewResponse(
        status=status,
        persona_id=str(persona["persona_id"]),
        persona_version=int(persona["persona_version"]),
        persona_digest=str(persona["persona_digest"]),
        proposal_digest=proposal_digest,
        target=target,
        message_preview=TelegramMessagePreviewDto(text=text if not reasons else "", char_count=len(text) if not reasons else 0),
        reasons=_dedupe(reasons),
        warnings=_dedupe(warnings),
        recommended_next_steps=(
            ["Preview generated only. No Telegram message was sent. Keep this digest for a future confirmed send flow."]
            if status == "completed"
            else _telegram_setup_steps(connections, runtime)
        ),
    )


def _telegram_live_apply_available() -> bool:
    status = _telegram_status_response()
    return status.overall_readiness == "ready" and status.hermes_gateway.provider_runtime_state == "connected" and _social_live_token_enabled()


def _telegram_apply_blocked_response(
    *,
    reasons: list[str],
    preview: TelegramMessagePreviewResponse | None = None,
    target: TelegramPreviewTargetDto | None = None,
    warnings: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> TelegramMessageApplyResponse:
    return TelegramMessageApplyResponse(
        **_persona_ref_fields(),
        status="blocked",
        execution_allowed=False,
        mutation_attempted=False,
        live_apply_available=_telegram_live_apply_available(),
        target=target or (preview.target if preview else _telegram_preview_target()),
        reasons=_dedupe(reasons),
        warnings=_dedupe(warnings or []),
        result=_safe_dict(result or {}),
    )


def _telegram_apply_idempotency_key(proposal_digest: str) -> str:
    return hashlib.sha256(f"telegram_message:{proposal_digest}".encode("utf-8")).hexdigest()


def _telegram_readiness_apply_reasons() -> list[str]:
    runtime = _hermes_runtime_status("telegram")
    connections = _telegram_connections()
    reasons: list[str] = []
    if not connections["bot_token_present"]:
        reasons.append("telegram_bot_token_missing")
    if not connections["allowed_users_configured"]:
        reasons.append("telegram_allowed_users_missing")
    if not _telegram_preview_target().configured:
        reasons.append("telegram_target_not_configured")
    if runtime.provider_runtime_state != "connected":
        reasons.append("telegram_gateway_not_connected")
    if _telegram_platform_state(runtime) != "connected":
        reasons.append("telegram_platform_not_connected")
    return _dedupe(reasons)


def _persona_digest_mismatch_response(
    *,
    kind: Literal["reply", "batch", "broadcast"],
    config: HamXConfig,
    reasons: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> SocialReactiveReplyApplyResponse | SocialReactiveBatchApplyResponse | SocialBroadcastApplyResponse:
    detail = _safe_dict({"persona": _persona_ref_fields(), **(result or {})})
    final_reasons = _dedupe([*(reasons or []), "persona_digest_mismatch"])
    if kind == "reply":
        return _blocked_apply_response(config, reasons=final_reasons, result=detail)
    if kind == "batch":
        return _blocked_batch_apply_response(config, reasons=final_reasons, result=detail)
    return _blocked_broadcast_apply_response(config, reasons=final_reasons, result=detail)


def _social_live_token_enabled() -> bool:
    return bool((os.environ.get("HAM_SOCIAL_LIVE_APPLY_TOKEN") or "").strip())


def _require_social_live_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_SOCIAL_LIVE_APPLY_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_LIVE_APPLY_DISABLED",
                    "message": "HAM_SOCIAL_LIVE_APPLY_TOKEN is not set; live Social apply is disabled.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SOCIAL_LIVE_APPLY_AUTH_REQUIRED",
                    "message": "Authorization: Bearer <HAM_SOCIAL_LIVE_APPLY_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_LIVE_APPLY_AUTH_INVALID",
                    "message": "Invalid Social live apply token.",
                }
            },
        )


def _display_path(path: Path | str) -> str:
    """Return a host-agnostic display string for a file path."""
    raw = Path(str(path))
    home = Path.home()
    repo_root = Path(__file__).resolve().parent.parent.parent
    candidate = raw
    try:
        candidate = raw.resolve(strict=False)
    except (OSError, RuntimeError):
        candidate = raw
    try:
        rel = candidate.relative_to(repo_root)
        return str(rel)
    except ValueError:
        pass
    try:
        rel = candidate.relative_to(home)
        return f"~/{rel}"
    except ValueError:
        pass
    return str(redact(str(raw)))


def _x_read_credential_present(cfg: HamXConfig) -> bool:
    return bool(cfg.x_bearer_token)


def _x_write_credential_present(cfg: HamXConfig) -> bool:
    return bool(
        cfg.x_api_key
        and cfg.x_api_secret
        and cfg.x_access_token
        and cfg.x_access_token_secret
    )


def _xai_key_present(cfg: HamXConfig) -> bool:
    return bool(cfg.xai_api_key)


def _reactive_handle_configured(cfg: HamXConfig) -> bool:
    return bool(cfg.reactive_handle.strip() or cfg.reactive_inbox_query.strip())


def _x_configured(cfg: HamXConfig) -> bool:
    return _x_read_credential_present(cfg) or _x_write_credential_present(cfg) or _xai_key_present(cfg)


def _broadcast_dry_run_available(cfg: HamXConfig) -> bool:
    return bool(
        cfg.enable_live_read_model_dry_run
        and cfg.dry_run
        and not cfg.autonomy_enabled
        and not cfg.enable_live_execution
        and not cfg.enable_live_smoke
        and not cfg.emergency_stop
        and (cfg.readonly_transport or "").strip().lower() == "direct"
        and _x_read_credential_present(cfg)
        and _xai_key_present(cfg)
    )


def _broadcast_live_configured(cfg: HamXConfig) -> bool:
    return bool(
        cfg.enable_goham_execution
        and cfg.enable_goham_controller
        and cfg.enable_goham_live_controller
        and cfg.enable_live_execution
        and cfg.autonomy_enabled
        and not cfg.dry_run
        and not cfg.emergency_stop
        and _x_write_credential_present(cfg)
    )


def _reactive_inbox_discovery_available(cfg: HamXConfig) -> bool:
    return bool(
        cfg.enable_reactive_inbox_discovery
        and _x_read_credential_present(cfg)
        and (cfg.reactive_handle.strip() or cfg.reactive_inbox_query.strip())
    )


def _reactive_reply_canary_available(cfg: HamXConfig) -> bool:
    return bool(
        cfg.enable_goham_reactive
        and cfg.goham_reactive_live_canary
        and not cfg.goham_reactive_dry_run
        and _x_write_credential_present(cfg)
        and not cfg.emergency_stop
    )


def _reactive_apply_reasons(cfg: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if not _social_live_token_enabled():
        reasons.append("social_live_apply_token_missing")
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if cfg.goham_reactive_dry_run:
        reasons.append("reactive_dry_run_enabled")
    if not cfg.goham_reactive_live_canary:
        reasons.append("reactive_live_canary_required")
    if cfg.goham_reactive_max_replies_per_run != 1:
        reasons.append("reactive_max_replies_per_run_must_equal_one")
    if not cfg.goham_reactive_block_links:
        reasons.append("reactive_link_blocking_required")
    if not _x_write_credential_present(cfg):
        reasons.append("x_write_credential_missing")
    return _dedupe(reasons)


def _reactive_batch_apply_reasons(cfg: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if not _social_live_token_enabled():
        reasons.append("social_live_apply_token_missing")
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not cfg.enable_goham_reactive_batch:
        reasons.append("reactive_batch_disabled")
    if cfg.goham_reactive_batch_dry_run:
        reasons.append("reactive_batch_dry_run_enabled")
    if not cfg.goham_reactive_block_links:
        reasons.append("reactive_link_blocking_required")
    if cfg.goham_reactive_batch_max_replies_per_run <= 0:
        reasons.append("reactive_batch_max_replies_required")
    if not _x_write_credential_present(cfg):
        reasons.append("x_write_credential_missing")
    return _dedupe(reasons)


def _broadcast_apply_reasons(cfg: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if not _social_live_token_enabled():
        reasons.append("social_live_apply_token_missing")
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_execution:
        reasons.append("goham_execution_disabled")
    if not cfg.enable_goham_controller:
        reasons.append("goham_controller_disabled")
    if not cfg.enable_goham_live_controller:
        reasons.append("goham_live_controller_disabled")
    if not cfg.autonomy_enabled:
        reasons.append("autonomy_disabled")
    if cfg.dry_run:
        reasons.append("dry_run_enabled")
    if not cfg.enable_live_execution:
        reasons.append("live_execution_disabled")
    if cfg.goham_live_max_actions_per_run != 1:
        reasons.append("goham_live_max_actions_per_run_must_equal_one")
    if not cfg.goham_block_links:
        reasons.append("goham_link_blocking_required")
    if "post" not in {item.strip() for item in (cfg.goham_allowed_actions or "").split(",") if item.strip()}:
        reasons.append("original_post_disabled")
    if not _x_write_credential_present(cfg):
        reasons.append("x_write_credential_missing")
    return _dedupe(reasons)


def _broadcast_lane_reasons(cfg: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_execution:
        reasons.append("goham_execution_disabled")
    if not cfg.enable_goham_controller:
        reasons.append("goham_controller_disabled")
    if not cfg.enable_goham_live_controller:
        reasons.append("goham_live_controller_disabled")
    if cfg.dry_run:
        reasons.append("dry_run_enabled")
    if not cfg.enable_live_execution:
        reasons.append("live_execution_disabled")
    if not _x_write_credential_present(cfg):
        reasons.append("x_write_credential_missing")
    return reasons


def _reactive_lane_reasons(cfg: HamXConfig) -> list[str]:
    reasons: list[str] = []
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
    if not cfg.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not _x_read_credential_present(cfg):
        reasons.append("x_read_credential_missing")
    if not _reactive_handle_configured(cfg):
        reasons.append("reactive_handle_or_query_missing")
    return reasons


def _bounded_jsonl_tail(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read up to MAX_ROWS_SCANNED tail rows of a JSONL file.

    Returns (rows, malformed_count). Missing files return ([], 0). All file IO
    is bounded by MAX_BYTES_SCANNED.
    """
    if not path.exists():
        return [], 0
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0
    try:
        with path.open("rb") as fh:
            if size > MAX_BYTES_SCANNED:
                fh.seek(size - MAX_BYTES_SCANNED)
                # Discard partial first line.
                fh.readline()
            data = fh.read(MAX_BYTES_SCANNED)
    except OSError:
        return [], 0
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return [], 0
    lines = [line for line in text.splitlines() if line.strip()]
    lines = lines[-MAX_ROWS_SCANNED:]
    rows: list[dict[str, Any]] = []
    malformed = 0
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            malformed += 1
    return rows, malformed


def _force_preview_flags(payload: dict[str, Any]) -> dict[str, Any]:
    out = _safe_dict(payload)
    out["execution_allowed"] = False
    out["mutation_attempted"] = False
    out["live_apply_available"] = False
    return out


def _reply_apply_available(config: HamXConfig) -> bool:
    return bool(_social_live_token_enabled() and _reactive_reply_canary_available(config))


def _batch_apply_available(config: HamXConfig) -> bool:
    return bool(
        _social_live_token_enabled()
        and config.enable_goham_reactive
        and config.enable_goham_reactive_batch
        and not config.goham_reactive_batch_dry_run
        and not config.emergency_stop
        and _x_write_credential_present(config)
    )


def _broadcast_apply_available(config: HamXConfig) -> bool:
    return bool(_social_live_token_enabled() and _broadcast_live_configured(config))


def _apply_available(config: HamXConfig) -> bool:
    return _reply_apply_available(config) or _batch_apply_available(config) or _broadcast_apply_available(config)


def _blocked_apply_response(
    config: HamXConfig,
    *,
    reasons: list[str],
    warnings: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> SocialReactiveReplyApplyResponse:
    return SocialReactiveReplyApplyResponse(
        **_persona_ref_fields(),
        status="blocked",
        live_apply_available=_apply_available(config),
        journal_path=_display_path(config.execution_journal_path),
        audit_path=_display_path(config.audit_log_path),
        reasons=_dedupe(reasons),
        warnings=warnings or [],
        result=_safe_dict(result or {}),
    )


def _blocked_batch_apply_response(
    config: HamXConfig,
    *,
    reasons: list[str],
    warnings: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> SocialReactiveBatchApplyResponse:
    return SocialReactiveBatchApplyResponse(
        **_persona_ref_fields(),
        status="blocked",
        live_apply_available=_batch_apply_available(config),
        journal_path=_display_path(config.execution_journal_path),
        audit_path=_display_path(config.audit_log_path),
        reasons=_dedupe(reasons),
        warnings=warnings or [],
        result=_safe_dict(result or {}),
    )


def _blocked_broadcast_apply_response(
    config: HamXConfig,
    *,
    reasons: list[str],
    warnings: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> SocialBroadcastApplyResponse:
    return SocialBroadcastApplyResponse(
        **_persona_ref_fields(),
        status="blocked",
        live_apply_available=_broadcast_apply_available(config),
        journal_path=_display_path(config.execution_journal_path),
        audit_path=_display_path(config.audit_log_path),
        reasons=_dedupe(reasons),
        warnings=warnings or [],
        result=_safe_dict(result or {}),
    )


def _safe_journal_item(row: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted/bounded subset of a journal row."""
    keys = (
        "action_id",
        "source_action_id",
        "idempotency_key",
        "action_type",
        "execution_kind",
        "provider_post_id",
        "status",
        "executed_at",
    )
    subset = {key: row.get(key) for key in keys if key in row}
    return _safe_dict(subset)


def _safe_audit_event(row: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted/bounded subset of an audit row."""
    payload = row.get("payload")
    safe_payload: dict[str, Any] = {}
    if isinstance(payload, dict):
        # Surface only descriptive scalars; skip nested provider-shaped blobs.
        scalar_keys = (
            "status",
            "stop_reason",
            "execution_allowed",
            "mutation_attempted",
            "mode",
            "candidate_count",
            "processed_count",
            "attempted_count",
            "executed_count",
            "failed_count",
            "blocked_count",
            "reasons",
            "diagnostic",
            "audit_sink",
        )
        for key in scalar_keys:
            if key in payload:
                safe_payload[key] = payload[key]
    subset = {
        "audit_id": row.get("audit_id"),
        "event_type": row.get("event_type"),
        "ts": row.get("ts"),
        "payload": safe_payload,
    }
    return _safe_dict(subset)


def _broadcast_status_from_ops(cfg: HamXConfig) -> tuple[int, int, int, bool]:
    """Return (cap, used, remaining, execution_allowed_now) via show_goham_status.

    Falls back to defaults on unexpected errors so the API never raises 500
    because of a missing/unreadable journal.
    """
    try:
        status = show_goham_status(config=cfg)
        return (
            int(status.daily_cap),
            int(status.daily_cap_used),
            int(status.daily_cap_remaining),
            bool(status.execution_allowed_now),
        )
    except Exception:
        cap = int(cfg.goham_autonomous_daily_cap)
        return cap, 0, cap, False


def _last_autonomous_post(cfg: HamXConfig) -> dict[str, Any] | None:
    try:
        status = show_goham_status(config=cfg)
    except Exception:
        return None
    if status.last_autonomous_post is None:
        return None
    return _safe_journal_item(dict(status.last_autonomous_post))


def _last_reactive_reply(cfg: HamXConfig) -> dict[str, Any] | None:
    rows, _ = _bounded_jsonl_tail(Path(cfg.execution_journal_path))
    latest: dict[str, Any] | None = None
    for row in rows:
        if row.get("execution_kind") != GOHAM_REACTIVE_EXECUTION_KIND:
            continue
        if row.get("status") != "executed":
            continue
        if latest is None or str(row.get("executed_at", "")) > str(latest.get("executed_at", "")):
            latest = row
    return _safe_journal_item(latest) if latest else None


def _inbox_selected_count(discovery: Any) -> int:
    candidates = getattr(discovery, "candidates", None)
    if not isinstance(candidates, list):
        return 1 if getattr(discovery, "selected_candidate", None) is not None else 0
    return sum(1 for candidate in candidates if getattr(candidate, "status", "") == "selected")


def _inbox_proposal_payload(discovery: Any, config: HamXConfig) -> dict[str, Any] | None:
    selected = getattr(discovery, "selected_candidate", None)
    if selected is None or _inbox_selected_count(discovery) != 1:
        return None
    inbound = getattr(selected, "inbound", None)
    policy = getattr(selected, "policy_decision", None)
    governor = getattr(selected, "governor_decision", None)
    inbound_id = str(getattr(inbound, "inbound_id", "") or "").strip()
    reply_target_id = str(getattr(selected, "reply_target_id", "") or "").strip()
    classification = str(getattr(policy, "classification", "") or "").strip()
    reply_text = str(getattr(policy, "reply_text", "") or "").strip()
    if not inbound_id or not reply_target_id or not reply_text:
        return None
    return _safe_dict(
        {
            "provider_id": "x",
            "preview_kind": "reactive_inbox",
            "selected_inbound_id": inbound_id,
            "selected_reply_target_id": reply_target_id,
            "selected_classification": classification,
            "reply_text": reply_text,
            "governor": {
                "allowed": bool(getattr(governor, "allowed", False)),
                "action_tier": str(getattr(governor, "action_tier", "") or ""),
                "reasons": list(getattr(governor, "reasons", []) or []),
                "response_fingerprint": getattr(governor, "response_fingerprint", None),
            },
            "safety_gates": {
                "emergency_stop": bool(config.emergency_stop),
                "enable_goham_reactive": bool(config.enable_goham_reactive),
                "goham_reactive_dry_run": bool(config.goham_reactive_dry_run),
                "goham_reactive_live_canary": bool(config.goham_reactive_live_canary),
                "goham_reactive_max_replies_per_run": int(config.goham_reactive_max_replies_per_run),
                "goham_reactive_block_links": bool(config.goham_reactive_block_links),
            },
        }
    )


def _inbox_proposal_digest(discovery: Any, config: HamXConfig) -> str | None:
    payload = _inbox_proposal_payload(discovery, config)
    payload = _proposal_payload_with_persona(payload)
    return _proposal_digest("reactive_inbox", payload) if payload else None


def _discover_for_reactive_apply(config: HamXConfig) -> Any:
    return discover_reactive_inbox_once(config=_preview_config(config))


def _discover_batch_candidates(config: HamXConfig) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    discovery = discover_reactive_inbox_once(config=_preview_config(config))
    candidates: list[dict[str, Any]] = []
    for candidate in list(getattr(discovery, "candidates", []) or []):
        if getattr(candidate, "status", "") not in {"eligible", "selected"}:
            continue
        inbound = getattr(candidate, "inbound", None)
        if inbound is None:
            continue
        if hasattr(inbound, "model_dump"):
            candidates.append(inbound.model_dump(mode="json"))
        elif hasattr(inbound, "redacted_dump"):
            candidates.append(inbound.redacted_dump())
    if not candidates and getattr(discovery, "selected_inbound", None) is not None:
        inbound = discovery.selected_inbound
        if hasattr(inbound, "model_dump"):
            candidates.append(inbound.model_dump(mode="json"))
        elif hasattr(inbound, "redacted_dump"):
            candidates.append(inbound.redacted_dump())
    return candidates, _safe_payload(discovery)


def _batch_proposal_payload(result: dict[str, Any], config: HamXConfig) -> dict[str, Any] | None:
    items = list(result.get("items") or [])
    dry_items = [item for item in items if isinstance(item, dict) and item.get("status") == "dry_run"]
    if not dry_items:
        return None
    canonical_items: list[dict[str, Any]] = []
    for item in dry_items[: config.goham_reactive_batch_max_replies_per_run]:
        inbound = item.get("inbound") if isinstance(item.get("inbound"), dict) else {}
        policy = item.get("policy_decision") if isinstance(item.get("policy_decision"), dict) else {}
        governor = item.get("governor_decision") if isinstance(item.get("governor_decision"), dict) else {}
        canonical_items.append(
            _safe_dict(
                {
                    "inbound_id": inbound.get("inbound_id"),
                    "reply_target_id": inbound.get("post_id") or inbound.get("in_reply_to_post_id"),
                    "classification": policy.get("classification"),
                    "reply_text": policy.get("reply_text"),
                    "governor": {
                        "allowed": governor.get("allowed"),
                        "action_tier": governor.get("action_tier"),
                        "reasons": governor.get("reasons"),
                        "response_fingerprint": governor.get("response_fingerprint"),
                    },
                }
            )
        )
    return _safe_dict(
        {
            "provider_id": "x",
            "preview_kind": "reactive_batch",
            "items": canonical_items,
            "max_replies_per_run": int(config.goham_reactive_batch_max_replies_per_run),
            "safety_gates": {
                "emergency_stop": bool(config.emergency_stop),
                "enable_goham_reactive": bool(config.enable_goham_reactive),
                "enable_goham_reactive_batch": bool(config.enable_goham_reactive_batch),
                "goham_reactive_block_links": bool(config.goham_reactive_block_links),
                "goham_reactive_max_replies_per_15m": int(config.goham_reactive_max_replies_per_15m),
                "goham_reactive_max_replies_per_hour": int(config.goham_reactive_max_replies_per_hour),
                "goham_reactive_min_seconds_between_replies": int(config.goham_reactive_min_seconds_between_replies),
            },
        }
    )


def _batch_proposal_digest(result: dict[str, Any], config: HamXConfig) -> str | None:
    payload = _batch_proposal_payload(result, config)
    payload = _proposal_payload_with_persona(payload)
    return _proposal_digest("reactive_batch", payload) if payload else None


def _preview_config(config: HamXConfig) -> HamXConfig:
    """Force dry-run-oriented flags for preview evaluation only."""
    return replace(
        config,
        dry_run=True,
        enable_live_execution=False,
        enable_live_smoke=False,
        autonomy_enabled=False,
        goham_controller_dry_run=True,
        goham_reactive_dry_run=True,
        goham_reactive_live_canary=False,
        goham_reactive_batch_dry_run=True,
    )


def _reactive_preview_state(config: HamXConfig) -> tuple[ExecutionJournal, ReactiveGovernorState]:
    journal = ExecutionJournal(config=config)
    return journal, state_from_journal(journal)


def _record_preview_reactive_state(
    item: ReactiveInboundItem,
    fingerprint: str | None,
    state: ReactiveGovernorState,
    *,
    now: datetime,
) -> None:
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    user_key = item.author_id or item.author_handle or "unknown_user"
    thread_key = item.thread_id or item.conversation_id or item.post_id or item.inbound_id
    state.handled_inbound_ids.add(item.inbound_id)
    if fingerprint:
        state.response_fingerprints.add(fingerprint)
    state.per_user_last_reply_at[user_key] = stamp
    state.per_thread_last_reply_at[thread_key] = stamp
    state.recent_reply_times.append(stamp)
    state.user_reply_counts_today[user_key] = state.user_reply_counts_today.get(user_key, 0) + 1
    state.thread_reply_counts_today[thread_key] = state.thread_reply_counts_today.get(thread_key, 0) + 1


def _reactive_batch_preview(
    body: SocialPreviewRequest,
    config: HamXConfig,
) -> tuple[PreviewStatus, dict[str, Any], list[str], list[str]]:
    cfg = _preview_config(config)
    journal, state = _reactive_preview_state(cfg)
    warnings: list[str] = []
    reasons: list[str] = []
    discovered_payload: dict[str, Any] | None = None
    if body.candidates:
        candidates = body.candidates[: body.max_candidates or len(body.candidates) or 25]
    else:
        candidates, discovered_payload = _discover_batch_candidates(cfg)
        candidates = candidates[: body.max_candidates or len(candidates) or 25]
    if not candidates:
        warnings.append("no_candidates_provided")
    if not cfg.enable_goham_reactive:
        reasons.append("reactive_disabled")
    if not cfg.enable_goham_reactive_batch:
        reasons.append("reactive_batch_disabled")
    if cfg.emergency_stop:
        reasons.append("emergency_stop")

    items: list[dict[str, Any]] = []
    attempted_count = 0
    blocked_count = 0
    now = datetime.now(timezone.utc)
    for idx, raw in enumerate(candidates):
        try:
            inbound = ReactiveInboundItem.model_validate(raw)
        except Exception as exc:
            blocked_count += 1
            items.append(
                {
                    "status": "blocked",
                    "reasons": ["invalid_inbound_candidate"],
                    "diagnostic": str(exc),
                    "execution_allowed": False,
                    "mutation_attempted": False,
                }
            )
            continue
        policy = evaluate_reactive_policy(inbound, config=cfg)
        governor = evaluate_reactive_governor(
            inbound,
            policy,
            config=cfg,
            state=state,
            actions_this_run=attempted_count,
            now=now,
            live_canary=False,
        )
        item_reasons = _dedupe([*policy.reasons, *governor.reasons])
        if policy.route != "reply_candidate" or not policy.allowed:
            item_reasons.append(f"policy_route_{policy.route}")
        if not governor.allowed:
            item_reasons.append("governor_not_allowed")
        if attempted_count >= cfg.goham_reactive_batch_max_replies_per_run:
            item_reasons.append("max_replies_per_run_reached")
        status = "blocked" if item_reasons else "dry_run"
        if status == "dry_run":
            attempted_count += 1
            _record_preview_reactive_state(inbound, governor.response_fingerprint, state, now=now)
        else:
            blocked_count += 1
        items.append(
            _safe_dict(
                {
                    "index": idx,
                    "status": status,
                    "inbound": inbound.redacted_dump(),
                    "policy_decision": policy.redacted_dump(),
                    "governor_decision": governor.redacted_dump(),
                    "reasons": _dedupe(item_reasons),
                    "execution_allowed": False,
                    "mutation_attempted": False,
                }
            )
        )

    result = {
        "status": "completed" if not reasons else "blocked",
        "candidate_count": len(candidates),
        "processed_count": len(items),
        "attempted_count": attempted_count,
        "blocked_count": blocked_count,
        "items": items,
        "journal_path": _display_path(journal.path),
        "audit_path": _display_path(cfg.audit_log_path),
        "diagnostic": "Reactive batch preview is dry-run-only and does not call providers.",
    }
    if discovered_payload is not None:
        result["discovery"] = discovered_payload
    status_out: PreviewStatus = "blocked" if reasons else "completed"
    return status_out, result, _dedupe(reasons), warnings


def _preflight_request_from_body(body: SocialPreviewRequest, config: HamXConfig) -> SimpleNamespace:
    raw = dict(body.preflight_candidate or {})
    text = str(raw.get("text") or "Ham preview-only broadcast preflight: governed autonomy stays capped, audited, and dry-run by default.")
    action_id = str(raw.get("action_id") or "social-preview-broadcast-preflight")
    source_action_id = str(raw.get("source_action_id") or action_id)
    idem = str(raw.get("idempotency_key") or f"social-preview-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]}")
    return SimpleNamespace(
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=config.campaign_id,
        account_id=config.account_id,
        action_type=str(raw.get("action_type") or "post"),
        text=text,
        action_id=action_id,
        source_action_id=source_action_id,
        idempotency_key=idem,
        target_post_id=raw.get("target_post_id"),
        quote_target_id=raw.get("quote_target_id"),
        reply_target_id=raw.get("reply_target_id"),
    )


def _server_broadcast_candidate(config: HamXConfig) -> GohamGovernorCandidate:
    text = "Ham is live-checking governed social automation with one capped, audited original post."
    digest = hashlib.sha256(f"{config.campaign_id}:{text}".encode("utf-8")).hexdigest()[:24]
    return GohamGovernorCandidate(
        action_id="social-broadcast-preview",
        source_action_id="social-broadcast-preview",
        idempotency_key=f"social-broadcast-{digest}",
        action_type="post",
        text=text,
        topic="social",
        score=1.0,
        metadata={"source": "social_broadcast_preflight"},
    )


def _server_broadcast_preflight(config: HamXConfig) -> tuple[dict[str, Any], GohamGovernorCandidate, list[str]]:
    cfg = _preview_config(config)
    journal = ExecutionJournal(config=cfg)
    candidate = _server_broadcast_candidate(cfg)
    decision = evaluate_goham_governor(candidate, config=cfg, journal=journal)
    request = SimpleNamespace(
        tenant_id=cfg.tenant_id,
        agent_id=cfg.agent_id,
        campaign_id=cfg.campaign_id,
        account_id=cfg.account_id,
        action_type=candidate.action_type,
        text=candidate.text,
        action_id=candidate.action_id,
        source_action_id=candidate.source_action_id,
        idempotency_key=candidate.idempotency_key,
        target_post_id=candidate.target_post_id,
        quote_target_id=candidate.quote_target_id,
        reply_target_id=None,
    )
    autonomy = _preflight_decision(request, cfg)
    eligibility = dry_preflight_goham_candidate(request, autonomy, config=cfg, journal=journal)
    result = _force_preview_flags(
        {
            "candidate": _safe_payload(candidate),
            "governor_decision": _safe_payload(decision),
            "eligibility": _safe_payload(eligibility),
            "journal_path": _display_path(journal.path),
            "audit_path": _display_path(cfg.audit_log_path),
            "diagnostic": "Broadcast preflight preview is eligibility-only and does not call GoHAM bridge or X providers.",
        }
    )
    reasons = _dedupe([*decision.reasons, *decision.provider_block_reasons, *eligibility.reasons])
    return result, candidate, reasons


def _broadcast_proposal_payload(result: dict[str, Any], config: HamXConfig) -> dict[str, Any] | None:
    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
    governor = result.get("governor_decision") if isinstance(result.get("governor_decision"), dict) else {}
    eligibility = result.get("eligibility") if isinstance(result.get("eligibility"), dict) else {}
    if candidate.get("action_type") != "post":
        return None
    if not candidate.get("action_id") or not candidate.get("text"):
        return None
    return _safe_dict(
        {
            "provider_id": "x",
            "preview_kind": "broadcast_preflight",
            "candidate": {
                "action_id": candidate.get("action_id"),
                "source_action_id": candidate.get("source_action_id"),
                "idempotency_key": candidate.get("idempotency_key"),
                "action_type": candidate.get("action_type"),
                "text": candidate.get("text"),
                "topic": candidate.get("topic"),
            },
            "campaign": {
                "campaign_id": config.campaign_id,
                "account_id": config.account_id,
                "tenant_id": config.tenant_id,
                "agent_id": config.agent_id,
            },
            "governor": {
                "allowed": governor.get("allowed"),
                "action_tier": governor.get("action_tier"),
                "reasons": governor.get("reasons"),
                "provider_call_allowed": governor.get("provider_call_allowed"),
                "provider_block_reasons": governor.get("provider_block_reasons"),
                "budget": governor.get("budget"),
            },
            "eligibility": {
                "allowed": eligibility.get("allowed"),
                "reasons": eligibility.get("reasons"),
            },
            "safety_gates": {
                "emergency_stop": bool(config.emergency_stop),
                "enable_goham_execution": bool(config.enable_goham_execution),
                "enable_goham_controller": bool(config.enable_goham_controller),
                "enable_goham_live_controller": bool(config.enable_goham_live_controller),
                "autonomy_enabled": bool(config.autonomy_enabled),
                "dry_run": bool(config.dry_run),
                "enable_live_execution": bool(config.enable_live_execution),
                "goham_live_max_actions_per_run": int(config.goham_live_max_actions_per_run),
                "goham_block_links": bool(config.goham_block_links),
            },
        }
    )


def _broadcast_proposal_digest(result: dict[str, Any], config: HamXConfig) -> str | None:
    payload = _broadcast_proposal_payload(result, config)
    payload = _proposal_payload_with_persona(payload)
    return _proposal_digest("broadcast_preflight", payload) if payload else None


def _setup_missing_requirements(cfg: HamXConfig) -> list[str]:
    missing: list[str] = []
    if not _x_read_credential_present(cfg):
        missing.append("x_read_credential")
    if not _x_write_credential_present(cfg):
        missing.append("x_write_credential")
    if not _xai_key_present(cfg):
        missing.append("xai_key")
    if not _reactive_handle_configured(cfg):
        missing.append("reactive_handle")
    if not _social_live_token_enabled():
        missing.append("social_live_apply_token")
    if cfg.emergency_stop:
        missing.append("emergency_stop_disabled")
    if not cfg.enable_goham_reactive:
        missing.append("reactive_enabled")
    if not cfg.enable_goham_reactive_batch:
        missing.append("reactive_batch_enabled")
    if not cfg.enable_goham_controller:
        missing.append("goham_controller_enabled")
    if not cfg.enable_goham_live_controller:
        missing.append("goham_live_controller_enabled")
    return _dedupe(missing)


def _setup_next_steps(cfg: HamXConfig, missing: list[str]) -> list[str]:
    steps: list[str] = []
    if "x_read_credential" in missing:
        steps.append("Configure the X Bearer token on the API host to enable read-only discovery.")
    if "x_write_credential" in missing:
        steps.append("Configure X OAuth write credentials on the API host before confirmed live controls can run.")
    if "xai_key" in missing:
        steps.append("Configure the xAI key on the API host to enable model-backed broadcast dry-runs.")
    if "reactive_handle" in missing:
        steps.append("Set a reactive handle or inbox query so X inbox discovery can find inbound items.")
    if "social_live_apply_token" in missing:
        steps.append("Set HAM_SOCIAL_LIVE_APPLY_TOKEN on the API host to enable confirmed live controls.")
    if cfg.emergency_stop:
        steps.append("Emergency stop is enabled; live controls will remain blocked until it is disabled server-side.")
    if not steps:
        steps.append("Readiness checks look healthy. Use previews before any confirmed live action.")
    return steps


def _preflight_decision(request: SimpleNamespace, config: HamXConfig) -> AutonomyDecisionResult:
    return AutonomyDecisionResult(
        decision="auto_approve",
        execution_state="candidate_only",
        execution_allowed=False,
        confidence=1.0,
        risk_level="low",
        reasons=["social_preview_only"],
        requires_human_review=False,
        score_100=100,
        raw_score=1.0,
        safety_severity="low",
        tenant_id=config.tenant_id,
        agent_id=config.agent_id,
        campaign_id=config.campaign_id,
        account_id=config.account_id,
        profile_id=config.profile_id,
        policy_profile_id=config.policy_profile_id,
        brand_voice_id=config.brand_voice_id,
        autonomy_mode="goham",
        catalog_skill_id=config.catalog_skill_id,
        action_id=str(request.action_id),
    )


def _safe_preflight_request(request: SimpleNamespace) -> dict[str, Any]:
    return _safe_dict(
        {
            "action_id": request.action_id,
            "source_action_id": request.source_action_id,
            "action_type": request.action_type,
            "text": request.text,
            "target_post_id": request.target_post_id,
            "quote_target_id": request.quote_target_id,
            "reply_target_id": request.reply_target_id,
        }
    )


def _overall_readiness(cfg: HamXConfig) -> tuple[OverallReadiness, list[str]]:
    reasons: list[str] = []
    if cfg.emergency_stop:
        reasons.append("emergency_stop")
        return "blocked", reasons
    if not _x_configured(cfg):
        reasons.append("no_x_credentials_or_xai_key")
        return "setup_required", reasons
    if (
        _broadcast_live_configured(cfg)
        or _broadcast_dry_run_available(cfg)
        or _reactive_inbox_discovery_available(cfg)
        or (cfg.enable_goham_reactive and cfg.goham_reactive_dry_run)
    ):
        return "ready", reasons
    reasons.append("no_lane_enabled")
    return "limited", reasons


def _x_provider_dto(cfg: HamXConfig) -> SocialProviderDto:
    enabled_lanes: list[str] = []
    if (
        _broadcast_live_configured(cfg)
        or _broadcast_dry_run_available(cfg)
        or cfg.enable_goham_controller
        or cfg.enable_goham_live_controller
    ):
        enabled_lanes.append("broadcast")
    if (
        cfg.enable_goham_reactive
        or cfg.enable_reactive_inbox_discovery
        or cfg.enable_goham_reactive_batch
    ):
        enabled_lanes.append("reactive")
    if cfg.emergency_stop:
        status: ProviderStatus = "blocked"
    elif _x_configured(cfg):
        status = "active"
    else:
        status = "setup_required"
    return SocialProviderDto(
        id="x",
        label="X",
        status=status,
        configured=_x_configured(cfg),
        coming_soon=False,
        enabled_lanes=enabled_lanes,
    )


_FUTURE_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("bluesky", "Bluesky"),
    ("farcaster", "Farcaster"),
    ("linkedin", "LinkedIn"),
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=SocialProvidersResponse)
def list_social_providers(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialProvidersResponse:
    cfg = load_ham_x_config()
    providers: list[SocialProviderDto] = [
        _x_provider_dto(cfg),
        _messaging_provider_dto("telegram"),
        _messaging_provider_dto("discord"),
    ]
    for pid, label in _FUTURE_PROVIDERS:
        providers.append(
            SocialProviderDto(
                id=pid,
                label=label,
                status="coming_soon",
                configured=False,
                coming_soon=True,
                enabled_lanes=[],
            )
        )
    return SocialProvidersResponse(providers=providers)


@router.get("/persona/current", response_model=SocialPersonaResponse)
def current_social_persona(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialPersonaResponse:
    return _social_persona_response()


@router.get("/personas/ham-canonical", response_model=SocialPersonaResponse)
def ham_canonical_social_persona(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialPersonaResponse:
    return _social_persona_response()


@router.get("/providers/telegram/status", response_model=SocialMessagingProviderStatusResponse)
def telegram_provider_status(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialMessagingProviderStatusResponse:
    return _telegram_status_response()


@router.get("/providers/telegram/capabilities", response_model=TelegramCapabilitiesResponse)
def telegram_capabilities(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> TelegramCapabilitiesResponse:
    connections = _telegram_connections()
    runtime = _hermes_runtime_status("telegram")
    readiness, _reasons = _messaging_readiness("telegram", connections, runtime)
    return TelegramCapabilitiesResponse(
        bot_token_present=connections["bot_token_present"],
        allowed_users_configured=connections["allowed_users_configured"],
        home_channel_configured=connections["home_channel_configured"],
        test_group_configured=connections["test_group_configured"],
        telegram_mode=_telegram_mode(),
        hermes_gateway_base_url_present=runtime.base_url_configured,
        hermes_gateway_status_path_present=runtime.status_path_configured,
        hermes_gateway_runtime_state=runtime.provider_runtime_state,
        telegram_platform_state=_telegram_platform_state(runtime),
        readiness=readiness,
        missing_requirements=_telegram_missing_requirements(connections, runtime),
        recommended_next_steps=_telegram_setup_steps(connections, runtime),
        inbound_available=runtime.provider_runtime_state == "connected",
        preview_available=runtime.provider_runtime_state == "connected",
        live_message_available=readiness == "ready" and _social_live_token_enabled(),
        live_apply_available=readiness == "ready" and _social_live_token_enabled(),
    )


@router.get("/providers/telegram/setup/checklist", response_model=SocialMessagingSetupChecklistResponse)
def telegram_setup_checklist(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialMessagingSetupChecklistResponse:
    connections = _telegram_connections()
    runtime = _hermes_runtime_status("telegram")
    return SocialMessagingSetupChecklistResponse(
        provider_id="telegram",
        items=[
            SetupChecklistItemDto(
                id="telegram_bot_token",
                label="Telegram bot token present",
                ok=connections["bot_token_present"],
            ),
            SetupChecklistItemDto(
                id="telegram_allowed_users",
                label="Telegram allowlist or pairing gate configured",
                ok=connections["allowed_users_configured"],
            ),
            SetupChecklistItemDto(
                id="telegram_home_channel",
                label="Telegram home channel configured",
                ok=connections["home_channel_configured"],
            ),
            SetupChecklistItemDto(
                id="telegram_test_group",
                label="Telegram private test group configured",
                ok=connections["test_group_configured"],
            ),
            SetupChecklistItemDto(
                id="telegram_mode",
                label="Telegram gateway mode selected",
                ok=_telegram_mode() != "unset",
            ),
            SetupChecklistItemDto(
                id="hermes_gateway_status",
                label="Hermes gateway status source configured",
                ok=runtime.base_url_configured or runtime.status_path_configured,
            ),
            SetupChecklistItemDto(
                id="hermes_gateway_runtime",
                label="Hermes gateway reports Telegram connected",
                ok=runtime.provider_runtime_state == "connected",
            ),
        ],
        recommended_next_steps=_telegram_setup_steps(connections, runtime),
    )


@router.post("/providers/telegram/messages/preview", response_model=TelegramMessagePreviewResponse)
def telegram_message_preview(
    body: TelegramMessagePreviewRequest | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> TelegramMessagePreviewResponse:
    return _telegram_preview_response(body or TelegramMessagePreviewRequest())


@router.post("/providers/telegram/messages/apply", response_model=TelegramMessageApplyResponse)
def telegram_message_apply(
    body: TelegramMessageApplyRequest,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> TelegramMessageApplyResponse:
    del _actor
    if not body.proposal_digest:
        return _telegram_apply_blocked_response(reasons=["proposal_digest_required"])
    if body.confirmation_phrase.strip() != LIVE_TELEGRAM_CONFIRMATION_PHRASE:
        return _telegram_apply_blocked_response(reasons=["confirmation_phrase_required"])

    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_social_live_token(ham_bearer)

    preview = _telegram_preview_response(TelegramMessagePreviewRequest(message_intent=body.message_intent))
    if preview.status != "completed" or not preview.proposal_digest:
        return _telegram_apply_blocked_response(
            reasons=["telegram_preview_not_available", *preview.reasons],
            preview=preview,
            warnings=preview.warnings,
        )
    if body.proposal_digest != preview.proposal_digest:
        return _telegram_apply_blocked_response(
            reasons=["proposal_digest_mismatch", "persona_digest_mismatch"],
            preview=preview,
            result={"expected_preview_status": preview.status},
        )

    readiness_reasons = _telegram_readiness_apply_reasons()
    if readiness_reasons:
        return _telegram_apply_blocked_response(reasons=readiness_reasons, preview=preview)

    request = TelegramSendRequest(
        target_kind=preview.target.kind,
        text=preview.message_preview.text,
        proposal_digest=preview.proposal_digest,
        persona_digest=preview.persona_digest,
        idempotency_key=_telegram_apply_idempotency_key(preview.proposal_digest),
        telegram_connected=True,
    )
    send_result = send_confirmed_telegram_message(request)
    return TelegramMessageApplyResponse(
        **_persona_ref_fields(),
        status=send_result.status,
        execution_allowed=bool(send_result.execution_allowed),
        mutation_attempted=bool(send_result.mutation_attempted),
        live_apply_available=_telegram_live_apply_available(),
        provider_message_id=send_result.provider_message_id,
        target=preview.target,
        reasons=_dedupe(send_result.reasons),
        warnings=_dedupe(send_result.warnings),
        result=_safe_dict(
            {
                "execution_kind": TELEGRAM_EXECUTION_KIND,
                "target_ref": send_result.target_ref,
                **send_result.result,
            }
        ),
    )


@router.get("/providers/discord/status", response_model=SocialMessagingProviderStatusResponse)
def discord_provider_status(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialMessagingProviderStatusResponse:
    return _discord_status_response()


@router.get("/providers/discord/capabilities", response_model=DiscordCapabilitiesResponse)
def discord_capabilities(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> DiscordCapabilitiesResponse:
    connections = _discord_connections()
    runtime = _hermes_runtime_status("discord")
    return DiscordCapabilitiesResponse(
        bot_token_present=connections["bot_token_present"],
        allowed_users_or_roles_configured=connections["allowed_users_or_roles_configured"],
        guild_or_channel_configured=connections["guild_or_channel_configured"],
        inbound_available=runtime.provider_runtime_state == "connected",
    )


@router.get("/providers/discord/setup/checklist", response_model=SocialMessagingSetupChecklistResponse)
def discord_setup_checklist(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> SocialMessagingSetupChecklistResponse:
    connections = _discord_connections()
    runtime = _hermes_runtime_status("discord")
    return SocialMessagingSetupChecklistResponse(
        provider_id="discord",
        items=[
            SetupChecklistItemDto(
                id="discord_bot_token",
                label="Discord bot token present",
                ok=connections["bot_token_present"],
            ),
            SetupChecklistItemDto(
                id="discord_allowed_users_or_roles",
                label="Discord allowlist or role gate configured",
                ok=connections["allowed_users_or_roles_configured"],
            ),
            SetupChecklistItemDto(
                id="discord_guild_or_channel",
                label="Discord guild/channel routing configured",
                ok=connections["guild_or_channel_configured"],
            ),
            SetupChecklistItemDto(
                id="hermes_gateway_runtime",
                label="Hermes gateway reports Discord connected",
                ok=runtime.provider_runtime_state == "connected",
            ),
        ],
        recommended_next_steps=_discord_setup_steps(connections, runtime),
    )


@router.get("/providers/x/status", response_model=XProviderStatusResponse)
def x_provider_status(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XProviderStatusResponse:
    cfg = load_ham_x_config()
    readiness, readiness_reasons = _overall_readiness(cfg)
    cap, used, remaining, exec_allowed = _broadcast_status_from_ops(cfg)
    broadcast = BroadcastLaneStatusDto(
        enabled=bool(cfg.enable_goham_execution or cfg.enable_goham_controller or cfg.enable_goham_live_controller),
        controller_enabled=cfg.enable_goham_controller,
        live_controller_enabled=cfg.enable_goham_live_controller,
        dry_run_available=_broadcast_dry_run_available(cfg),
        live_configured=_broadcast_live_configured(cfg),
        execution_allowed_now=exec_allowed,
        reasons=_broadcast_lane_reasons(cfg),
    )
    reactive = ReactiveLaneStatusDto(
        enabled=cfg.enable_goham_reactive,
        inbox_discovery_enabled=cfg.enable_reactive_inbox_discovery,
        dry_run_enabled=cfg.goham_reactive_dry_run,
        live_canary_enabled=cfg.goham_reactive_live_canary,
        batch_enabled=cfg.enable_goham_reactive_batch,
        reasons=_reactive_lane_reasons(cfg),
    )
    cap_summary = CapCooldownSummaryDto(
        broadcast_daily_cap=cap,
        broadcast_daily_used=used,
        broadcast_daily_remaining=remaining,
        broadcast_per_run_cap=int(cfg.goham_autonomous_per_run_cap),
        broadcast_min_spacing_minutes=int(cfg.goham_min_spacing_minutes),
        reactive_max_replies_per_15m=int(cfg.goham_reactive_max_replies_per_15m),
        reactive_max_replies_per_hour=int(cfg.goham_reactive_max_replies_per_hour),
        reactive_max_replies_per_user_per_day=int(cfg.goham_reactive_max_replies_per_user_per_day),
        reactive_max_replies_per_thread_per_day=int(cfg.goham_reactive_max_replies_per_thread_per_day),
        reactive_min_seconds_between_replies=int(cfg.goham_reactive_min_seconds_between_replies),
        reactive_batch_max_replies_per_run=int(cfg.goham_reactive_batch_max_replies_per_run),
    )
    return XProviderStatusResponse(
        overall_readiness=readiness,
        readiness_reasons=readiness_reasons,
        emergency_stop=EmergencyStopDto(enabled=cfg.emergency_stop),
        dry_run_defaults=DryRunDefaultsDto(
            global_dry_run=cfg.dry_run,
            controller_dry_run=cfg.goham_controller_dry_run,
            reactive_dry_run=cfg.goham_reactive_dry_run,
            reactive_batch_dry_run=cfg.goham_reactive_batch_dry_run,
        ),
        broadcast_lane=broadcast,
        reactive_lane=reactive,
        last_autonomous_post=_last_autonomous_post(cfg),
        last_reactive_reply=_last_reactive_reply(cfg),
        cap_cooldown_summary=cap_summary,
        paths=SafePathsDto(
            execution_journal_path=_display_path(cfg.execution_journal_path),
            audit_log_path=_display_path(cfg.audit_log_path),
        ),
    )


@router.get("/providers/x/capabilities", response_model=XCapabilitiesResponse)
def x_capabilities(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XCapabilitiesResponse:
    cfg = load_ham_x_config()
    return XCapabilitiesResponse(
        live_read_available=_x_read_credential_present(cfg)
        and (cfg.readonly_transport or "").strip().lower() == "direct",
        live_model_available=_xai_key_present(cfg),
        broadcast_dry_run_available=_broadcast_dry_run_available(cfg),
        broadcast_live_available=_broadcast_live_configured(cfg),
        broadcast_apply_available=_broadcast_apply_available(cfg),
        reactive_inbox_discovery_available=_reactive_inbox_discovery_available(cfg),
        reactive_dry_run_available=cfg.enable_goham_reactive and cfg.goham_reactive_dry_run,
        reactive_reply_canary_available=_reactive_reply_canary_available(cfg),
        reactive_batch_available=cfg.enable_goham_reactive and cfg.enable_goham_reactive_batch,
        reactive_reply_apply_available=_reply_apply_available(cfg),
        reactive_batch_apply_available=_batch_apply_available(cfg),
        live_apply_available=_apply_available(cfg),
    )


@router.get("/providers/x/setup/checklist", response_model=XSetupChecklistResponse)
def x_setup_checklist(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XSetupChecklistResponse:
    cfg = load_ham_x_config()
    items = [
        SetupChecklistItemDto(
            id="x_read_credential",
            label="X read credential present",
            ok=_x_read_credential_present(cfg),
        ),
        SetupChecklistItemDto(
            id="x_write_credential",
            label="X write credentials present",
            ok=_x_write_credential_present(cfg),
        ),
        SetupChecklistItemDto(
            id="xai_key",
            label="xAI key present",
            ok=_xai_key_present(cfg),
        ),
        SetupChecklistItemDto(
            id="reactive_handle",
            label="Reactive handle configured",
            ok=_reactive_handle_configured(cfg),
        ),
        SetupChecklistItemDto(
            id="emergency_stop",
            label="Emergency stop disabled",
            ok=not cfg.emergency_stop,
        ),
    ]
    feature_flags: dict[str, bool] = {
        "ham_x_dry_run": bool(cfg.dry_run),
        "ham_x_enable_live_read_model_dry_run": bool(cfg.enable_live_read_model_dry_run),
        "ham_x_enable_goham_execution": bool(cfg.enable_goham_execution),
        "ham_x_enable_goham_controller": bool(cfg.enable_goham_controller),
        "ham_x_enable_goham_live_controller": bool(cfg.enable_goham_live_controller),
        "ham_x_enable_goham_reactive": bool(cfg.enable_goham_reactive),
        "ham_x_enable_reactive_inbox_discovery": bool(cfg.enable_reactive_inbox_discovery),
        "ham_x_enable_goham_reactive_batch": bool(cfg.enable_goham_reactive_batch),
        "ham_x_goham_reactive_live_canary": bool(cfg.goham_reactive_live_canary),
        "ham_x_autonomy_enabled": bool(cfg.autonomy_enabled),
        "ham_x_enable_live_execution": bool(cfg.enable_live_execution),
    }
    return XSetupChecklistResponse(items=items, feature_flags=feature_flags)


@router.get("/providers/x/setup/summary", response_model=XSetupSummaryResponse)
def x_setup_summary(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XSetupSummaryResponse:
    cfg = load_ham_x_config()
    readiness, _readiness_reasons = _overall_readiness(cfg)
    missing = _setup_missing_requirements(cfg)
    connections = {
        "x_read_credential_present": _x_read_credential_present(cfg),
        "x_write_credential_present": _x_write_credential_present(cfg),
        "xai_key_present": _xai_key_present(cfg),
        "reactive_handle_configured": _reactive_handle_configured(cfg),
        "operator_token_ready": _social_live_token_enabled(),
        "emergency_stop_disabled": not cfg.emergency_stop,
    }
    lane_readiness = {
        "broadcast": {
            "dry_run_available": _broadcast_dry_run_available(cfg),
            "live_configured": _broadcast_live_configured(cfg),
            "confirmed_live_available": _broadcast_apply_available(cfg),
            "missing": [item for item in missing if item in {"x_write_credential", "social_live_apply_token", "goham_controller_enabled", "goham_live_controller_enabled", "emergency_stop_disabled"}],
        },
        "reactive": {
            "inbox_discovery_available": _reactive_inbox_discovery_available(cfg),
            "dry_run_available": bool(cfg.enable_goham_reactive and cfg.goham_reactive_dry_run),
            "reply_apply_available": _reply_apply_available(cfg),
            "batch_apply_available": _batch_apply_available(cfg),
            "missing": [item for item in missing if item in {"x_read_credential", "x_write_credential", "reactive_handle", "reactive_enabled", "reactive_batch_enabled", "social_live_apply_token", "emergency_stop_disabled"}],
        },
        "preview": {
            "status_refresh_available": True,
            "inbox_preview_available": _reactive_inbox_discovery_available(cfg),
            "batch_dry_run_available": bool(cfg.enable_goham_reactive and cfg.enable_goham_reactive_batch),
            "broadcast_preflight_available": _broadcast_dry_run_available(cfg),
        },
        "confirmed_live": {
            "live_reply_available": _reply_apply_available(cfg),
            "reactive_batch_available": _batch_apply_available(cfg),
            "broadcast_available": _broadcast_apply_available(cfg),
        },
    }
    safe_identifiers = {
        "tenant_id": _safe_id(cfg.tenant_id),
        "agent_id": _safe_id(cfg.agent_id),
        "campaign_id": _safe_id(cfg.campaign_id),
        "account_id": _safe_id(cfg.account_id),
        "profile_id": _safe_id(cfg.profile_id),
        "policy_profile_id": _safe_id(cfg.policy_profile_id),
        "brand_voice_id": _safe_id(cfg.brand_voice_id),
    }
    caps = {
        "broadcast_daily_cap": int(cfg.goham_autonomous_daily_cap),
        "broadcast_per_run_cap": int(cfg.goham_autonomous_per_run_cap),
        "broadcast_min_spacing_minutes": int(cfg.goham_min_spacing_minutes),
        "reactive_max_replies_per_15m": int(cfg.goham_reactive_max_replies_per_15m),
        "reactive_max_replies_per_hour": int(cfg.goham_reactive_max_replies_per_hour),
        "reactive_max_replies_per_user_per_day": int(cfg.goham_reactive_max_replies_per_user_per_day),
        "reactive_max_replies_per_thread_per_day": int(cfg.goham_reactive_max_replies_per_thread_per_day),
        "reactive_min_seconds_between_replies": int(cfg.goham_reactive_min_seconds_between_replies),
        "reactive_batch_max_replies_per_run": int(cfg.goham_reactive_batch_max_replies_per_run),
    }
    flags = {
        "ham_x_dry_run": bool(cfg.dry_run),
        "ham_x_emergency_stop": bool(cfg.emergency_stop),
        "ham_x_autonomy_enabled": bool(cfg.autonomy_enabled),
        "ham_x_enable_live_execution": bool(cfg.enable_live_execution),
        "ham_x_enable_live_read_model_dry_run": bool(cfg.enable_live_read_model_dry_run),
        "ham_x_enable_goham_execution": bool(cfg.enable_goham_execution),
        "ham_x_enable_goham_controller": bool(cfg.enable_goham_controller),
        "ham_x_enable_goham_live_controller": bool(cfg.enable_goham_live_controller),
        "ham_x_enable_goham_reactive": bool(cfg.enable_goham_reactive),
        "ham_x_enable_reactive_inbox_discovery": bool(cfg.enable_reactive_inbox_discovery),
        "ham_x_enable_goham_reactive_batch": bool(cfg.enable_goham_reactive_batch),
        "ham_x_goham_reactive_live_canary": bool(cfg.goham_reactive_live_canary),
    }
    return XSetupSummaryResponse(
        provider_configured=_x_configured(cfg),
        overall_readiness=readiness,
        missing_requirement_ids=missing,
        ready_for_dry_run=_broadcast_dry_run_available(cfg) or _reactive_inbox_discovery_available(cfg),
        ready_for_confirmed_live_reply=_reply_apply_available(cfg),
        ready_for_reactive_batch=_batch_apply_available(cfg),
        ready_for_broadcast=_broadcast_apply_available(cfg),
        required_connections=connections,
        lane_readiness=lane_readiness,
        safe_identifiers=safe_identifiers,
        caps_cooldowns=caps,
        feature_flags=flags,
        recommended_next_steps=_setup_next_steps(cfg, missing),
    )


@router.get("/providers/x/journal/summary", response_model=XJournalSummaryResponse)
def x_journal_summary(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XJournalSummaryResponse:
    cfg = load_ham_x_config()
    rows, malformed = _bounded_jsonl_tail(Path(cfg.execution_journal_path))
    counts: dict[str, int] = {}
    latest_broadcast: dict[str, Any] | None = None
    latest_reactive: dict[str, Any] | None = None
    for row in rows:
        kind = str(row.get("execution_kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
        executed_at = str(row.get("executed_at") or "")
        if row.get("status") == "executed":
            if kind == GOHAM_EXECUTION_KIND:
                if latest_broadcast is None or executed_at > str(latest_broadcast.get("executed_at", "")):
                    latest_broadcast = row
            elif kind == GOHAM_REACTIVE_EXECUTION_KIND:
                if latest_reactive is None or executed_at > str(latest_reactive.get("executed_at", "")):
                    latest_reactive = row
    recent = [_safe_journal_item(row) for row in rows[-MAX_RECENT_ITEMS:]]
    return XJournalSummaryResponse(
        journal_path=_display_path(cfg.execution_journal_path),
        total_count_scanned=len(rows),
        malformed_count=malformed,
        counts_by_execution_kind=counts,
        latest_broadcast_post=_safe_journal_item(latest_broadcast) if latest_broadcast else None,
        latest_reactive_reply=_safe_journal_item(latest_reactive) if latest_reactive else None,
        recent_items=recent,
    )


@router.get("/providers/x/audit/summary", response_model=XAuditSummaryResponse)
def x_audit_summary(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> XAuditSummaryResponse:
    cfg = load_ham_x_config()
    rows, malformed = _bounded_jsonl_tail(Path(cfg.audit_log_path))
    counts: dict[str, int] = {}
    audit_ids: list[str] = []
    for row in rows:
        event_type = str(row.get("event_type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
        aid = row.get("audit_id")
        if isinstance(aid, str) and aid:
            audit_ids.append(aid)
    latest_audit_ids = audit_ids[-MAX_RECENT_EVENTS:]
    recent = [_safe_audit_event(row) for row in rows[-MAX_RECENT_EVENTS:]]
    return XAuditSummaryResponse(
        audit_path=_display_path(cfg.audit_log_path),
        total_count_scanned=len(rows),
        malformed_count=malformed,
        counts_by_event_type=counts,
        latest_audit_ids=latest_audit_ids,
        recent_events=recent,
    )


@router.post("/providers/x/reactive/inbox/preview", response_model=SocialPreviewResponse)
def x_reactive_inbox_preview(
    body: SocialPreviewRequest | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> SocialPreviewResponse:
    del _actor
    request = body or SocialPreviewRequest()
    actual_cfg = load_ham_x_config()
    result = discover_reactive_inbox_once(config=_preview_config(actual_cfg))
    payload = _force_preview_flags(_safe_payload(result))
    proposal_digest = _inbox_proposal_digest(result, actual_cfg)
    reasons = _dedupe(list(result.reasons))
    status: PreviewStatus = "completed" if result.status == "completed" else "blocked"
    return SocialPreviewResponse(
        **_persona_ref_fields(),
        preview_kind="reactive_inbox",
        status=status,
        reasons=reasons,
        warnings=[],
        result=payload,
        proposal_digest=proposal_digest,
    )


@router.post("/providers/x/reactive/batch/dry-run", response_model=SocialPreviewResponse)
def x_reactive_batch_dry_run(
    body: SocialPreviewRequest | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> SocialPreviewResponse:
    del _actor
    request = body or SocialPreviewRequest()
    actual_cfg = load_ham_x_config()
    status, result, reasons, warnings = _reactive_batch_preview(request, actual_cfg)
    payload = _force_preview_flags(result)
    proposal_digest = _batch_proposal_digest(result, actual_cfg)
    return SocialPreviewResponse(
        **_persona_ref_fields(),
        preview_kind="reactive_batch_dry_run",
        status=status,
        reasons=reasons,
        warnings=warnings,
        result=payload,
        proposal_digest=proposal_digest,
    )


@router.post("/providers/x/broadcast/preflight", response_model=SocialPreviewResponse)
def x_broadcast_preflight(
    body: SocialPreviewRequest | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> SocialPreviewResponse:
    del _actor
    request = body or SocialPreviewRequest()
    actual_cfg = load_ham_x_config()
    if request.preflight_candidate:
        cfg = _preview_config(actual_cfg)
        journal = ExecutionJournal(config=cfg)
        preflight_request = _preflight_request_from_body(request, cfg)
        decision = _preflight_decision(preflight_request, cfg)
        result = dry_preflight_goham_candidate(preflight_request, decision, config=cfg, journal=journal)
        payload = _force_preview_flags(
            {
                "request": _safe_preflight_request(preflight_request),
                "decision": _safe_payload(decision),
                "eligibility": _safe_payload(result),
                "journal_path": _display_path(journal.path),
                "audit_path": _display_path(cfg.audit_log_path),
                "diagnostic": "Broadcast preflight preview is eligibility-only and does not call GoHAM bridge or X providers.",
            }
        )
        proposal_digest = None
        status = "completed" if result.allowed else "blocked"
        reasons = list(result.reasons)
    else:
        payload, _candidate, reasons = _server_broadcast_preflight(actual_cfg)
        proposal_digest = _broadcast_proposal_digest(payload, actual_cfg)
        status = "completed" if proposal_digest else "blocked"
    return SocialPreviewResponse(
        **_persona_ref_fields(),
        preview_kind="broadcast_preflight",
        status=status,
        reasons=reasons,
        warnings=[],
        result=payload,
        proposal_digest=proposal_digest,
    )


@router.post("/providers/x/reactive/reply/apply", response_model=SocialReactiveReplyApplyResponse)
def x_reactive_reply_apply(
    body: SocialReactiveReplyApplyRequest,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> SocialReactiveReplyApplyResponse:
    del _actor
    cfg = load_ham_x_config()
    if not body.proposal_digest:
        return _blocked_apply_response(cfg, reasons=["proposal_digest_required"])
    if body.confirmation_phrase.strip() != LIVE_REPLY_CONFIRMATION_PHRASE:
        return _blocked_apply_response(cfg, reasons=["confirmation_phrase_required"])

    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_social_live_token(ham_bearer)

    gate_reasons = _reactive_apply_reasons(cfg)
    if gate_reasons:
        return _blocked_apply_response(cfg, reasons=gate_reasons)

    discovery = _discover_for_reactive_apply(cfg)
    expected_digest = _inbox_proposal_digest(discovery, cfg)
    if expected_digest is None:
        return _blocked_apply_response(
            cfg,
            reasons=["no_current_preview_candidate"],
            result={"discovery": _safe_payload(discovery)},
        )
    if body.proposal_digest != expected_digest:
        return _blocked_apply_response(
            cfg,
            reasons=["proposal_digest_mismatch", "persona_digest_mismatch"],
            result={"expected_preview": _safe_payload(discovery)},
        )

    selected = getattr(discovery, "selected_candidate", None)
    inbound = getattr(selected, "inbound", None)
    if inbound is None:
        return _blocked_apply_response(cfg, reasons=["selected_inbound_missing"])

    live_result = run_reactive_live_once(inbound, config=cfg)
    result_payload = _safe_payload(live_result)
    provider_status_code = getattr(live_result.execution_result, "provider_status_code", None)
    provider_post_id = getattr(live_result.execution_result, "provider_post_id", None)
    safe_provider_post_id = redact(provider_post_id) if isinstance(provider_post_id, str) else provider_post_id
    return SocialReactiveReplyApplyResponse(
        **_persona_ref_fields(),
        status=live_result.status,
        execution_allowed=bool(live_result.execution_allowed),
        mutation_attempted=bool(live_result.mutation_attempted),
        live_apply_available=_apply_available(cfg),
        provider_status_code=provider_status_code,
        provider_post_id=safe_provider_post_id,
        audit_ids=list(getattr(live_result, "audit_ids", []) or []),
        journal_path=_display_path(getattr(live_result, "journal_path", cfg.execution_journal_path)),
        audit_path=_display_path(getattr(live_result, "audit_path", cfg.audit_log_path)),
        reasons=_dedupe(list(getattr(live_result, "reasons", []) or [])),
        warnings=[],
        result=result_payload,
    )


@router.post("/providers/x/reactive/batch/apply", response_model=SocialReactiveBatchApplyResponse)
def x_reactive_batch_apply(
    body: SocialReactiveBatchApplyRequest,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> SocialReactiveBatchApplyResponse:
    del _actor
    cfg = load_ham_x_config()
    if not body.proposal_digest:
        return _blocked_batch_apply_response(cfg, reasons=["proposal_digest_required"])
    if body.confirmation_phrase.strip() != LIVE_BATCH_CONFIRMATION_PHRASE:
        return _blocked_batch_apply_response(cfg, reasons=["confirmation_phrase_required"])

    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_social_live_token(ham_bearer)

    gate_reasons = _reactive_batch_apply_reasons(cfg)
    if gate_reasons:
        return _blocked_batch_apply_response(cfg, reasons=gate_reasons)

    preview_request = SocialPreviewRequest()
    _, dry_result, dry_reasons, dry_warnings = _reactive_batch_preview(preview_request, cfg)
    expected_digest = _batch_proposal_digest(dry_result, cfg)
    if expected_digest is None:
        return _blocked_batch_apply_response(
            cfg,
            reasons=["no_current_batch_preview_candidate", *dry_reasons],
            warnings=dry_warnings,
            result=dry_result,
        )
    if body.proposal_digest != expected_digest:
        return _blocked_batch_apply_response(
            cfg,
            reasons=["proposal_digest_mismatch", "persona_digest_mismatch"],
            warnings=dry_warnings,
            result={"expected_preview": dry_result},
        )

    candidates = [
        item.get("inbound")
        for item in list(dry_result.get("items") or [])
        if isinstance(item, dict) and item.get("status") == "dry_run" and isinstance(item.get("inbound"), dict)
    ]
    if not candidates:
        return _blocked_batch_apply_response(
            cfg,
            reasons=["no_live_batch_candidates"],
            warnings=dry_warnings,
            result=dry_result,
        )

    live_cfg = replace(cfg, goham_reactive_batch_dry_run=False)
    live_result = run_reactive_batch_once(candidates, config=live_cfg)
    result_payload = _safe_payload(live_result)
    provider_post_ids: list[str] = []
    for item in list(getattr(live_result, "items", []) or []):
        execution_result = getattr(item, "execution_result", None)
        provider_post_id = getattr(execution_result, "provider_post_id", None)
        if provider_post_id:
            safe_id = redact(provider_post_id) if isinstance(provider_post_id, str) else provider_post_id
            if isinstance(safe_id, str):
                provider_post_ids.append(safe_id)
    return SocialReactiveBatchApplyResponse(
        **_persona_ref_fields(),
        status=live_result.status,
        execution_allowed=bool(live_result.execution_allowed),
        mutation_attempted=bool(live_result.mutation_attempted),
        live_apply_available=_batch_apply_available(cfg),
        attempted_count=int(getattr(live_result, "attempted_count", 0) or 0),
        executed_count=int(getattr(live_result, "executed_count", 0) or 0),
        failed_count=int(getattr(live_result, "failed_count", 0) or 0),
        blocked_count=int(getattr(live_result, "blocked_count", 0) or 0),
        provider_post_ids=provider_post_ids,
        audit_ids=list(getattr(live_result, "audit_ids", []) or []),
        journal_path=_display_path(getattr(live_result, "journal_path", cfg.execution_journal_path)),
        audit_path=_display_path(getattr(live_result, "audit_path", cfg.audit_log_path)),
        reasons=_dedupe(list(getattr(live_result, "reasons", []) or [])),
        warnings=dry_warnings,
        result=result_payload,
    )


@router.post("/providers/x/broadcast/apply", response_model=SocialBroadcastApplyResponse)
def x_broadcast_apply(
    body: SocialBroadcastApplyRequest,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> SocialBroadcastApplyResponse:
    del _actor
    cfg = load_ham_x_config()
    if not body.proposal_digest:
        return _blocked_broadcast_apply_response(cfg, reasons=["proposal_digest_required"])
    if body.confirmation_phrase.strip() != LIVE_BROADCAST_CONFIRMATION_PHRASE:
        return _blocked_broadcast_apply_response(cfg, reasons=["confirmation_phrase_required"])

    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_social_live_token(ham_bearer)

    gate_reasons = _broadcast_apply_reasons(cfg)
    if gate_reasons:
        return _blocked_broadcast_apply_response(cfg, reasons=gate_reasons)

    preview_payload, candidate, preview_reasons = _server_broadcast_preflight(cfg)
    expected_digest = _broadcast_proposal_digest(preview_payload, cfg)
    if expected_digest is None:
        return _blocked_broadcast_apply_response(
            cfg,
            reasons=["no_current_broadcast_preview_candidate", *preview_reasons],
            result=preview_payload,
        )
    if body.proposal_digest != expected_digest:
        return _blocked_broadcast_apply_response(
            cfg,
            reasons=["proposal_digest_mismatch", "persona_digest_mismatch"],
            result={"expected_preview": preview_payload},
        )

    live_result = run_live_controller_once([candidate], config=cfg)
    result_payload = _safe_payload(live_result)
    provider_post_id = getattr(live_result, "provider_post_id", None)
    safe_provider_post_id = redact(provider_post_id) if isinstance(provider_post_id, str) else provider_post_id
    return SocialBroadcastApplyResponse(
        **_persona_ref_fields(),
        status=live_result.status,
        execution_allowed=bool(live_result.execution_allowed),
        mutation_attempted=bool(live_result.mutation_attempted),
        live_apply_available=_broadcast_apply_available(cfg),
        provider_status_code=getattr(live_result, "provider_status_code", None),
        provider_post_id=safe_provider_post_id,
        audit_ids=list(getattr(live_result, "audit_ids", []) or []),
        journal_path=_display_path(getattr(live_result, "journal_path", cfg.execution_journal_path)),
        audit_path=_display_path(getattr(live_result, "audit_path", cfg.audit_log_path)),
        reasons=_dedupe(list(getattr(live_result, "reasons", []) or [])),
        warnings=[],
        result=result_payload,
    )


__all__ = [
    "router",
    "SocialProvidersResponse",
    "XProviderStatusResponse",
    "XCapabilitiesResponse",
    "XSetupChecklistResponse",
    "XSetupSummaryResponse",
    "SocialMessagingProviderStatusResponse",
    "TelegramCapabilitiesResponse",
    "DiscordCapabilitiesResponse",
    "SocialMessagingSetupChecklistResponse",
    "SocialPersonaResponse",
    "XJournalSummaryResponse",
    "XAuditSummaryResponse",
    "SocialPreviewRequest",
    "SocialPreviewResponse",
    "SocialReactiveReplyApplyRequest",
    "SocialReactiveReplyApplyResponse",
    "SocialReactiveBatchApplyRequest",
    "SocialReactiveBatchApplyResponse",
    "SocialBroadcastApplyRequest",
    "SocialBroadcastApplyResponse",
]
