"""
Minimal FastAPI service: POST /v1/ham/droid-exec

Run (example):
  HAM_DROID_RUNNER_SERVICE_TOKEN=secret uvicorn src.ham.droid_runner.service:app --host 127.0.0.1 --port 8791

See docs/HAM_DROID_RUNNER_SERVICE.md.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.ham.droid_runner.allowed_roots import (
    cwd_allowlist_violation_message,
    load_allowed_roots_from_env,
)
from src.ham.droid_runner.argv_validate import validate_remote_droid_argv
from src.ham.droid_runner.runner_audit import append_runner_audit_line
from src.tools.droid_executor import DroidExecutionRecord, droid_executor

_MIN_TIMEOUT = 1
_MAX_TIMEOUT = 3600
_MAX_STDOUT = 120_000
_MAX_STDERR = 32_000


def _service_token() -> str:
    import os

    return (os.environ.get("HAM_DROID_RUNNER_SERVICE_TOKEN") or "").strip()


class DroidExecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    argv: list[str] = Field(min_length=1)
    cwd: str = Field(min_length=1, max_length=8192)
    timeout_sec: int = Field(ge=1, le=_MAX_TIMEOUT)
    workflow_id: str | None = Field(default=None, max_length=128)
    audit_id: str | None = Field(
        default=None,
        max_length=80,
        description="Optional Ham-side correlation id (e.g. project audit).",
    )
    session_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(default=None, max_length=180)
    proposal_digest: str | None = Field(default=None, max_length=80)


def _parse_stdout_json(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        val = json.loads(text)
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, dict) else None


def _require_bearer(authorization: str | None) -> None:
    expected = _service_token()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "RUNNER_NOT_CONFIGURED",
                    "message": "HAM_DROID_RUNNER_SERVICE_TOKEN is not set on this runner.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Authorization: Bearer <token> required.",
                }
            },
        )
    if authorization[7:].strip() != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Invalid bearer token.",
                }
            },
        )


def _metadata_response_fields(body: DroidExecRequest, runner_request_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {"runner_request_id": runner_request_id}
    if body.workflow_id is not None:
        out["workflow_id"] = body.workflow_id
    if body.audit_id is not None:
        out["audit_id"] = body.audit_id
    if body.session_id is not None:
        out["session_id"] = body.session_id
    if body.project_id is not None:
        out["project_id"] = body.project_id
    if body.proposal_digest is not None:
        out["proposal_digest"] = body.proposal_digest
    return out


def _audit_base(
    *,
    body: DroidExecRequest,
    runner_request_id: str,
    cwd_requested: str,
    cwd_normalized: str | None,
    status: str,
    blocked_code: str | None = None,
    blocked_reason: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    timed_out: bool | None = None,
    execution_ok: bool | None = None,
    failure_kind: str | None = None,
) -> None:
    append_runner_audit_line(
        {
            "runner_request_id": runner_request_id,
            "status": status,
            "cwd_requested": cwd_requested[:8192],
            "cwd_normalized": cwd_normalized,
            "workflow_id": body.workflow_id,
            "project_id": body.project_id,
            "session_id": body.session_id,
            "proposal_digest": body.proposal_digest,
            "ham_audit_id": body.audit_id,
            "blocked_code": blocked_code,
            "blocked_reason": blocked_reason,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "execution_ok": execution_ok,
            "failure_kind": failure_kind,
        }
    )


router = APIRouter(prefix="/v1/ham", tags=["ham-droid-runner"])


@router.post("/droid-exec")
def post_droid_exec(
    body: DroidExecRequest,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """
    Execute a pre-built `droid exec` argv under a validated cwd.

    Request JSON: ``argv``, ``cwd``, ``timeout_sec``, optional correlation metadata.
    Response: execution fields for ``droid_runner_client``, optional ``parsed_stdout``,
    echoed metadata, and ``runner_request_id``.
    """
    _require_bearer(authorization)
    runner_request_id = str(uuid.uuid4())
    allowed = load_allowed_roots_from_env()

    cwd_path: Path | None = None
    try:
        cwd_path = Path(body.cwd).expanduser().resolve()
    except OSError as exc:
        _audit_base(
            body=body,
            runner_request_id=runner_request_id,
            cwd_requested=body.cwd,
            cwd_normalized=None,
            status="blocked",
            blocked_code="INVALID_CWD",
            blocked_reason=f"Cannot resolve cwd: {exc}",
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "INVALID_CWD",
                    "message": f"Cannot resolve cwd: {exc}",
                }
            },
        ) from exc

    msg = cwd_allowlist_violation_message(cwd_path, allowed)
    if msg:
        _audit_base(
            body=body,
            runner_request_id=runner_request_id,
            cwd_requested=body.cwd,
            cwd_normalized=str(cwd_path),
            status="blocked",
            blocked_code="CWD_NOT_ALLOWED",
            blocked_reason=msg,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CWD_NOT_ALLOWED",
                    "message": msg,
                }
            },
        )

    if not cwd_path.is_dir():
        _audit_base(
            body=body,
            runner_request_id=runner_request_id,
            cwd_requested=body.cwd,
            cwd_normalized=str(cwd_path),
            status="blocked",
            blocked_code="CWD_NOT_ACCESSIBLE",
            blocked_reason=f"cwd is not a directory or is not accessible: {cwd_path}",
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CWD_NOT_ACCESSIBLE",
                    "message": f"cwd is not a directory or is not accessible: {cwd_path}",
                }
            },
        )

    v_err = validate_remote_droid_argv(body.argv, expected_cwd=cwd_path)
    if v_err:
        _audit_base(
            body=body,
            runner_request_id=runner_request_id,
            cwd_requested=body.cwd,
            cwd_normalized=str(cwd_path),
            status="blocked",
            blocked_code="ARGV_REJECTED",
            blocked_reason=v_err,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "ARGV_REJECTED",
                    "message": v_err,
                }
            },
        )

    timeout = max(_MIN_TIMEOUT, min(int(body.timeout_sec), _MAX_TIMEOUT))
    record: DroidExecutionRecord = droid_executor(
        body.argv,
        working_dir=str(cwd_path),
        timeout_sec=timeout,
        max_stdout_chars=_MAX_STDOUT,
        max_stderr_chars=_MAX_STDERR,
    )

    ok_exec = not record.timed_out and record.exit_code == 0
    failure_kind: str | None = None
    if not ok_exec:
        failure_kind = "timeout" if record.timed_out else "non_zero_exit"
    _audit_base(
        body=body,
        runner_request_id=runner_request_id,
        cwd_requested=body.cwd,
        cwd_normalized=str(cwd_path),
        status="executed",
        exit_code=record.exit_code,
        duration_ms=record.duration_ms,
        timed_out=record.timed_out,
        execution_ok=ok_exec,
        failure_kind=failure_kind,
    )

    out: dict[str, Any] = {
        "argv": record.argv,
        "working_dir": record.working_dir,
        "exit_code": record.exit_code,
        "timed_out": record.timed_out,
        "stdout": record.stdout,
        "stderr": record.stderr,
        "stdout_truncated": record.stdout_truncated,
        "stderr_truncated": record.stderr_truncated,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "duration_ms": record.duration_ms,
    }
    out.update(_metadata_response_fields(body, runner_request_id))
    parsed = _parse_stdout_json(record.stdout)
    if parsed is not None:
        out["parsed_stdout"] = parsed
    return out


app = FastAPI(title="HAM Droid Runner", version="1")
app.include_router(router)
