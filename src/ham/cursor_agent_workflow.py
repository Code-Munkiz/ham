"""HAM policy layer for Cursor Cloud Agents: preview digest, verify, summarize, audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.integrations.cursor_cloud_client import (
    CursorCloudApiError,
    cursor_api_get_agent,
    cursor_api_launch_agent,
)
from src.persistence.control_plane_run import (
    ControlPlaneAuditRef,
    ControlPlaneProviderAuditRef,
    ControlPlaneRun,
    ControlPlaneRunStore,
    cap_error_summary,
    cap_last_provider_status,
    cap_summary,
    map_cursor_raw_status,
    new_ham_run_id,
    utc_now_iso,
)
from src.persistence.cursor_credentials import get_effective_cursor_api_key

CURSOR_AGENT_BASE_REVISION = "cursor-agent-v1"

_METADATA_REPO_KEY = "cursor_cloud_repository"


def central_audit_file_path() -> Path:
    override = (os.environ.get("HAM_CURSOR_AGENT_AUDIT_FILE") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ham" / "_audit" / "cursor_cloud_agent.jsonl"


def resolve_cursor_repository_url(
    *,
    explicit: str | None,
    project_metadata: dict[str, Any],
) -> str | None:
    """
    Resolve GitHub repo URL in order:
    1. explicit ``cursor_repository`` from operator
    2. ``ProjectRecord.metadata["cursor_cloud_repository"]``
    3. ``HAM_CURSOR_DEFAULT_REPOSITORY`` env (demo fallback only)
    """
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    raw = project_metadata.get(_METADATA_REPO_KEY)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    env = (os.environ.get("HAM_CURSOR_DEFAULT_REPOSITORY") or "").strip()
    return env or None


def compose_prompt_for_cursor(*, task_prompt: str, expected_deliverable: str | None) -> str:
    task = (task_prompt or "").strip()
    deliv = (expected_deliverable or "").strip()
    if not deliv:
        return task
    return f"{task}\n\n**Expected deliverable:** {deliv}"


def compute_cursor_proposal_digest(
    *,
    project_id: str,
    repository: str,
    ref: str | None,
    model: str,
    auto_create_pr: bool,
    branch_name: str | None,
    expected_deliverable: str | None,
    task_prompt: str,
) -> str:
    canonical = {
        "base_revision": CURSOR_AGENT_BASE_REVISION,
        "project_id": project_id.strip(),
        "repository": repository.strip(),
        "ref": (ref or "").strip(),
        "model": (model or "default").strip(),
        "auto_create_pr": bool(auto_create_pr),
        "branch_name": (branch_name or "").strip(),
        "expected_deliverable": (expected_deliverable or "").strip(),
        "task_prompt": (task_prompt or "").strip(),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_cursor_launch_against_preview(
    *,
    project_id: str,
    repository: str,
    ref: str | None,
    model: str,
    auto_create_pr: bool,
    branch_name: str | None,
    expected_deliverable: str | None,
    task_prompt: str,
    proposal_digest: str,
    base_revision: str,
) -> str | None:
    if base_revision != CURSOR_AGENT_BASE_REVISION:
        return f"Stale cursor_base_revision: expected {CURSOR_AGENT_BASE_REVISION!r}, got {base_revision!r}."
    expected = compute_cursor_proposal_digest(
        project_id=project_id,
        repository=repository,
        ref=ref,
        model=model,
        auto_create_pr=auto_create_pr,
        branch_name=branch_name,
        expected_deliverable=expected_deliverable,
        task_prompt=task_prompt,
    )
    if expected != proposal_digest.strip():
        return "cursor_proposal_digest mismatch — re-run preview before launch."
    return None


def summarize_cursor_agent_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Best-effort HAM-native summary; defensive for partial Cursor JSON."""
    agent_id = raw.get("id") or raw.get("agentId")
    status = raw.get("status")
    summary = raw.get("summary") or raw.get("name") or ""
    pr_url: str | None = None
    target = raw.get("target")
    if isinstance(target, dict):
        pr_url = target.get("prUrl") or target.get("pullRequestUrl")
    source = raw.get("source")
    repo: str | None = None
    ref: str | None = None
    if isinstance(source, dict):
        repo = source.get("repository")
        ref = source.get("ref")
    return {
        "provider": "cursor_cloud_agent",
        "agent_id": str(agent_id) if agent_id is not None else None,
        "status": str(status) if status is not None else None,
        "repository": str(repo) if repo else None,
        "ref": str(ref) if ref else None,
        "summary": str(summary)[:8000] if summary else None,
        "pr_url": str(pr_url) if pr_url else None,
    }


