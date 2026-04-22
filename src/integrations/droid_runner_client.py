"""
Narrow seam between HAM and Factory `droid exec`.

- Never accepts raw shell from the browser.
- Never logs or transports FACTORY_API_KEY to HAM clients.

Modes:
- **local** (default): run `droid` via subprocess on the API host (`droid_executor`).
  Use only when the API process is co-located with Factory auth + workspace (dev/single VM).
- **remote**: POST a structured payload to `HAM_DROID_RUNNER_URL` with
  `Authorization: Bearer <HAM_DROID_RUNNER_TOKEN>`. The remote runner must execute
  the supplied argv with Factory credentials on the runner host.

If remote URL is unset, local mode is used. If local `droid` is missing, execution fails
with an honest error (no fake success).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.tools.droid_executor import DroidExecutionRecord, droid_executor


class RemoteRunnerError(RuntimeError):
    def __init__(self, message: str, *, code: str = "RUNNER_ERROR"):
        super().__init__(message)
        self.code = code


def resolve_runner_id() -> str:
    rid = (os.environ.get("HAM_DROID_RUNNER_ID") or "").strip()
    if rid:
        return rid
    if (os.environ.get("HAM_DROID_RUNNER_URL") or "").strip():
        return "remote"
    return "local"


def run_droid_argv(
    argv: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    max_stdout_chars: int = 120_000,
    max_stderr_chars: int = 32_000,
    workflow_id: str | None = None,
    audit_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    proposal_digest: str | None = None,
) -> DroidExecutionRecord:
    url = (os.environ.get("HAM_DROID_RUNNER_URL") or "").strip().rstrip("/")
    if url:
        return _run_remote(
            url,
            argv,
            cwd=cwd,
            timeout_sec=timeout_sec,
            workflow_id=workflow_id,
            audit_id=audit_id,
            session_id=session_id,
            project_id=project_id,
            proposal_digest=proposal_digest,
        )
    return droid_executor(
        argv,
        working_dir=str(cwd),
        timeout_sec=timeout_sec,
        max_stdout_chars=max_stdout_chars,
        max_stderr_chars=max_stderr_chars,
    )


def _run_remote(
    base_url: str,
    argv: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    workflow_id: str | None = None,
    audit_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    proposal_digest: str | None = None,
) -> DroidExecutionRecord:
    import urllib.error
    import urllib.request

    token = (os.environ.get("HAM_DROID_RUNNER_TOKEN") or "").strip()
    if not token:
        raise RemoteRunnerError(
            "HAM_DROID_RUNNER_URL is set but HAM_DROID_RUNNER_TOKEN is missing.",
            code="RUNNER_TOKEN_MISSING",
        )
    body: dict[str, Any] = {
        "argv": argv,
        "cwd": str(cwd.resolve()),
        "timeout_sec": timeout_sec,
    }
    if workflow_id is not None:
        body["workflow_id"] = workflow_id
    if audit_id is not None:
        body["audit_id"] = audit_id
    if session_id is not None:
        body["session_id"] = session_id
    if project_id is not None:
        body["project_id"] = project_id
    if proposal_digest is not None:
        body["proposal_digest"] = proposal_digest
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/v1/ham/droid-exec",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=min(timeout_sec + 30, 600)) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RemoteRunnerError(
            f"Runner HTTP {exc.code}: {detail}",
            code="RUNNER_HTTP_ERROR",
        ) from exc
    except OSError as exc:
        raise RemoteRunnerError(str(exc), code="RUNNER_UNAVAILABLE") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RemoteRunnerError("Runner returned non-JSON body", code="RUNNER_BAD_RESPONSE") from exc

    return DroidExecutionRecord(
        argv=list(data.get("argv") or argv),
        working_dir=str(data.get("working_dir") or cwd.resolve()),
        exit_code=data.get("exit_code"),
        timed_out=bool(data.get("timed_out")),
        stdout=str(data.get("stdout") or ""),
        stderr=str(data.get("stderr") or ""),
        stdout_truncated=bool(data.get("stdout_truncated")),
        stderr_truncated=bool(data.get("stderr_truncated")),
        started_at=str(data.get("started_at") or ""),
        ended_at=str(data.get("ended_at") or ""),
        duration_ms=int(data.get("duration_ms") or 0),
    )
