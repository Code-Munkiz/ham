"""
Minimal FastAPI service: POST /v1/ham/droid-exec

Run (example):
  HAM_DROID_RUNNER_SERVICE_TOKEN=secret uvicorn src.ham.droid_runner.service:app --host 127.0.0.1 --port 8791

See docs/HAM_DROID_RUNNER_SERVICE.md.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.ham.droid_runner.allowed_roots import (
    cwd_allowlist_violation_message,
    load_allowed_roots_from_env,
)
from src.ham.droid_runner.argv_validate import RequestMode, validate_remote_droid_argv
from src.ham.droid_runner.build_lane import (
    BuildLaneInputs,
    BuildLaneResult,
    SubprocessRunner,
    execute_build_lane_post_exec,
    generate_branch_name,
    is_safe_branch_name,
    make_default_runner,
)
from src.ham.droid_runner.runner_audit import append_runner_audit_line
from src.tools.droid_executor import DroidExecutionRecord, droid_executor

_MIN_TIMEOUT = 1
_MAX_TIMEOUT = 3600
_MAX_STDOUT = 120_000
_MAX_STDERR = 32_000

_BUILD_LANE_TIMEOUT_SEC = 300
_MAX_PR_TITLE = 120
_MAX_PR_BODY = 8_000
_MAX_COMMIT_MSG = 200
_GENERIC_PR_TITLE = "HAM Droid build: safe project update"
_GENERIC_COMMIT_MSG = "chore(droid-build): safe project update"


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
    # Optional Build-Lane request mode. Default ``None`` keeps legacy (Phase 1)
    # audit behavior unchanged; ``"build"`` triggers the post-exec Build Lane
    # (commit + push + ``gh pr create``) when ``accept_pr=True`` AND ``droid exec``
    # succeeds. The runner refuses ``mode="build"`` without ``accept_pr=True``.
    mode: Literal["audit", "build"] | None = Field(default=None)
    accept_pr: bool = Field(default=False)
    # Build-Lane post-exec text suggestions. All optional; runner-derived text
    # from ``droid exec`` JSON takes precedence, then these API suggestions,
    # then a generic safe fallback. The runner is the final authority — it
    # sanitizes every field and rejects sensitive substrings.
    commit_message: str | None = Field(default=None, max_length=400)
    pr_title: str | None = Field(default=None, max_length=200)
    pr_body: str | None = Field(default=None, max_length=8000)
    base_ref: str | None = Field(default=None, max_length=200)


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
    if body.mode is not None:
        out["mode"] = body.mode
    return out


_FORBIDDEN_TEXT_SUBSTRINGS: tuple[str, ...] = (
    "safe_edit_low",
    "readonly_repo_audit",
    "HAM_DROID_EXEC_TOKEN",
    "FACTORY_API_KEY",
    "HAM_DROID_RUNNER_TOKEN",
    "--auto",
    "--skip-permissions-unsafe",
    "droid exec",
    "/v1/ham/droid-exec",
)


def _safe_one_line(text: str, *, max_chars: int) -> str:
    """Strip control chars, collapse to one line, clamp length."""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text or "")
    t = t.replace("\r", " ").replace("\n", " ").strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return ""
    if len(t) > max_chars:
        t = t[: max(1, max_chars - 1)].rstrip() + "…"
    return t


def _redact_unsafe(text: str) -> str:
    """Drop the field if it references any forbidden internal marker."""
    if not text:
        return ""
    lowered = text.lower()
    for marker in _FORBIDDEN_TEXT_SUBSTRINGS:
        if marker.lower() in lowered:
            return ""
    return text


def _droid_result_text(parsed: dict[str, Any] | None) -> str:
    if not isinstance(parsed, dict):
        return ""
    res = parsed.get("result")
    if not isinstance(res, str):
        return ""
    return _redact_unsafe(_safe_one_line(res, max_chars=_MAX_PR_TITLE))


def _resolve_build_text(
    body: DroidExecRequest,
    parsed_stdout: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """
    Pick ``(commit_message, pr_title, pr_body_seed)``.

    Order of precedence: runner-derived (from droid exec ``result`` JSON), then
    API-suggested fields on the request body, then a generic safe fallback.
    Every chosen string is sanitized + length-capped + redacted of forbidden
    internal markers.
    """
    droid_text = _droid_result_text(parsed_stdout)
    api_title = _redact_unsafe(_safe_one_line(body.pr_title or "", max_chars=_MAX_PR_TITLE))
    api_commit = _redact_unsafe(
        _safe_one_line(body.commit_message or "", max_chars=_MAX_COMMIT_MSG)
    )
    api_body_raw = _redact_unsafe((body.pr_body or "").strip())

    if droid_text:
        title = _safe_one_line(f"HAM Droid build: {droid_text}", max_chars=_MAX_PR_TITLE)
        commit = _safe_one_line(f"chore(droid-build): {droid_text}", max_chars=_MAX_COMMIT_MSG)
    else:
        title = api_title or _GENERIC_PR_TITLE
        commit = api_commit or _GENERIC_COMMIT_MSG

    if api_body_raw and len(api_body_raw) <= _MAX_PR_BODY:
        body_seed = api_body_raw
    elif droid_text:
        body_seed = f"Automated HAM Droid Build Lane change: {droid_text}"
    else:
        body_seed = "Automated HAM Droid Build Lane change."
    return commit, title, body_seed


def _compose_pr_body(
    *,
    body: DroidExecRequest,
    base_body: str,
    branch: str,
    runner_request_id: str,
) -> str:
    lines = [
        base_body.rstrip(),
        "",
        "## HAM Build Context",
        f"- HAM audit id: `{body.audit_id or 'unknown'}`",
        f"- Project id: `{body.project_id or 'unknown'}`",
        f"- Proposal digest: `{(body.proposal_digest or 'unknown')[:80]}`",
        f"- Branch: `{branch}`",
        f"- Runner request id: `{runner_request_id}`",
        "",
        (
            "This pull request was opened by the HAM Droid Build Lane. "
            "Review changes carefully before merging. No direct push to "
            "the default branch occurred."
        ),
    ]
    out = "\n".join(lines)
    if len(out) > _MAX_PR_BODY:
        out = out[: _MAX_PR_BODY - 1] + "…"
    return out


def _run_build_lane(
    *,
    body: DroidExecRequest,
    cwd_path: Path,
    record: DroidExecutionRecord,
    runner_request_id: str,
) -> BuildLaneResult:
    parsed = _parse_stdout_json(record.stdout)
    commit_msg, pr_title, body_seed = _resolve_build_text(body, parsed)
    branch = generate_branch_name()
    if not is_safe_branch_name(branch):  # pragma: no cover - defense in depth
        return BuildLaneResult(
            build_outcome="pr_failed",
            pr_url=None,
            pr_branch=None,
            pr_commit_sha=None,
            error_summary="generated unsafe branch name",
        )
    base_ref = _safe_one_line(body.base_ref or "", max_chars=200) or "origin/main"
    pr_body = _compose_pr_body(
        body=body,
        base_body=body_seed,
        branch=branch,
        runner_request_id=runner_request_id,
    )
    inputs = BuildLaneInputs(
        project_root=cwd_path,
        branch_name=branch,
        commit_message=commit_msg,
        pr_title=pr_title,
        pr_body=pr_body,
        base_ref=base_ref,
    )
    build_runner: SubprocessRunner = make_default_runner(
        cwd=cwd_path,
        timeout_sec=_BUILD_LANE_TIMEOUT_SEC,
    )
    return execute_build_lane_post_exec(inputs, runner=build_runner)


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
    build_outcome: str | None = None,
) -> None:
    row: dict[str, Any] = {
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
    if body.mode is not None:
        row["mode"] = body.mode
    if build_outcome is not None:
        row["build_outcome"] = build_outcome
    append_runner_audit_line(row)


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

    argv_mode: RequestMode | None = body.mode
    v_err = validate_remote_droid_argv(body.argv, expected_cwd=cwd_path, mode=argv_mode)
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

    if body.mode == "build" and not body.accept_pr:
        _audit_base(
            body=body,
            runner_request_id=runner_request_id,
            cwd_requested=body.cwd,
            cwd_normalized=str(cwd_path),
            status="blocked",
            blocked_code="BUILD_MODE_REQUIRES_ACCEPT_PR",
            blocked_reason="mode=build requires accept_pr=true",
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_MODE_REQUIRES_ACCEPT_PR",
                    "message": "Build mode requires accept_pr=true.",
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

    build_result: BuildLaneResult | None = None
    if body.mode == "build" and body.accept_pr and ok_exec:
        try:
            build_result = _run_build_lane(
                body=body,
                cwd_path=cwd_path,
                record=record,
                runner_request_id=runner_request_id,
            )
        except Exception as exc:  # noqa: BLE001 - last-ditch guard around subprocess pipeline.
            build_result = BuildLaneResult(
                build_outcome="pr_failed",
                pr_url=None,
                pr_branch=None,
                pr_commit_sha=None,
                error_summary=f"build lane crashed: {type(exc).__name__}",
            )

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
        build_outcome=build_result.build_outcome if build_result is not None else None,
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
    if build_result is not None:
        out["build_outcome"] = build_result.build_outcome
        out["pr_url"] = build_result.pr_url
        out["pr_branch"] = build_result.pr_branch
        out["pr_commit_sha"] = build_result.pr_commit_sha
        if build_result.error_summary:
            out["build_error_summary"] = build_result.error_summary
    return out


app = FastAPI(title="HAM Droid Runner", version="1")
app.include_router(router)
