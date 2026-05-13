"""Preview, launch, verify, and audit for allowlisted Droid workflows."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ham.droid_workflows.registry import (
    REGISTRY_REVISION,
    DroidWorkflowDefinition,
    get_workflow,
    list_workflow_ids,
)
from src.ham.managed_workspace.paths import ham_managed_workspace_root
from src.integrations.droid_runner_client import (
    RemoteRunnerError,
    run_droid_argv,
    run_droid_build_argv,
)
from src.persistence.control_plane_run import (
    DROID_BUILD_OUTCOMES,
    ControlPlaneAuditRef,
    ControlPlaneProviderAuditRef,
    ControlPlaneRun,
    ControlPlaneRunStore,
    DroidBuildOutcome,
    cap_error_summary,
    cap_summary,
    droid_build_outcome_to_ham_status,
    droid_outcome_to_ham_status,
    new_ham_run_id,
    utc_now_iso,
)


@dataclass(frozen=True)
class DroidPreviewResult:
    ok: bool
    blocking_reason: str | None
    workflow_id: str | None
    project_id: str | None
    cwd: str | None
    tier: str | None
    mutates: bool | None
    proposal_digest: str | None
    base_revision: str | None
    runner_id: str | None
    summary_preview: str | None
    user_prompt: str | None


@dataclass(frozen=True)
class DroidLaunchResult:
    ok: bool
    blocking_reason: str | None
    workflow_id: str | None
    audit_id: str | None
    runner_id: str | None
    cwd: str | None
    exit_code: int | None
    duration_ms: int | None
    summary: str | None
    stdout: str | None
    stderr: str | None
    stdout_truncated: bool
    stderr_truncated: bool
    parsed_json: dict[str, Any] | None
    session_id: str | None
    timed_out: bool
    ham_run_id: str | None = None
    control_plane_status: str | None = None


def _runner_id() -> str:
    from src.integrations import droid_runner_client as dr

    return dr.resolve_runner_id()


def _sanitize_user_focus(text: str) -> str:
    t = text.strip()
    if len(t) > 12_000:
        t = t[:12_000]
    # strip control chars that could confuse argv / logs
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    return t


def custom_droid_markdown_path(project_root: Path, name: str) -> Path:
    slug = name.strip().lower().replace(" ", "-")
    return (project_root / ".factory" / "droids" / f"{slug}.md").resolve()


def custom_droid_exists(project_root: Path, name: str) -> bool:
    p = custom_droid_markdown_path(project_root, name)
    try:
        p.relative_to(project_root.resolve())
    except ValueError:
        return False
    return p.is_file()


def _managed_workspace_root_blocker(root: Path) -> str | None:
    """For ``output_target=managed_workspace`` runs the cwd lives on the runner,
    not on this ham-api pod, so ``is_dir()`` is meaningless here. Instead we
    enforce that the resolved path is exactly one ``managed/<wid>/<pid>/working``
    leaf under ``HAM_MANAGED_WORKSPACE_ROOT``. The strict cwd allow-list +
    ``MANAGED_WORKSPACE_CWD_MISMATCH`` check on the runner remain authoritative.
    """
    try:
        resolved = root.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return "Invalid managed-workspace project root."
    try:
        managed_prefix = (ham_managed_workspace_root() / "managed").resolve(strict=False)
    except (OSError, RuntimeError):
        return "Invalid HAM_MANAGED_WORKSPACE_ROOT."
    try:
        rel = resolved.relative_to(managed_prefix)
    except ValueError:
        return (
            "Managed-workspace project root is not under "
            f"{managed_prefix}. Got: {resolved}"
        )
    parts = rel.parts
    if len(parts) != 3 or parts[-1] != "working":
        return (
            "Managed-workspace project root must end with "
            "'<workspace_id>/<project_id>/working'."
        )
    return None


def build_exec_argv(wf: DroidWorkflowDefinition, cwd: Path, user_focus: str) -> list[str]:
    if "{user_focus}" not in wf.prompt_template:
        raise ValueError("prompt_template must include {user_focus}")
    focus = _sanitize_user_focus(user_focus)
    if not focus:
        raise ValueError("user_focus must not be empty")
    prompt = wf.prompt_template.format(user_focus=focus)
    if wf.custom_droid_name:
        dn = wf.custom_droid_name.strip()
        prompt = (
            f"Use the Factory Custom Droid subagent `{dn}` via the Task tool where appropriate.\n\n"
            f"{prompt}"
        )
    argv: list[str] = [
        "droid",
        "exec",
        "--cwd",
        str(cwd.resolve()),
        "--output-format",
        wf.output_format,
    ]
    if wf.auto_level:
        argv.extend(["--auto", wf.auto_level])
    for tool in wf.disabled_tools:
        argv.extend(["--disabled-tools", tool])
    if "--skip-permissions-unsafe" in argv:
        raise RuntimeError("forbidden flag in argv")
    argv.append(prompt)
    return argv


def compute_proposal_digest(
    *,
    workflow_id: str,
    project_id: str,
    cwd: str,
    user_prompt: str,
) -> str:
    canonical = {
        "registry_revision": REGISTRY_REVISION,
        "workflow_id": workflow_id,
        "project_id": project_id,
        "cwd": cwd,
        "user_prompt": user_prompt,
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_droid_preview(
    *,
    workflow_id: str,
    project_id: str,
    project_root: Path,
    user_prompt: str,
    output_target: str = "github_pr",
) -> DroidPreviewResult:
    wf = get_workflow(workflow_id)
    if wf is None:
        return DroidPreviewResult(
            ok=False,
            blocking_reason=f"Unknown workflow_id {workflow_id!r}. Allowlisted: {list_workflow_ids()}.",
            workflow_id=None,
            project_id=project_id,
            cwd=None,
            tier=None,
            mutates=None,
            proposal_digest=None,
            base_revision=None,
            runner_id=None,
            summary_preview=None,
            user_prompt=None,
        )
    root = project_root.expanduser().resolve()
    target = (output_target or "").strip()
    if target == "managed_workspace":
        managed_blocker = _managed_workspace_root_blocker(root)
        if managed_blocker is not None:
            return DroidPreviewResult(
                ok=False,
                blocking_reason=managed_blocker,
                workflow_id=workflow_id,
                project_id=project_id,
                cwd=None,
                tier=wf.tier,
                mutates=wf.mutates,
                proposal_digest=None,
                base_revision=None,
                runner_id=_runner_id(),
                summary_preview=None,
                user_prompt=None,
            )
    else:
        if not root.is_dir():
            return DroidPreviewResult(
                ok=False,
                blocking_reason=f"Project root is not a directory: {root}",
                workflow_id=workflow_id,
                project_id=project_id,
                cwd=None,
                tier=wf.tier,
                mutates=wf.mutates,
                proposal_digest=None,
                base_revision=None,
                runner_id=_runner_id(),
                summary_preview=None,
                user_prompt=None,
            )

    focus = _sanitize_user_focus(user_prompt)
    if not focus:
        return DroidPreviewResult(
            ok=False,
            blocking_reason="user_prompt is empty after sanitization.",
            workflow_id=workflow_id,
            project_id=project_id,
            cwd=str(root),
            tier=wf.tier,
            mutates=wf.mutates,
            proposal_digest=None,
            base_revision=None,
            runner_id=_runner_id(),
            summary_preview=None,
            user_prompt=None,
        )

    if (
        target != "managed_workspace"
        and wf.custom_droid_name
        and not custom_droid_exists(root, wf.custom_droid_name)
    ):
        return DroidPreviewResult(
            ok=False,
            blocking_reason=(
                f"Custom Droid `{wf.custom_droid_name}` is required but missing under "
                f"`.factory/droids/` for this project."
            ),
            workflow_id=workflow_id,
            project_id=project_id,
            cwd=str(root),
            tier=wf.tier,
            mutates=wf.mutates,
            proposal_digest=None,
            base_revision=None,
            runner_id=_runner_id(),
            summary_preview=None,
            user_prompt=focus,
        )

    try:
        argv = build_exec_argv(wf, root, focus)
    except ValueError as exc:
        return DroidPreviewResult(
            ok=False,
            blocking_reason=str(exc),
            workflow_id=workflow_id,
            project_id=project_id,
            cwd=str(root),
            tier=wf.tier,
            mutates=wf.mutates,
            proposal_digest=None,
            base_revision=None,
            runner_id=_runner_id(),
            summary_preview=None,
            user_prompt=focus,
        )

    digest = compute_proposal_digest(
        workflow_id=wf.workflow_id,
        project_id=project_id,
        cwd=str(root),
        user_prompt=focus,
    )
    mut_warn = (
        "**This workflow mutates the repository** (`--auto low`). "
        "Launch requires confirmation and `HAM_DROID_EXEC_TOKEN`."
        if wf.mutates
        else "**Read-only** — no `--auto`; no launch token required."
    )
    summary = (
        f"Workflow **`{wf.workflow_id}`** ({wf.tier}): {wf.description}\n\n"
        f"{mut_warn}\n\n"
        f"- **cwd:** `{root}`\n"
        f"- **registry:** `{REGISTRY_REVISION}`\n"
        f"- **runner:** `{_runner_id()}`\n"
        f"- **argv head:** `{' '.join(argv[:6])} …` (full prompt not logged)\n"
    )
    return DroidPreviewResult(
        ok=True,
        blocking_reason=None,
        workflow_id=wf.workflow_id,
        project_id=project_id,
        cwd=str(root),
        tier=wf.tier,
        mutates=wf.mutates,
        proposal_digest=digest,
        base_revision=REGISTRY_REVISION,
        runner_id=_runner_id(),
        summary_preview=summary,
        user_prompt=focus,
    )


def verify_launch_against_preview(
    *,
    workflow_id: str,
    project_id: str,
    project_root: Path,
    user_prompt: str,
    proposal_digest: str,
    base_revision: str,
    output_target: str = "github_pr",
) -> str | None:
    if base_revision != REGISTRY_REVISION:
        return f"Stale droid_base_revision: expected {REGISTRY_REVISION!r}, got {base_revision!r}."
    wf = get_workflow(workflow_id)
    if wf is None:
        return f"Unknown workflow_id {workflow_id!r}."
    root = project_root.expanduser().resolve()
    target = (output_target or "").strip()
    if target == "managed_workspace":
        managed_blocker = _managed_workspace_root_blocker(root)
        if managed_blocker is not None:
            return managed_blocker
    else:
        if not root.is_dir():
            return f"Invalid project root: {root}"
    focus = _sanitize_user_focus(user_prompt)
    expected = compute_proposal_digest(
        workflow_id=workflow_id,
        project_id=project_id,
        cwd=str(root),
        user_prompt=focus,
    )
    if expected != proposal_digest.strip():
        return "proposal_digest mismatch — re-run preview before launch."
    if (
        target != "managed_workspace"
        and wf.custom_droid_name
        and not custom_droid_exists(root, wf.custom_droid_name)
    ):
        return f"Custom Droid `{wf.custom_droid_name}` missing under `.factory/droids/`."
    return None


def parse_droid_json_stdout(stdout: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Parse Factory droid exec JSON line; return (parsed, result_text, session_id)."""
    text = (stdout or "").strip()
    if not text:
        return None, None, None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None
    result = data.get("result")
    result_str = str(result) if result is not None else None
    sid = data.get("session_id")
    session_id = str(sid) if sid is not None else None
    return data, result_str, session_id