@dataclass(frozen=True)
class CursorAgentPreviewResult:
    ok: bool
    blocking_reason: str | None
    proposal_digest: str | None
    base_revision: str | None
    repository: str | None
    mutates: bool
    summary_preview: str | None
    project_id: str | None


def build_cursor_agent_preview(
    *,
    project_id: str,
    project_metadata: dict[str, Any],
    cursor_repository: str | None,
    cursor_task_prompt: str,
    cursor_ref: str | None,
    cursor_model: str,
    cursor_auto_create_pr: bool,
    cursor_branch_name: str | None,
    cursor_expected_deliverable: str | None,
) -> CursorAgentPreviewResult:
    repo = resolve_cursor_repository_url(
        explicit=cursor_repository,
        project_metadata=project_metadata,
    )
    if not repo:
        return CursorAgentPreviewResult(
            ok=False,
            blocking_reason=(
                "No repository URL resolved. Set operator `cursor_repository`, or "
                f"`metadata.{_METADATA_REPO_KEY}` on the project, or `HAM_CURSOR_DEFAULT_REPOSITORY` for demos."
            ),
            proposal_digest=None,
            base_revision=None,
            repository=None,
            mutates=False,
            summary_preview=None,
            project_id=project_id,
        )
    if not get_effective_cursor_api_key():
        return CursorAgentPreviewResult(
            ok=False,
            blocking_reason=(
                "No Cursor API key on this API host. Set it in Settings or `CURSOR_API_KEY` / credentials file."
            ),
            proposal_digest=None,
            base_revision=None,
            repository=repo,
            mutates=False,
            summary_preview=None,
            project_id=project_id,
        )
    focus = (cursor_task_prompt or "").strip()
    if not focus:
        return CursorAgentPreviewResult(
            ok=False,
            blocking_reason="cursor_task_prompt is empty.",
            proposal_digest=None,
            base_revision=None,
            repository=repo,
            mutates=False,
            summary_preview=None,
            project_id=project_id,
        )

    digest = compute_cursor_proposal_digest(
        project_id=project_id,
        repository=repo,
        ref=cursor_ref,
        model=cursor_model,
        auto_create_pr=cursor_auto_create_pr,
        branch_name=cursor_branch_name,
        expected_deliverable=cursor_expected_deliverable,
        task_prompt=focus,
    )
    mutates = bool(cursor_auto_create_pr)
    preview_text = (
        f"**Cursor Cloud Agent** (preview only — no launch yet)\n\n"
        f"- **project:** `{project_id}`\n"
        f"- **repository:** `{repo}`\n"
        f"- **ref:** `{cursor_ref or '(default branch)'}`\n"
        f"- **model:** `{cursor_model or 'default'}`\n"
        f"- **auto_create_pr:** `{cursor_auto_create_pr}`\n"
        f"- **branch_name:** `{cursor_branch_name or '(none)'}`\n"
        f"- **expected_deliverable:** {(cursor_expected_deliverable or '(none)')[:500]}\n"
        f"- **mutates (PR path):** `{mutates}`\n"
        f"- **base_revision:** `{CURSOR_AGENT_BASE_REVISION}`\n"
    )
    return CursorAgentPreviewResult(
        ok=True,
        blocking_reason=None,
        proposal_digest=digest,
        base_revision=CURSOR_AGENT_BASE_REVISION,
        repository=repo,
        mutates=mutates,
        summary_preview=preview_text,
        project_id=project_id,
    )


