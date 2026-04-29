"""Gate policy for HAM-on-X manual canary execution."""
from __future__ import annotations

from typing import Any

from src.ham.ham_x.config import HamXConfig
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.safety_policy import check_social_action

MAX_CANARY_TEXT_CHARS = 280


def allowed_canary_actions(config: HamXConfig) -> set[str]:
    return {
        item.strip()
        for item in (config.canary_allowed_actions or "").split(",")
        if item.strip()
    }


def payload_contains_secret(payload: dict[str, Any]) -> bool:
    return redact(payload) != payload


def evaluate_canary_request(
    request: Any,
    *,
    config: HamXConfig,
    journal: ExecutionJournal,
    per_run_count: int = 0,
) -> list[str]:
    reasons: list[str] = []
    if not config.enable_live_execution:
        reasons.append("live_execution_disabled")
    if config.dry_run:
        reasons.append("dry_run_enabled")
    if config.autonomy_enabled:
        reasons.append("autonomy_enabled")
    if config.emergency_stop:
        reasons.append("emergency_stop")
    if not bool(getattr(request, "manual_confirm", False)):
        reasons.append("manual_confirm_required")
    if per_run_count >= config.execution_per_run_cap:
        reasons.append("per_run_cap_exceeded")
    if journal.daily_executed_count() >= config.execution_daily_cap:
        reasons.append("daily_cap_exceeded")

    action_type = str(getattr(request, "action_type", ""))
    if action_type not in allowed_canary_actions(config):
        reasons.append("unsupported_action_type")

    text = str(getattr(request, "text", "") or "")
    if not text.strip():
        reasons.append("empty_text")
    if len(text) > MAX_CANARY_TEXT_CHARS:
        reasons.append("text_too_long")
    policy = check_social_action(text, action_type=action_type)
    if not policy.allowed:
        reasons.extend([f"safety_policy:{reason}" for reason in policy.reasons])

    if action_type == "quote" and not str(getattr(request, "quote_target_id", "") or "").strip():
        reasons.append("quote_target_id_required")

    payload = {
        "text": text,
        "reason": getattr(request, "reason", ""),
        "operator_label": getattr(request, "operator_label", ""),
        "quote_target_id": getattr(request, "quote_target_id", ""),
    }
    if payload_contains_secret(payload):
        reasons.append("payload_contains_secret")

    if journal.has_executed(
        action_id=str(getattr(request, "action_id", "")),
        idempotency_key=str(getattr(request, "idempotency_key", "")),
    ):
        reasons.append("duplicate_execution")
    return _dedupe(reasons)


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out
