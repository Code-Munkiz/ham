from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.browser_runtime import router as browser_runtime_router
from src.api.chat import router as chat_router
from src.api.cursor_settings import router as cursor_settings_router
from src.api.cursor_skills import router as cursor_skills_router
from src.api.cursor_subagents import router as cursor_subagents_router
from src.api.hermes_skills import router as hermes_skills_router
from src.api.models_catalog import router as models_catalog_router
from src.api.project_settings import router as project_settings_router
from src.ham.agent_profiles import agents_config_from_merged
from src.memory_heist import context_engine_dashboard_payload, discover_config
from src.persistence.project_store import ProjectStore
from src.persistence.run_store import RunStore
from src.registry.droids import DEFAULT_DROID_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY

app = FastAPI(title="HAM API", version="0.1.0")

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _cors_allow_origins() -> list[str]:
    raw = (os.environ.get("HAM_CORS_ORIGINS") or "").strip()
    if not raw:
        return list(_DEFAULT_CORS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def _cors_allow_origin_regex() -> str | None:
    """Optional regex for origins (e.g. all Vercel previews). See HAM_CORS_ORIGIN_REGEX."""
    raw = (os.environ.get("HAM_CORS_ORIGIN_REGEX") or "").strip()
    return raw or None


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(browser_runtime_router)
app.include_router(cursor_settings_router)
app.include_router(cursor_skills_router)
app.include_router(cursor_subagents_router)
app.include_router(hermes_skills_router)
app.include_router(project_settings_router)
app.include_router(models_catalog_router)

_store = RunStore()
_projects = ProjectStore()


def get_project_store() -> ProjectStore:
    """Shared project registry (lazy consumers import from server after app load)."""
    return _projects


# ---------------------------------------------------------------------------
# Root (browser opens service URL with no path)
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict[str, Any]:
    """So opening the Cloud Run URL in a tab is not a bare 404 JSON."""
    return {
        "service": "HAM API",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "status": "/api/status",
        "cursor_skills": "/api/cursor-skills",
        "cursor_subagents": "/api/cursor-subagents",
        "hermes_skills_catalog": "/api/hermes-skills/catalog",
        "hermes_skills_capabilities": "/api/hermes-skills/capabilities",
        "hermes_skills_install_preview": "/api/hermes-skills/install/preview",
        "hermes_skills_install_apply": "/api/hermes-skills/install/apply",
        "chat_stream": "/api/chat/stream",
        "settings_write_status": "/api/settings/write-status",
        "project_agents": "/api/projects/{project_id}/agents",
    }


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def get_status() -> dict:
    return {
        "version": "0.1.0",
        "run_count": _store.count(),
        "capabilities": {
            "project_agent_profiles_read": True,
        },
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


@app.get("/api/projects/{project_id}/agents")
async def get_project_agents(project_id: str) -> dict[str, Any]:
    """HAM Agent Builder — effective profiles from merged Ham config (`.ham/settings.json` chain)."""
    record = _projects.get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    merged = discover_config(Path(record.root)).merged
    cfg = agents_config_from_merged(merged)
    return {
        "kind": "ham_agent_profiles",
        "agents": cfg.model_dump(mode="json"),
    }


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
