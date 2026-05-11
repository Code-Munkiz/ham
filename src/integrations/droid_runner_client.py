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

Build-lane variant: :func:`run_droid_build_argv` is the mutating counterpart used by
``/api/droid/build/launch``. It forces ``mode="build"`` and ``accept_pr=True`` on the
runner request and surfaces PR fields (``pr_url`` / ``pr_branch`` / ``pr_commit_sha`` /
``build_outcome``) returned by the runner's Build Lane post-exec step. The build path
requires a remote runner; local execution does not perform the post-exec git/gh step
and is rejected here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
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


def _post_runner_request(
    base_url: str,
    body: dict[str, Any],
    *,
    timeout_sec: int,
) -> dict[str, Any]:
    """POST one request to the remote runner and return the parsed JSON dict."""
    import urllib.error
    import urllib.request

    token = (os.environ.get("HAM_DROID_RUNNER_TOKEN") or "").strip()
    if not token:
        raise RemoteRunnerError(
            "HAM_DROID_RUNNER_URL is set but HAM_DROID_RUNNER_TOKEN is missing.",
            code="RUNNER_TOKEN_MISSING",
        )
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - URL validated by env-driven base_url
        f"{base_url}/v1/ham/droid-exec",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=min(timeout_sec + 30, 600)) as resp:  # noqa: S310 - URL validated by env-driven base_url
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RemoteRunnerError(
            f"Runner HTTP {exc.code}: {detail}",
            code="RUNNER_HTTP_ERROR",
        ) from exc
    except OSError as exc:
        raise RemoteRunnerError(str(exc), code="RUNNER_UNAVAILABLE") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RemoteRunnerError("Runner returned non-JSON body", code="RUNNER_BAD_RESPONSE") from exc
    if not isinstance(data, dict):
        raise RemoteRunnerError("Runner returned non-object JSON", code="RUNNER_BAD_RESPONSE")
    return data


def _execution_record_from_data(
    data: dict[str, Any],
    *,
    argv: list[str],
    cwd: Path,
) -> DroidExecutionRecord:
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
    data = _post_runner_request(base_url, body, timeout_sec=timeout_sec)
    return _execution_record_from_data(data, argv=argv, cwd=cwd)


@dataclass(frozen=True)
class RemoteDroidBuildResult:
    """
    Build-lane runner result.

    Wraps the underlying :class:`DroidExecutionRecord` from ``droid exec`` and
    surfaces the runner's Build Lane post-exec output. ``pr_url`` / ``pr_branch``
    / ``pr_commit_sha`` are populated only when the runner selected the
    ``github_pr`` adapter; for ``managed_workspace`` runs they remain ``None``
    and the snapshot/preview coordinates live under ``output_ref``. All
    optional fields default to ``None`` so a runner that did not reach the
    post-exec step (e.g. droid exec failed) still produces a well-formed
    record.

    The ``build_outcome`` value, when present, is one of the strings in
    ``src.persistence.control_plane_run.DROID_BUILD_OUTCOMES``; this module
    keeps it as a plain ``str`` to avoid a runtime dependency cycle between
    HAM persistence and the integrations seam. ``output_target`` mirrors
    :attr:`src.registry.projects.ProjectRecord.output_target` and is the
    primary signal for downstream readers (preview_launch, ControlPlaneRun,
    API response).
    """

    execution: DroidExecutionRecord
    pr_url: str | None
    pr_branch: str | None
    pr_commit_sha: str | None
    build_outcome: str | None
    build_error_summary: str | None
    runner_request_id: str | None
    output_target: str | None = None
    output_ref: dict[str, Any] | None = None


def run_droid_build_argv(
    argv: list[str],
    *,
    cwd: Path,
    timeout_sec: int,
    accept_pr: bool,
    workflow_id: str | None = None,
    audit_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    proposal_digest: str | None = None,
    base_ref: str | None = None,
    commit_message: str | None = None,
    pr_title: str | None = None,
    pr_body: str | None = None,
    output_target: str | None = None,
    workspace_id: str | None = None,
) -> RemoteDroidBuildResult:
    """
    Build-lane variant of :func:`run_droid_argv`.

    Always targets a remote runner (the post-exec git/gh step is meaningless
    locally). Forces ``mode="build"`` and forwards ``accept_pr`` plus optional
    branch/commit/PR-text overrides. The runner is the authority on the final
    branch name and PR text; the API may pass server-generated suggestions
    that the runner is free to override with droid output.

    Raises :class:`RemoteRunnerError` if ``HAM_DROID_RUNNER_URL`` is unset or
    if ``accept_pr`` is not explicitly true (defense in depth — the API gate
    is still the primary check).
    """
    if not accept_pr:
        raise RemoteRunnerError(
            "Build mode requires accept_pr=True (API gate must allow it).",
            code="BUILD_MODE_REQUIRES_ACCEPT_PR",
        )
    url = (os.environ.get("HAM_DROID_RUNNER_URL") or "").strip().rstrip("/")
    if not url:
        raise RemoteRunnerError(
            "HAM_DROID_RUNNER_URL is required for build mode; local execution is not supported.",
            code="RUNNER_URL_REQUIRED",
        )
    body: dict[str, Any] = {
        "argv": argv,
        "cwd": str(cwd.resolve()),
        "timeout_sec": timeout_sec,
        "mode": "build",
        "accept_pr": True,
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
    if base_ref is not None:
        body["base_ref"] = base_ref
    if commit_message is not None:
        body["commit_message"] = commit_message
    if pr_title is not None:
        body["pr_title"] = pr_title
    if pr_body is not None:
        body["pr_body"] = pr_body
    if output_target is not None:
        body["output_target"] = output_target
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    data = _post_runner_request(url, body, timeout_sec=timeout_sec)
    execution = _execution_record_from_data(data, argv=argv, cwd=cwd)
    rid = data.get("runner_request_id")
    raw_output_ref = data.get("output_ref")
    output_ref_val = raw_output_ref if isinstance(raw_output_ref, dict) else None
    return RemoteDroidBuildResult(
        execution=execution,
        pr_url=(data.get("pr_url") or None),
        pr_branch=(data.get("pr_branch") or None),
        pr_commit_sha=(data.get("pr_commit_sha") or None),
        build_outcome=(data.get("build_outcome") or None),
        build_error_summary=(data.get("build_error_summary") or None),
        runner_request_id=str(rid) if rid is not None else None,
        output_target=(data.get("output_target") or None),
        output_ref=output_ref_val,
    )