def _droid_control_plane_audit_ref(project_root: Path) -> ControlPlaneAuditRef:
    return ControlPlaneAuditRef(
        provider_audit=ControlPlaneProviderAuditRef(
            sink="droid_jsonl",
            path=str((project_root / ".ham" / "_audit" / "droid_exec.jsonl").resolve()),
        ),
    )


def _persist_droid_control_plane_run(
    store: ControlPlaneRunStore,
    *,
    project_id: str,
    workflow_id: str,
    proposal_digest: str,
    project_root: Path,
    created_by: dict[str, Any] | None,
    status: str,
    status_reason: str,
    summary: str | None,
    error_summary: str | None,
    session_id: str | None,
) -> str:
    now = utc_now_iso()
    rid = new_ham_run_id()
    prs = str(project_root.resolve())
    run = ControlPlaneRun(
        ham_run_id=rid,
        provider="factory_droid",
        action_kind="launch",
        project_id=project_id,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status=status,
        status_reason=status_reason,
        proposal_digest=proposal_digest,
        base_revision=REGISTRY_REVISION,
        external_id=session_id,
        workflow_id=workflow_id,
        summary=cap_summary(summary),
        error_summary=cap_error_summary(error_summary),
        last_provider_status=None,
        audit_ref=_droid_control_plane_audit_ref(project_root),
        project_root=prs,
    )
    store.save(run, project_root_for_mirror=prs)
    return rid


