"""
HAM workspace Operations: JSON-backed agent cards + scheduled jobs (local dev / lift slice).

**Storage:** ``<workspace_root>/.ham/workspace_state/operations.json``

**Semantics:** ``play`` / ``pause`` flip ``active`` / ``paused``; synthetic output lines on play.
No external agent runtimes — local state only.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor

router = APIRouter(prefix="/api/workspace/operations", tags=["workspace-operations"])

_lock = threading.Lock()
StatePath: Path | None = None

AgentStatus = Literal["idle", "active", "paused", "error"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _workspace_root() -> Path:
    import os

    raw = (
        (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip()
        or (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    )
    if raw:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    d = _repo_root() / ".ham_workspace_sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _state_path() -> Path:
    global StatePath
    if StatePath is not None:
        return StatePath
    root = _workspace_root()
    d = root / ".ham" / "workspace_state"
    d.mkdir(parents=True, exist_ok=True)
    StatePath = d / "operations.json"
    return StatePath


def _default_settings() -> dict[str, Any]:
    return {
        "defaultModel": "ham-local",
        "outputsRetention": 50,
        "notes": "",
    }


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"agents": {}, "scheduledJobs": {}, "settings": _default_settings()}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"agents": {}, "scheduledJobs": {}, "settings": _default_settings()}
        data.setdefault("agents", {})
        data.setdefault("scheduledJobs", {})
        data.setdefault("settings", _default_settings())
        return data
    except (OSError, json.JSONDecodeError):
        return {"agents": {}, "scheduledJobs": {}, "settings": _default_settings()}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


class OutputLine(BaseModel):
    at: float
    line: str


class AgentOut(BaseModel):
    id: str
    name: str
    model: str = "ham-local"
    status: AgentStatus
    cronEnabled: bool = False
    cronExpr: str = ""
    outputs: list[OutputLine]
    createdAt: float
    updatedAt: float


def _to_agent(data: dict[str, Any]) -> AgentOut:
    outs: list[OutputLine] = []
    for r in data.get("outputs", []):
        if isinstance(r, dict) and "line" in r:
            outs.append(OutputLine(at=float(r.get("at", 0)), line=str(r.get("line", ""))))
    return AgentOut(
        id=data["id"],
        name=data.get("name", "Agent"),
        model=data.get("model", "ham-local") or "ham-local",
        status=data.get("status", "idle"),
        cronEnabled=bool(data.get("cronEnabled", False)),
        cronExpr=str(data.get("cronExpr", "") or ""),
        outputs=outs,
        createdAt=float(data.get("createdAt", 0)),
        updatedAt=float(data.get("updatedAt", 0)),
    )


def _agent_dict(aid: str) -> dict[str, Any]:
    with _lock:
        raw = _load()
    a = raw.get("agents", {}).get(aid)
    if not a or not isinstance(a, dict):
        raise HTTPException(status_code=404, detail="Agent not found")
    a = dict(a)
    a.setdefault("id", aid)
    return _to_agent(a).model_dump()


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    model: str = Field(default="ham-local", max_length=200)


class PatchAgentBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    cronEnabled: bool | None = None
    cronExpr: str | None = Field(default=None, max_length=200)


class CreateScheduledJobBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cronExpr: str = Field(default="0 * * * *", max_length=200)
    enabled: bool = True


class PatchScheduledJobBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cronExpr: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


class OperationsSettingsBody(BaseModel):
    defaultModel: str | None = Field(default=None, max_length=200)
    outputsRetention: int | None = Field(default=None, ge=1, le=10_000)
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/settings")
def get_settings(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    return {"settings": dict(raw.get("settings") or _default_settings())}


@router.patch("/settings")
def patch_settings(
    body: OperationsSettingsBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        cur = dict(raw.get("settings") or _default_settings())
        if body.defaultModel is not None:
            cur["defaultModel"] = body.defaultModel.strip()
        if body.outputsRetention is not None:
            cur["outputsRetention"] = body.outputsRetention
        if body.notes is not None:
            cur["notes"] = body.notes.strip()
        raw["settings"] = cur
        _save(raw)
    return {"settings": cur}


@router.get("/agents")
def list_agents(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    items: list[AgentOut] = []
    for aid, v in raw.get("agents", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", aid)
        items.append(_to_agent(v))
    items.sort(key=lambda x: (-x.updatedAt, x.name.lower()))
    return {"agents": [x.model_dump() for x in items]}


@router.post("/agents", status_code=201)
def create_agent(
    body: CreateAgentBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    aid = str(uuid.uuid4())
    rec = {
        "id": aid,
        "name": body.name.strip(),
        "model": (body.model or "ham-local").strip() or "ham-local",
        "status": "idle",
        "cronEnabled": False,
        "cronExpr": "",
        "outputs": [],
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("agents", {})[aid] = rec
        _save(data)
    return _to_agent(rec).model_dump()


@router.get("/agents/{agent_id}")
def get_agent(
    agent_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    return _agent_dict(agent_id)


@router.patch("/agents/{agent_id}")
def patch_agent(
    agent_id: str,
    body: PatchAgentBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        agents = raw.setdefault("agents", {})
        a = agents.get(agent_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Agent not found")
        if body.name is not None:
            a["name"] = body.name.strip()
        if body.model is not None:
            a["model"] = body.model.strip() or "ham-local"
        if body.cronEnabled is not None:
            a["cronEnabled"] = body.cronEnabled
        if body.cronExpr is not None:
            a["cronExpr"] = body.cronExpr.strip()
        a["updatedAt"] = time.time()
        _save(raw)
    return _agent_dict(agent_id)


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(
    agent_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    with _lock:
        raw = _load()
        agents = raw.setdefault("agents", {})
        if agent_id not in agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        del agents[agent_id]
        _save(raw)


@router.post("/agents/{agent_id}/play")
def play_agent(
    agent_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    with _lock:
        raw = _load()
        agents = raw.setdefault("agents", {})
        a = agents.get(agent_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Agent not found")
        a["status"] = "active"
        a.setdefault("outputs", []).append(
            {
                "at": now,
                "line": f"[{time.strftime('%H:%M:%S', time.localtime(now))}] Agent active (synthetic; HAM local only).",
            }
        )
        _trim_outputs(a, raw)
        a["updatedAt"] = time.time()
        _save(raw)
    return _agent_dict(agent_id)


def _trim_outputs(agent: dict[str, Any], raw: dict[str, Any]) -> None:
    try:
        lim = int((raw.get("settings") or {}).get("outputsRetention", 50))
    except (TypeError, ValueError):
        lim = 50
    outs = agent.get("outputs")
    if isinstance(outs, list) and len(outs) > lim:
        agent["outputs"] = outs[-lim:]


@router.post("/agents/{agent_id}/pause")
def pause_agent(
    agent_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    with _lock:
        raw = _load()
        agents = raw.setdefault("agents", {})
        a = agents.get(agent_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Agent not found")
        a["status"] = "paused"
        a.setdefault("outputs", []).append({"at": now, "line": "Agent paused."})
        _trim_outputs(a, raw)
        a["updatedAt"] = time.time()
        _save(raw)
    return _agent_dict(agent_id)


@router.get("/scheduled-jobs")
def list_scheduled(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    items: list[dict[str, Any]] = []
    for jid, v in raw.get("scheduledJobs", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", jid)
        items.append(
            {
                "id": jid,
                "name": v.get("name", "Job"),
                "cronExpr": v.get("cronExpr", ""),
                "enabled": bool(v.get("enabled", True)),
                "createdAt": float(v.get("createdAt", 0)),
                "updatedAt": float(v.get("updatedAt", 0)),
            }
        )
    items.sort(key=lambda x: -x["updatedAt"])
    return {"scheduledJobs": items}


@router.post("/scheduled-jobs", status_code=201)
def create_scheduled(
    body: CreateScheduledJobBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    jid = str(uuid.uuid4())
    rec = {
        "id": jid,
        "name": body.name.strip(),
        "cronExpr": (body.cronExpr or "0 * * * *").strip(),
        "enabled": body.enabled,
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("scheduledJobs", {})[jid] = rec
        _save(data)
    return {
        "id": rec["id"],
        "name": rec["name"],
        "cronExpr": rec["cronExpr"],
        "enabled": rec["enabled"],
        "createdAt": rec["createdAt"],
        "updatedAt": rec["updatedAt"],
    }


@router.patch("/scheduled-jobs/{job_id}")
def patch_scheduled(
    job_id: str,
    body: PatchScheduledJobBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("scheduledJobs", {})
        j = jobs.get(job_id)
        if not j or not isinstance(j, dict):
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        if body.name is not None:
            j["name"] = body.name.strip()
        if body.cronExpr is not None:
            j["cronExpr"] = body.cronExpr.strip()
        if body.enabled is not None:
            j["enabled"] = body.enabled
        j["updatedAt"] = time.time()
        out = {
            "id": job_id,
            "name": j.get("name", ""),
            "cronExpr": j.get("cronExpr", ""),
            "enabled": bool(j.get("enabled", True)),
            "createdAt": float(j.get("createdAt", 0)),
            "updatedAt": float(j.get("updatedAt", 0)),
        }
        _save(raw)
    return out


@router.delete("/scheduled-jobs/{job_id}", status_code=204)
def delete_scheduled(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("scheduledJobs", {})
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        del jobs[job_id]
        _save(raw)
