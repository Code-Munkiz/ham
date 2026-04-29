"""Phase 2C guarded GoHAM bridge for one autonomous original post."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.autonomy import AutonomyDecisionResult
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_policy import (
    GOHAM_EXECUTION_KIND,
    GoHamEligibilityResult,
    evaluate_goham_eligibility,
)
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.x_executor import XCanaryExecutor, XProviderResult

GohamStatus = Literal["blocked", "executed", "failed"]


class GohamExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    action_type: str = "post"
    text: str
    source_action_id: str
    idempotency_key: str
    reason: str = "phase_2c_guarded_goham_execution"
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_post_id: str | None = None
    quote_target_id: str | None = None
    reply_target_id: str | None = None

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


class GohamExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GohamStatus
    execution_kind: str = GOHAM_EXECUTION_KIND
    action_id: str
    source_action_id: str
    action_type: str
    execution_allowed: bool = False
    mutation_attempted: bool = False
    provider_status_code: int | None = None
    provider_post_id: str | None = None
    provider_response: dict[str, Any] = Field(default_factory=dict)
    audit_event_id: str | None = None
    audit_path: str
    reasons: list[str] = Field(default_factory=list)
    diagnostic: str = ""

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


def run_goham_guarded_post(
    request: GohamExecutionRequest,
    *,
    decision: AutonomyDecisionResult,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    executor: XCanaryExecutor | None = None,
    per_run_count: int = 0,
) -> GohamExecutionResult:
    """Execute exactly one autonomous original post after strict GoHAM gates."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    append_audit_event(
        "goham_execution_requested",
        {
            "request": request.redacted_dump(),
            "autonomy_decision": decision.model_dump(mode="json"),
            "execution_kind": GOHAM_EXECUTION_KIND,
        },
        config=cfg,
    )
    eligibility = evaluate_goham_eligibility(
        request,
        decision=decision,
        config=cfg,
        journal=jrnl,
        per_run_count=per_run_count,
    )
    if not eligibility.allowed:
        event = _blocked_event(eligibility)
        audit_id = append_audit_event(
            event,
            {
                "request": request.redacted_dump(),
                "eligibility": eligibility.model_dump(mode="json"),
                "status": "blocked",
            },
            config=cfg,
        )
        return _result(
            request,
            cfg,
            status="blocked",
            reasons=eligibility.reasons,
            diagnostic="GoHAM autonomous execution blocked by Phase 2C gates.",
            audit_event_id=audit_id,
        )

    append_audit_event(
        "goham_execution_allowed",
        {
            "request": request.redacted_dump(),
            "eligibility": eligibility.model_dump(mode="json"),
            "execution_kind": GOHAM_EXECUTION_KIND,
        },
        config=cfg,
    )
    provider = (executor or XCanaryExecutor(config=cfg)).execute(request)
    if provider.status == "executed":
        jrnl.append_executed(
            action_id=request.action_id,
            source_action_id=request.source_action_id,
            idempotency_key=request.idempotency_key,
            action_type="post",
            execution_kind=GOHAM_EXECUTION_KIND,
            provider_post_id=provider.provider_post_id,
        )
        audit_id = append_audit_event(
            "goham_execution_executed",
            _provider_payload(request, provider, "executed"),
            config=cfg,
        )
        return _result(
            request,
            cfg,
            status="executed",
            execution_allowed=True,
            mutation_attempted=True,
            provider=provider,
            audit_event_id=audit_id,
        )

    audit_id = append_audit_event(
        "goham_execution_failed",
        _provider_payload(request, provider, "failed"),
        config=cfg,
    )
    return _result(
        request,
        cfg,
        status="failed",
        execution_allowed=True,
        mutation_attempted=True,
        provider=provider,
        diagnostic=provider.diagnostic,
        audit_event_id=audit_id,
    )


def _result(
    request: GohamExecutionRequest,
    config: HamXConfig,
    *,
    status: GohamStatus,
    reasons: list[str] | None = None,
    diagnostic: str = "",
    execution_allowed: bool = False,
    mutation_attempted: bool = False,
    provider: XProviderResult | None = None,
    audit_event_id: str | None = None,
) -> GohamExecutionResult:
    return GohamExecutionResult(
        status=status,
        action_id=request.action_id,
        source_action_id=request.source_action_id,
        action_type=request.action_type,
        execution_allowed=execution_allowed,
        mutation_attempted=mutation_attempted,
        provider_status_code=provider.status_code if provider else None,
        provider_post_id=provider.provider_post_id if provider else None,
        provider_response=provider.as_dict() if provider else {},
        audit_event_id=audit_event_id,
        audit_path=str(config.audit_log_path),
        reasons=reasons or [],
        diagnostic=diagnostic,
    )


def _blocked_event(eligibility: GoHamEligibilityResult) -> str:
    reasons = set(eligibility.reasons)
    if "duplicate_execution" in reasons:
        return "goham_execution_duplicate_blocked"
    if "goham_per_run_cap_exceeded" in reasons or "goham_daily_cap_exceeded" in reasons:
        return "goham_execution_cap_blocked"
    if any(reason.startswith("safety_policy:") for reason in reasons) or {
        "financial_or_buy_language",
        "links_not_allowed",
        "safety_severity_not_low",
    } & reasons:
        return "goham_execution_policy_blocked"
    return "goham_execution_blocked"


def _provider_payload(
    request: GohamExecutionRequest,
    provider: XProviderResult,
    status: str,
) -> dict[str, Any]:
    return {
        "request": request.redacted_dump(),
        "status": status,
        "execution_kind": GOHAM_EXECUTION_KIND,
        "provider": provider.as_dict(),
    }
