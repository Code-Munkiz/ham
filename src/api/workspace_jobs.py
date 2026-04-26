"""
HAM workspace jobs: JSON-backed job cards with run history (local dev / lift slice).

**Storage:** ``<workspace_root>/.ham/workspace_state/jobs.json``
Same workspace root resolution as ``workspace_files`` (``HAM_WORKSPACE_ROOT`` / legacy / sandbox).

**Semantics:** ``paused`` means the job queue is paused (``run`` is rejected until ``resume``).
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

router = APIRouter(prefix="/api/workspace/jobs", tags=["workspace-jobs"])

_lock = threading.Lock()
StatePath: Path | None = None


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
    StatePath = d / "jobs.json"
    return StatePath


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"jobs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"jobs": {}}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


JobStatus = Literal["idle", "running", "paused", "failed"]


class RunEntry(BaseModel):
    id: str
    startedAt: float
    finishedAt: float
    status: Literal["ok", "error", "cancelled"]
    output: str = ""


class JobOut(BaseModel):
    id: str
    name: str
    description: str = ""
    status: JobStatus
    createdAt: float
    updatedAt: float
    runs: list[RunEntry]


def _to_job(data: dict[str, Any]) -> JobOut:
    runs = []
    for r in data.get("runs", []):
        if isinstance(r, dict):
            runs.append(RunEntry(**r))
    return JobOut(
        id=data["id"],
        name=data.get("name", "Job"),
        description=data.get("description", "") or "",
        status=data.get("status", "idle"),
        createdAt=float(data.get("createdAt", 0)),
        updatedAt=float(data.get("updatedAt", 0)),
        runs=runs,
    )


def _job_to_dict(job_id: str) -> dict[str, Any]:
    with _lock:
        raw = _load()
    j = raw.get("jobs", {}).get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    jd = dict(j)
    jd.setdefault("id", job_id)
    return _to_job(jd).model_dump()


class CreateJobBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="")


class PatchJobBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


@router.get("")
def list_jobs(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    q: str | None = Query(default=None, description="Search name/description"),
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    jobs: dict[str, Any] = raw.get("jobs", {})
    items: list[JobOut] = []
    for sid, v in jobs.items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", sid)
        j = _to_job(v)
        if q and q.strip():
            t = f"{j.name} {j.description}".lower()
            if q.lower() not in t:
                continue
        items.append(j)
    items.sort(key=lambda x: -x.updatedAt)
    return {"jobs": [j.model_dump() for j in items]}


@router.post("", status_code=201)
def create_job(
    body: CreateJobBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    sid = str(uuid.uuid4())
    rec = {
        "id": sid,
        "name": body.name.strip(),
        "description": (body.description or "").strip(),
        "status": "idle",
        "createdAt": now,
        "updatedAt": now,
        "runs": [],
    }
    with _lock:
        data = _load()
        data.setdefault("jobs", {})[sid] = rec
        _save(data)
    return _to_job(rec).model_dump()


@router.get("/{job_id}")
def get_job(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    return _job_to_dict(job_id)


@router.patch("/{job_id}")
def patch_job(
    job_id: str,
    body: PatchJobBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("jobs", {})
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        if body.name is not None:
            j["name"] = body.name.strip()
        if body.description is not None:
            j["description"] = body.description.strip() if body.description else ""
        j["updatedAt"] = time.time()
        _save(raw)
    return _job_to_dict(job_id)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("jobs", {})
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        del jobs[job_id]
        _save(raw)


@router.post("/{job_id}/run")
def run_job(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    run_id = str(uuid.uuid4())
    with _lock:
        raw = _load()
        jobs = raw.setdefault("jobs", {})
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        st = j.get("status", "idle")
        if st == "paused":
            raise HTTPException(status_code=400, detail="Job is paused; resume before running")
        if st == "running":
            raise HTTPException(status_code=409, detail="Job is already running")
        j["status"] = "running"
        j["updatedAt"] = now
        out_lines = [
            f"[{time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now))}] Starting run {run_id[:8]}…",
            f"Job: {j.get('name', '')}",
            "HAM workspace job run (synthetic; no external scheduler).",
            "— done —",
        ]
        output = "\n".join(out_lines)
        run = {
            "id": run_id,
            "startedAt": now,
            "finishedAt": now + 0.01,
            "status": "ok",
            "output": output,
        }
        j.setdefault("runs", []).insert(0, run)
        j["status"] = "idle"
        j["updatedAt"] = time.time()
        _save(raw)
    return _job_to_dict(job_id)


@router.post("/{job_id}/pause")
def pause_job(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("jobs", {})
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        st = j.get("status", "idle")
        if st == "paused":
            raise HTTPException(status_code=400, detail="Job is already paused")
        if st == "running":
            raise HTTPException(status_code=400, detail="Cannot pause while running a slice run")
        j["status"] = "paused"
        j["updatedAt"] = time.time()
        _save(raw)
    return _job_to_dict(job_id)


@router.post("/{job_id}/resume")
def resume_job(
    job_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        jobs = raw.setdefault("jobs", {})
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        if j.get("status") != "paused":
            raise HTTPException(status_code=400, detail="Job is not paused")
        j["status"] = "idle"
        j["updatedAt"] = time.time()
        _save(raw)
    return _job_to_dict(job_id)
