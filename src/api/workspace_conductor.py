"""
HAM workspace Conductor: JSON-backed missions (local dev / lift slice).

**Storage:** ``<workspace_root>/.ham/workspace_state/conductor.json``

**Semantics:** Missions move through ``draft`` → ``running`` → ``completed`` (or ``failed``).
``POST .../run`` simulates a worker pass (synthetic lines, optional cost increment) — no external APIs.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor

router = APIRouter(prefix="/api/workspace/conductor", tags=["workspace-conductor"])

_lock = threading.Lock()
StatePath: Path | None = None

QuickAction = Literal["research", "build", "review", "deploy"]
MissionPhase = Literal["draft", "running", "completed", "failed"]


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
    StatePath = d / "conductor.json"
    return StatePath


def _default_settings() -> dict[str, Any]:
    return {
        "budgetCents": 10_000,
        "defaultModel": "ham-local",
        "notes": "",
    }


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"missions": {}, "settings": _default_settings()}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"missions": {}, "settings": _default_settings()}
        data.setdefault("missions", {})
        data.setdefault("settings", _default_settings())
        return data
    except (OSError, json.JSONDecodeError):
        return {"missions": {}, "settings": _default_settings()}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


QUICK_TEMPLATES: dict[str, str] = {
    "research": "Research mission: gather context, summarize findings, list open questions.",
    "build": "Build mission: implement the target, add tests, verify locally.",
    "review": "Review mission: audit diffs, note risks, approve or request changes.",
    "deploy": "Deploy mission: validate release checklist, promote, monitor rollout.",
}


class OutputLine(BaseModel):
    at: float
    line: str


class MissionOut(BaseModel):
    id: str
    title: str
    body: str = ""
    phase: MissionPhase
    quickAction: str | None = None
    outputs: list[OutputLine]
    costCents: int = 0
    createdAt: float
    updatedAt: float


def _to_mission(data: dict[str, Any]) -> MissionOut:
    outs: list[OutputLine] = []
    for r in data.get("outputs", []):
        if isinstance(r, dict) and "line" in r:
            outs.append(OutputLine(at=float(r.get("at", 0)), line=str(r.get("line", ""))))
    return MissionOut(
        id=data["id"],
        title=data.get("title", "Mission"),
        body=data.get("body", "") or "",
        phase=data.get("phase", "draft"),
        quickAction=data.get("quickAction"),
        outputs=outs,
        costCents=int(data.get("costCents", 0)),
        createdAt=float(data.get("createdAt", 0)),
        updatedAt=float(data.get("updatedAt", 0)),
    )


def _mission_dict(mid: str) -> dict[str, Any]:
    with _lock:
        raw = _load()
    m = raw.get("missions", {}).get(mid)
    if not m or not isinstance(m, dict):
        raise HTTPException(status_code=404, detail="Mission not found")
    m = dict(m)
    m.setdefault("id", mid)
    return _to_mission(m).model_dump()


class CreateMissionBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="")
    quickAction: QuickAction | None = None


class PatchMissionBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    phase: MissionPhase | None = None
    quickAction: QuickAction | None = None


class AppendOutputBody(BaseModel):
    line: str = Field(min_length=1, max_length=4000)


class ConductorSettingsBody(BaseModel):
    budgetCents: int | None = Field(default=None, ge=0, le=1_000_000_000)
    defaultModel: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/settings")
def get_settings(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    s = dict(raw.get("settings") or _default_settings())
    return {"settings": s}


@router.patch("/settings")
def patch_settings(
    body: ConductorSettingsBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        cur = dict(raw.get("settings") or _default_settings())
        if body.budgetCents is not None:
            cur["budgetCents"] = body.budgetCents
        if body.defaultModel is not None:
            cur["defaultModel"] = body.defaultModel.strip()
        if body.notes is not None:
            cur["notes"] = body.notes.strip()
        raw["settings"] = cur
        _save(raw)
    return {"settings": cur}


@router.get("/missions")
def list_missions(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    q: str | None = Query(default=None),
    phase: MissionPhase | None = Query(default=None),
    historyOnly: bool = Query(default=False, description="Only completed/failed"),
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    items: list[MissionOut] = []
    for mid, v in raw.get("missions", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", mid)
        m = _to_mission(v)
        if historyOnly and m.phase not in ("completed", "failed"):
            continue
        if phase and m.phase != phase:
            continue
        if q and q.strip():
            blob = f"{m.title} {m.body}".lower()
            if q.lower() not in blob:
                continue
        items.append(m)
    items.sort(key=lambda x: -x.updatedAt)
    return {"missions": [x.model_dump() for x in items]}


def _create_mission_record(body: CreateMissionBody) -> dict[str, Any]:
    now = time.time()
    mid = str(uuid.uuid4())
    b = (body.body or "").strip()
    qa: str | None = body.quickAction
    if qa and not b:
        b = QUICK_TEMPLATES.get(qa, b)
    rec: dict[str, Any] = {
        "id": mid,
        "title": body.title.strip(),
        "body": b,
        "phase": "draft",
        "quickAction": qa,
        "outputs": [],
        "costCents": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("missions", {})[mid] = rec
        _save(data)
    return _to_mission(rec).model_dump()


@router.post("/missions", status_code=201)
def create_mission(
    body: CreateMissionBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    return _create_mission_record(body)


class QuickCreateBody(BaseModel):
    quick: QuickAction
    title: str | None = Field(default=None, max_length=300)


@router.post("/missions/quick", status_code=201)
def create_mission_quick(
    body: QuickCreateBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    qa = body.quick
    title = (body.title or f"{qa.title()} mission").strip()
    b = QUICK_TEMPLATES[qa]
    return _create_mission_record(CreateMissionBody(title=title, body=b, quickAction=qa))


@router.get("/missions/{mission_id}")
def get_mission(
    mission_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    return _mission_dict(mission_id)


@router.patch("/missions/{mission_id}")
def patch_mission(
    mission_id: str,
    body: PatchMissionBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        missions = raw.setdefault("missions", {})
        m = missions.get(mission_id)
        if not m or not isinstance(m, dict):
            raise HTTPException(status_code=404, detail="Mission not found")
        if body.title is not None:
            m["title"] = body.title.strip()
        if body.body is not None:
            m["body"] = body.body.strip()
        if body.phase is not None:
            m["phase"] = body.phase
        if body.quickAction is not None:
            m["quickAction"] = body.quickAction
        m["updatedAt"] = time.time()
        _save(raw)
    return _mission_dict(mission_id)


@router.post("/missions/{mission_id}/output")
def append_output(
    mission_id: str,
    body: AppendOutputBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    with _lock:
        raw = _load()
        missions = raw.setdefault("missions", {})
        m = missions.get(mission_id)
        if not m or not isinstance(m, dict):
            raise HTTPException(status_code=404, detail="Mission not found")
        m.setdefault("outputs", []).append({"at": now, "line": body.line.strip()})
        m["updatedAt"] = now
        _save(raw)
    return _mission_dict(mission_id)


@router.post("/missions/{mission_id}/run")
def run_mission(
    mission_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Synthetic run: draft/running → completed with worker lines (no external calls)."""
    now = time.time()
    with _lock:
        raw = _load()
        missions = raw.setdefault("missions", {})
        m = missions.get(mission_id)
        if not m or not isinstance(m, dict):
            raise HTTPException(status_code=404, detail="Mission not found")
        st = m.get("phase", "draft")
        if st in ("completed", "failed"):
            raise HTTPException(status_code=400, detail="Mission is already terminal")
        if st == "running":
            raise HTTPException(status_code=409, detail="Mission is already running")
        m["phase"] = "running"
        m["updatedAt"] = now
        lines = [
            f"[{time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now))}] Worker started (synthetic).",
            f"Mission: {m.get('title', '')}",
            "Phase check — HAM Conductor bridge (no upstream Hermes/Cursor).",
            "— completed —",
        ]
        m.setdefault("outputs", []).extend([{"at": now + i * 0.01, "line": ln} for i, ln in enumerate(lines)])
        m["phase"] = "completed"
        m["costCents"] = int(m.get("costCents", 0)) + 25
        m["updatedAt"] = time.time()
        _save(raw)
    return _mission_dict(mission_id)


@router.post("/missions/{mission_id}/fail")
def fail_mission(
    mission_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    with _lock:
        raw = _load()
        missions = raw.setdefault("missions", {})
        m = missions.get(mission_id)
        if not m or not isinstance(m, dict):
            raise HTTPException(status_code=404, detail="Mission not found")
        m["phase"] = "failed"
        m.setdefault("outputs", []).append({"at": now, "line": "Mission marked failed (manual)."})
        m["updatedAt"] = now
        _save(raw)
    return _mission_dict(mission_id)


@router.delete("/missions/{mission_id}", status_code=204)
def delete_mission(
    mission_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    with _lock:
        raw = _load()
        missions = raw.setdefault("missions", {})
        if mission_id not in missions:
            raise HTTPException(status_code=404, detail="Mission not found")
        del missions[mission_id]
        _save(raw)
