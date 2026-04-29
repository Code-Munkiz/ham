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
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.goham_ops import show_goham_status
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND
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
        live_apply_available=False,
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


__all__ = [
    "router",
    "SocialProvidersResponse",
    "XProviderStatusResponse",
    "XCapabilitiesResponse",
    "XSetupChecklistResponse",
    "XJournalSummaryResponse",
    "XAuditSummaryResponse",
]
