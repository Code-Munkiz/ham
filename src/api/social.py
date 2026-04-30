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
from src.ham.ham_x.goham_ops import dry_preflight_goham_candidate, show_goham_status
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
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
SocialApplyStatus = Literal["blocked", "executed", "failed"]
SocialApplyKind = Literal["reactive_reply"]
LIVE_REPLY_CONFIRMATION_PHRASE = "SEND ONE LIVE REPLY"


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
    reactive_inbox_discovery_available: bool
    reactive_dry_run_available: bool
    reactive_reply_canary_available: bool
    reactive_batch_available: bool
    reactive_reply_apply_available: bool = False
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


class SocialReactiveReplyApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_digest: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=128)


class SocialReactiveReplyApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x"] = "x"
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


def _apply_available(config: HamXConfig) -> bool:
    return bool(_social_live_token_enabled() and _reactive_reply_canary_available(config))


def _blocked_apply_response(
    config: HamXConfig,
    *,
    reasons: list[str],
    warnings: list[str] | None = None,
    result: dict[str, Any] | None = None,
) -> SocialReactiveReplyApplyResponse:
    return SocialReactiveReplyApplyResponse(
        status="blocked",
        live_apply_available=_apply_available(config),
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
    return _proposal_digest("reactive_inbox", payload) if payload else None


def _discover_for_reactive_apply(config: HamXConfig) -> Any:
    return discover_reactive_inbox_once(config=_preview_config(config))


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
    candidates = body.candidates[: body.max_candidates or len(body.candidates) or 25]
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
    ("telegram", "Telegram"),
    ("discord", "Discord"),
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
    providers: list[SocialProviderDto] = [_x_provider_dto(cfg)]
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
        reactive_inbox_discovery_available=_reactive_inbox_discovery_available(cfg),
        reactive_dry_run_available=cfg.enable_goham_reactive and cfg.goham_reactive_dry_run,
        reactive_reply_canary_available=_reactive_reply_canary_available(cfg),
        reactive_batch_available=cfg.enable_goham_reactive and cfg.enable_goham_reactive_batch,
        reactive_reply_apply_available=_apply_available(cfg),
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
    status, result, reasons, warnings = _reactive_batch_preview(request, load_ham_x_config())
    payload = _force_preview_flags(result)
    return SocialPreviewResponse(
        preview_kind="reactive_batch_dry_run",
        status=status,
        reasons=reasons,
        warnings=warnings,
        result=payload,
        proposal_digest=_proposal_digest(
            "reactive_batch_dry_run",
            {"client_request_id": request.client_request_id, "result": payload},
        ),
    )


@router.post("/providers/x/broadcast/preflight", response_model=SocialPreviewResponse)
def x_broadcast_preflight(
    body: SocialPreviewRequest | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> SocialPreviewResponse:
    del _actor
    request = body or SocialPreviewRequest()
    cfg = _preview_config(load_ham_x_config())
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
    return SocialPreviewResponse(
        preview_kind="broadcast_preflight",
        status="completed" if result.allowed else "blocked",
        reasons=list(result.reasons),
        warnings=[],
        result=payload,
        proposal_digest=_proposal_digest(
            "broadcast_preflight",
            {"client_request_id": request.client_request_id, "result": payload},
        ),
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
            reasons=["proposal_digest_mismatch"],
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


__all__ = [
    "router",
    "SocialProvidersResponse",
    "XProviderStatusResponse",
    "XCapabilitiesResponse",
    "XSetupChecklistResponse",
    "XJournalSummaryResponse",
    "XAuditSummaryResponse",
    "SocialPreviewRequest",
    "SocialPreviewResponse",
    "SocialReactiveReplyApplyRequest",
    "SocialReactiveReplyApplyResponse",
]
