"""Bounded Telegram reactive reply run-once controller for Social TG-R4."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.social_delivery_log import MAX_LOG_SCAN_BYTES, default_delivery_log_path
from src.ham.social_telegram_reactive import (
    TELEGRAM_REACTIVE_REPLY_ACTION_TYPE,
    TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND,
    TelegramReactiveItemResult,
    preview_telegram_reactive_replies_once,
)
from src.ham.social_telegram_send import (
    TelegramSendRequest,
    TelegramSendResult,
    TelegramTransport,
    send_confirmed_telegram_message,
)

TelegramReactiveRunStatus = Literal["completed", "blocked", "sent", "failed", "duplicate"]

DEFAULT_REACTIVE_HOURLY_CAP = 2
DEFAULT_REACTIVE_DAILY_CAP = 3


class TelegramReactiveRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    readiness: str = "setup_required"
    gateway_runtime_state: str = "unknown"
    transcript_paths: list[Path] | None = None
    delivery_log_path: Path | None = None
    now: datetime | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    hourly_cap: int = Field(default=DEFAULT_REACTIVE_HOURLY_CAP, ge=0, le=24)
    daily_cap: int = Field(default=DEFAULT_REACTIVE_DAILY_CAP, ge=0, le=100)


class TelegramReactiveRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    run_kind: Literal["telegram_reactive_reply_run_once"] = "telegram_reactive_reply_run_once"
    status: TelegramReactiveRunStatus = "blocked"
    dry_run: bool = True
    execution_allowed: bool = False
    mutation_attempted: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    inbound_count: int = 0
    processed_count: int = 0
    reply_candidate_count: int = 0
    selected_inbound_id: str | None = None
    selected_classification: str | None = None
    selected_author_ref: str = ""
    selected_chat_ref: str = ""
    selected_session_ref: str = ""
    proposal_digest: str | None = None
    reply_candidate_text: str = ""
    provider_message_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, object] = Field(default_factory=dict)


def run_telegram_reactive_once(
    config: TelegramReactiveRunConfig | None = None,
    *,
    transport: TelegramTransport | None = None,
) -> TelegramReactiveRunResult:
    cfg = config or TelegramReactiveRunConfig()
    preview = preview_telegram_reactive_replies_once(transcript_paths=cfg.transcript_paths, max_reply_candidates=1)
    selected = _first_safe_candidate(preview.items)
    base = {
        "dry_run": cfg.dry_run,
        "persona_id": preview.persona_id,
        "persona_version": preview.persona_version,
        "persona_digest": preview.persona_digest,
        "inbound_count": preview.inbound_count,
        "processed_count": preview.processed_count,
        "reply_candidate_count": preview.reply_candidate_count,
        "selected_inbound_id": selected.inbound_id if selected else None,
        "selected_classification": selected.classification if selected else None,
        "selected_author_ref": selected.author_ref if selected else "",
        "selected_chat_ref": selected.chat_ref if selected else "",
        "selected_session_ref": selected.session_ref if selected else "",
        "proposal_digest": selected.proposal_digest if selected else None,
        "reply_candidate_text": selected.reply_candidate_text if selected else "",
        "warnings": list(preview.warnings),
    }

    if cfg.dry_run:
        reasons = list(preview.reasons)
        if preview.status != "completed":
            reasons = ["telegram_reactive_preview_not_available", *reasons]
        if selected is None:
            reasons = [*reasons, "telegram_reactive_no_safe_candidate"]
        return TelegramReactiveRunResult(
            status="completed" if preview.status == "completed" else "blocked",
            execution_allowed=False,
            mutation_attempted=False,
            reasons=_dedupe(reasons),
            result={"mode": "dry_run"},
            **base,
        )

    reasons = _live_gate_reasons()
    if cfg.readiness != "ready":
        reasons.append("telegram_readiness_not_ready")
    if cfg.gateway_runtime_state != "connected":
        reasons.append("telegram_gateway_not_connected")
    if preview.status != "completed":
        reasons.extend(["telegram_reactive_preview_not_available", *preview.reasons])
    if selected is None:
        reasons.append("telegram_reactive_no_safe_candidate")
    elif not selected.repliable:
        reasons.append("telegram_reactive_candidate_not_repliable")
    elif selected.already_answered:
        reasons.append("telegram_inbound_already_answered")
    elif not selected.policy.allowed:
        reasons.extend(["telegram_reactive_policy_blocked", *selected.policy.reasons])
    elif not selected.governor.allowed:
        reasons.extend(["telegram_reactive_governor_blocked", *selected.governor.reasons])

    if selected is not None and selected.proposal_digest:
        reasons.extend(
            _delivery_guard_reasons(
                inbound_id=selected.inbound_id,
                proposal_digest=selected.proposal_digest,
                now=cfg.now,
                delivery_log_path=cfg.delivery_log_path,
                hourly_cap=cfg.hourly_cap,
                daily_cap=cfg.daily_cap,
            )
        )

    reasons = _dedupe(reasons)
    if reasons:
        return TelegramReactiveRunResult(
            status="blocked",
            execution_allowed=False,
            mutation_attempted=False,
            reasons=reasons,
            result={"mode": "live_blocked"},
            **base,
        )

    assert selected is not None
    assert selected.proposal_digest is not None
    request = TelegramSendRequest(
        target_kind="test_group",
        text=selected.reply_candidate_text,
        proposal_digest=selected.proposal_digest,
        persona_digest=preview.persona_digest,
        idempotency_key=_idempotency_key(selected.inbound_id),
        telegram_connected=True,
    )
    send_result = send_confirmed_telegram_message(
        request,
        transport=transport,
        delivery_log_path=cfg.delivery_log_path,
        timeout_seconds=cfg.timeout_seconds,
        execution_kind=TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND,
        action_type=TELEGRAM_REACTIVE_REPLY_ACTION_TYPE,
    )
    return TelegramReactiveRunResult(
        status=send_result.status,
        execution_allowed=bool(send_result.execution_allowed),
        mutation_attempted=bool(send_result.mutation_attempted),
        provider_message_id=send_result.provider_message_id,
        reasons=list(send_result.reasons),
        result={
            "execution_kind": TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND,
            "target_ref": send_result.target_ref,
            "inbound_id": selected.inbound_id,
            **send_result.result,
        },
        **base,
    )


def _first_safe_candidate(items: list[TelegramReactiveItemResult]) -> TelegramReactiveItemResult | None:
    for item in items:
        if item.proposal_digest and item.repliable and not item.already_answered and item.policy.allowed and item.governor.allowed:
            return item
    return None


def _live_gate_reasons() -> list[str]:
    reasons: list[str] = []
    if (os.environ.get("HAM_SOCIAL_TELEGRAM_REACTIVE_AUTONOMY_ENABLED") or "").strip().lower() != "true":
        reasons.append("telegram_reactive_autonomy_disabled")
    if (os.environ.get("HAM_SOCIAL_TELEGRAM_REACTIVE_DRY_RUN") or "true").strip().lower() != "false":
        reasons.append("telegram_reactive_dry_run_enabled")
    return reasons


def _delivery_guard_reasons(
    *,
    inbound_id: str,
    proposal_digest: str,
    now: datetime | None,
    delivery_log_path: Path | None,
    hourly_cap: int,
    daily_cap: int,
) -> list[str]:
    point = now if isinstance(now, datetime) else datetime.now(UTC)
    if point.tzinfo is None:
        point = point.replace(tzinfo=UTC)
    rows = _load_delivery_rows(delivery_log_path)
    reasons: list[str] = []
    idempotency = _idempotency_key(inbound_id)
    hourly_used = 0
    daily_used = 0
    for row in rows:
        if row.get("provider_id") != "telegram":
            continue
        if row.get("execution_kind") != TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND:
            continue
        if row.get("status") != "sent":
            continue
        if row.get("idempotency_key") == idempotency:
            reasons.append("telegram_reactive_inbound_already_handled")
        if row.get("proposal_digest") == proposal_digest:
            reasons.append("telegram_reactive_response_fingerprint_duplicate")
        ts = _parse_iso(str(row.get("executed_at") or ""))
        if ts is None:
            continue
        if ts >= point - timedelta(hours=1):
            hourly_used += 1
        if ts >= point - timedelta(days=1):
            daily_used += 1
    if hourly_used >= hourly_cap:
        reasons.append("telegram_reactive_hourly_cap_reached")
    if daily_used >= daily_cap:
        reasons.append("telegram_reactive_daily_cap_reached")
    return _dedupe(reasons)


def _load_delivery_rows(path: Path | None) -> list[dict[str, object]]:
    target = path or default_delivery_log_path()
    if not target.is_file():
        return []
    try:
        if target.stat().st_size > MAX_LOG_SCAN_BYTES:
            return []
    except OSError:
        return []
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _idempotency_key(inbound_id: str) -> str:
    digest = hashlib.sha256(f"telegram-reactive-reply:{inbound_id}".encode("utf-8")).hexdigest()
    return f"telegram-reactive-reply-{digest[:32]}"


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
