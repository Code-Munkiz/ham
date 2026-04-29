"""Manual-only canary execution entrypoint for HAM-on-X Phase 2A."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import platform_context_from_config
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.execution_policy import evaluate_canary_request
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.x_executor import XCanaryExecutor, XProviderResult

CanaryActionType = Literal["post", "quote"]
CanaryStatus = Literal["blocked", "dry_run", "executed", "failed"]


class ManualCanaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    action_type: CanaryActionType
    text: str
    quote_target_id: str | None = None
    manual_confirm: bool = False
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reason: str
    operator_label: str | None = None

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


class CanaryExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CanaryStatus
    action_id: str
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


def run_manual_canary_action(
    request: ManualCanaryRequest,
    *,
    config: HamXConfig | None = None,
    journal: ExecutionJournal | None = None,
    executor: XCanaryExecutor | None = None,
    per_run_count: int = 0,
) -> CanaryExecutionResult:
    """Run a manually confirmed canary action if every Phase 2A gate passes."""
    cfg = config or load_ham_x_config()
    jrnl = journal or ExecutionJournal(config=cfg)
    append_audit_event(
        "execution_canary_requested",
        {"request": request.redacted_dump()},
        config=cfg,
    )

    reasons = evaluate_canary_request(request, config=cfg, journal=jrnl, per_run_count=per_run_count)
    if reasons:
        event = _blocked_event(reasons)
        status = _blocked_status(reasons)
        audit_id = append_audit_event(
            event,
            {"request": request.redacted_dump(), "status": status, "reasons": reasons},
            config=cfg,
        )
        return _result(
            request,
            cfg,
            status=status,
            reasons=reasons,
            diagnostic="Manual canary execution blocked by Phase 2A gates.",
            audit_event_id=audit_id,
        )

    provider = (executor or XCanaryExecutor(config=cfg)).execute(request)
    if provider.status == "executed":
        jrnl.append_executed(
            action_id=request.action_id,
            idempotency_key=request.idempotency_key,
            action_type=request.action_type,
            provider_post_id=provider.provider_post_id,
        )
        audit_id = append_audit_event(
            "execution_canary_executed",
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
        "execution_canary_failed",
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
    request: ManualCanaryRequest,
    config: HamXConfig,
    *,
    status: CanaryStatus,
    reasons: list[str] | None = None,
    diagnostic: str = "",
    execution_allowed: bool = False,
    mutation_attempted: bool = False,
    provider: XProviderResult | None = None,
    audit_event_id: str | None = None,
) -> CanaryExecutionResult:
    return CanaryExecutionResult(
        status=status,
        action_id=request.action_id,
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


def _blocked_event(reasons: list[str]) -> str:
    if "emergency_stop" in reasons:
        return "execution_emergency_stop_blocked"
    if "duplicate_execution" in reasons:
        return "execution_duplicate_blocked"
    if "per_run_cap_exceeded" in reasons or "daily_cap_exceeded" in reasons:
        return "execution_cap_blocked"
    if "dry_run_enabled" in reasons:
        return "execution_canary_dry_run"
    return "execution_canary_blocked"


def _blocked_status(reasons: list[str]) -> CanaryStatus:
    if "dry_run_enabled" in reasons:
        return "dry_run"
    return "blocked"


def _provider_payload(
    request: ManualCanaryRequest,
    provider: XProviderResult,
    status: str,
) -> dict[str, Any]:
    return {
        **platform_context_from_config(None),
        "request": request.redacted_dump(),
        "status": status,
        "provider": provider.as_dict(),
    }
