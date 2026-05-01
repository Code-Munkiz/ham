"""Service-safe Telegram activity run-once controller for TG-A3."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.social_telegram_activity import (
    TELEGRAM_ACTIVITY_EXECUTION_KIND,
    TelegramActivityKind,
    plan_telegram_activity_once,
)
from src.ham.social_telegram_send import (
    TelegramSendRequest,
    TelegramSendResult,
    TelegramTransport,
    send_confirmed_telegram_message,
)

TelegramActivityRunStatus = Literal["completed", "blocked", "sent", "failed", "duplicate"]


class TelegramActivityRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_kind: TelegramActivityKind = "test_activity"
    dry_run: bool = True
    readiness: str = "setup_required"
    gateway_runtime_state: str = "unknown"
    emergency_stop: bool = False
    now: datetime | None = None
    delivery_log_path: Path | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)


class TelegramActivityRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    run_kind: Literal["telegram_activity_run_once"] = "telegram_activity_run_once"
    status: TelegramActivityRunStatus = "blocked"
    dry_run: bool = True
    execution_allowed: bool = False
    mutation_attempted: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    proposal_digest: str | None = None
    target: dict[str, object]
    activity_preview: dict[str, object]
    governor: dict[str, object]
    provider_message_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, object] = Field(default_factory=dict)


def run_telegram_activity_once(
    config: TelegramActivityRunConfig | None = None,
    *,
    transport: TelegramTransport | None = None,
) -> TelegramActivityRunResult:
    cfg = config or TelegramActivityRunConfig()
    preview = plan_telegram_activity_once(
        activity_kind=cfg.activity_kind,
        readiness=cfg.readiness,
        gateway_runtime_state=cfg.gateway_runtime_state,
        emergency_stop=cfg.emergency_stop,
        now=cfg.now,
        delivery_log_path=cfg.delivery_log_path,
    )

    base = {
        "dry_run": cfg.dry_run,
        "persona_id": preview.persona_id,
        "persona_version": preview.persona_version,
        "persona_digest": preview.persona_digest,
        "proposal_digest": preview.proposal_digest,
        "target": preview.target,
        "activity_preview": preview.activity_preview,
        "governor": preview.governor,
        "warnings": list(preview.warnings),
    }

    if cfg.dry_run:
        return TelegramActivityRunResult(
            status=preview.status,
            execution_allowed=False,
            mutation_attempted=False,
            reasons=list(preview.reasons),
            result={"mode": "dry_run"},
            **base,
        )

    blocked_reasons = _live_gate_reasons()
    if preview.status != "completed" or not preview.proposal_digest:
        blocked_reasons.extend(["telegram_activity_preview_not_available", *preview.reasons])
    if not bool(preview.governor.get("allowed")):
        blocked_reasons.extend(["telegram_activity_governor_blocked", *_as_strings(preview.governor.get("reasons"))])

    reasons = _dedupe(blocked_reasons)
    if reasons:
        return TelegramActivityRunResult(
            status="blocked",
            execution_allowed=False,
            mutation_attempted=False,
            reasons=reasons,
            result={"mode": "live_blocked"},
            **base,
        )

    request = TelegramSendRequest(
        target_kind="test_group",
        text=str(preview.activity_preview.get("text") or ""),
        proposal_digest=preview.proposal_digest,
        persona_digest=preview.persona_digest,
        idempotency_key=_run_once_idempotency_key(preview.proposal_digest),
        telegram_connected=True,
    )
    send_result = send_confirmed_telegram_message(
        request,
        transport=transport,
        delivery_log_path=cfg.delivery_log_path,
        timeout_seconds=cfg.timeout_seconds,
        execution_kind=TELEGRAM_ACTIVITY_EXECUTION_KIND,
        action_type="activity",
    )

    return TelegramActivityRunResult(
        status=send_result.status,
        execution_allowed=bool(send_result.execution_allowed),
        mutation_attempted=bool(send_result.mutation_attempted),
        provider_message_id=send_result.provider_message_id,
        reasons=list(send_result.reasons),
        result=_send_result_payload(send_result),
        **base,
    )


def _live_gate_reasons() -> list[str]:
    reasons: list[str] = []
    if (os.environ.get("HAM_SOCIAL_TELEGRAM_ACTIVITY_AUTONOMY_ENABLED") or "").strip().lower() != "true":
        reasons.append("telegram_activity_autonomy_disabled")
    if (os.environ.get("HAM_SOCIAL_TELEGRAM_ACTIVITY_DRY_RUN") or "true").strip().lower() != "false":
        reasons.append("telegram_activity_dry_run_enabled")
    return reasons


def _run_once_idempotency_key(proposal_digest: str) -> str:
    digest = hashlib.sha256(f"telegram-activity-run-once:{proposal_digest}".encode("utf-8")).hexdigest()
    return f"telegram-activity-run-once-{digest[:32]}"


def _send_result_payload(send_result: TelegramSendResult) -> dict[str, object]:
    return {
        "execution_kind": TELEGRAM_ACTIVITY_EXECUTION_KIND,
        "target_ref": send_result.target_ref,
        **send_result.result,
    }


def _as_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