def append_droid_audit(project_root: Path, record: dict[str, Any]) -> str:
    audit_dir = project_root / ".ham" / "_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "droid_exec.jsonl"
    aid = str(record.get("audit_id") or uuid.uuid4())
    row = {**record, "audit_id": aid, "logged_at": datetime.now(UTC).isoformat()}
    line = json.dumps(row, ensure_ascii=False) + "\n"
    path.open("a", encoding="utf-8").write(line)
    return aid


def execute_droid_workflow(
    *,
    workflow_id: str,
    project_root: Path,
    user_prompt: str,
    project_id: str | None = None,
    proposal_digest: str | None = None,
    created_by: dict[str, Any] | None = None,
    control_plane_run_store: ControlPlaneRunStore | None = None,
) -> DroidLaunchResult:
    st = control_plane_run_store or ControlPlaneRunStore()
    digest_key = (proposal_digest or "").strip() or ("0" * 64)
    pid_s = (project_id or "").strip()

    wf = get_workflow(workflow_id)
    if wf is None:
        hid: str | None = None
        if pid_s:
            pr0 = project_root.expanduser().resolve()
            hid = _persist_droid_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=pr0,
                created_by=created_by,
                status="failed",
                status_reason="unknown_workflow",
                summary=None,
                error_summary=f"Unknown workflow_id {workflow_id!r}",
                session_id=None,
            )
        return DroidLaunchResult(
            ok=False,
            blocking_reason=f"Unknown workflow_id {workflow_id!r}",
            workflow_id=workflow_id,
            audit_id=None,
            runner_id=_runner_id(),
            cwd=None,
            exit_code=None,
            duration_ms=None,
            summary=None,
            stdout=None,
            stderr=None,
            stdout_truncated=False,
            stderr_truncated=False,
            parsed_json=None,
            session_id=None,
            timed_out=False,
            ham_run_id=hid,
            control_plane_status="failed" if hid else None,
        )
    root = project_root.expanduser().resolve()
    focus = _sanitize_user_focus(user_prompt)
    try:
        argv = build_exec_argv(wf, root, focus)
    except ValueError as exc:
        hid_ve: str | None = None
        if pid_s:
            hid_ve = _persist_droid_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=root,
                created_by=created_by,
                status="failed",
                status_reason="argv_build_error",
                summary=None,
                error_summary=str(exc),
                session_id=None,
            )
        return DroidLaunchResult(
            ok=False,
            blocking_reason=str(exc),
            workflow_id=workflow_id,
            audit_id=None,
            runner_id=_runner_id(),
            cwd=str(root),
            exit_code=None,
            duration_ms=None,
            summary=None,
            stdout=None,
            stderr=None,
            stdout_truncated=False,
            stderr_truncated=False,
            parsed_json=None,
            session_id=None,
            timed_out=False,
            ham_run_id=hid_ve,
            control_plane_status="failed" if hid_ve else None,
        )

    ham_audit_id = str(uuid.uuid4())
    try:
        rec = run_droid_argv(
            argv,
            cwd=root,
            timeout_sec=wf.timeout_seconds,
            workflow_id=workflow_id,
            audit_id=ham_audit_id,
            project_id=project_id,
            proposal_digest=proposal_digest,
        )
    except RemoteRunnerError as exc:
        audit_payload = {
            "workflow_id": workflow_id,
            "runner_id": _runner_id(),
            "cwd": str(root),
            "exit_code": None,
            "duration_ms": None,
            "timed_out": False,
            "summary": str(exc),
            "stdout": "",
            "stderr": str(exc),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "parsed_json": None,
            "session_id": None,
            "ok": False,
            "runner_error_code": getattr(exc, "code", None),
            "audit_id": ham_audit_id,
            "project_id": project_id,
            "proposal_digest": proposal_digest,
        }
        audit_id = append_droid_audit(root, audit_payload)
        hid_re: str | None = None
        if pid_s:
            hid_re = _persist_droid_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=root,
                created_by=created_by,
                status="failed",
                status_reason="remote_runner",
                summary=None,
                error_summary=str(exc),
                session_id=None,
            )
        return DroidLaunchResult(
            ok=False,
            blocking_reason=str(exc),
            workflow_id=workflow_id,
            audit_id=audit_id,
            runner_id=_runner_id(),
            cwd=str(root),
            exit_code=None,
            duration_ms=None,
            summary=str(exc),
            stdout="",
            stderr=str(exc),
            stdout_truncated=False,
            stderr_truncated=False,
            parsed_json=None,
            session_id=None,
            timed_out=False,
            ham_run_id=hid_re,
            control_plane_status="failed" if hid_re else None,
        )
    parsed, result_text, session_id = parse_droid_json_stdout(rec.stdout)
    ok_exec = not rec.timed_out and rec.exit_code == 0
    summary = result_text
    if summary is None and rec.stderr:
        summary = rec.stderr[:500]
    if summary is None and rec.stdout:
        summary = rec.stdout[:500]

    audit_payload = {
        "workflow_id": workflow_id,
        "runner_id": _runner_id(),
        "cwd": str(root),
        "exit_code": rec.exit_code,
        "duration_ms": rec.duration_ms,
        "timed_out": rec.timed_out,
        "summary": summary,
        "stdout": rec.stdout,
        "stderr": rec.stderr,
        "stdout_truncated": rec.stdout_truncated,
        "stderr_truncated": rec.stderr_truncated,
        "parsed_json": parsed,
        "session_id": session_id,
        "ok": ok_exec,
        "audit_id": ham_audit_id,
        "project_id": project_id,
        "proposal_digest": proposal_digest,
    }
    audit_id = append_droid_audit(root, audit_payload)

    blocking = None
    if rec.timed_out:
        blocking = "droid exec timed out"
    elif rec.exit_code != 0:
        blocking = f"droid exec failed (exit {rec.exit_code})"
    elif not ok_exec:
        blocking = "droid exec did not succeed"

    hst, hsr = droid_outcome_to_ham_status(
        ok=ok_exec,
        timed_out=rec.timed_out,
        exit_code=rec.exit_code,
        had_runner_body=True,
    )
    hid_f: str | None = None
    if pid_s:
        err_end = cap_error_summary(blocking) if not ok_exec and blocking else None
        hid_f = _persist_droid_control_plane_run(
            st,
            project_id=pid_s,
            workflow_id=workflow_id,
            proposal_digest=digest_key,
            project_root=root,
            created_by=created_by,
            status=hst,
            status_reason=hsr,
            summary=summary,
            error_summary=err_end,
            session_id=session_id,
        )

    return DroidLaunchResult(
        ok=ok_exec,
        blocking_reason=blocking,
        workflow_id=workflow_id,
        audit_id=audit_id,
        runner_id=_runner_id(),
        cwd=str(root),
        exit_code=rec.exit_code,
        duration_ms=rec.duration_ms,
        summary=summary,
        stdout=rec.stdout,
        stderr=rec.stderr,
        stdout_truncated=rec.stdout_truncated,
        stderr_truncated=rec.stderr_truncated,
        parsed_json=parsed,
        session_id=session_id,
        timed_out=rec.timed_out,
        ham_run_id=hid_f,
        control_plane_status=hst if hid_f else None,
    )


