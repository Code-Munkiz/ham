"""Strict dry-run wrapper shape for xurl.

Phase 1A never executes mutating xurl commands. Search is represented as a
planned command so reviewers can inspect intent without touching the network.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.rate_limits import InProcessRateLimiter
from src.ham.ham_x.redaction import redact

MUTATING_ACTIONS = frozenset({"post", "quote", "like"})


@dataclass(frozen=True)
class XurlCommandResult:
    action_type: str
    argv: list[str]
    dry_run: bool
    blocked: bool
    reason: str
    output: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return redact(
            {
                "action_type": self.action_type,
                "argv": self.argv,
                "dry_run": self.dry_run,
                "blocked": self.blocked,
                "reason": self.reason,
                "output": self.output,
                "metadata": self.metadata,
            }
        )


class XurlWrapper:
    def __init__(
        self,
        *,
        config: HamXConfig | None = None,
        rate_limiter: InProcessRateLimiter | None = None,
    ) -> None:
        self.config = config or load_ham_x_config()
        self.rate_limiter = rate_limiter or InProcessRateLimiter()

    def plan_search(self, query: str, *, max_results: int = 20) -> XurlCommandResult:
        """Return a non-executed xurl search command plan."""
        limited = max(1, min(int(max_results), 100))
        rate = self.rate_limiter.check("search", config=self.config)
        argv = [self.config.xurl_bin, "search", query, "--max-results", str(limited)]
        append_audit_event(
            "search_attempt",
            {
                "argv": argv,
                "catalog_skill_id": self.config.catalog_skill_id,
                "rate_limit_result": rate.as_dict(),
                "dry_run": True,
            },
            config=self.config,
        )
        metadata = {
            "catalog_skill_id": self.config.catalog_skill_id,
            "rate_limit_result": rate.as_dict(),
        }
        if not rate.allowed:
            return XurlCommandResult(
                action_type="search",
                argv=argv,
                dry_run=True,
                blocked=True,
                reason=rate.reason,
                metadata=metadata,
            )
        return XurlCommandResult(
            action_type="search",
            argv=argv,
            dry_run=True,
            blocked=False,
            reason="planned_only_no_live_api_call",
            metadata=metadata,
        )

    def plan_mutating_action(self, action_type: str, *, text: str | None = None) -> XurlCommandResult:
        """Block post/quote/like plans unless future phases explicitly wire execution."""
        if action_type not in MUTATING_ACTIONS:
            raise ValueError(f"unsupported mutating action: {action_type}")
        argv = [self.config.xurl_bin, action_type]
        if text:
            argv.extend(["--text", text])

        rate = self.rate_limiter.check(action_type, config=self.config)  # type: ignore[arg-type]
        gate_closed = (
            not self.config.autonomy_enabled
            or self.config.dry_run
            or not rate.allowed
        )
        reason = "mutating_actions_disabled_in_phase_1a"
        if not self.config.autonomy_enabled:
            reason = "autonomy_disabled"
        elif self.config.dry_run:
            reason = "dry_run_enabled"
        elif not rate.allowed:
            reason = rate.reason

        append_audit_event(
            "blocked_mutating_action",
            {
                "action_type": action_type,
                "argv": argv,
                "catalog_skill_id": self.config.catalog_skill_id,
                "rate_limit_result": rate.as_dict(),
                "reason": reason,
            },
            config=self.config,
        )
        return XurlCommandResult(
            action_type=action_type,
            argv=argv,
            dry_run=self.config.dry_run,
            blocked=True,
            reason=reason if gate_closed else "mutating_execution_not_implemented",
            metadata={
                "catalog_skill_id": self.config.catalog_skill_id,
                "rate_limit_result": rate.as_dict(),
            },
        )
