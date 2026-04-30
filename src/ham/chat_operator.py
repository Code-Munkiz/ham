"""
Server-side operator execution for dashboard chat — real reads/writes via ProjectStore,
settings preview/apply, RunStore, and optional one-shot bridge launch.

Natural-language triggers are intentionally narrow; explicit ``ChatRequest.operator`` is supported
for confirm/apply flows from the UI.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from src.ham.agent_profiles import (
    HamAgentsConfig,
    agents_config_from_merged,
    validate_agents_config,
)
from src.ham.agent_router import AgentRouteResult, is_local_repo_operation_intent, route_agent_intent
from src.ham.cursor_agent_workflow import (
    audit_cursor_preview,
    build_cursor_agent_preview,
    resolve_cursor_repository_url,
    run_cursor_agent_launch,
    run_cursor_agent_status,
    sanitize_cursor_agent_id,
    verify_cursor_launch_against_preview,
)
from src.ham.managed_mission_wiring import get_managed_mission_store
from src.ham.droid_workflows import (
    build_droid_preview,
    execute_droid_workflow,
    get_workflow,
    verify_launch_against_preview,
)
from src.ham.clerk_auth import HamActor
from src.ham.clerk_policy import (
    enforce_operator_permission,
    permission_for_intent,
    permission_for_phase,
)
from src.ham.harness_advisory import (
    HarnessAdvisory,
    build_harness_advisory_for_cursor_preview,
    build_harness_advisory_for_droid_preview,
    format_harness_advisory_for_operator_message,
    harness_advisory_enabled,
)
from src.persistence.cursor_credentials import get_effective_cursor_api_key
from src.ham.one_shot_run import run_ham_one_shot
from src.ham.settings_write import (
    ApplyResult,
    PreviewResult,
    SettingsChanges,
    apply_project_settings,
    preview_project_settings,
    settings_writes_enabled,
)
from src.memory_heist import discover_config
from src.persistence.control_plane_run import ControlPlaneRunStore
from src.persistence.managed_mission import ManagedMission
from src.persistence.project_store import ProjectStore
from src.persistence.run_store import RunRecord, RunStore


def _control_plane_created_by(ham_actor: HamActor | None) -> dict[str, Any] | None:
    if ham_actor is None:
        return None
    d: dict[str, Any] = {
        "user_id": ham_actor.user_id,
    }
    if ham_actor.org_id:
        d["org_id"] = ham_actor.org_id
    if ham_actor.email:
        d["email"] = ham_actor.email
    if ham_actor.session_id:
        d["session_id"] = ham_actor.session_id
    return d


def operator_enabled() -> bool:
    raw = (os.environ.get("HAM_CHAT_OPERATOR") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def project_root_accessible(root: Path) -> tuple[bool, str]:
    try:
        r = root.expanduser().resolve()
        if not r.is_dir():
            return False, f"Not a directory on this API host: {r}"
        return True, ""
    except OSError as exc:
        return False, f"API host cannot access path ({type(exc).__name__}: {exc})"


def _require_bearer(authorization: str | None, expected: str, *, code: str) -> None:
    from fastapi import HTTPException

    if not expected:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": code, "message": "Operator writes are disabled (token not set on server)."}},
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": f"{code}_AUTH", "message": "Authorization: Bearer <token> required."}},
        )
    if authorization[7:].strip() != expected:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": f"{code}_INVALID", "message": "Invalid bearer token."}},
        )


def _settings_token() -> str:
    return (os.environ.get("HAM_SETTINGS_WRITE_TOKEN") or "").strip()


def _launch_token() -> str:
    return (os.environ.get("HAM_RUN_LAUNCH_TOKEN") or "").strip()


def _droid_exec_token() -> str:
    return (os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip()


def _cursor_agent_launch_token() -> str:
    return (os.environ.get("HAM_CURSOR_AGENT_LAUNCH_TOKEN") or "").strip()


def _droid_preview_turn(
    *,
    project_store: ProjectStore,
    project_id: str,
    workflow_id: str,
    user_prompt: str,
) -> OperatorTurnResult:
    prec = project_store.get_project(project_id.strip())
    if prec is None:
        return OperatorTurnResult(
            handled=True,
            intent="droid_preview",
            ok=False,
            blocking_reason=f"Unknown project_id {project_id!r}.",
        )
    ok_path, why = project_root_accessible(Path(prec.root))
    if not ok_path:
        return OperatorTurnResult(
            handled=True,
            intent="droid_preview",
            ok=False,
            blocking_reason=f"Cannot preview droid workflow: {why}",
        )
    preview = build_droid_preview(
        workflow_id=workflow_id.strip(),
        project_id=project_id.strip(),
        project_root=Path(prec.root),
        user_prompt=user_prompt,
    )
    if not preview.ok:
        return OperatorTurnResult(
            handled=True,
            intent="droid_preview",
            ok=False,
            blocking_reason=preview.blocking_reason,
        )
    wf = get_workflow(workflow_id.strip())
    token_note = ""
    if wf and wf.requires_launch_token and not _droid_exec_token():
        token_note = (
            "\n\n_Note: `HAM_DROID_EXEC_TOKEN` is not set on this API host — "
            "mutating launches will be rejected until it is configured._"
        )
    pending = {
        "project_id": project_id.strip(),
        "workflow_id": preview.workflow_id,
        "proposal_digest": preview.proposal_digest,
        "base_revision": preview.base_revision,
        "droid_user_prompt": preview.user_prompt,
        "mutates": preview.mutates,
        "tier": preview.tier,
        "summary_preview": (preview.summary_preview or "") + token_note,
    }
    hadv: HarnessAdvisory | None = None
    if harness_advisory_enabled():
        hadv = build_harness_advisory_for_droid_preview(
            workflow_id=str(preview.workflow_id or workflow_id).strip(),
            mutates=preview.mutates,
            tier=preview.tier,
            requires_launch_token=bool(wf.requires_launch_token) if wf is not None else False,
            droid_exec_token_configured=bool(_droid_exec_token()),
            user_prompt=str(preview.user_prompt or user_prompt),
        )
    return OperatorTurnResult(
        handled=True,
        intent="droid_preview",
        ok=True,
        pending_droid=pending,
        harness_advisory=hadv,
        data={
            "workflow_id": preview.workflow_id,
            "proposal_digest": preview.proposal_digest,
            "message": (preview.summary_preview or "") + token_note,
        },
    )


class ChatOperatorPayload(BaseModel):
    """Explicit operator follow-up (confirm apply / register / launch) from the client."""

    model_config = ConfigDict(extra="forbid")

    phase: Literal[
        "apply_settings",
        "register_project",
        "launch_run",
        "droid_preview",
        "droid_launch",
        "cursor_agent_preview",
        "cursor_agent_launch",
        "cursor_agent_status",
    ] | None = None
    confirmed: bool = False
    project_id: str | None = Field(default=None, max_length=180)
    changes: dict[str, Any] | None = None
    base_revision: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    root: str | None = Field(default=None, max_length=4096)
    description: str | None = Field(default=None, max_length=2000)
    prompt: str | None = Field(default=None, max_length=50_000)
    profile_id: str | None = Field(default=None, max_length=128)
    droid_workflow_id: str | None = Field(default=None, max_length=64)
    droid_user_prompt: str | None = Field(default=None, max_length=50_000)
    droid_proposal_digest: str | None = Field(default=None, max_length=80)
    droid_base_revision: str | None = Field(default=None, max_length=64)
    cursor_task_prompt: str | None = Field(default=None, max_length=100_000)
    cursor_repository: str | None = Field(default=None, max_length=2048)
    cursor_ref: str | None = Field(default=None, max_length=512)
    cursor_model: str = Field(default="default", max_length=128)
    cursor_auto_create_pr: bool = False
    cursor_branch_name: str | None = Field(default=None, max_length=512)
    cursor_expected_deliverable: str | None = Field(default=None, max_length=10_000)
    cursor_proposal_digest: str | None = Field(default=None, max_length=80)
    cursor_base_revision: str | None = Field(default=None, max_length=64)
    cursor_mission_handling: Literal["direct", "managed"] | None = None
    cursor_agent_id: str | None = Field(default=None, max_length=128)


class OperatorTurnResult(BaseModel):
    """Structured outcome appended to chat API responses."""

    model_config = ConfigDict(extra="forbid")

    handled: bool
    intent: str | None = None
    ok: bool = True
    blocking_reason: str | None = None
    pending_apply: dict[str, Any] | None = None
    pending_launch: dict[str, Any] | None = None
    pending_register: dict[str, Any] | None = None
    pending_droid: dict[str, Any] | None = None
    pending_cursor_agent: dict[str, Any] | None = None
    harness_advisory: HarnessAdvisory | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def _summarize_run(rec: RunRecord, *, max_lines: int = 24, max_chars: int = 6000) -> dict[str, Any]:
    br = rec.bridge_result if isinstance(rec.bridge_result, dict) else {}
    cmds = br.get("commands") if isinstance(br.get("commands"), list) else []
    lines: list[str] = []
    status = str(br.get("status", ""))
    summary = str(br.get("summary", "") or "")
    lines.append(f"run_id: {rec.run_id}")
    lines.append(f"created_at: {rec.created_at}")
    lines.append(f"profile_id: {rec.profile_id}")
    lines.append(f"bridge.status: {status}")
    if summary:
        lines.append(f"bridge.summary: {summary[:2000]}")
    for c in cmds[:8]:
        if not isinstance(c, dict):
            continue
        argv = c.get("argv")
        st = c.get("status", "")
        lines.append(f"command: {argv} -> {st}")
        out = c.get("stdout")
        err = c.get("stderr")
        if isinstance(out, str) and out.strip():
            lines.append("stdout:")
            lines.extend(out.strip().splitlines()[:max_lines])
        if isinstance(err, str) and err.strip():
            lines.append("stderr:")
            lines.extend(err.strip().splitlines()[:max_lines])
    hr = rec.hermes_review if isinstance(rec.hermes_review, dict) else {}
    if hr:
        ok = hr.get("ok")
        notes = hr.get("notes")
        lines.append(f"hermes_review.ok: {ok}")
        if isinstance(notes, list) and notes:
            lines.append("hermes_review.notes: " + "; ".join(str(n) for n in notes[:12]))
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated; full record in .ham/runs/]"
    return {
        "run_id": rec.run_id,
        "status": status,
        "log_excerpt": text,
    }


def _merge_agent_skills(
    cfg: HamAgentsConfig,
    profile_id: str,
    *,
    add_skills: list[str],
    remove_skills: list[str],
) -> HamAgentsConfig:
    profiles: list[Any] = []
    found = False
    for p in cfg.profiles:
        if p.id != profile_id:
            profiles.append(p)
            continue
        found = True
        skills = [str(s) for s in p.skills]
        for s in remove_skills:
            skills = [x for x in skills if x != s]
        for s in add_skills:
            if s not in skills:
                skills.append(s)
        profiles.append(p.model_copy(update={"skills": skills}))
    if not found:
        raise ValueError(f"unknown profile_id {profile_id!r}")
    out = HamAgentsConfig(profiles=profiles, primary_agent_id=cfg.primary_agent_id)
    validate_agents_config(out, validate_skill_catalog=True)
    return out


def _extract_project_id(text: str) -> str | None:
    m = re.search(r"\b(project\.[a-z0-9._-]+)\b", text, re.I)
    return m.group(1) if m else None


def _extract_run_id(text: str) -> str | None:
    m = re.search(r"\b(run-[a-f0-9]{12})\b", text, re.I)
    if m:
        return m.group(1)
    m2 = re.search(r"\binspect\s+run\s+([a-z0-9._-]+)", text, re.I)
    return m2.group(1) if m2 else None


def _extract_cursor_agent_id(text: str) -> str | None:
    m = re.search(r"\b(bc_[a-z0-9._-]+)\b", text, re.I)
    return m.group(1) if m else None


_SHELL_LINE_RE = re.compile(r"^\s*(cd|git|gh|npm|pnpm|yarn|pytest|python)\b", re.I)
_SECRET_VALUE_RE = re.compile(r"\b(?:ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|sk-[A-Za-z0-9]{8,})\b")


def _redact_sensitive_shell_value(line: str) -> str:
    out = _SECRET_VALUE_RE.sub("<redacted>", line)
    out = re.sub(r"(?i)(--with-token)\s+\S+", r"\1 <redacted>", out)
    out = re.sub(r"(?i)\b(token|pat)\s*[:=]\s*\S+", r"\1=<redacted>", out)
    return out


def _extract_local_repo_commands(text: str) -> list[str]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    commands: list[str] = []
    for ln in lines:
        trimmed = ln.strip()
        if trimmed.startswith("```"):
            continue
        if _SHELL_LINE_RE.search(trimmed):
            commands.append(_redact_sensitive_shell_value(trimmed))
    if commands:
        return commands
    # Single-line prose fallback
    if is_local_repo_operation_intent(text):
        return [_redact_sensitive_shell_value(text.strip())]
    return []


def _normalize_repo_hint(repo: str | None) -> str:
    raw = str(repo or "").strip().rstrip("/")
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.startswith("https://github.com/"):
        return lowered.removeprefix("https://github.com/").strip("/")
    if lowered.startswith("http://github.com/"):
        return lowered.removeprefix("http://github.com/").strip("/")
    return lowered


def _project_matches_repo_hint(project_metadata: dict[str, Any], repo_hint: str) -> bool:
    expected = _normalize_repo_hint(repo_hint)
    if not expected:
        return False
    meta_repo = project_metadata.get("cursor_cloud_repository")
    if not isinstance(meta_repo, str) or not meta_repo.strip():
        return False
    return _normalize_repo_hint(meta_repo) == expected


def _resolve_project_id_from_repo_hint(
    *,
    project_store: ProjectStore,
    repo_hint: str | None,
) -> str | None:
    normalized = _normalize_repo_hint(repo_hint)
    if not normalized:
        return None
    for record in project_store.list_projects():
        if _project_matches_repo_hint(dict(record.metadata or {}), normalized):
            return record.id
    return None


def _project_default_cursor_ref(project_metadata: dict[str, Any]) -> str | None:
    for key in ("cursor_cloud_ref", "cursor_ref", "default_branch", "branch", "git_branch"):
        raw = project_metadata.get(key)
        if not isinstance(raw, str):
            continue
        val = raw.strip()
        if val:
            return val
    return None


def _normalize_cursor_repository(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    ssh = re.match(r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$", raw, re.I)
    if ssh:
        return f"{ssh.group('owner')}/{ssh.group('repo')}"
    if raw.lower().startswith(("http://", "https://")):
        try:
            u = urlparse(raw)
            if u.netloc.lower() != "github.com":
                return raw.rstrip("/")
            parts = [p for p in u.path.split("/") if p]
            if len(parts) >= 2:
                repo = parts[1]
                if repo.lower().endswith(".git"):
                    repo = repo[:-4]
                return f"{parts[0]}/{repo}"
        except ValueError:
            return raw.rstrip("/")
    return raw.rstrip("/")


def _infer_project_cursor_metadata_from_git(project_root: str | Path) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        return {}
    try:
        repo_cmd = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    repo = _normalize_cursor_repository(repo_cmd.stdout.strip() if repo_cmd.returncode == 0 else "")
    if not repo:
        return {}
    ref: str | None = None
    for argv in (
        ["git", "-C", str(root), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
    ):
        try:
            ref_cmd = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if ref_cmd.returncode != 0:
            continue
        candidate = ref_cmd.stdout.strip()
        if candidate.startswith("origin/"):
            candidate = candidate[len("origin/") :]
        if candidate and candidate.upper() != "HEAD":
            ref = candidate
            break
    updates = {"cursor_cloud_repository": repo}
    if ref:
        updates["cursor_cloud_ref"] = ref
    return updates


def _ensure_project_cursor_metadata(project_store: ProjectStore, record: Any) -> Any:
    metadata = dict(record.metadata or {})
    if metadata.get("cursor_cloud_repository"):
        return record
    inferred = _infer_project_cursor_metadata_from_git(record.root)
    if not inferred:
        return record
    updated = record.model_copy(update={"metadata": {**metadata, **inferred}})
    project_store.register(updated)
    return updated


def _mission_project_id(mission: ManagedMission) -> str | None:
    hid = str(mission.control_plane_ham_run_id or "").strip()
    if not hid:
        return None
    try:
        run = ControlPlaneRunStore().get(hid)
    except ValueError:
        return None
    if run is None:
        return None
    pid = str(run.project_id or "").strip()
    return pid or None


def _latest_managed_mission(
    *,
    project_store: ProjectStore,
    project_id: str | None,
) -> ManagedMission | None:
    rows = get_managed_mission_store().list_newest_first(limit=80)
    if not rows:
        return None
    pid = str(project_id or "").strip()
    if not pid:
        open_any = next((m for m in rows if m.mission_lifecycle == "open"), None)
        return open_any or rows[0]
    rec = project_store.get_project(pid)
    project_repo = None
    if rec is not None:
        project_repo = _normalize_repo_hint(dict(rec.metadata or {}).get("cursor_cloud_repository"))
    scoped: list[ManagedMission] = []
    for m in rows:
        mid = _mission_project_id(m)
        if mid and mid == pid:
            scoped.append(m)
            continue
        if project_repo:
            observed = _normalize_repo_hint(m.repository_observed or m.repo_key)
            if observed and observed == project_repo:
                scoped.append(m)
    if not scoped:
        open_any = next((m for m in rows if m.mission_lifecycle == "open"), None)
        return open_any or rows[0]
    open_scoped = next((m for m in scoped if m.mission_lifecycle == "open"), None)
    return open_scoped or scoped[0]


def _managed_mission_payload(
    mission: ManagedMission,
    *,
    include_events: bool = False,
    max_events: int = 6,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "provider": "cursor_cloud_agent",
        "reason_code": "mission_state_ready",
        "mission_registry_id": mission.mission_registry_id,
        "agent_id": mission.cursor_agent_id,
        "cursor_agent_id": mission.cursor_agent_id,
        "repository": mission.repository_observed,
        "ref": mission.ref_observed,
        "status": mission.cursor_status_last_observed,
        "mission_checkpoint": mission.mission_checkpoint_latest,
        "mission_lifecycle": mission.mission_lifecycle,
        "mission_status_reason": mission.status_reason_last_observed,
        "pr_url": mission.pr_url_last_observed,
        "last_server_observed_at": mission.last_server_observed_at,
    }
    if include_events:
        events = list(mission.mission_checkpoint_events)[-max_events:]
        out["checkpoint_events"] = [
            {
                "checkpoint": e.checkpoint,
                "observed_at": e.observed_at,
                "reason": e.reason,
            }
            for e in events
        ]
    return out


def _map_agent_router_result(
    *,
    routed: AgentRouteResult,
    user_text: str,
    default_project_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    explicit_pid = _extract_project_id(user_text)
    resolved_pid = explicit_pid or default_project_id
    repo_ref = routed.repo_ref.strip() if routed.repo_ref else None
    branch_ref = routed.branch.strip() if routed.branch else None
    if routed.intent == "normal_chat":
        return None
    if routed.provider not in ("cursor",):
        return (
            "agent_router_blocked",
            {
                "reason_code": routed.reason_code or "provider_not_implemented",
                "provider": routed.provider,
            },
        )
    if routed.intent == "agent_preview":
        params: dict[str, Any] = {}
        if "task" in routed.missing:
            params["missing"] = "task_prompt"
            return "cursor_agent_preview", params
        if "project" in routed.missing and not repo_ref:
            params["missing"] = "project_id"
            return "cursor_agent_preview", params
        if repo_ref:
            params["cursor_repository"] = repo_ref
        if branch_ref:
            params["cursor_ref"] = branch_ref
        if resolved_pid:
            params["project_id"] = resolved_pid
            params["project_context_source"] = "explicit" if explicit_pid else "default"
        return (
            "cursor_agent_preview",
            {**params, "cursor_task_prompt": routed.task or ""},
        )
    if routed.intent == "agent_launch":
        params = {}
        if "task" in routed.missing:
            params["missing"] = "task_prompt"
            return "cursor_agent_launch", params
        if "project" in routed.missing and not repo_ref:
            params["missing"] = "project_id"
            return "cursor_agent_launch", params
        if repo_ref:
            params["cursor_repository"] = repo_ref
        if branch_ref:
            params["cursor_ref"] = branch_ref
        if resolved_pid:
            params["project_id"] = resolved_pid
            params["project_context_source"] = "explicit" if explicit_pid else "default"
        return (
            "cursor_agent_launch",
            {**params, "cursor_task_prompt": routed.task or ""},
        )
    if routed.intent == "agent_status":
        aid = _extract_cursor_agent_id(user_text)
        if not aid:
            return (
                "cursor_agent_status",
                {
                    "project_id": resolved_pid,
                    "project_context_source": "explicit" if explicit_pid else "default",
                },
            )
        return (
            "cursor_agent_status",
            {
                "project_id": resolved_pid,
                "cursor_agent_id": aid,
                "project_context_source": "explicit" if explicit_pid else "default",
            },
        )
    if routed.intent == "agent_cancel":
        aid = _extract_cursor_agent_id(user_text)
        if not aid:
            return (
                "cursor_agent_cancel",
                {
                    "project_id": resolved_pid,
                    "project_context_source": "explicit" if explicit_pid else "default",
                },
            )
        return (
            "cursor_agent_cancel",
            {
                "project_id": resolved_pid,
                "cursor_agent_id": aid,
                "project_context_source": "explicit" if explicit_pid else "default",
            },
        )
    if routed.intent == "agent_continue":
        return (
            "agent_router_blocked",
            {"reason_code": "continue_not_supported", "provider": routed.provider},
        )
    if routed.intent == "agent_choose_provider":
        return (
            "agent_router_blocked",
            {"reason_code": "missing_provider", "provider": "auto"},
        )
    return None


def _reasoned_block(intent: str, code: str, message: str) -> OperatorTurnResult:
    return OperatorTurnResult(
        handled=True,
        intent=intent,
        ok=False,
        blocking_reason=f"{code}: {message}",
        data={"reason_code": code},
    )


def _map_cursor_launch_failure_code(payload: dict[str, Any], fallback: str | None) -> str:
    status_code_raw = payload.get("status_code")
    status_code = int(status_code_raw) if isinstance(status_code_raw, int) else None
    if status_code in (401, 403):
        return "provider_unauthorized"
    if status_code == 429:
        return "provider_rate_limited"
    low = (fallback or "").lower()
    if "unauthorized" in low or "forbidden" in low:
        return "provider_unauthorized"
    if "rate" in low and "limit" in low:
        return "provider_rate_limited"
    return "launch_failed"


def _parse_skill_mutation(text: str) -> tuple[str | None, list[str], list[str], str | None]:
    """Returns (profile_id, add, remove, kind). kind is 'add'|'remove'|None"""
    # add skill X to PROFILE / add skill X to agent PROFILE
    m = re.search(
        r"\b(?:add|attach)\s+skills?\s+([^\n]+?)\s+(?:to|for)\s+(?:profile|agent)\s+([\w.-]+)\b",
        text,
        re.I,
    )
    if m:
        raw_skills = m.group(1).strip()
        prof = m.group(2).strip()
        skills = [s.strip() for s in re.split(r"[\s,]+", raw_skills) if s.strip()]
        return prof, skills, [], "add"
    m = re.search(
        r"\b(?:add|attach)\s+skill\s+([\w-]+)\s+(?:to|for)\s+(?:profile|agent)\s+([\w.-]+)\b",
        text,
        re.I,
    )
    if m:
        return m.group(2).strip(), [m.group(1).strip()], [], "add"
    m = re.search(
        r"\b(?:remove|detach)\s+skills?\s+([^\n]+?)\s+from\s+(?:profile|agent)\s+([\w.-]+)\b",
        text,
        re.I,
    )
    if m:
        raw_skills = m.group(1).strip()
        prof = m.group(2).strip()
        skills = [s.strip() for s in re.split(r"[\s,]+", raw_skills) if s.strip()]
        return prof, [], skills, "remove"
    m = re.search(
        r"\b(?:remove|detach)\s+skill\s+([\w-]+)\s+from\s+(?:profile|agent)\s+([\w.-]+)\b",
        text,
        re.I,
    )
    if m:
        return m.group(2).strip(), [], [m.group(1).strip()], "remove"
    return None, [], [], None


def try_heuristic_intent(
    user_text: str,
    *,
    default_project_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    t = user_text.strip()
    low = t.lower()
    if is_local_repo_operation_intent(t):
        return "local_repo_operation", {"commands": _extract_local_repo_commands(t)}
    if re.search(r"\b(list|show)\s+(all\s+)?projects?\b", low):
        return "list_projects", {}
    if re.search(r"\b(inspect|show)\s+agents?\b", low) or re.search(
        r"\bagent\s+builder\b.*\b(profiles?|skills?)\b",
        low,
    ):
        pid = _extract_project_id(t) or default_project_id
        if not pid:
            return "inspect_agents", {"missing": "project_id"}
        return "inspect_agents", {"project_id": pid}
    if re.search(r"\b(inspect|describe|show)\s+project\b", low):
        pid = _extract_project_id(t) or default_project_id
        if not pid:
            return "inspect_project", {"missing": "project_id"}
        return "inspect_project", {"project_id": pid}
    if re.search(r"\b(list|show)\s+runs?\b", low):
        pid = _extract_project_id(t) or default_project_id
        return "list_runs", {"project_id": pid}
    rid = _extract_run_id(t)
    if rid and re.search(r"\b(inspect|show|describe)\s+run\b", low):
        pid = _extract_project_id(t) or default_project_id
        return "inspect_run", {"run_id": rid, "project_id": pid}
    if re.search(r"\b(status|what happened|show mission status|how is the agent doing)\b", low):
        pid = _extract_project_id(t) or default_project_id
        aid = _extract_cursor_agent_id(t)
        return "cursor_agent_status", {"project_id": pid, "cursor_agent_id": aid}
    if re.search(r"\b(show logs|show checkpoints|what has it done)\b", low):
        pid = _extract_project_id(t) or default_project_id
        aid = _extract_cursor_agent_id(t)
        return "cursor_agent_logs", {"project_id": pid, "cursor_agent_id": aid}
    if re.search(r"\b(stop the agent|cancel the mission|cancel agent|stop agent)\b", low):
        pid = _extract_project_id(t) or default_project_id
        aid = _extract_cursor_agent_id(t)
        return "cursor_agent_cancel", {"project_id": pid, "cursor_agent_id": aid}
    if re.search(r"\bcancel\s+this\s+mission\b", low):
        pid = _extract_project_id(t) or default_project_id
        aid = _extract_cursor_agent_id(t)
        return "cursor_agent_cancel", {"project_id": pid, "cursor_agent_id": aid}

    prof, add_s, rem, kind = _parse_skill_mutation(t)
    if kind and prof:
        pid = _extract_project_id(t) or default_project_id
        if not pid:
            return "update_agents_preview", {"missing": "project_id", "profile_id": prof, "add": add_s, "remove": rem}
        return "update_agents_preview", {
            "project_id": pid,
            "profile_id": prof,
            "add_skills": add_s,
            "remove_skills": rem,
        }

    if re.search(r"\bregister\s+project\b", low):
        # path: quoted or "register project /path"
        m = re.search(r"register\s+project\s+[\"']([^\"']+)[\"']", t, re.I)
        path = m.group(1).strip() if m else None
        if not path:
            m2 = re.search(r"register\s+project\s+(\S+)", t, re.I)
            path = m2.group(1).strip() if m2 else None
        name_m = re.search(r"\bname\s+[\"']([^\"']+)[\"']", t, re.I)
        name = name_m.group(1) if name_m else None
        return "register_project", {"root": path, "name": name}

    if re.search(r"\blaunch\s+run\b", low) or re.search(r"\brun\s+bridge\b", low):
        pid = _extract_project_id(t) or default_project_id
        prompt = t
        for prefix in (r"^.*?\blaunch\s+run\s*[:,]?\s*", r"^.*?\brun\s+bridge\s*[:,]?\s*"):
            prompt = re.sub(prefix, "", t, flags=re.I).strip()
        return "launch_run", {"project_id": pid, "prompt": prompt or t}

    routed = route_agent_intent(
        t,
        default_provider="cursor",
        default_project_id=default_project_id,
    )
    mapped = _map_agent_router_result(
        routed=routed,
        user_text=t,
        default_project_id=default_project_id,
    )
    if mapped is not None:
        return mapped

    if re.search(r"\bpreview\s+(?:factory\s+)?droid\b", low):
        m_wf = re.search(r"\b(readonly_repo_audit|safe_edit_low)\b", t, re.I)
        if not m_wf:
            return "droid_preview", {"missing": "workflow_id"}
        wf_id = m_wf.group(1).lower()
        tail = t[m_wf.end() :].strip()
        focus = re.sub(r"^[:\s—\-]+", "", tail).strip()
        pid = _extract_project_id(t) or default_project_id
        if not pid:
            return "droid_preview", {"missing": "project_id", "workflow_id": wf_id}
        if not focus:
            return "droid_preview", {"missing": "user_prompt", "workflow_id": wf_id, "project_id": pid}
        return "droid_preview", {"project_id": pid, "workflow_id": wf_id, "user_prompt": focus}

    if re.search(r"\bcursor\s+agent\s+status\b", low):
        aid = _extract_cursor_agent_id(t)
        pid = _extract_project_id(t) or default_project_id
        if not aid:
            return "cursor_agent_status", {"missing": "agent_id"}
        if not pid:
            return "cursor_agent_status", {"missing": "project_id"}
        return "cursor_agent_status", {"project_id": pid, "cursor_agent_id": aid}

    return None


def process_operator_turn(
    *,
    user_text: str,
    project_store: ProjectStore,
    default_project_id: str | None,
    operator_payload: ChatOperatorPayload | None,
    ham_operator_authorization: str | None,
    ham_actor: HamActor | None = None,
) -> OperatorTurnResult | None:
    if not operator_enabled():
        return None

    # Explicit client phase takes precedence
    if operator_payload and operator_payload.phase:
        enforce_operator_permission(ham_actor, permission_for_phase(operator_payload.phase))
        return _execute_explicit_phase(
            operator_payload,
            project_store=project_store,
            ham_operator_authorization=ham_operator_authorization,
            ham_actor=ham_actor,
        )

    parsed = try_heuristic_intent(user_text, default_project_id=default_project_id)
    if not parsed:
        return None
    intent, params = parsed
    enforce_operator_permission(ham_actor, permission_for_intent(intent))
    out = _dispatch_intent(
        intent,
        params,
        project_store=project_store,
        ham_operator_authorization=ham_operator_authorization,
        confirmed=False,
        ham_actor=ham_actor,
    )
    if not out.handled:
        return None
    return out


_AGENT_ROUTER_ONLY_INTENTS = {
    "cursor_agent_preview",
    "cursor_agent_launch",
    "cursor_agent_status",
    "cursor_agent_logs",
    "cursor_agent_cancel",
    "agent_router_blocked",
}


def process_agent_router_turn(
    *,
    user_text: str,
    project_store: ProjectStore,
    default_project_id: str | None,
    ham_operator_authorization: str | None,
    ham_actor: HamActor | None = None,
) -> OperatorTurnResult | None:
    """Route only provider-agent intents when full operator mode is disabled."""
    parsed = try_heuristic_intent(user_text, default_project_id=default_project_id)
    if not parsed:
        return None
    intent, params = parsed
    if intent not in _AGENT_ROUTER_ONLY_INTENTS:
        return None
    enforce_operator_permission(ham_actor, permission_for_intent(intent))
    out = _dispatch_intent(
        intent,
        params,
        project_store=project_store,
        ham_operator_authorization=ham_operator_authorization,
        confirmed=False,
        ham_actor=ham_actor,
    )
    if not out.handled:
        return None
    return out


def _execute_explicit_phase(
    op: ChatOperatorPayload,
    *,
    project_store: ProjectStore,
    ham_operator_authorization: str | None,
    ham_actor: HamActor | None = None,
) -> OperatorTurnResult:
    if op.phase == "apply_settings":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason="Apply requires confirmed=true from the client.",
            )
        _require_bearer(ham_operator_authorization, _settings_token(), code="SETTINGS_WRITES_DISABLED")
        if not op.project_id or not op.changes or not op.base_revision:
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason="apply_settings requires project_id, changes, and base_revision.",
            )
        rec = project_store.get_project(op.project_id.strip())
        if rec is None:
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        ok_path, why = project_root_accessible(Path(rec.root))
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason=f"Cannot apply: {why}",
            )
        try:
            changes = SettingsChanges.model_validate(op.changes)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason=f"Invalid changes payload: {exc}",
            )
        try:
            result: ApplyResult = apply_project_settings(
                Path(rec.root),
                changes,
                base_revision=op.base_revision.strip(),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason=str(exc),
            )
        return OperatorTurnResult(
            handled=True,
            intent="apply_settings",
            ok=True,
            data={
                "project_id": op.project_id,
                "new_revision": result.new_revision,
                "backup_id": result.backup_id,
                "audit_id": result.audit_id,
            },
        )

    if op.phase == "register_project":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="register_project",
                ok=False,
                blocking_reason="Registration requires confirmed=true.",
            )
        _require_bearer(ham_operator_authorization, _settings_token(), code="OPERATOR_REGISTER")
        if not op.root or not op.name:
            return OperatorTurnResult(
                handled=True,
                intent="register_project",
                ok=False,
                blocking_reason="register_project requires name and root.",
            )
        root_path = Path(op.root.strip())
        ok_path, why = project_root_accessible(root_path)
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent="register_project",
                ok=False,
                blocking_reason=f"Cannot register: {why}",
            )
        record = project_store.make_record(
            name=op.name.strip(),
            root=str(root_path.resolve()),
            description=(op.description or "").strip(),
            metadata={},
        )
        project_store.register(record)
        return OperatorTurnResult(
            handled=True,
            intent="register_project",
            ok=True,
            data={"project": record.model_dump()},
        )

    if op.phase == "launch_run":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="launch_run",
                ok=False,
                blocking_reason="launch_run requires confirmed=true.",
            )
        _require_bearer(ham_operator_authorization, _launch_token(), code="RUN_LAUNCH")
        if not op.project_id or not op.prompt or not str(op.prompt).strip():
            return OperatorTurnResult(
                handled=True,
                intent="launch_run",
                ok=False,
                blocking_reason="launch_run requires project_id and prompt.",
            )
        rec = project_store.get_project(op.project_id.strip())
        if rec is None:
            return OperatorTurnResult(
                handled=True,
                intent="launch_run",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        ok_path, why = project_root_accessible(Path(rec.root))
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent="launch_run",
                ok=False,
                blocking_reason=f"Cannot launch: {why}",
            )
        shot = run_ham_one_shot(
            Path(rec.root),
            op.prompt.strip(),
            profile_id=op.profile_id.strip() if op.profile_id else None,
        )
        if not shot.ok:
            return OperatorTurnResult(
                handled=True,
                intent="launch_run",
                ok=False,
                blocking_reason=shot.error or "launch failed",
            )
        return OperatorTurnResult(
            handled=True,
            intent="launch_run",
            ok=True,
            data={
                "run_id": shot.run_id,
                "profile_id": shot.profile_id,
                "persist_path": shot.persist_path,
                "bridge_status": shot.bridge_status,
            },
        )

    if op.phase == "cursor_agent_preview":
        if not op.project_id or not op.cursor_task_prompt or not str(op.cursor_task_prompt).strip():
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_preview",
                ok=False,
                blocking_reason="cursor_agent_preview requires project_id and cursor_task_prompt.",
            )
        prec = project_store.get_project(op.project_id.strip())
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_preview",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        prev = build_cursor_agent_preview(
            project_id=prec.id,
            project_metadata=dict(prec.metadata or {}),
            cursor_repository=(op.cursor_repository.strip() if op.cursor_repository else None),
            cursor_task_prompt=op.cursor_task_prompt.strip(),
            cursor_ref=op.cursor_ref.strip() if op.cursor_ref else None,
            cursor_model=(op.cursor_model or "default").strip(),
            cursor_auto_create_pr=bool(op.cursor_auto_create_pr),
            cursor_branch_name=op.cursor_branch_name.strip() if op.cursor_branch_name else None,
            cursor_expected_deliverable=(
                op.cursor_expected_deliverable.strip() if op.cursor_expected_deliverable else None
            ),
            cursor_mission_handling=op.cursor_mission_handling,
        )
        audit_cursor_preview(
            project_id=prec.id,
            proposal_digest=prev.proposal_digest,
            repository=prev.repository,
            ok=prev.ok,
            summary=prev.summary_preview if prev.ok else None,
            blocking_reason=prev.blocking_reason,
            project_root_for_mirror=str(prec.root),
        )
        if not prev.ok:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_preview",
                ok=False,
                blocking_reason=prev.blocking_reason,
            )
        tok_note = ""
        if not _cursor_agent_launch_token():
            tok_note = (
                "\n\n_Note: `HAM_CURSOR_AGENT_LAUNCH_TOKEN` is not set — launches will be rejected until it is configured._"
            )
        mh = op.cursor_mission_handling or "direct"
        pending = {
            "project_id": prec.id,
            "proposal_digest": prev.proposal_digest,
            "base_revision": prev.base_revision,
            "repository": prev.repository,
            "cursor_repository": (op.cursor_repository.strip() if op.cursor_repository else None),
            "cursor_mission_handling": mh,
            "cursor_task_prompt": op.cursor_task_prompt.strip(),
            "cursor_ref": op.cursor_ref.strip() if op.cursor_ref else None,
            "cursor_model": (op.cursor_model or "default").strip(),
            "cursor_auto_create_pr": bool(op.cursor_auto_create_pr),
            "cursor_branch_name": op.cursor_branch_name.strip() if op.cursor_branch_name else None,
            "cursor_expected_deliverable": (
                op.cursor_expected_deliverable.strip() if op.cursor_expected_deliverable else None
            ),
            "mutates": prev.mutates,
            "summary_preview": (prev.summary_preview or "") + tok_note,
        }
        hadv_c: HarnessAdvisory | None = None
        if harness_advisory_enabled():
            hadv_c = build_harness_advisory_for_cursor_preview(
                repository_resolved=bool(prev.repository and str(prev.repository).strip()),
                mutates=prev.mutates,
                auto_create_pr=bool(op.cursor_auto_create_pr),
                cursor_launch_token_configured=bool(_cursor_agent_launch_token()),
                task_prompt=op.cursor_task_prompt.strip(),
            )
        return OperatorTurnResult(
            handled=True,
            intent="cursor_agent_preview",
            ok=True,
            pending_cursor_agent=pending,
            harness_advisory=hadv_c,
            data={
                "proposal_digest": prev.proposal_digest,
                "repository": prev.repository,
                "message": (prev.summary_preview or "") + tok_note,
            },
        )

    if op.phase == "cursor_agent_launch":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason="cursor_agent_launch requires confirmed=true.",
            )
        _require_bearer(ham_operator_authorization, _cursor_agent_launch_token(), code="CURSOR_AGENT_LAUNCH")
        if (
            not op.project_id
            or not op.cursor_task_prompt
            or not op.cursor_proposal_digest
            or not op.cursor_base_revision
        ):
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason=(
                    "cursor_agent_launch requires project_id, cursor_task_prompt, "
                    "cursor_proposal_digest, and cursor_base_revision."
                ),
            )
        prec = project_store.get_project(op.project_id.strip())
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        repo = resolve_cursor_repository_url(
            explicit=op.cursor_repository.strip() if op.cursor_repository else None,
            project_metadata=dict(prec.metadata or {}),
        )
        if not repo:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason="Could not resolve repository for launch.",
            )
        v_err = verify_cursor_launch_against_preview(
            project_id=prec.id,
            repository=repo,
            ref=op.cursor_ref.strip() if op.cursor_ref else None,
            model=(op.cursor_model or "default").strip(),
            auto_create_pr=bool(op.cursor_auto_create_pr),
            branch_name=op.cursor_branch_name.strip() if op.cursor_branch_name else None,
            expected_deliverable=(
                op.cursor_expected_deliverable.strip() if op.cursor_expected_deliverable else None
            ),
            task_prompt=op.cursor_task_prompt.strip(),
            proposal_digest=op.cursor_proposal_digest.strip(),
            base_revision=op.cursor_base_revision.strip(),
            mission_handling=op.cursor_mission_handling,
        )
        if v_err:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason=v_err,
            )
        api_key = get_effective_cursor_api_key()
        if not api_key:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_launch",
                ok=False,
                blocking_reason="No Cursor API key configured on this API host.",
            )
        ok_launch, payload, blocking, _cp_lid = run_cursor_agent_launch(
            api_key=api_key,
            project_id=prec.id,
            repository=repo,
            ref=op.cursor_ref.strip() if op.cursor_ref else None,
            model=(op.cursor_model or "default").strip(),
            auto_create_pr=bool(op.cursor_auto_create_pr),
            branch_name=op.cursor_branch_name.strip() if op.cursor_branch_name else None,
            expected_deliverable=(
                op.cursor_expected_deliverable.strip() if op.cursor_expected_deliverable else None
            ),
            task_prompt=op.cursor_task_prompt.strip(),
            proposal_digest=op.cursor_proposal_digest.strip(),
            project_root_for_mirror=str(prec.root),
            created_by=_control_plane_created_by(ham_actor),
            mission_handling=op.cursor_mission_handling,
        )
        out_data: dict[str, Any] = {**payload}
        out_data.setdefault("provider", "cursor_cloud_agent")
        ext = out_data.get("agent_id")
        if ext not in (None, ""):
            out_data["external_id"] = str(ext)
        return OperatorTurnResult(
            handled=True,
            intent="cursor_agent_launch",
            ok=ok_launch,
            blocking_reason=blocking,
            data=out_data,
        )

    if op.phase == "cursor_agent_status":
        if not op.project_id or not op.cursor_agent_id or not str(op.cursor_agent_id).strip():
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_status",
                ok=False,
                blocking_reason="cursor_agent_status requires project_id and cursor_agent_id.",
            )
        prec = project_store.get_project(op.project_id.strip())
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_status",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        try:
            aid = sanitize_cursor_agent_id(op.cursor_agent_id)
        except ValueError as exc:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_status",
                ok=False,
                blocking_reason=str(exc),
            )
        api_key = get_effective_cursor_api_key()
        if not api_key:
            return OperatorTurnResult(
                handled=True,
                intent="cursor_agent_status",
                ok=False,
                blocking_reason="No Cursor API key configured on this API host.",
            )
        ok_st, payload, blocking, _cp_sid = run_cursor_agent_status(
            api_key=api_key,
            project_id=prec.id,
            agent_id=aid,
            project_root_for_mirror=str(prec.root),
        )
        st_data: dict[str, Any] = {**payload}
        st_data.setdefault("provider", "cursor_cloud_agent")
        st_data["external_id"] = aid
        return OperatorTurnResult(
            handled=True,
            intent="cursor_agent_status",
            ok=ok_st,
            blocking_reason=blocking,
            data=st_data,
        )

    if op.phase == "droid_preview":
        if not op.project_id or not op.droid_workflow_id or not op.droid_user_prompt:
            return OperatorTurnResult(
                handled=True,
                intent="droid_preview",
                ok=False,
                blocking_reason=(
                    "droid_preview requires project_id, droid_workflow_id, and droid_user_prompt."
                ),
            )
        return _droid_preview_turn(
            project_store=project_store,
            project_id=op.project_id.strip(),
            workflow_id=op.droid_workflow_id.strip(),
            user_prompt=op.droid_user_prompt.strip(),
        )

    if op.phase == "droid_launch":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason="droid_launch requires confirmed=true.",
            )
        if (
            not op.project_id
            or not op.droid_workflow_id
            or not op.droid_user_prompt
            or not op.droid_proposal_digest
            or not op.droid_base_revision
        ):
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason=(
                    "droid_launch requires project_id, droid_workflow_id, droid_user_prompt, "
                    "droid_proposal_digest, and droid_base_revision (re-run preview if stale)."
                ),
            )
        rec = project_store.get_project(op.project_id.strip())
        if rec is None:
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason=f"Unknown project_id {op.project_id!r}.",
            )
        root = Path(rec.root)
        ok_path, why = project_root_accessible(root)
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason=f"Cannot launch droid workflow: {why}",
            )
        v_err = verify_launch_against_preview(
            workflow_id=op.droid_workflow_id.strip(),
            project_id=op.project_id.strip(),
            project_root=root,
            user_prompt=op.droid_user_prompt.strip(),
            proposal_digest=op.droid_proposal_digest.strip(),
            base_revision=op.droid_base_revision.strip(),
        )
        if v_err:
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason=v_err,
            )
        wf = get_workflow(op.droid_workflow_id.strip())
        if wf is None:
            return OperatorTurnResult(
                handled=True,
                intent="droid_launch",
                ok=False,
                blocking_reason=f"Unknown workflow_id {op.droid_workflow_id!r}.",
            )
        if wf.requires_launch_token:
            _require_bearer(ham_operator_authorization, _droid_exec_token(), code="DROID_EXEC")
        launch = execute_droid_workflow(
            workflow_id=op.droid_workflow_id.strip(),
            project_root=root,
            user_prompt=op.droid_user_prompt.strip(),
            project_id=op.project_id.strip(),
            proposal_digest=op.droid_proposal_digest.strip(),
            created_by=_control_plane_created_by(ham_actor),
        )
        droid_data: dict[str, Any] = {
            "provider": "factory_droid",
            "workflow_id": launch.workflow_id,
            "audit_id": launch.audit_id,
            "runner_id": launch.runner_id,
            "cwd": launch.cwd,
            "exit_code": launch.exit_code,
            "duration_ms": launch.duration_ms,
            "summary": launch.summary,
            "stdout": launch.stdout,
            "stderr": launch.stderr,
            "stdout_truncated": launch.stdout_truncated,
            "stderr_truncated": launch.stderr_truncated,
            "parsed_json": launch.parsed_json,
            "session_id": launch.session_id,
            "timed_out": launch.timed_out,
        }
        if launch.ham_run_id:
            droid_data["ham_run_id"] = launch.ham_run_id
        if launch.control_plane_status:
            droid_data["control_plane_status"] = launch.control_plane_status
        if launch.session_id:
            droid_data["external_id"] = launch.session_id
        return OperatorTurnResult(
            handled=True,
            intent="droid_launch",
            ok=launch.ok,
            blocking_reason=launch.blocking_reason if not launch.ok else None,
            data=droid_data,
        )

    return OperatorTurnResult(handled=False, ok=True, data={})


def _dispatch_intent(
    intent: str,
    params: dict[str, Any],
    *,
    project_store: ProjectStore,
    ham_operator_authorization: str | None,
    confirmed: bool,
    ham_actor: HamActor | None = None,
) -> OperatorTurnResult:
    if intent == "list_projects":
        projects = project_store.list_projects()
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={"projects": [x.model_dump() for x in projects], "count": len(projects)},
        )

    if intent == "local_repo_operation":
        commands = [str(x).strip() for x in (params.get("commands") or []) if str(x).strip()]
        if not commands:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=True,
                data={
                    "reason_code": "local_repo_operation",
                    "message": (
                        "This is a local repo operation, not a ManagedMission command. "
                        "Run the requested git/gh/shell commands in the target environment."
                    ),
                },
            )
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={
                "reason_code": "local_repo_operation",
                "commands": commands,
            },
        )

    if intent == "inspect_project":
        if params.get("missing") == "project_id":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Say which project (e.g. `project.myrepo-a1b2c3`) or set workspace project context.",
            )
        pid = str(params["project_id"])
        rec = project_store.get_project(pid)
        if rec is None:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Unknown project_id {pid!r}.",
            )
        ok_path, why = project_root_accessible(Path(rec.root))
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=ok_path,
            blocking_reason=None if ok_path else why,
            data={"project": rec.model_dump(), "root_accessible": ok_path},
        )

    if intent == "inspect_agents":
        if params.get("missing") == "project_id":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Say which project id to inspect, or open Chat from a registered workspace.",
            )
        pid = str(params["project_id"])
        prec = project_store.get_project(pid)
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Unknown project_id {pid!r}.",
            )
        ok_path, why = project_root_accessible(Path(prec.root))
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Cannot read agents config: {why}",
            )
        merged = discover_config(Path(prec.root)).merged
        cfg = agents_config_from_merged(merged)
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={"project_id": pid, "agents": cfg.model_dump(mode="json")},
        )

    if intent == "list_runs":
        pid = params.get("project_id")
        if pid:
            prec = project_store.get_project(str(pid))
            if prec is None:
                return OperatorTurnResult(
                    handled=True,
                    intent=intent,
                    ok=False,
                    blocking_reason=f"Unknown project_id {pid!r}.",
                )
            ok_path, why = project_root_accessible(Path(prec.root))
            if not ok_path:
                return OperatorTurnResult(
                    handled=True,
                    intent=intent,
                    ok=False,
                    blocking_reason=f"Cannot list runs: {why}",
                )
            store = RunStore(root=Path(prec.root))
            label = str(pid)
        else:
            store = RunStore()
            label = "(api cwd)"
        runs = store.list_runs(limit=30)
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={
                "scope": label,
                "runs": [r.model_dump() for r in runs],
                "count": len(runs),
            },
        )

    if intent == "inspect_run":
        rid = str(params["run_id"])
        pid = params.get("project_id")
        if pid:
            prec = project_store.get_project(str(pid))
            if prec is None:
                return OperatorTurnResult(
                    handled=True,
                    intent=intent,
                    ok=False,
                    blocking_reason=f"Unknown project_id {pid!r}.",
                )
            ok_path, why = project_root_accessible(Path(prec.root))
            if not ok_path:
                return OperatorTurnResult(
                    handled=True,
                    intent=intent,
                    ok=False,
                    blocking_reason=f"Cannot read run: {why}",
                )
            store = RunStore(root=Path(prec.root))
        else:
            store = RunStore()
        rec = store.get_run(rid)
        if rec is None:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Run {rid!r} not found in this scope. Try listing runs with a project id.",
            )
        summ = _summarize_run(rec)
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data=summ,
        )

    if intent == "update_agents_preview":
        if params.get("missing") == "project_id":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Say which project id, e.g. mention `project.slug-abc123`.",
            )
        pid = str(params["project_id"])
        prof = str(params["profile_id"])
        prec = project_store.get_project(pid)
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Unknown project_id {pid!r}.",
            )
        ok_path, why = project_root_accessible(Path(prec.root))
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Cannot preview agent changes: {why}",
            )
        merged = discover_config(Path(prec.root)).merged
        cfg = agents_config_from_merged(merged)
        try:
            new_cfg = _merge_agent_skills(
                cfg,
                prof,
                add_skills=list(params.get("add_skills") or []),
                remove_skills=list(params.get("remove_skills") or []),
            )
        except ValueError as exc:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=str(exc),
            )
        changes = SettingsChanges(agents=new_cfg)
        try:
            preview: PreviewResult = preview_project_settings(Path(prec.root), changes)
        except ValueError as exc:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=str(exc),
            )
        pending = {
            "project_id": pid,
            "base_revision": preview.base_revision,
            "proposal_digest": preview.proposal_digest,
            "changes": changes.model_dump(mode="json", exclude_none=True),
            "diff": [dict(x) for x in preview.diff] if preview.diff else [],
            "warnings": list(preview.warnings),
        }
        if not settings_writes_enabled():
            pending["note"] = "HAM_SETTINGS_WRITE_TOKEN is not set on the server — apply will be unavailable."
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            pending_apply=pending,
            data={
                "preview": "Agent Builder change is ready. Confirm in the UI (token + Apply) or send operator.phase=apply_settings with confirmed=true.",
                "proposal_digest": preview.proposal_digest,
            },
        )

    if intent == "register_project":
        root = params.get("root")
        name = params.get("name")
        if not root:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Say: register project /absolute/path on this API host (or use quoted path). Then confirm with operator payload + token.",
            )
        root_path = Path(str(root))
        ok_path, why = project_root_accessible(root_path)
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Cannot register: {why}",
            )
        stem = name or root_path.name
        if not settings_writes_enabled():
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Project registration in chat requires HAM_SETTINGS_WRITE_TOKEN on the API host (same gate as settings apply).",
            )
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            pending_register={"name": stem, "root": str(root_path.resolve())},
            data={
                "message": f"Ready to register **{stem}** at `{root_path.resolve()}`. "
                "Use Confirm + token in the chat panel, or send operator.phase=register_project with confirmed=true.",
                "name": stem,
                "root": str(root_path.resolve()),
            },
        )

    if intent == "launch_run":
        pid = params.get("project_id")
        prompt = str(params.get("prompt") or "").strip()
        if not pid:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Launch needs a registered project id (mention `project.…` or use workspace context).",
            )
        if not prompt:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Add a prompt for the bridge run after 'launch run'.",
            )
        prec = project_store.get_project(str(pid))
        if prec is None:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Unknown project_id {pid!r}.",
            )
        ok_path, why = project_root_accessible(Path(prec.root))
        if not ok_path:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"Cannot launch: {why}",
            )
        if not _launch_token():
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Run launch from chat is disabled until HAM_RUN_LAUNCH_TOKEN is set on the API host.",
            )
        if not os.getenv("OPENROUTER_API_KEY"):
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="OPENROUTER_API_KEY is not set on the API host (required for Hermes review after bridge).",
            )
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            pending_launch={
                "project_id": str(pid),
                "prompt": prompt,
            },
            data={
                "message": "Ready to launch one inspect-class bridge run at the project root. "
                "Confirm in the UI with HAM_RUN_LAUNCH_TOKEN, or send operator.phase=launch_run with confirmed=true.",
                "project_id": pid,
                "prompt": prompt[:500],
            },
        )

    if intent == "droid_preview":
        if params.get("missing") == "workflow_id":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=(
                    "Say which allowlisted workflow: `readonly_repo_audit` or `safe_edit_low` "
                    "(e.g. preview factory droid readonly_repo_audit: …)."
                ),
            )
        if params.get("missing") == "project_id":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Mention a registered `project.…` id or open Chat from a workspace with project context.",
            )
        if params.get("missing") == "user_prompt":
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason="Add a focus line after the workflow id (what to audit or edit).",
            )
        return _droid_preview_turn(
            project_store=project_store,
            project_id=str(params["project_id"]),
            workflow_id=str(params["workflow_id"]),
            user_prompt=str(params["user_prompt"]),
        )

    if intent == "cursor_agent_preview":
        if params.get("missing") == "project_id":
            return _reasoned_block(
                intent,
                "missing_project_context",
                "I can start an agent, but I need an active project or repo first.",
            )
        if params.get("missing") == "task_prompt":
            return _reasoned_block(
                intent,
                "missing_task_prompt",
                "I need one task sentence to build a Cloud Agent preview.",
            )
        pid_raw = params.get("project_id")
        repo_hint = params.get("cursor_repository")
        explicit_cursor_ref = str(params.get("cursor_ref") or "").strip() or None
        resolved_pid: str | None
        if pid_raw:
            resolved_pid = str(pid_raw)
        else:
            resolved_pid = _resolve_project_id_from_repo_hint(
                project_store=project_store,
                repo_hint=str(repo_hint or ""),
            )
            if not resolved_pid:
                if repo_hint:
                    return _reasoned_block(
                        intent,
                        "missing_project_mapping",
                        (
                            "No registered project maps to repository "
                            f"{str(repo_hint)!r}. Add `metadata.cursor_cloud_repository` to a project."
                        ),
                    )
                return _reasoned_block(
                    intent,
                    "missing_project_ref",
                    "No active project is selected for this workspace chat.",
                )
        pid = resolved_pid
        task_prompt = str(params.get("cursor_task_prompt") or "").strip()
        project_context_source = str(params.get("project_context_source") or "").strip().lower()
        prec = project_store.get_project(pid)
        if prec is None:
            if project_context_source == "default":
                return _reasoned_block(
                    intent,
                    "missing_project_context",
                    "I can start an agent, but I need an active project or repo first.",
                )
            return _reasoned_block(
                intent,
                "missing_project_ref",
                f"Unknown project_id {pid!r}.",
            )
        prec = _ensure_project_cursor_metadata(project_store, prec)
        default_cursor_ref = _project_default_cursor_ref(dict(prec.metadata or {}))
        cursor_ref = explicit_cursor_ref or default_cursor_ref
        prev = build_cursor_agent_preview(
            project_id=prec.id,
            project_metadata=dict(prec.metadata or {}),
            cursor_repository=str(repo_hint).strip() if repo_hint else None,
            cursor_task_prompt=task_prompt,
            cursor_ref=cursor_ref,
            cursor_model="default",
            cursor_auto_create_pr=False,
            cursor_branch_name=None,
            cursor_expected_deliverable=None,
            cursor_mission_handling="managed",
        )
        audit_cursor_preview(
            project_id=prec.id,
            proposal_digest=prev.proposal_digest,
            repository=prev.repository,
            ok=prev.ok,
            summary=prev.summary_preview if prev.ok else None,
            blocking_reason=prev.blocking_reason,
            project_root_for_mirror=str(prec.root),
        )
        if not prev.ok:
            reason = (prev.blocking_reason or "").lower()
            if "repository" in reason:
                return _reasoned_block(intent, "missing_repo_context", prev.blocking_reason or "Missing repository.")
            if "api key" in reason:
                return _reasoned_block(intent, "missing_cursor_api_key", prev.blocking_reason or "Missing Cursor API key.")
            return _reasoned_block(intent, "config_gap", prev.blocking_reason or "Cannot build Cloud Agent preview.")
        pending = {
            "project_id": prec.id,
            "proposal_digest": prev.proposal_digest,
            "base_revision": prev.base_revision,
            "repository": prev.repository,
            "cursor_repository": None,
            "cursor_mission_handling": "managed",
            "cursor_task_prompt": task_prompt,
            "cursor_ref": cursor_ref,
            "cursor_model": "default",
            "cursor_auto_create_pr": False,
            "cursor_branch_name": None,
            "cursor_expected_deliverable": None,
            "mutates": prev.mutates,
            "summary_preview": prev.summary_preview or "",
        }
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            pending_cursor_agent=pending,
            data={
                "reason_code": "preview_ready",
                "proposal_digest": prev.proposal_digest,
                "repository": prev.repository,
                "message": prev.summary_preview or "",
            },
        )

    if intent == "cursor_agent_launch":
        if params.get("missing") == "project_id":
            return _reasoned_block(
                intent,
                "missing_project_context",
                "I can start an agent, but I need an active project or repo first.",
            )
        if params.get("missing") == "task_prompt":
            return _reasoned_block(
                intent,
                "missing_task_prompt",
                "I need one task sentence before launching a Cloud Agent mission.",
            )
        pid_raw = params.get("project_id")
        repo_hint = params.get("cursor_repository")
        explicit_cursor_ref = str(params.get("cursor_ref") or "").strip() or None
        resolved_pid: str | None
        if pid_raw:
            resolved_pid = str(pid_raw)
        else:
            resolved_pid = _resolve_project_id_from_repo_hint(
                project_store=project_store,
                repo_hint=str(repo_hint or ""),
            )
            if not resolved_pid:
                if repo_hint:
                    return _reasoned_block(
                        intent,
                        "missing_project_mapping",
                        (
                            "No registered project maps to repository "
                            f"{str(repo_hint)!r}. Add `metadata.cursor_cloud_repository` to a project."
                        ),
                    )
                return _reasoned_block(
                    intent,
                    "missing_project_ref",
                    "No active project is selected for this workspace chat.",
                )
        pid = resolved_pid
        task_prompt = str(params.get("cursor_task_prompt") or "").strip()
        project_context_source = str(params.get("project_context_source") or "").strip().lower()
        prec = project_store.get_project(pid)
        if prec is None:
            if project_context_source == "default":
                return _reasoned_block(
                    intent,
                    "missing_project_context",
                    "I can start an agent, but I need an active project or repo first.",
                )
            return _reasoned_block(
                intent,
                "missing_project_ref",
                f"Unknown project_id {pid!r}.",
            )
        prec = _ensure_project_cursor_metadata(project_store, prec)
        default_cursor_ref = _project_default_cursor_ref(dict(prec.metadata or {}))
        cursor_ref = explicit_cursor_ref or default_cursor_ref
        prev = build_cursor_agent_preview(
            project_id=prec.id,
            project_metadata=dict(prec.metadata or {}),
            cursor_repository=str(repo_hint).strip() if repo_hint else None,
            cursor_task_prompt=task_prompt,
            cursor_ref=cursor_ref,
            cursor_model="default",
            cursor_auto_create_pr=False,
            cursor_branch_name=None,
            cursor_expected_deliverable=None,
            cursor_mission_handling="managed",
        )
        if not prev.ok:
            reason = (prev.blocking_reason or "").lower()
            if "repository" in reason:
                return _reasoned_block(intent, "missing_repo_context", prev.blocking_reason or "Missing repository.")
            if "api key" in reason:
                return _reasoned_block(intent, "missing_cursor_api_key", prev.blocking_reason or "Missing Cursor API key.")
            return _reasoned_block(intent, "config_gap", prev.blocking_reason or "Cannot launch Cloud Agent.")
        api_key = get_effective_cursor_api_key()
        if not api_key:
            return _reasoned_block(
                intent,
                "missing_cursor_api_key",
                "No Cursor API key configured on this API host.",
            )
        ok_launch, payload, blocking, _cp_hid = run_cursor_agent_launch(
            api_key=api_key,
            project_id=prec.id,
            repository=str(prev.repository or ""),
            ref=cursor_ref,
            model="default",
            auto_create_pr=False,
            branch_name=None,
            expected_deliverable=None,
            task_prompt=task_prompt,
            proposal_digest=str(prev.proposal_digest or ""),
            project_root_for_mirror=str(prec.root),
            created_by=_control_plane_created_by(ham_actor),
            mission_handling="managed",
        )
        if not ok_launch:
            reason_code = _map_cursor_launch_failure_code(payload, blocking)
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=f"{reason_code}: {blocking or payload.get('error') or 'Cursor launch failed.'}",
                data={
                    "reason_code": reason_code,
                    "status_code": payload.get("status_code"),
                },
            )
        out_data: dict[str, Any] = {**payload}
        out_data.setdefault("provider", "cursor_cloud_agent")
        agent_id = str(out_data.get("agent_id") or "").strip()
        if agent_id:
            mission = get_managed_mission_store().find_by_cursor_agent_id(agent_id)
            if mission is not None:
                out_data["mission_registry_id"] = mission.mission_registry_id
                out_data["mission_lifecycle"] = mission.mission_lifecycle
                out_data["mission_checkpoint"] = mission.mission_checkpoint_latest
        out_data["reason_code"] = "mission_launched"
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data=out_data,
        )

    if intent == "cursor_agent_status":
        pid = str(params.get("project_id") or "").strip() or None
        aid_raw = str(params.get("cursor_agent_id") or "").strip() or None
        mission: ManagedMission | None = None
        if aid_raw:
            mission = get_managed_mission_store().find_by_cursor_agent_id(aid_raw)
        if mission is None:
            mission = _latest_managed_mission(
                project_store=project_store,
                project_id=pid,
            )
        if mission is None:
            return _reasoned_block(
                intent,
                "missing_mission_context",
                "I could not find a recent managed mission for this workspace yet.",
            )
        aid_raw = mission.cursor_agent_id
        project_for_status = _mission_project_id(mission) or pid
        prec = project_store.get_project(project_for_status) if project_for_status else None
        try:
            aid = sanitize_cursor_agent_id(aid_raw)
        except ValueError as exc:
            return OperatorTurnResult(
                handled=True,
                intent=intent,
                ok=False,
                blocking_reason=str(exc),
            )
        st_d = _managed_mission_payload(mission)
        api_key = get_effective_cursor_api_key()
        ok_st = True
        blocking = None
        if api_key and prec is not None:
            ok_poll, payload, blocking_poll, _cp_hid = run_cursor_agent_status(
                api_key=api_key,
                project_id=prec.id,
                agent_id=aid,
                project_root_for_mirror=str(prec.root),
            )
            if ok_poll:
                refreshed = get_managed_mission_store().find_by_cursor_agent_id(aid)
                if refreshed is not None:
                    st_d = _managed_mission_payload(refreshed)
                    mission = refreshed
                else:
                    st_d.update(payload)
            else:
                st_d["reason_code"] = "status_poll_failed"
                st_d["poll_error"] = blocking_poll
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=ok_st,
            blocking_reason=blocking,
            data=st_d,
        )

    if intent == "cursor_agent_logs":
        pid = str(params.get("project_id") or "").strip() or None
        aid_raw = str(params.get("cursor_agent_id") or "").strip() or None
        mission: ManagedMission | None = None
        if aid_raw:
            mission = get_managed_mission_store().find_by_cursor_agent_id(aid_raw)
        if mission is None:
            mission = _latest_managed_mission(
                project_store=project_store,
                project_id=pid,
            )
        if mission is None:
            return _reasoned_block(
                intent,
                "missing_mission_context",
                "I could not find a recent managed mission for this workspace yet.",
            )
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={
                **_managed_mission_payload(mission, include_events=True),
                "reason_code": "checkpoint_summary_ready",
            },
        )

    if intent == "cursor_agent_cancel":
        pid = str(params.get("project_id") or "").strip() or None
        aid_raw = str(params.get("cursor_agent_id") or "").strip() or None
        mission: ManagedMission | None = None
        if aid_raw:
            mission = get_managed_mission_store().find_by_cursor_agent_id(aid_raw)
        if mission is None:
            mission = _latest_managed_mission(
                project_store=project_store,
                project_id=pid,
            )
        if mission is None:
            return _reasoned_block(
                intent,
                "missing_mission_context",
                "I could not find a managed mission to cancel for this workspace.",
            )
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={
                **_managed_mission_payload(mission),
                "reason_code": "cancel_not_supported",
                "cancel_supported": False,
                "cancel_message": "Cloud Agent cancel is not available in this chat flow yet.",
            },
        )

    if intent == "agent_router_blocked":
        code = str(params.get("reason_code") or "provider_not_implemented")
        provider = str(params.get("provider") or "unknown")
        message = {
            "provider_not_implemented": f"Provider `{provider}` is routed but not executable yet.",
            "provider_not_configured": f"Provider `{provider}` is not configured on this HAM host.",
            "missing_provider": "Specify a provider (e.g. Cursor) or configure a default agent provider.",
            "continue_not_supported": f"Continue/resume is not supported for provider `{provider}` yet.",
        }.get(code, f"Agent route blocked for provider `{provider}`.")
        return _reasoned_block(intent, code, message)

    return OperatorTurnResult(handled=False, ok=True, data={})


def format_operator_assistant_message(op: OperatorTurnResult) -> str:
    """Ham voice: operational summary for the transcript."""
    if not op.handled:
        return ""
    intent = op.intent or "operator"
    if op.blocking_reason:
        return (
            f"**Operator — {intent}**\n\n"
            f"Blocked: {op.blocking_reason}\n\n"
            f"_No changes were made._"
        )
    if op.pending_apply:
        d = op.pending_apply
        diff_n = len(d.get("diff") or [])
        w = d.get("warnings") or []
        warn_txt = ("\nWarnings: " + "; ".join(str(x) for x in w)) if w else ""
        return (
            f"**Operator — preview ready ({intent})**\n\n"
            f"Project `{d.get('project_id')}` — **{diff_n}** diff row(s).{warn_txt}\n\n"
            f"Confirm with the **Apply pending change** control (settings token), or send a structured operator apply from the client.\n\n"
            f"_Digest: `{d.get('proposal_digest', '')[:16]}…`_"
        )
    if op.pending_launch:
        d = op.pending_launch
        return (
            f"**Operator — launch pending ({intent})**\n\n"
            f"Project `{d.get('project_id')}` — ready to run bridge + review + persist under `.ham/runs/`.\n\n"
            f"Confirm with **Confirm launch** (requires `HAM_RUN_LAUNCH_TOKEN` on the API host)."
        )
    if op.pending_register:
        d = op.pending_register
        return (
            f"**Operator — register pending ({intent})**\n\n"
            f"**{d.get('name')}** → `{d.get('root')}`\n\n"
            f"Confirm with **Confirm register** (requires `HAM_SETTINGS_WRITE_TOKEN` on the API host)."
        )
    if op.pending_droid:
        d = op.pending_droid or {}
        mut = d.get("mutates")
        tok = (
            "\n\n**Mutating workflow** — launch requires `confirmed=true` plus "
            "`Authorization: Bearer` matching `HAM_DROID_EXEC_TOKEN` on the API host."
            if mut
            else "\n\n**Read-only workflow** — launch requires `confirmed=true` (no droid exec token)."
        )
        prev = d.get("summary_preview") or ""
        body = (
            f"**Operator — droid preview ready**\n\n"
            f"Project `{d.get('project_id')}` — workflow `{d.get('workflow_id')}`.\n\n"
            f"{prev}{tok}\n\n"
            "Send `operator.phase=droid_launch` with the same `droid_user_prompt`, "
            "`droid_proposal_digest`, and `droid_base_revision` from `operator_result.pending_droid`."
        )
        if op.harness_advisory:
            body += format_harness_advisory_for_operator_message(op.harness_advisory)
        return body
    if op.pending_cursor_agent:
        d = op.pending_cursor_agent or {}
        prev = d.get("summary_preview") or ""
        body = (
            f"**Operator — Cursor Cloud Agent preview**\n\n"
            f"Project `{d.get('project_id')}` → `{d.get('repository')}`\n\n"
            f"{prev}\n\n"
            "Launch with `operator.phase=cursor_agent_launch`, `confirmed=true`, matching "
            "`cursor_proposal_digest` / `cursor_base_revision`, and "
            "`Authorization: Bearer` = `HAM_CURSOR_AGENT_LAUNCH_TOKEN`."
        )
        if op.harness_advisory:
            body += format_harness_advisory_for_operator_message(op.harness_advisory)
        return body
    if intent == "local_repo_operation":
        commands = op.data.get("commands") if isinstance(op.data.get("commands"), list) else []
        if commands:
            cmd_lines = "\n".join(f"- `{str(c)}`" for c in commands[:16])
            return (
                "**Operator — local repo operation**\n\n"
                "This is a local repo/terminal task, not a ManagedMission command.\n\n"
                "Run these commands in the target environment:\n"
                f"{cmd_lines}\n\n"
                "_If authentication is required, use `gh auth login --with-token` in the terminal prompt. "
                "Do not paste tokens in chat._"
            )
        return (
            "**Operator — local repo operation**\n\n"
            "This is a local repo/terminal task, not a ManagedMission command.\n\n"
            "Run the requested git/gh/shell commands directly in the target environment."
        )
    if intent == "list_projects":
        data = op.data.get("projects") or []
        if not data:
            return "**Operator — list_projects**\n\nNo projects registered on this API host."
        lines = [f"- **{p['name']}** (`{p['id']}`) — `{p['root']}`" for p in data]
        return "**Operator — projects**\n\n" + "\n".join(lines)
    if intent == "inspect_project":
        p = op.data.get("project") or {}
        acc = op.data.get("root_accessible")
        flag = "accessible" if acc else "NOT accessible"
        return (
            f"**Operator — inspect_project**\n\n"
            f"- **id:** `{p.get('id')}`\n"
            f"- **root:** `{p.get('root')}`\n"
            f"- **API host sees root:** {flag}\n"
        )
    if intent == "inspect_agents":
        agents = op.data.get("agents") or {}
        profs = agents.get("profiles") or []
        primary = agents.get("primary_agent_id")
        lines = []
        for x in profs:
            sk = ", ".join(x.get("skills") or [])
            lines.append(f"- `{x.get('id')}` — skills: {sk or '(none)'}")
        body = "\n".join(lines) if lines else "(no profiles)"
        return f"**Operator — agents** (primary: `{primary}`)\n\n{body}"
    if intent == "list_runs":
        runs = op.data.get("runs") or []
        scope = op.data.get("scope")
        if not runs:
            return f"**Operator — list_runs** ({scope})\n\nNo runs found."
        lines = [f"- `{r.get('run_id')}` — {r.get('created_at')} — profile `{r.get('profile_id')}`" for r in runs[:25]]
        return f"**Operator — runs** ({scope})\n\n" + "\n".join(lines)
    if intent == "inspect_run":
        ex = op.data.get("log_excerpt") or ""
        return "**Operator — inspect_run**\n\n```text\n" + ex + "\n```"
    if intent == "apply_settings":
        return (
            "**Operator — apply_settings**\n\n"
            f"Applied. New revision: `{op.data.get('new_revision', '')[:16]}…` "
            f"(backup `{op.data.get('backup_id')}`)."
        )
    if intent == "register_project":
        p = op.data.get("project") or {}
        return (
            "**Operator — register_project**\n\n"
            f"Registered **{p.get('name')}** as `{p.get('id')}` → `{p.get('root')}`."
        )
    if intent == "launch_run":
        return (
            "**Operator — launch_run**\n\n"
            f"Run **`{op.data.get('run_id')}`** completed (bridge status: `{op.data.get('bridge_status')}`). "
            f"Persisted: `{op.data.get('persist_path')}`."
        )
    if intent == "droid_launch":
        data = op.data or {}
        extra = ""
        if data.get("stderr") and not op.ok:
            err = str(data.get("stderr") or "")[:2000]
            extra = f"\n\n```text\n{err}\n```"
        elif data.get("stdout") and not data.get("parsed_json"):
            out = str(data.get("stdout") or "")[:2000]
            extra = f"\n\n```text\n{out}\n```"
        return (
            f"**Operator — droid_launch** ({'ok' if op.ok else 'failed'})\n\n"
            f"- **workflow:** `{data.get('workflow_id')}`\n"
            f"- **audit_id:** `{data.get('audit_id')}`\n"
            f"- **runner:** `{data.get('runner_id')}`\n"
            f"- **cwd:** `{data.get('cwd')}`\n"
            f"- **exit_code:** `{data.get('exit_code')}`\n"
            f"- **duration_ms:** `{data.get('duration_ms')}`\n"
            f"- **session_id:** `{data.get('session_id')}`\n\n"
            f"**Summary:** {data.get('summary') or '(none)'}"
            f"{extra}"
        )
    if intent == "cursor_agent_launch":
        data = op.data or {}
        return (
            f"**Cloud Agent mission launched**\n\n"
            f"- **provider:** `Cursor`\n"
            f"- **managed_mission_id:** `{data.get('mission_registry_id') or '(pending sync)'}`\n"
            f"- **cursor_agent_id:** `{data.get('agent_id') or data.get('external_id')}`\n"
            f"- **repo/ref:** `{data.get('repository')}` @ `{data.get('ref') or '(default)'}`\n"
            f"- **status:** `{data.get('status')}`\n"
            f"- **checkpoint:** `{data.get('mission_checkpoint') or '(pending sync)'}`\n"
            f"\nOpen `/workspace/conductor` for live mission state and `/workspace/operations` for history.\n\n"
            "Try next: `status`, `show logs`, `stop`, `what changed?`"
        )
    if intent == "cursor_agent_status":
        data = op.data or {}
        terminal = str(data.get("mission_lifecycle") or "") in ("succeeded", "failed")
        final_hint = (
            f"\n\nFinal artifacts: PR `{data.get('pr_url')}`"
            if terminal and data.get("pr_url")
            else ""
        )
        return (
            f"**Cloud Agent mission status**\n\n"
            f"- **provider:** `Cursor`\n"
            f"- **managed_mission_id:** `{data.get('mission_registry_id')}`\n"
            f"- **agent_id:** `{data.get('agent_id') or data.get('cursor_agent_id')}`\n"
            f"- **lifecycle/checkpoint:** `{data.get('mission_lifecycle')}` / `{data.get('mission_checkpoint')}`\n"
            f"- **status:** `{data.get('status')}`\n"
            f"- **repo/ref:** `{data.get('repository')}` @ `{data.get('ref')}`\n"
            f"- **pr_url:** `{data.get('pr_url')}`\n\n"
            f"Open `/workspace/conductor` and `/workspace/operations` for synchronized mission state."
            f"{final_hint}"
        )
    if intent == "cursor_agent_logs":
        data = op.data or {}
        events = data.get("checkpoint_events") if isinstance(data.get("checkpoint_events"), list) else []
        lines = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            lines.append(
                f"- `{ev.get('observed_at')}` · `{ev.get('checkpoint')}` · `{ev.get('reason') or 'observed'}`"
            )
        if not lines:
            lines = ["- No checkpoint events recorded yet."]
        return (
            f"**Cloud Agent mission checkpoints**\n\n"
            f"- **managed_mission_id:** `{data.get('mission_registry_id')}`\n"
            f"- **agent_id:** `{data.get('agent_id') or data.get('cursor_agent_id')}`\n"
            f"- **latest:** `{data.get('mission_checkpoint')}` ({data.get('last_server_observed_at')})\n\n"
            + "\n".join(lines)
        )
    if intent == "cursor_agent_cancel":
        data = op.data or {}
        return (
            f"**Cloud Agent cancel**\n\n"
            f"- **result:** `{data.get('reason_code')}`\n"
            f"- **managed_mission_id:** `{data.get('mission_registry_id')}`\n"
            f"- **agent_id:** `{data.get('agent_id') or data.get('cursor_agent_id')}`\n"
            f"- **message:** {data.get('cancel_message') or 'Cancel is not currently available.'}\n\n"
            "Mission status remains available via `status` and `show logs`."
        )
    if op.data.get("message"):
        return f"**Operator — {intent}**\n\n{op.data['message']}"
    return f"**Operator — {intent}**\n\n{op.data!r}"