# ---------------------------------------------------------------------------
# Build-lane execution path (mutating; dark/gated; called only by the
# Build router after every API gate passes and HAM_DROID_EXEC_TOKEN is set).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DroidBuildExecutionResult:
    """Build-lane execution outcome (droid exec + runner Build Lane post-exec).

    ``output_target`` and ``output_ref`` are the target-neutral fields
    introduced in PR-A; ``pr_*`` are retained for backward compatibility and
    are populated only when ``output_target == "github_pr"``.
    """

    ok: bool
    blocking_reason: str | None
    workflow_id: str
    audit_id: str | None
    runner_id: str | None
    cwd: str | None
    exit_code: int | None
    duration_ms: int | None
    summary: str | None
    timed_out: bool
    ham_run_id: str | None
    control_plane_status: str | None
    pr_url: str | None
    pr_branch: str | None
    pr_commit_sha: str | None
    build_outcome: DroidBuildOutcome | None
    build_error_summary: str | None
    output_target: str | None = None
    output_ref: dict[str, Any] | None = None


def _coerce_build_outcome(value: object) -> DroidBuildOutcome | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in DROID_BUILD_OUTCOMES:
        return s  # type: ignore[return-value]
    return None


def _decide_build_status(
    *,
    target: str,
    ok_exec: bool,
    timed_out: bool,
    exit_code: int | None,
    build_outcome: DroidBuildOutcome | None,
    build_err: str | None,
    output_ref: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Compute ``(build_ok, blocking_reason)`` for a build-lane run.

    A build is ``ok`` only when the adapter reported a terminal success state
    for its target. ``github_pr`` success = ``pr_opened`` / ``nothing_to_change``.
    ``managed_workspace`` success = runner ``output_ref["neutral_outcome"]`` is
    ``succeeded`` or ``nothing_to_change`` after droid succeeds.
    """
    if timed_out:
        return False, "droid exec timed out"
    if exit_code != 0:
        return False, f"droid exec failed (exit {exit_code})"
    if not ok_exec:
        return False, "droid exec did not succeed"
    if target == "managed_workspace":
        ref = dict(output_ref or {})
        neo = str(ref.get("neutral_outcome") or "").strip()
        if neo in {"succeeded", "nothing_to_change"}:
            return True, None
        return False, (build_err or "managed workspace snapshot failed")
    if target != "github_pr":
        return False, (build_err or "unknown output_target")
    if build_outcome is None:
        return False, (build_err or "runner did not report a build outcome")
    if build_outcome not in {"pr_opened", "nothing_to_change"}:
        return False, (build_err or f"build lane outcome: {build_outcome}")
    return True, None


def _persist_droid_build_control_plane_run(
    store: ControlPlaneRunStore,
    *,
    project_id: str,
    workflow_id: str,
    proposal_digest: str,
    project_root: Path,
    created_by: dict[str, Any] | None,
    status: str,
    status_reason: str,
    summary: str | None,
    error_summary: str | None,
    session_id: str | None,
    pr_url: str | None,
    pr_branch: str | None,
    pr_commit_sha: str | None,
    build_outcome: DroidBuildOutcome | None,
    output_target: str | None = None,
    output_ref: dict[str, Any] | None = None,
) -> str:
    now = utc_now_iso()
    rid = new_ham_run_id()
    prs = str(project_root.resolve())
    run = ControlPlaneRun(
        ham_run_id=rid,
        provider="factory_droid",
        action_kind="launch",
        project_id=project_id,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=now,
        last_observed_at=now,
        status=status,
        status_reason=status_reason,
        proposal_digest=proposal_digest,
        base_revision=REGISTRY_REVISION,
        external_id=session_id,
        workflow_id=workflow_id,
        summary=cap_summary(summary),
        error_summary=cap_error_summary(error_summary),
        last_provider_status=None,
        audit_ref=_droid_control_plane_audit_ref(project_root),
        project_root=prs,
        pr_url=pr_url,
        pr_branch=pr_branch,
        pr_commit_sha=pr_commit_sha,
        build_outcome=build_outcome,
        output_target=output_target,
        output_ref=output_ref,
    )
    store.save(run, project_root_for_mirror=prs)
    return rid


def execute_droid_build_workflow_remote(
    *,
    workflow_id: str,
    project_root: Path,
    user_prompt: str,
    project_id: str,
    proposal_digest: str,
    created_by: dict[str, Any] | None = None,
    control_plane_run_store: ControlPlaneRunStore | None = None,
    output_target: str = "github_pr",
    workspace_id: str | None = None,
) -> DroidBuildExecutionResult:
    """
    Run the build workflow against a remote runner with ``mode="build"``.

    The runner is responsible for the post-droid commit / push / ``gh pr create``
    step (``execute_build_lane_post_exec``); this function only forwards the
    request, persists ``ControlPlaneRun`` with PR fields, and writes a HAM-side
    audit row. ``run_droid_build_argv`` already requires ``accept_pr=True``
    (defense in depth — the API gate is still the primary check).

    Never invoked from chat or the audit lane: the only caller is
    :func:`src.api.droid_build.execute_droid_build_workflow`.
    """
    st = control_plane_run_store or ControlPlaneRunStore()
    digest_key = (proposal_digest or "").strip() or ("0" * 64)
    pid_s = (project_id or "").strip()

    wf = get_workflow(workflow_id)
    if wf is None or not wf.mutates or not wf.requires_launch_token:
        hid: str | None = None
        if pid_s:
            pr0 = project_root.expanduser().resolve()
            hid = _persist_droid_build_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=pr0,
                created_by=created_by,
                status="failed",
                status_reason="droid_build:workflow_missing_or_misconfigured",
                summary=None,
                error_summary=f"Unknown or non-mutating workflow_id {workflow_id!r}",
                session_id=None,
                pr_url=None,
                pr_branch=None,
                pr_commit_sha=None,
                build_outcome=None,
                output_target=output_target,
                output_ref=None,
            )
        return DroidBuildExecutionResult(
            ok=False,
            blocking_reason=f"Unknown or non-mutating workflow_id {workflow_id!r}",
            workflow_id=workflow_id,
            audit_id=None,
            runner_id=_runner_id(),
            cwd=None,
            exit_code=None,
            duration_ms=None,
            summary=None,
            timed_out=False,
            ham_run_id=hid,
            control_plane_status="failed" if hid else None,
            pr_url=None,
            pr_branch=None,
            pr_commit_sha=None,
            build_outcome=None,
            build_error_summary=None,
            output_target=output_target,
            output_ref=None,
        )

    root = project_root.expanduser().resolve()
    focus = _sanitize_user_focus(user_prompt)
    try:
        argv = build_exec_argv(wf, root, focus)
    except ValueError as exc:
        hid_ve: str | None = None
        if pid_s:
            hid_ve = _persist_droid_build_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=root,
                created_by=created_by,
                status="failed",
                status_reason="droid_build:argv_build_error",
                summary=None,
                error_summary=str(exc),
                session_id=None,
                pr_url=None,
                pr_branch=None,
                pr_commit_sha=None,
                build_outcome=None,
                output_target=output_target,
                output_ref=None,
            )
        return DroidBuildExecutionResult(
            ok=False,
            blocking_reason=str(exc),
            workflow_id=workflow_id,
            audit_id=None,
            runner_id=_runner_id(),
            cwd=str(root),
            exit_code=None,
            duration_ms=None,
            summary=None,
            timed_out=False,
            ham_run_id=hid_ve,
            control_plane_status="failed" if hid_ve else None,
            pr_url=None,
            pr_branch=None,
            pr_commit_sha=None,
            build_outcome=None,
            build_error_summary=None,
            output_target=output_target,
            output_ref=None,
        )

    ham_audit_id = str(uuid.uuid4())
    # ``accept_pr`` is meaningful only for the github_pr adapter; the runner
    # ignores it for managed_workspace (PR-A stub). We still pass ``True`` so
    # the client-side defense-in-depth check in :func:`run_droid_build_argv`
    # is satisfied uniformly.
    try:
        remote = run_droid_build_argv(
            argv,
            cwd=root,
            timeout_sec=wf.timeout_seconds,
            accept_pr=True,
            workflow_id=workflow_id,
            audit_id=ham_audit_id,
            project_id=project_id,
            proposal_digest=proposal_digest,
            output_target=output_target,
            workspace_id=workspace_id,
        )
    except RemoteRunnerError as exc:
        audit_payload = {
            "workflow_id": workflow_id,
            "runner_id": _runner_id(),
            "cwd": str(root),
            "exit_code": None,
            "duration_ms": None,
            "timed_out": False,
            "summary": str(exc),
            "stdout": "",
            "stderr": str(exc),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "parsed_json": None,
            "session_id": None,
            "ok": False,
            "runner_error_code": getattr(exc, "code", None),
            "audit_id": ham_audit_id,
            "project_id": project_id,
            "proposal_digest": proposal_digest,
            "mode": "build",
        }
        audit_id_re = append_droid_audit(root, audit_payload)
        hid_re: str | None = None
        if pid_s:
            hid_re = _persist_droid_build_control_plane_run(
                st,
                project_id=pid_s,
                workflow_id=workflow_id,
                proposal_digest=digest_key,
                project_root=root,
                created_by=created_by,
                status="failed",
                status_reason="droid_build:remote_runner",
                summary=None,
                error_summary=str(exc),
                session_id=None,
                pr_url=None,
                pr_branch=None,
                pr_commit_sha=None,
                build_outcome=None,
                output_target=output_target,
                output_ref=None,
            )
        return DroidBuildExecutionResult(
            ok=False,
            blocking_reason=str(exc),
            workflow_id=workflow_id,
            audit_id=audit_id_re,
            runner_id=_runner_id(),
            cwd=str(root),
            exit_code=None,
            duration_ms=None,
            summary=str(exc),
            timed_out=False,
            ham_run_id=hid_re,
            control_plane_status="failed" if hid_re else None,
            pr_url=None,
            pr_branch=None,
            pr_commit_sha=None,
            build_outcome=None,
            build_error_summary=str(exc),
            output_target=output_target,
            output_ref=None,
        )

    rec = remote.execution
    parsed, result_text, session_id = parse_droid_json_stdout(rec.stdout)
    ok_exec = not rec.timed_out and rec.exit_code == 0
    summary = result_text
    if summary is None and rec.stderr:
        summary = rec.stderr[:500]
    if summary is None and rec.stdout:
        summary = rec.stdout[:500]

    build_outcome = _coerce_build_outcome(remote.build_outcome)
    pr_url = remote.pr_url
    pr_branch = remote.pr_branch
    pr_commit_sha = remote.pr_commit_sha
    build_err = remote.build_error_summary
    resolved_output_target = (remote.output_target or output_target or "github_pr").strip()
    resolved_output_ref = remote.output_ref or {}

    build_ok, blocking = _decide_build_status(
        target=resolved_output_target,
        ok_exec=ok_exec,
        timed_out=rec.timed_out,
        exit_code=rec.exit_code,
        build_outcome=build_outcome,
        build_err=build_err,
        output_ref=resolved_output_ref,
    )

    audit_payload = {
        "workflow_id": workflow_id,
        "runner_id": _runner_id(),
        "cwd": str(root),
        "exit_code": rec.exit_code,
        "duration_ms": rec.duration_ms,
        "timed_out": rec.timed_out,
        "summary": summary,
        "stdout": rec.stdout,
        "stderr": rec.stderr,
        "stdout_truncated": rec.stdout_truncated,
        "stderr_truncated": rec.stderr_truncated,
        "parsed_json": parsed,
        "session_id": session_id,
        "ok": build_ok,
        "audit_id": ham_audit_id,
        "project_id": project_id,
        "proposal_digest": proposal_digest,
        "mode": "build",
        "build_outcome": build_outcome,
        "pr_url": pr_url,
        "pr_branch": pr_branch,
        "pr_commit_sha": pr_commit_sha,
        "output_target": resolved_output_target,
        "output_ref": resolved_output_ref,
    }
    audit_id_f = append_droid_audit(root, audit_payload)

    hst, hsr = droid_build_outcome_to_ham_status(
        outcome=build_outcome,
        ok=ok_exec,
        timed_out=rec.timed_out,
        exit_code=rec.exit_code,
        had_runner_body=True,
    )
    hid_f: str | None = None
    if pid_s:
        err_end = cap_error_summary(blocking) if not build_ok and blocking else None
        hid_f = _persist_droid_build_control_plane_run(
            st,
            project_id=pid_s,
            workflow_id=workflow_id,
            proposal_digest=digest_key,
            project_root=root,
            created_by=created_by,
            status=hst,
            status_reason=hsr,
            summary=summary,
            error_summary=err_end,
            session_id=session_id,
            pr_url=pr_url,
            pr_branch=pr_branch,
            pr_commit_sha=pr_commit_sha,
            build_outcome=build_outcome,
            output_target=resolved_output_target,
            output_ref=resolved_output_ref or None,
        )

    return DroidBuildExecutionResult(
        ok=build_ok,
        blocking_reason=blocking,
        workflow_id=workflow_id,
        audit_id=audit_id_f,
        runner_id=_runner_id(),
        cwd=str(root),
        exit_code=rec.exit_code,
        duration_ms=rec.duration_ms,
        summary=summary,
        timed_out=rec.timed_out,
        ham_run_id=hid_f,
        control_plane_status=hst if hid_f else None,
        pr_url=pr_url,
        pr_branch=pr_branch,
        pr_commit_sha=pr_commit_sha,
        build_outcome=build_outcome,
        build_error_summary=build_err,
        output_target=resolved_output_target,
        output_ref=resolved_output_ref or None,
    )
