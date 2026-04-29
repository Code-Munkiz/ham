"""Strict dry-run and read-only wrapper shape for xurl.

Phase 1 never executes mutating xurl commands. Phase 1E adds a gated read-only
search smoke path for validating xurl wiring without enabling posting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import shutil
import subprocess
from typing import Any, Callable

from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.rate_limits import InProcessRateLimiter
from src.ham.ham_x.redaction import redact

MUTATING_ACTIONS = frozenset({"post", "quote", "like"})
READONLY_ACTIONS = frozenset({"search"})
DEFAULT_READONLY_TIMEOUT_SECONDS = 15

XurlRunner = Callable[..., Any]
XurlWhich = Callable[[str], str | None]


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


@dataclass(frozen=True)
class XurlReadonlyResult:
    action_type: str
    argv: list[str]
    blocked: bool
    executed: bool
    exit_code: int | None
    reason: str
    stdout: str = ""
    stderr: str = ""
    catalog_skill_id: str = ""
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def as_dict(self) -> dict[str, object]:
        return redact(
            {
                "action_type": self.action_type,
                "argv": self.argv,
                "blocked": self.blocked,
                "executed": self.executed,
                "exit_code": self.exit_code,
                "reason": self.reason,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "catalog_skill_id": self.catalog_skill_id,
                "execution_allowed": False,
                "mutation_attempted": False,
            }
        )


class XurlWrapper:
    def __init__(
        self,
        *,
        config: HamXConfig | None = None,
        rate_limiter: InProcessRateLimiter | None = None,
        runner: XurlRunner | None = None,
        binary_resolver: XurlWhich | None = None,
    ) -> None:
        self.config = config or load_ham_x_config()
        self.rate_limiter = rate_limiter or InProcessRateLimiter()
        self.runner = runner or subprocess.run
        self.binary_resolver = binary_resolver or shutil.which

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

    def execute_readonly_search(
        self,
        query: str,
        *,
        max_results: int = 10,
        timeout_seconds: int = DEFAULT_READONLY_TIMEOUT_SECONDS,
    ) -> XurlReadonlyResult:
        """Execute a gated read-only xurl search smoke command."""
        return self.execute_readonly_action(
            "search",
            query=query,
            max_results=max_results,
            timeout_seconds=timeout_seconds,
        )

    def execute_readonly_action(
        self,
        action_type: str,
        *,
        query: str,
        max_results: int,
        timeout_seconds: int,
    ) -> XurlReadonlyResult:
        if action_type in MUTATING_ACTIONS:
            argv = [self.config.xurl_bin, action_type]
            append_audit_event(
                "x_mutation_blocked",
                {
                    "action_type": action_type,
                    "argv": argv,
                    "reason": "mutating_action_blocked_before_runner",
                    "catalog_skill_id": self.config.catalog_skill_id,
                    "execution_allowed": False,
                    "mutation_attempted": False,
                },
                config=self.config,
            )
            return XurlReadonlyResult(
                action_type=action_type,
                argv=argv,
                blocked=True,
                executed=False,
                exit_code=None,
                reason="mutating_action_blocked_before_runner",
                catalog_skill_id=self.config.catalog_skill_id,
            )
        if action_type not in READONLY_ACTIONS:
            return XurlReadonlyResult(
                action_type=action_type,
                argv=[self.config.xurl_bin, action_type],
                blocked=True,
                executed=False,
                exit_code=None,
                reason="unsupported_readonly_action",
                catalog_skill_id=self.config.catalog_skill_id,
            )

        limited = max(10, min(int(max_results), 100))
        argv = [self.config.xurl_bin, "search", query, "--max-results", str(limited)]
        append_audit_event(
            "x_readonly_smoke_planned",
            {
                "argv": argv,
                "catalog_skill_id": self.config.catalog_skill_id,
                "execution_allowed": False,
                "mutation_attempted": False,
            },
            config=self.config,
        )

        binary_path = self.binary_resolver(self.config.xurl_bin)
        if not binary_path:
            return self._blocked_readonly(
                argv,
                reason="xurl_binary_not_found",
                event_type="x_readonly_smoke_blocked",
            )

        try:
            completed = self.runner(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return self._failed_readonly(
                argv,
                reason="xurl_readonly_smoke_timeout",
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )
        except OSError as exc:
            return self._failed_readonly(
                argv,
                reason="xurl_readonly_smoke_error",
                exit_code=None,
                stdout="",
                stderr=str(exc),
            )

        exit_code = int(getattr(completed, "returncode", 1))
        stdout = str(getattr(completed, "stdout", "") or "")
        stderr = str(getattr(completed, "stderr", "") or "")
        if exit_code != 0:
            return self._failed_readonly(
                argv,
                reason="xurl_readonly_smoke_nonzero_exit",
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
            )

        result = XurlReadonlyResult(
            action_type="search",
            argv=argv,
            blocked=False,
            executed=True,
            exit_code=exit_code,
            reason="xurl_readonly_smoke_executed",
            stdout=redact(stdout),
            stderr=redact(stderr),
            catalog_skill_id=self.config.catalog_skill_id,
        )
        append_audit_event("x_readonly_smoke_executed", result.as_dict(), config=self.config)
        return result

    def _blocked_readonly(
        self,
        argv: list[str],
        *,
        reason: str,
        event_type: str,
    ) -> XurlReadonlyResult:
        result = XurlReadonlyResult(
            action_type="search",
            argv=argv,
            blocked=True,
            executed=False,
            exit_code=None,
            reason=reason,
            catalog_skill_id=self.config.catalog_skill_id,
        )
        append_audit_event(event_type, result.as_dict(), config=self.config)  # type: ignore[arg-type]
        return result

    def _failed_readonly(
        self,
        argv: list[str],
        *,
        reason: str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> XurlReadonlyResult:
        result = XurlReadonlyResult(
            action_type="search",
            argv=argv,
            blocked=False,
            executed=True,
            exit_code=exit_code,
            reason=reason,
            stdout=redact(stdout),
            stderr=redact(stderr),
            catalog_skill_id=self.config.catalog_skill_id,
        )
        append_audit_event("x_readonly_smoke_failed", result.as_dict(), config=self.config)
        return result
