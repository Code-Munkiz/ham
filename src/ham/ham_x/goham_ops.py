"""Read-only GoHAM v0 operator status helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_policy import (
    GOHAM_EXECUTION_KIND,
    GoHamEligibilityResult,
    evaluate_goham_eligibility,
)
from src.ham.ham_x.redaction import redact

MAX_SUMMARY_RECORDS = 10
MAX_TEXT_CHARS = 1000


class GohamJournalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journal_path: str
    total_autonomous_count: int = 0
    today_autonomous_count: int = 0
    last_autonomous_post: dict[str, Any] | None = None
    provider_post_id: str | None = None
    latest_executed_at: str | None = None
    recent_autonomous_posts: list[dict[str, Any]] = Field(default_factory=list)
    execution_kind: str = GOHAM_EXECUTION_KIND
    read_only: bool = True
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


class GohamCapStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_cap: int
    daily_cap_used: int
    daily_cap_remaining: int
    cap_available: bool
    journal_path: str
    execution_kind: str = GOHAM_EXECUTION_KIND
    read_only: bool = True
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


class GohamStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_autonomous_post: dict[str, Any] | None = None
    provider_post_id: str | None = None
    daily_cap_used: int
    daily_cap_remaining: int
    daily_cap: int
    journal_path: str
    audit_path: str
    emergency_stop: bool
    gate_state: dict[str, Any]
    execution_allowed_now: bool
    mutation_attempted: bool = False
    read_only: bool = True
    diagnostic: str = "GoHAM ops/status is read-only and does not execute provider actions."

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


def summarize_goham_journal(config: HamXConfig | None = None) -> GohamJournalSummary:
    """Return bounded read-only summary of autonomous GoHAM execution rows."""
    cfg = config or load_ham_x_config()
    journal = ExecutionJournal(config=cfg)
    records = [_bounded_record(row) for row in journal.records() if row.get("execution_kind") == GOHAM_EXECUTION_KIND]
    records.sort(key=lambda row: str(row.get("executed_at", "")))
    today = _today()
    today_count = sum(1 for row in records if str(row.get("executed_at", "")).startswith(today))
    last = records[-1] if records else None
    return GohamJournalSummary(
        journal_path=str(journal.path),
        total_autonomous_count=len(records),
        today_autonomous_count=today_count,
        last_autonomous_post=last,
        provider_post_id=str(last.get("provider_post_id")) if last and last.get("provider_post_id") else None,
        latest_executed_at=str(last.get("executed_at")) if last and last.get("executed_at") else None,
        recent_autonomous_posts=records[-MAX_SUMMARY_RECORDS:],
    )


def check_goham_cap(
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
) -> GohamCapStatus:
    """Return today's GoHAM autonomous cap usage without attempting execution."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    cap = int(cfg.goham_autonomous_daily_cap)
    used = jrnl.daily_executed_count(execution_kind=GOHAM_EXECUTION_KIND)
    remaining = max(0, cap - used)
    return GohamCapStatus(
        daily_cap=cap,
        daily_cap_used=used,
        daily_cap_remaining=remaining,
        cap_available=remaining > 0,
        journal_path=str(jrnl.path),
    )


def show_goham_status(
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
) -> GohamStatus:
    """Return GoHAM v0 daily operating status; this is strictly read-only."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    summary = summarize_goham_journal(cfg)
    cap = check_goham_cap(cfg, jrnl)
    gate_state = {
        "enable_goham_execution": cfg.enable_goham_execution,
        "autonomy_enabled": cfg.autonomy_enabled,
        "dry_run": cfg.dry_run,
        "enable_live_execution": cfg.enable_live_execution,
        "goham_allowed_actions": cfg.goham_allowed_actions,
        "goham_block_links": cfg.goham_block_links,
    }
    execution_allowed_now = (
        cfg.enable_goham_execution
        and cfg.autonomy_enabled
        and not cfg.dry_run
        and not cfg.emergency_stop
        and cfg.enable_live_execution
        and cap.cap_available
    )
    return GohamStatus(
        last_autonomous_post=summary.last_autonomous_post,
        provider_post_id=summary.provider_post_id,
        daily_cap_used=cap.daily_cap_used,
        daily_cap_remaining=cap.daily_cap_remaining,
        daily_cap=cap.daily_cap,
        journal_path=str(jrnl.path),
        audit_path=str(cfg.audit_log_path),
        emergency_stop=cfg.emergency_stop,
        gate_state=redact(gate_state),
        execution_allowed_now=execution_allowed_now,
    )


def dry_preflight_goham_candidate(
    request: Any,
    decision: Any,
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    per_run_count: int = 0,
) -> GoHamEligibilityResult:
    """Run GoHAM eligibility only; never attempts provider execution."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    return evaluate_goham_eligibility(
        request,
        decision=decision,
        config=cfg,
        journal=jrnl,
        per_run_count=per_run_count,
    )


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _bounded_record(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in list(row.items())[:50]:
        out[str(key)[:128]] = _bound_value(value)
    return redact(out)


def _bound_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[: MAX_TEXT_CHARS - 3] + "..." if len(value) > MAX_TEXT_CHARS else value
    if isinstance(value, list):
        return [_bound_value(item) for item in value[:25]]
    if isinstance(value, dict):
        return {str(k)[:128]: _bound_value(v) for k, v in list(value.items())[:50]}
    return value
