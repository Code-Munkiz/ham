"""One-shot GoHAM v0 daily runner."""
from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_bridge import (
    GohamExecutionRequest,
    GohamExecutionResult,
    run_goham_guarded_post,
)
from src.ham.ham_x.goham_ops import (
    GohamStatus,
    dry_preflight_goham_candidate,
    show_goham_status,
)
from src.ham.ham_x.goham_policy import GoHamEligibilityResult
from src.ham.ham_x.redaction import redact

GohamDailyStatus = Literal["blocked", "executed", "failed"]
RunPost = Callable[..., GohamExecutionResult]
MAX_SUMMARY_CHARS = 1000


class GohamDailyRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_before: GohamStatus
    preflight: GoHamEligibilityResult
    execution_result: GohamExecutionResult | None = None
    status_after: GohamStatus
    status: GohamDailyStatus
    action_id: str
    source_action_id: str
    provider_post_id: str | None = None
    execution_allowed: bool = False
    mutation_attempted: bool = False
    reasons: list[str] = Field(default_factory=list)
    diagnostic: str = ""
    journal_path: str
    audit_path: str

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_bound_value(self.model_dump(mode="json")))


def run_goham_daily_once(
    request: GohamExecutionRequest,
    decision: AutonomyDecisionResult,
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    run_post: RunPost | None = None,
) -> GohamDailyRunResult:
    """Run exactly one guarded GoHAM candidate and stop."""
    if isinstance(request, (list, tuple)):
        raise TypeError("run_goham_daily_once accepts exactly one GohamExecutionRequest")

    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    status_before = show_goham_status(config=cfg, journal=jrnl)
    preflight = dry_preflight_goham_candidate(
        request,
        decision,
        config=cfg,
        journal=jrnl,
        per_run_count=0,
    )
    if not preflight.allowed:
        status_after = show_goham_status(config=cfg, journal=jrnl)
        return _daily_result(
            request,
            cfg,
            status_before=status_before,
            preflight=preflight,
            status_after=status_after,
            status="blocked",
            reasons=preflight.reasons,
            diagnostic="GoHAM daily runner blocked before execution by dry preflight.",
        )

    post_once = run_post or run_goham_guarded_post
    execution = post_once(
        request,
        decision=decision,
        config=cfg,
        journal=jrnl,
        per_run_count=0,
    )
    status_after = show_goham_status(config=cfg, journal=jrnl)
    return _daily_result(
        request,
        cfg,
        status_before=status_before,
        preflight=preflight,
        execution_result=execution,
        status_after=status_after,
        status=execution.status,
        provider_post_id=execution.provider_post_id,
        execution_allowed=execution.execution_allowed,
        mutation_attempted=execution.mutation_attempted,
        reasons=execution.reasons,
        diagnostic=execution.diagnostic,
    )


def _daily_result(
    request: GohamExecutionRequest,
    config: HamXConfig,
    *,
    status_before: GohamStatus,
    preflight: GoHamEligibilityResult,
    status_after: GohamStatus,
    status: GohamDailyStatus,
    execution_result: GohamExecutionResult | None = None,
    provider_post_id: str | None = None,
    execution_allowed: bool = False,
    mutation_attempted: bool = False,
    reasons: list[str] | None = None,
    diagnostic: str = "",
) -> GohamDailyRunResult:
    return GohamDailyRunResult(
        status_before=status_before,
        preflight=preflight,
        execution_result=execution_result,
        status_after=status_after,
        status=status,
        action_id=request.action_id,
        source_action_id=request.source_action_id,
        provider_post_id=provider_post_id,
        execution_allowed=execution_allowed,
        mutation_attempted=mutation_attempted,
        reasons=reasons or [],
        diagnostic=diagnostic,
        journal_path=str(config.execution_journal_path),
        audit_path=str(config.audit_log_path),
    )


def _bound_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[: MAX_SUMMARY_CHARS - 3] + "..." if len(value) > MAX_SUMMARY_CHARS else value
    if isinstance(value, list):
        return [_bound_value(item) for item in value[:25]]
    if isinstance(value, dict):
        return {str(key)[:128]: _bound_value(item) for key, item in list(value.items())[:50]}
    return value
