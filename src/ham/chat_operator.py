"""
Server-side operator execution for dashboard chat — real reads/writes via ProjectStore,
settings preview/apply, RunStore, and optional one-shot bridge launch.

Natural-language triggers are intentionally narrow; explicit ``ChatRequest.operator`` is supported
for confirm/apply flows from the UI.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.agent_profiles import (
    HamAgentsConfig,
    agents_config_from_merged,
    validate_agents_config,
)
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
from src.persistence.project_store import ProjectStore
from src.persistence.run_store import RunRecord, RunStore


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


class ChatOperatorPayload(BaseModel):
    """Explicit operator follow-up (confirm apply / register / launch) from the client."""

    model_config = ConfigDict(extra="forbid")

    phase: Literal["apply_settings", "register_project", "launch_run"] | None = None
    confirmed: bool = False
    project_id: str | None = Field(default=None, max_length=180)
    changes: dict[str, Any] | None = None
    base_revision: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    root: str | None = Field(default=None, max_length=4096)
    description: str | None = Field(default=None, max_length=2000)
    prompt: str | None = Field(default=None, max_length=50_000)
    profile_id: str | None = Field(default=None, max_length=128)


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
        text = text[:max_chars] + f"\n… [truncated; full record in .ham/runs/]"
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

    return None


def process_operator_turn(
    *,
    user_text: str,
    project_store: ProjectStore,
    default_project_id: str | None,
    operator_payload: ChatOperatorPayload | None,
    authorization: str | None,
) -> OperatorTurnResult | None:
    if not operator_enabled():
        return None

    # Explicit client phase takes precedence
    if operator_payload and operator_payload.phase:
        return _execute_explicit_phase(
            operator_payload,
            project_store=project_store,
            authorization=authorization,
        )

    parsed = try_heuristic_intent(user_text, default_project_id=default_project_id)
    if not parsed:
        return None
    intent, params = parsed
    out = _dispatch_intent(
        intent,
        params,
        project_store=project_store,
        authorization=authorization,
        confirmed=False,
    )
    if not out.handled:
        return None
    return out


def _execute_explicit_phase(
    op: ChatOperatorPayload,
    *,
    project_store: ProjectStore,
    authorization: str | None,
) -> OperatorTurnResult:
    if op.phase == "apply_settings":
        if not op.confirmed:
            return OperatorTurnResult(
                handled=True,
                intent="apply_settings",
                ok=False,
                blocking_reason="Apply requires confirmed=true from the client.",
            )
        _require_bearer(authorization, _settings_token(), code="SETTINGS_WRITES_DISABLED")
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
        _require_bearer(authorization, _settings_token(), code="OPERATOR_REGISTER")
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
        _require_bearer(authorization, _launch_token(), code="RUN_LAUNCH")
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

    return OperatorTurnResult(handled=False, ok=True, data={})


def _dispatch_intent(
    intent: str,
    params: dict[str, Any],
    *,
    project_store: ProjectStore,
    authorization: str | None,
    confirmed: bool,
) -> OperatorTurnResult:
    if intent == "list_projects":
        projects = project_store.list_projects()
        return OperatorTurnResult(
            handled=True,
            intent=intent,
            ok=True,
            data={"projects": [x.model_dump() for x in projects], "count": len(projects)},
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
    if op.data.get("message"):
        return f"**Operator — {intent}**\n\n{op.data['message']}"
    return f"**Operator — {intent}**\n\n{op.data!r}"
