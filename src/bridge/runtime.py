from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.bridge.contracts import (
    BridgeResult,
    BridgeStatus,
    CommandEvidence,
    CommandState,
    ExecutionIntent,
)
from src.bridge.policy import validate_intent
from src.memory_heist import MAX_DIFF_CHARS, git_diff, git_status
from src.registry.backends import DEFAULT_BACKEND_ID
from src.tools.droid_executor import DroidExecutionRecord


def run_bridge_v0(assembly, intent: ExecutionIntent) -> BridgeResult:
    started = datetime.now(UTC)
    policy = validate_intent(intent)
    if not policy.accepted:
        ended = datetime.now(UTC)
        return BridgeResult(
            intent_id=intent.intent_id,
            request_id=intent.request_id,
            run_id=intent.run_id,
            status=BridgeStatus.REJECTED,
            policy_decision=policy,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_ms=_duration_ms(started, ended),
            commands=[],
            summary="Intent rejected by Bridge v0 policy gate.",
        )

    cwd = Path.cwd()
    pre_git = git_status(cwd)
    pre_git_diff = git_diff(cwd)
    command_evidence: list[CommandEvidence] = []
    saw_timeout = False
    saw_failure = False
    saw_success = False

    for cmd in intent.commands:
        try:
            record = assembly.backend_registry.get(DEFAULT_BACKEND_ID).execute(
                cmd.argv,
                working_dir=cmd.working_dir,
                timeout_sec=intent.limits.timeout_sec_per_command,
                max_stdout_chars=intent.limits.max_stdout_chars,
                max_stderr_chars=intent.limits.max_stderr_chars,
                env_overrides=cmd.env_overrides,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught  # conservative failure mapping
            now = datetime.now(UTC).isoformat()
            evidence = CommandEvidence(
                command_id=cmd.command_id,
                argv=cmd.argv,
                working_dir=cmd.working_dir,
                status=CommandState.FAILED,
                exit_code=None,
                timed_out=False,
                stdout="",
                stderr=f"Bridge execution error: {type(exc).__name__}: {exc}",
                stdout_truncated=False,
                stderr_truncated=False,
                started_at=now,
                ended_at=now,
                duration_ms=0,
            )
            saw_failure = True
            command_evidence.append(evidence)
            continue

        evidence = _record_to_evidence(cmd.command_id, record)
        command_evidence.append(evidence)
        if evidence.status == CommandState.TIMED_OUT:
            saw_timeout = True
        elif evidence.status == CommandState.FAILED:
            saw_failure = True
        elif evidence.status == CommandState.EXECUTED:
            saw_success = True

    post_git = git_status(cwd)
    post_git_diff = git_diff(cwd)
    _enforce_total_output_budget(command_evidence, intent.limits.max_total_output_chars)
    ended = datetime.now(UTC)
    status = _map_terminal_status(saw_success, saw_failure, saw_timeout)
    summary = _build_summary(status, command_evidence)

    return BridgeResult(
        intent_id=intent.intent_id,
        request_id=intent.request_id,
        run_id=intent.run_id,
        status=status,
        policy_decision=policy,
        started_at=started.isoformat(),
        ended_at=ended.isoformat(),
        duration_ms=_duration_ms(started, ended),
        commands=command_evidence,
        summary=summary,
        pre_exec_git_status=pre_git,
        post_exec_git_status=post_git,
        mutation_detected=_compute_mutation_signal(pre_git, post_git),
        mutation_diff=_compute_mutation_diff(pre_git_diff, post_git_diff),
    )


def _record_to_evidence(command_id: str, record: DroidExecutionRecord) -> CommandEvidence:
    status = CommandState.EXECUTED
    if record.timed_out:
        status = CommandState.TIMED_OUT
    elif record.exit_code not in (0, None):
        status = CommandState.FAILED
    elif record.exit_code is None:
        status = CommandState.FAILED
    return CommandEvidence(
        command_id=command_id,
        argv=record.argv,
        working_dir=record.working_dir,
        status=status,
        exit_code=record.exit_code,
        timed_out=record.timed_out,
        stdout=record.stdout,
        stderr=record.stderr,
        stdout_truncated=record.stdout_truncated,
        stderr_truncated=record.stderr_truncated,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_ms=record.duration_ms,
    )


def _map_terminal_status(saw_success: bool, saw_failure: bool, saw_timeout: bool) -> BridgeStatus:
    if saw_timeout and (saw_success or saw_failure):
        return BridgeStatus.PARTIAL
    if saw_timeout:
        return BridgeStatus.TIMED_OUT
    if saw_failure and saw_success:
        return BridgeStatus.PARTIAL
    if saw_failure:
        return BridgeStatus.FAILED
    return BridgeStatus.EXECUTED


def _duration_ms(started: datetime, ended: datetime) -> int:
    return int((ended - started).total_seconds() * 1000)


def _build_summary(status: BridgeStatus, commands: list[CommandEvidence]) -> str:
    return (
        f"Bridge v0 {status.value}: {len(commands)} command(s), "
        f"{sum(1 for c in commands if c.status == CommandState.EXECUTED)} executed, "
        f"{sum(1 for c in commands if c.status == CommandState.FAILED)} failed, "
        f"{sum(1 for c in commands if c.status == CommandState.TIMED_OUT)} timed out."
    )


def _enforce_total_output_budget(commands: list[CommandEvidence], max_total_chars: int) -> None:
    remaining = max_total_chars
    for cmd in commands:
        original_stdout = cmd.stdout
        original_stderr = cmd.stderr

        keep_stdout = min(len(original_stdout), max(remaining, 0))
        cmd.stdout = original_stdout[:keep_stdout]
        remaining -= keep_stdout

        keep_stderr = min(len(original_stderr), max(remaining, 0))
        cmd.stderr = original_stderr[:keep_stderr]
        remaining -= keep_stderr

        if keep_stdout < len(original_stdout):
            cmd.stdout_truncated = True
        if keep_stderr < len(original_stderr):
            cmd.stderr_truncated = True


def _compute_mutation_signal(pre_git: str | None, post_git: str | None) -> bool | None:
    if pre_git is None or post_git is None:
        return None
    if pre_git == post_git:
        return False
    # Advisory-only signal: repo state snapshot changed during this run.
    return True


def _compute_mutation_diff(
    pre_git_diff: str | None,
    post_git_diff: str | None,
    *,
    max_chars: int = MAX_DIFF_CHARS,
) -> str | None:
    """Return the capped post-exec git diff when it differs from pre-exec.

    When Bridge policy eventually permits write-capable intents, the Hermes
    critic should review what Droid actually changed in the workspace, not
    the bridge metadata envelope. This helper returns the post-exec diff
    (truncated at ``max_chars``) when it differs from the pre-exec capture;
    otherwise returns ``None`` so the caller can fall back to the existing
    bridge-JSON review payload.

    Caveat: ``post_git_diff`` is the full post-exec unstaged+staged diff,
    so the returned payload includes any pre-existing user changes alongside
    Droid's mutations. This matches the surface already exposed via
    ``ContextBuilder`` and ``pre_exec_git_status`` / ``post_exec_git_status``,
    so the critic is not seeing new data -- only getting a richer review
    target than the command-evidence envelope. A precise Droid-only delta
    is a possible follow-up.

    Dormancy note: Bridge v0 policy rejects ``allow_write=True`` and all
    current ``build_runtime_intent`` callers set ``task_class="inspect"``,
    so ``post_git_diff`` matches ``pre_git_diff`` for 100% of production
    runs today and this returns ``None``. The field is wired through the
    call chain so it is ready when writes are introduced.
    """
    if post_git_diff is None:
        return None
    if pre_git_diff == post_git_diff:
        return None
    capped = post_git_diff[:max_chars]
    return capped if capped else None

