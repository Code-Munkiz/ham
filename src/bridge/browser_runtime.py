from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from src.bridge.browser_policy import validate_browser_intent
from src.bridge.contracts import (
    BrowserIntent,
    BrowserResult,
    BrowserRunStatus,
    BrowserStepEvidence,
    BrowserStepState,
    BrowserStepSpec,
    PolicyDecision,
)
from src.memory_heist import git_status


class BrowserStepExecutor(Protocol):
    def execute_step(self, step: BrowserStepSpec, *, timeout_ms: int) -> dict[str, Any]:
        ...


def browser_runtime_enabled() -> bool:
    raw = (os.environ.get("HAM_ENABLE_BROWSER_RUNTIME") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def run_browser_v0(
    assembly: Any,
    intent: BrowserIntent,
    *,
    repo_root: Path | None = None,
    enabled_override: bool | None = None,
) -> BrowserResult:
    started = datetime.now(UTC)
    enabled = enabled_override if enabled_override is not None else browser_runtime_enabled()
    if not enabled:
        decision = PolicyDecision(
            accepted=False,
            reasons=["Browser runtime is disabled (`HAM_ENABLE_BROWSER_RUNTIME=false`)."],
            policy_version="browser-v0",
        )
        return _result_from_rejection(intent, BrowserRunStatus.BLOCKED, decision, started)

    policy = validate_browser_intent(intent, repo_root=repo_root)
    if not policy.accepted:
        return _result_from_rejection(intent, BrowserRunStatus.REJECTED, policy, started)

    root = (repo_root or Path.cwd()).resolve()
    executor = _resolve_executor(assembly)
    pre_git = git_status(root)

    steps: list[BrowserStepEvidence] = []
    saw_success = False
    saw_failure = False
    saw_timeout = False
    saw_blocked = False

    try:
        for step in intent.steps:
            timeout_ms = step.timeout_ms or intent.policy.step_timeout_ms
            step_started = datetime.now(UTC)
            try:
                raw = executor.execute_step(step, timeout_ms=timeout_ms)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                raw = {
                    "status": "failed",
                    "error": f"Browser execution error: {type(exc).__name__}: {exc}",
                    "url_before": None,
                    "url_after": None,
                    "dom_excerpt": "",
                    "console_errors": [],
                    "network_summary": {},
                    "screenshot_path": None,
                }
            step_ended = datetime.now(UTC)

            evidence = _build_step_evidence(
                step=step,
                raw=raw,
                started_at=step_started.isoformat(),
                ended_at=step_ended.isoformat(),
                duration_ms=_duration_ms(step_started, step_ended),
                max_dom_chars=intent.policy.max_dom_chars,
                max_console_chars=intent.policy.max_console_chars,
                max_network_events=intent.policy.max_network_events,
            )
            steps.append(evidence)
            if evidence.status == BrowserStepState.EXECUTED:
                saw_success = True
            elif evidence.status == BrowserStepState.FAILED:
                saw_failure = True
            elif evidence.status == BrowserStepState.TIMED_OUT:
                saw_timeout = True
            elif evidence.status == BrowserStepState.BLOCKED:
                saw_blocked = True
    finally:
        _close_executor(executor)

    post_git = git_status(root)
    ended = datetime.now(UTC)
    status = _map_terminal_status(saw_success, saw_failure, saw_timeout, saw_blocked)

    return BrowserResult(
        intent_id=intent.intent_id,
        request_id=intent.request_id,
        run_id=intent.run_id,
        status=status,
        policy_decision=policy,
        started_at=started.isoformat(),
        ended_at=ended.isoformat(),
        duration_ms=_duration_ms(started, ended),
        steps=steps,
        summary=_build_summary(status, steps),
        pre_exec_git_status=pre_git,
        post_exec_git_status=post_git,
        mutation_detected=_compute_mutation_signal(pre_git, post_git),
    )


def _resolve_executor(assembly: Any) -> BrowserStepExecutor:
    candidate = getattr(assembly, "browser_executor", None)
    if candidate is None:
        raise ValueError("Assembly does not expose `browser_executor`.")
    if hasattr(candidate, "execute_step") and callable(candidate.execute_step):
        return candidate

    if callable(candidate):
        class _CallableAdapter:
            def __init__(self, fn):
                self._fn = fn

            def execute_step(self, step: BrowserStepSpec, *, timeout_ms: int) -> dict[str, Any]:
                return self._fn(step, timeout_ms=timeout_ms)

        return _CallableAdapter(candidate)
    raise ValueError("Assembly.browser_executor must be callable or implement execute_step().")


def _close_executor(executor: BrowserStepExecutor) -> None:
    close = getattr(executor, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # pylint: disable=broad-exception-caught
            return


def _build_step_evidence(
    *,
    step: BrowserStepSpec,
    raw: dict[str, Any],
    started_at: str,
    ended_at: str,
    duration_ms: int,
    max_dom_chars: int,
    max_console_chars: int,
    max_network_events: int,
) -> BrowserStepEvidence:
    return BrowserStepEvidence(
        step_id=step.step_id,
        action=step.action,
        status=_coerce_step_state(raw.get("status")),
        url_before=_coerce_optional_str(raw.get("url_before")),
        url_after=_coerce_optional_str(raw.get("url_after")),
        dom_excerpt=_truncate(_coerce_str(raw.get("dom_excerpt")), max_dom_chars),
        console_errors=_cap_console_errors(raw.get("console_errors"), max_console_chars),
        network_summary=_cap_network_summary(raw.get("network_summary"), max_network_events),
        screenshot_path=_coerce_optional_str(raw.get("screenshot_path")),
        error=_coerce_optional_str(raw.get("error")),
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
    )


def _coerce_step_state(raw: Any) -> BrowserStepState:
    if isinstance(raw, BrowserStepState):
        return raw
    if isinstance(raw, str):
        low = raw.strip().lower()
        for state in BrowserStepState:
            if state.value == low:
                return state
    return BrowserStepState.FAILED


def _cap_console_errors(raw: Any, max_chars: int) -> list[str]:
    items: list[str]
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = [str(x) for x in raw]
    else:
        items = []
    out: list[str] = []
    remaining = max_chars
    for item in items:
        if remaining <= 0:
            break
        clipped = _truncate(item, remaining)
        out.append(clipped)
        remaining -= len(clipped)
    return out


def _cap_network_summary(raw: Any, max_events: int) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    used = 0
    for key, value in raw.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        remain = max(max_events - used, 0)
        clipped = min(count, remain)
        out[str(key)] = clipped
        used += clipped
    return out


def _result_from_rejection(
    intent: BrowserIntent,
    status: BrowserRunStatus,
    policy_decision: PolicyDecision,
    started: datetime,
) -> BrowserResult:
    ended = datetime.now(UTC)
    return BrowserResult(
        intent_id=intent.intent_id,
        request_id=intent.request_id,
        run_id=intent.run_id,
        status=status,
        policy_decision=policy_decision,
        started_at=started.isoformat(),
        ended_at=ended.isoformat(),
        duration_ms=_duration_ms(started, ended),
        steps=[],
        summary=f"Browser intent {status.value} by browser-v0 policy gate.",
    )


def _map_terminal_status(
    saw_success: bool,
    saw_failure: bool,
    saw_timeout: bool,
    saw_blocked: bool,
) -> BrowserRunStatus:
    if saw_timeout and (saw_success or saw_failure or saw_blocked):
        return BrowserRunStatus.PARTIAL
    if saw_timeout:
        return BrowserRunStatus.TIMED_OUT
    if saw_blocked and (saw_success or saw_failure):
        return BrowserRunStatus.PARTIAL
    if saw_blocked:
        return BrowserRunStatus.BLOCKED
    if saw_failure and saw_success:
        return BrowserRunStatus.PARTIAL
    if saw_failure:
        return BrowserRunStatus.FAILED
    return BrowserRunStatus.EXECUTED


def _build_summary(status: BrowserRunStatus, steps: list[BrowserStepEvidence]) -> str:
    return (
        f"Browser v0 {status.value}: {len(steps)} step(s), "
        f"{sum(1 for s in steps if s.status == BrowserStepState.EXECUTED)} executed, "
        f"{sum(1 for s in steps if s.status == BrowserStepState.FAILED)} failed, "
        f"{sum(1 for s in steps if s.status == BrowserStepState.TIMED_OUT)} timed out, "
        f"{sum(1 for s in steps if s.status == BrowserStepState.BLOCKED)} blocked."
    )


def _duration_ms(started: datetime, ended: datetime) -> int:
    return int((ended - started).total_seconds() * 1000)


def _compute_mutation_signal(pre_git: str | None, post_git: str | None) -> bool | None:
    if pre_git is None or post_git is None:
        return None
    return pre_git != post_git


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return "" if value is None else str(value)


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
