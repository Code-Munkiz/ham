"""
Droid execution entrypoint: bounded subprocess backend for Bridge v0.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class DroidExecutionRecord:
    argv: list[str]
    working_dir: str
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    started_at: str
    ended_at: str
    duration_ms: int


def droid_executor(
    argv: list[str],
    *,
    working_dir: str | None = None,
    timeout_sec: int = 30,
    max_stdout_chars: int = 8_000,
    max_stderr_chars: int = 8_000,
    env_overrides: dict[str, str] | None = None,
) -> DroidExecutionRecord:
    """
    Execute a single command in a bounded subprocess context.

    Bridge policy is responsible for command allowlist and scope validation.
    This backend enforces deterministic capture, timeout, and output caps.
    """
    if not argv:
        raise ValueError("argv must not be empty")

    cwd_path = Path(working_dir or Path.cwd()).resolve()
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    started = datetime.now(UTC)
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
            shell=False,
            env=env,
        )
        stdout, stdout_trunc = _cap(result.stdout or "", max_stdout_chars)
        stderr, stderr_trunc = _cap(result.stderr or "", max_stderr_chars)
        ended = datetime.now(UTC)
        return DroidExecutionRecord(
            argv=list(argv),
            working_dir=str(cwd_path),
            exit_code=result.returncode,
            timed_out=False,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_ms=int((ended - started).total_seconds() * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = _safe_text(exc.stdout)
        raw_stderr = _safe_text(exc.stderr)
        stdout, stdout_trunc = _cap(raw_stdout, max_stdout_chars)
        stderr, stderr_trunc = _cap(raw_stderr, max_stderr_chars)
        ended = datetime.now(UTC)
        return DroidExecutionRecord(
            argv=list(argv),
            working_dir=str(cwd_path),
            exit_code=None,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_ms=int((ended - started).total_seconds() * 1000),
        )
    except FileNotFoundError as exc:
        ended = datetime.now(UTC)
        err = f"Executable not found: {exc}"
        stderr, stderr_trunc = _cap(err, max_stderr_chars)
        return DroidExecutionRecord(
            argv=list(argv),
            working_dir=str(cwd_path),
            exit_code=None,
            timed_out=False,
            stdout="",
            stderr=stderr,
            stdout_truncated=False,
            stderr_truncated=stderr_trunc,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            duration_ms=int((ended - started).total_seconds() * 1000),
        )


def _cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _safe_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
