"""Dry-run Telegram regular activity planner for Social TG-A1."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.redaction import redact
from src.ham.social_delivery_log import MAX_LOG_SCAN_BYTES, default_delivery_log_path
from src.ham.social_persona import load_social_persona, persona_digest
from src.ham.social_telegram_send import mask_target_ref

TelegramActivityKind = Literal["status_update", "test_activity"]
TelegramActivityStatus = Literal["completed", "blocked", "failed"]

TELEGRAM_ACTIVITY_EXECUTION_KIND = "social_telegram_activity"
DEFAULT_ACTIVITY_DAILY_CAP = 1
DEFAULT_ACTIVITY_MIN_SPACING_MINUTES = 720
MAX_ACTIVITY_TEXT_CHARS = 700


class TelegramActivityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_kind: TelegramActivityKind = "test_activity"
    target_kind: Literal["test_group"] = "test_group"
    target_ref: str = ""
    text: str = ""
    char_count: int = 0


class TelegramActivityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool = True
    reasons: list[str] = Field(default_factory=list)
    next_allowed_send_time: str | None = None
    daily_cap: int = DEFAULT_ACTIVITY_DAILY_CAP
    daily_used: int = 0
    min_spacing_minutes: int = DEFAULT_ACTIVITY_MIN_SPACING_MINUTES


class TelegramActivityPreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    preview_kind: Literal["telegram_activity"] = "telegram_activity"
    status: TelegramActivityStatus = "blocked"
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    proposal_digest: str | None = None
    target: dict[str, object]
    activity_preview: dict[str, object]
    governor: dict[str, object]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    read_only: bool = True


def plan_telegram_activity_once(
    *,
    activity_kind: TelegramActivityKind = "test_activity",
    readiness: str = "setup_required",
    gateway_runtime_state: str = "unknown",
    emergency_stop: bool = False,
    now: datetime | None = None,
    delivery_log_path: Path | None = None,
) -> TelegramActivityPreviewResult:
    persona = load_social_persona("ham-canonical", 1)
    persona_ref = {
        "persona_id": persona.persona_id,
        "persona_version": persona.version,
        "persona_digest": persona_digest(persona),
    }
    target_raw = _telegram_test_group()
    target = {
        "kind": "test_group",
        "configured": bool(target_raw),
        "masked_id": mask_target_ref(target_raw),
    }
    text = _activity_text(activity_kind=activity_kind, display_name=persona.display_name)
    candidate = TelegramActivityCandidate(
        activity_kind=activity_kind,
        target_ref=str(target["masked_id"]),
        text=text,
        char_count=len(text),
    )
    decision = _evaluate_activity_governor(
        emergency_stop=emergency_stop,
        now=now,
        delivery_log_path=delivery_log_path,
    )

    reasons: list[str] = []
    warnings: list[str] = []
    if readiness != "ready":
        reasons.append("telegram_readiness_not_ready")
    if gateway_runtime_state != "connected":
        reasons.append("telegram_gateway_not_connected")
    if not bool(target["configured"]):
        reasons.append("telegram_target_not_configured")
    if not decision.allowed:
        reasons.extend(decision.reasons)

    proposal_digest: str | None = None
    status: TelegramActivityStatus = "completed"
    preview_text = candidate.text
    preview_char_count = candidate.char_count
    if reasons:
        status = "blocked"
        preview_text = ""
        preview_char_count = 0
    else:
        proposal_digest = _activity_proposal_digest(
            persona_ref=persona_ref,
            target=target,
            candidate=candidate,
            governor=decision,
        )

    if decision.next_allowed_send_time and "telegram_activity_min_spacing_active" in decision.reasons:
        warnings.append("telegram_activity_next_window_scheduled")

    return TelegramActivityPreviewResult(
        status=status,
        proposal_digest=proposal_digest,
        target=target,
        activity_preview={
            "text": preview_text,
            "char_count": preview_char_count,
            "activity_kind": activity_kind,
        },
        governor={
            "allowed": decision.allowed,
            "reasons": list(decision.reasons),
            "next_allowed_send_time": decision.next_allowed_send_time,
            "daily_cap": decision.daily_cap,
            "daily_used": decision.daily_used,
            "min_spacing_minutes": decision.min_spacing_minutes,
        },
        reasons=_dedupe(reasons),
        warnings=_dedupe(warnings),
        recommended_next_steps=_recommended_steps(
            reasons=_dedupe(reasons),
            next_allowed_send_time=decision.next_allowed_send_time,
        ),
        **persona_ref,
    )


def _activity_text(*, activity_kind: TelegramActivityKind, display_name: str) -> str:
    if activity_kind == "status_update":
        text = (
            f"{display_name} activity update: Telegram is connected, persona protections are active, "
            "and Social live sends remain confirmation-gated."
        )
    else:
        text = (
            f"{display_name} activity check: Telegram is connected, persona is protected, "
            "and Social will only send live messages through confirmed controls."
        )
    return str(redact(text)).strip()[:MAX_ACTIVITY_TEXT_CHARS]


def _telegram_test_group() -> str:
    return (
        os.environ.get("TELEGRAM_TEST_GROUP")
        or os.environ.get("TELEGRAM_TEST_GROUP_ID")
        or os.environ.get("TELEGRAM_TEST_CHAT_ID")
        or ""
    ).strip()


def _evaluate_activity_governor(
    *,
    emergency_stop: bool,
    now: datetime | None,
    delivery_log_path: Path | None,
) -> TelegramActivityDecision:
    point_in_time = now if isinstance(now, datetime) else datetime.now(UTC)
    if point_in_time.tzinfo is None:
        point_in_time = point_in_time.replace(tzinfo=UTC)
    day_ago = point_in_time - timedelta(days=1)
    spacing_delta = timedelta(minutes=DEFAULT_ACTIVITY_MIN_SPACING_MINUTES)

    recent_sends = _load_recent_activity_sends(path=delivery_log_path, since=day_ago)
    daily_used = len(recent_sends)
    latest = max(recent_sends) if recent_sends else None

    reasons: list[str] = []
    next_allowed_send_time: str | None = None
    if emergency_stop:
        reasons.append("telegram_activity_emergency_stop_enabled")
    if daily_used >= DEFAULT_ACTIVITY_DAILY_CAP:
        reasons.append("telegram_activity_daily_cap_reached")
    if latest is not None:
        next_allowed = latest + spacing_delta
        if point_in_time < next_allowed:
            reasons.append("telegram_activity_min_spacing_active")
            next_allowed_send_time = _iso_utc(next_allowed)

    return TelegramActivityDecision(
        allowed=not reasons,
        reasons=_dedupe(reasons),
        next_allowed_send_time=next_allowed_send_time,
        daily_cap=DEFAULT_ACTIVITY_DAILY_CAP,
        daily_used=daily_used,
        min_spacing_minutes=DEFAULT_ACTIVITY_MIN_SPACING_MINUTES,
    )


def _load_recent_activity_sends(*, path: Path | None, since: datetime) -> list[datetime]:
    target = path or default_delivery_log_path()
    if not target.is_file():
        return []
    try:
        if target.stat().st_size > MAX_LOG_SCAN_BYTES:
            return []
    except OSError:
        return []
    try:
        rows = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    points: list[datetime] = []
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("provider_id") != "telegram":
            continue
        if row.get("execution_kind") != TELEGRAM_ACTIVITY_EXECUTION_KIND:
            continue
        if row.get("status") != "sent":
            continue
        ts = _parse_iso_utc(str(row.get("executed_at") or ""))
        if ts is None:
            continue
        if ts >= since:
            points.append(ts)
    return points


def _activity_proposal_digest(
    *,
    persona_ref: dict[str, object],
    target: dict[str, object],
    candidate: TelegramActivityCandidate,
    governor: TelegramActivityDecision,
) -> str:
    payload = {
        "provider_id": "telegram",
        "preview_kind": "telegram_activity",
        "persona": persona_ref,
        "target": target,
        "activity_preview": {
            "text": candidate.text,
            "char_count": candidate.char_count,
            "activity_kind": candidate.activity_kind,
        },
        "governor": {
            "allowed": governor.allowed,
            "reasons": governor.reasons,
            "next_allowed_send_time": governor.next_allowed_send_time,
        },
        "safety_gates": {
            "execution_allowed": False,
            "mutation_attempted": False,
            "live_apply_available": False,
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _recommended_steps(*, reasons: list[str], next_allowed_send_time: str | None) -> list[str]:
    if not reasons:
        return ["Dry-run activity proposal generated. Live activity apply is not available in TG-A1."]
    steps: list[str] = []
    if "telegram_target_not_configured" in reasons:
        steps.append("Configure TELEGRAM_TEST_GROUP_ID on the runtime host for TG-A1 activity previews.")
    if "telegram_gateway_not_connected" in reasons or "telegram_readiness_not_ready" in reasons:
        steps.append("Restore Telegram readiness to ready/connected before generating activity previews.")
    if "telegram_activity_daily_cap_reached" in reasons:
        steps.append("Daily activity cap reached for TG-A1 dry-run governor.")
    if next_allowed_send_time:
        steps.append(f"Next allowed activity window: {next_allowed_send_time}")
    if not steps:
        steps.append("Resolve readiness and governor blockers, then rerun activity preview.")
    return steps[:5]


def _parse_iso_utc(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    out = value.astimezone(UTC).replace(microsecond=0).isoformat()
    return out.replace("+00:00", "Z")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out