def append_cursor_agent_audit(
    row: dict[str, Any],
    *,
    project_root_for_mirror: str | None,
) -> None:
    """Central JSONL audit (primary); optional project-local mirror when root is writable."""
    rid = str(row.get("audit_row_id") or uuid.uuid4())
    out = {
        **row,
        "audit_row_id": rid,
        "logged_at": datetime.now(UTC).isoformat(),
        "provider": "cursor_cloud_agent",
    }
    line = json.dumps(out, ensure_ascii=False) + "\n"
    path = central_audit_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.open("a", encoding="utf-8").write(line)
    except OSError as exc:
        print(
            f"Warning: cursor agent central audit failed ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )

    if not project_root_for_mirror or not str(project_root_for_mirror).strip():
        return
    try:
        root = Path(project_root_for_mirror).expanduser().resolve()
        if not root.is_dir():
            return
        mir = root / ".ham" / "_audit" / "cursor_cloud_agent.jsonl"
        mir.parent.mkdir(parents=True, exist_ok=True)
        mir.open("a", encoding="utf-8").write(line)
    except OSError:
        pass


def _cursor_control_plane_audit_ref() -> ControlPlaneAuditRef:
    return ControlPlaneAuditRef(
        provider_audit=ControlPlaneProviderAuditRef(
            sink="cursor_jsonl",
            path=str(central_audit_file_path()),
        ),
    )


def _audit_row_common(
    *,
    action: str,
    project_id: str,
    proposal_digest: str | None,
    repository: str | None,
    ref: str | None,
    ok: bool,
    summary: str | None,
    agent_id: str | None,
    provider_excerpt: str | None,
) -> dict[str, Any]:
    return {
        "action": action,
        "project_id": project_id,
        "proposal_digest": proposal_digest,
        "agent_id": agent_id,
        "repository": repository,
        "ref": ref,
        "summary": (summary or "")[:4000] if summary else None,
        "ok": ok,
        "provider_excerpt": (provider_excerpt or "")[:1500] if provider_excerpt else None,
    }


def audit_cursor_preview(
    *,
    project_id: str,
    proposal_digest: str | None,
    repository: str | None,
    ok: bool,
    summary: str | None,
    blocking_reason: str | None,
    project_root_for_mirror: str | None,
) -> None:
    append_cursor_agent_audit(
        _audit_row_common(
            action="preview",
            project_id=project_id,
            proposal_digest=proposal_digest,
            repository=repository,
            ref=None,
            ok=ok,
            summary=summary or blocking_reason,
            agent_id=None,
            provider_excerpt=None,
        ),
        project_root_for_mirror=project_root_for_mirror,
    )


def run_cursor_agent_launch(
    *,
    api_key: str,
    project_id: str,
    repository: str,
    ref: str | None,
    model: str,
    auto_create_pr: bool,
    branch_name: str | None,
    expected_deliverable: str | None,
    task_prompt: str,
    proposal_digest: str,
    project_root_for_mirror: str | None,
    created_by: dict[str, Any] | None = None,
    control_plane_run_store: ControlPlaneRunStore | None = None,
) -> tuple[bool, dict[str, Any], str | None, str | None]:
    """
    Call Cursor launch; return (ok, ham_summary_or_error_dict, blocking_reason, ham_run_id).

    On failure after commit, ok is False and a **failed** ControlPlaneRun row is still created
    when a durable run record is possible.
    """
    st_global = control_plane_run_store or ControlPlaneRunStore()
    prompt_text = compose_prompt_for_cursor(
        task_prompt=task_prompt,
        expected_deliverable=expected_deliverable,
    )
    excerpt: str | None = None
    pr_root: str | None = None
    if project_root_for_mirror and str(project_root_for_mirror).strip():
        p = Path(project_root_for_mirror).expanduser().resolve()
        if p.is_dir():
            pr_root = str(p)
    now = utc_now_iso()
    try:
        raw = cursor_api_launch_agent(
            api_key=api_key,
            prompt_text=prompt_text,
            repository=repository,
            ref=ref,
            model=model,
            auto_create_pr=auto_create_pr,
            branch_name=branch_name,
        )
        summary = summarize_cursor_agent_payload(raw)
        excerpt = json.dumps(raw, ensure_ascii=False, sort_keys=True)[:1500]
        append_cursor_agent_audit(
            _audit_row_common(
                action="launch",
                project_id=project_id,
                proposal_digest=proposal_digest,
                repository=repository,
                ref=ref,
                ok=True,
                summary=summary.get("summary"),
                agent_id=summary.get("agent_id"),
                provider_excerpt=excerpt,
            ),
            project_root_for_mirror=project_root_for_mirror,
        )
        ham_status, s_reason = map_cursor_raw_status(
            str(summary.get("status")) if summary.get("status") is not None else None,
        )
        ext_id: str | None
        a = summary.get("agent_id")
        ext_id = str(a).strip() if a not in (None, "") else None
        if not ext_id:
            r_id = raw.get("id") or raw.get("agentId")
            ext_id = str(r_id).strip() if r_id not in (None, "") else None
        fin = now if ham_status in ("succeeded", "failed") else None
        rid = new_ham_run_id()
        run = ControlPlaneRun(
            ham_run_id=rid,
            provider="cursor_cloud_agent",
            action_kind="launch",
            project_id=project_id,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            committed_at=now,
            started_at=now,
            finished_at=fin,
            last_observed_at=now,
            status=ham_status,
            status_reason=s_reason,
            proposal_digest=proposal_digest,
            base_revision=CURSOR_AGENT_BASE_REVISION,
            external_id=ext_id,
            workflow_id=None,
            summary=cap_summary(
                str(summary.get("summary")) if summary.get("summary") is not None else None,
            ),
            error_summary=None,
            last_provider_status=cap_last_provider_status(
                str(summary.get("status")) if summary.get("status") is not None else None,
            ),
            audit_ref=_cursor_control_plane_audit_ref(),
            project_root=pr_root,
        )
        st_global.save(run, project_root_for_mirror=pr_root)
        out = {**summary, "ham_run_id": rid, "control_plane_status": run.status}
        return True, out, None, rid
    except CursorCloudApiError as exc:
        excerpt = exc.body_excerpt
        append_cursor_agent_audit(
            _audit_row_common(
                action="launch",
                project_id=project_id,
                proposal_digest=proposal_digest,
                repository=repository,
                ref=ref,
                ok=False,
                summary=str(exc),
                agent_id=None,
                provider_excerpt=excerpt,
            ),
            project_root_for_mirror=project_root_for_mirror,
        )
        fail_id = new_ham_run_id()
        err_text = str(exc)
        frun = ControlPlaneRun(
            ham_run_id=fail_id,
            provider="cursor_cloud_agent",
            action_kind="launch",
            project_id=project_id,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            committed_at=now,
            started_at=now,
            finished_at=now,
            last_observed_at=now,
            status="failed",
            status_reason="cursor_api:launch",
            proposal_digest=proposal_digest,
            base_revision=CURSOR_AGENT_BASE_REVISION,
            external_id=None,
            workflow_id=None,
            summary=None,
            error_summary=cap_error_summary(err_text),
            last_provider_status=None,
            audit_ref=_cursor_control_plane_audit_ref(),
            project_root=pr_root,
        )
        st_global.save(frun, project_root_for_mirror=pr_root)
        return (
            False,
            {
                "error": err_text,
                "status_code": exc.status_code,
                "ham_run_id": fail_id,
                "control_plane_status": "failed",
                "provider": "cursor_cloud_agent",
            },
            err_text,
            fail_id,
        )


def run_cursor_agent_status(
    *,
    api_key: str,
    project_id: str,
    agent_id: str,
    project_root_for_mirror: str | None,
    control_plane_run_store: ControlPlaneRunStore | None = None,
) -> tuple[bool, dict[str, Any], str | None, str | None]:
    """Return (ok, payload, blocking_reason, ham_run_id) — ``ham_run_id`` is set when a run row is updated."""
    st_global = control_plane_run_store or ControlPlaneRunStore()
    pr_root: str | None = None
    if project_root_for_mirror and str(project_root_for_mirror).strip():
        p = Path(project_root_for_mirror).expanduser().resolve()
        if p.is_dir():
            pr_root = str(p)
    existing = st_global.find_by_project_and_external(
        project_id=project_id,
        provider="cursor_cloud_agent",
        external_id=agent_id,
    )
    excerpt: str | None = None
    try:
        raw = cursor_api_get_agent(api_key=api_key, agent_id=agent_id)
        summary = summarize_cursor_agent_payload(raw)
        excerpt = json.dumps(raw, ensure_ascii=False, sort_keys=True)[:1500]
        append_cursor_agent_audit(
            _audit_row_common(
                action="status",
                project_id=project_id,
                proposal_digest=None,
                repository=summary.get("repository"),
                ref=summary.get("ref"),
                ok=True,
                summary=summary.get("summary"),
                agent_id=summary.get("agent_id") or agent_id,
                provider_excerpt=excerpt,
            ),
            project_root_for_mirror=project_root_for_mirror,
        )
        n = utc_now_iso()
        hst_out: str | None = None
        if existing:
            hst, sre = map_cursor_raw_status(
                str(summary.get("status")) if summary.get("status") is not None else None,
            )
            hst_out = hst
            upd = {
                "updated_at": n,
                "last_observed_at": n,
                "last_provider_status": cap_last_provider_status(
                    str(summary.get("status")) if summary.get("status") is not None else None,
                ),
                "status": hst,
                "status_reason": sre,
                "summary": cap_summary(
                    str(summary.get("summary")) if summary.get("summary") is not None else None,
                ),
            }
            if hst in ("succeeded", "failed"):
                upd["finished_at"] = n
            merged = existing.model_copy(update=upd)
            st_global.save(merged, project_root_for_mirror=pr_root)
        out = {**summary}
        if hst_out is not None:
            out["control_plane_status"] = hst_out
        if existing:
            out["ham_run_id"] = existing.ham_run_id
        return True, out, None, (existing.ham_run_id if existing else None)
    except CursorCloudApiError as exc:
        excerpt = exc.body_excerpt
        append_cursor_agent_audit(
            _audit_row_common(
                action="status",
                project_id=project_id,
                proposal_digest=None,
                repository=None,
                ref=None,
                ok=False,
                summary=str(exc),
                agent_id=agent_id,
                provider_excerpt=excerpt,
            ),
            project_root_for_mirror=project_root_for_mirror,
        )
        n = utc_now_iso()
        if existing:
            upd = existing.model_copy(
                update={
                    "updated_at": n,
                    "last_observed_at": n,
                    "status": "unknown",
                    "status_reason": "status_poll:cursor_api_error",
                    "error_summary": cap_error_summary(str(exc)),
                },
            )
            st_global.save(upd, project_root_for_mirror=pr_root)
        return (
            False,
            {
                "error": str(exc),
                "status_code": exc.status_code,
                "provider": "cursor_cloud_agent",
            },
            str(exc),
            (existing.ham_run_id if existing else None),
        )


def sanitize_cursor_agent_id(agent_id: str) -> str:
    aid = agent_id.strip()
    if not re.match(r"^[a-z0-9._-]+$", aid, re.I):
        raise ValueError("invalid cursor_agent_id format")
    return aid
