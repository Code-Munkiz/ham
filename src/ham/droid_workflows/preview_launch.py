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
from src.integrations.droid_runner_client import RemoteRunnerError, run_droid_argv


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

    if wf.custom_droid_name and not custom_droid_exists(root, wf.custom_droid_name):
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
) -> str | None:
    if base_revision != REGISTRY_REVISION:
        return f"Stale droid_base_revision: expected {REGISTRY_REVISION!r}, got {base_revision!r}."
    wf = get_workflow(workflow_id)
    if wf is None:
        return f"Unknown workflow_id {workflow_id!r}."
    root = project_root.expanduser().resolve()
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
    if wf.custom_droid_name and not custom_droid_exists(root, wf.custom_droid_name):
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
) -> DroidLaunchResult:
    wf = get_workflow(workflow_id)
    if wf is None:
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
        )
    root = project_root.expanduser().resolve()
    focus = _sanitize_user_focus(user_prompt)
    try:
        argv = build_exec_argv(wf, root, focus)
    except ValueError as exc:
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
    )
