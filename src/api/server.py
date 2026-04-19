from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.memory_heist import context_engine_dashboard_payload
from src.persistence.project_store import ProjectStore
from src.persistence.run_store import RunStore
from src.registry.droids import DEFAULT_DROID_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY

app = FastAPI(title="HAM API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

_store = RunStore()
_projects = ProjectStore()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def get_status() -> dict:
    return {
        "version": "0.1.0",
        "run_count": _store.count(),
    }


# ---------------------------------------------------------------------------
# Runs (CWD-scoped — the "current" project)
# ---------------------------------------------------------------------------


@app.get("/api/runs")
async def list_runs(limit: int = 50) -> dict:
    runs = _store.list_runs(limit=max(1, min(limit, 200)))
    return {"runs": [r.model_dump() for r in runs]}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    record = _store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return record.model_dump()


# ---------------------------------------------------------------------------
# Profiles & Droids
# ---------------------------------------------------------------------------


@app.get("/api/profiles")
async def list_profiles() -> dict:
    return {
        "profiles": [
            DEFAULT_PROFILE_REGISTRY.get(pid).model_dump()
            for pid in DEFAULT_PROFILE_REGISTRY.ids()
        ]
    }


@app.get("/api/droids")
async def list_droids() -> dict:
    return {
        "droids": [
            DEFAULT_DROID_REGISTRY.get(did).model_dump()
            for did in DEFAULT_DROID_REGISTRY.ids()
        ]
    }


# ---------------------------------------------------------------------------
# Context engine (memory_heist) — read-only dashboard snapshot
# ---------------------------------------------------------------------------


@app.get("/api/context-engine")
async def get_context_engine() -> dict:
    """Snapshot for the API server's current working directory (repo root when started from repo)."""
    return context_engine_dashboard_payload(Path.cwd())


@app.get("/api/projects/{project_id}/context-engine")
async def get_project_context_engine(project_id: str) -> dict:
    record = _projects.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return context_engine_dashboard_payload(Path(record.root))


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class RegisterProjectRequest(BaseModel):
    name: str
    root: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/projects")
async def list_projects() -> dict:
    return {"projects": [p.model_dump() for p in _projects.list_projects()]}


@app.post("/api/projects", status_code=201)
async def register_project(body: RegisterProjectRequest) -> dict:
    root_path = Path(body.root)
    if not root_path.is_dir():
        raise HTTPException(
            status_code=422,
            detail=f"Root path does not exist or is not a directory: {body.root!r}",
        )
    record = _projects.make_record(
        name=body.name,
        root=body.root,
        description=body.description,
        metadata=body.metadata,
    )
    _projects.register(record)
    return record.model_dump()


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict:
    record = _projects.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return record.model_dump()


@app.delete("/api/projects/{project_id}", status_code=204)
async def remove_project(project_id: str) -> None:
    if not _projects.remove(project_id):
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")


@app.get("/api/projects/{project_id}/status")
async def get_project_status(project_id: str) -> dict:
    record = _projects.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    store = RunStore(root=Path(record.root))
    return {
        "project_id": project_id,
        "run_count": store.count(),
    }


@app.get("/api/projects/{project_id}/runs")
async def list_project_runs(project_id: str, limit: int = 50) -> dict:
    record = _projects.get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    store = RunStore(root=Path(record.root))
    runs = store.list_runs(limit=max(1, min(limit, 200)))
    return {"runs": [r.model_dump() for r in runs]}
