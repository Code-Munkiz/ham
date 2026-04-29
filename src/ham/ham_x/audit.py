"""Append-only HAM-on-X audit log.

Phase 1A mirrors HAM's existing operator audit shape while keeping a
social-agent-specific event stream. Future consolidation can share append and
redaction primitives once the record semantics are stable.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from src.ham.ham_x.action_envelope import apply_platform_context, utc_now_iso
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

AuditEventType = Literal[
    "search_attempt",
    "search_plan_created",
    "score_attempt",
    "candidate_scored",
    "candidate_ignored",
    "draft_attempt",
    "draft_created",
    "safety_reject",
    "policy_allowed",
    "policy_rejected",
    "queued_for_review",
    "blocked_mutating_action",
    "dry_run_action",
    "autonomy_decision_created",
    "action_auto_rejected",
    "action_ignored",
    "action_monitored",
    "action_draft_only",
    "action_queued_review",
    "action_queued_exception",
    "action_auto_approved_candidate",
    "emergency_stop_blocked",
    "execution_blocked_phase1c",
    "x_readonly_smoke_planned",
    "x_readonly_smoke_blocked",
    "x_readonly_smoke_executed",
    "x_readonly_smoke_failed",
    "x_mutation_blocked",
    "xai_smoke_blocked",
    "xai_smoke_planned",
    "xai_smoke_executed",
    "xai_smoke_failed",
    "execution_canary_requested",
    "execution_canary_blocked",
    "execution_canary_dry_run",
    "execution_canary_executed",
    "execution_canary_failed",
    "execution_cap_blocked",
    "execution_duplicate_blocked",
    "execution_emergency_stop_blocked",
    "live_dry_run_blocked",
    "live_dry_run_planned",
    "live_dry_run_search_completed",
    "live_dry_run_candidate_scored",
    "live_dry_run_draft_created",
    "live_dry_run_policy_reviewed",
    "live_dry_run_autonomy_decision",
    "live_dry_run_routed",
    "live_dry_run_completed",
    "goham_execution_requested",
    "goham_execution_blocked",
    "goham_execution_allowed",
    "goham_execution_executed",
    "goham_execution_failed",
    "goham_execution_cap_blocked",
    "goham_execution_duplicate_blocked",
    "goham_execution_policy_blocked",
    "goham_controller_started",
    "goham_controller_candidate_decision",
    "goham_controller_completed",
    "goham_live_controller_started",
    "goham_live_controller_candidate_decision",
    "goham_live_controller_completed",
    "goham_reactive_started",
    "goham_reactive_inbound_seen",
    "goham_reactive_classified",
    "goham_reactive_governor_decision",
    "goham_reactive_reply_candidate_created",
    "goham_reactive_completed",
    "goham_reactive_reply_requested",
    "goham_reactive_reply_executed",
    "goham_reactive_reply_failed",
    "goham_reactive_reply_blocked",
]


def _path(config: HamXConfig | None) -> Path:
    cfg = config or load_ham_x_config()
    return cfg.audit_log_path


def append_audit_event(
    event_type: AuditEventType,
    payload: dict[str, Any] | None = None,
    *,
    config: HamXConfig | None = None,
) -> str:
    """Append one redacted JSONL audit event and return its audit id."""
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    audit_id = str(uuid.uuid4())
    row = apply_platform_context(
        {
            "audit_id": audit_id,
            "event_type": event_type,
            "ts": utc_now_iso(),
            "payload": _cap(redact(payload or {})),
        },
        config,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=True, default=str) + "\n")
    return audit_id
