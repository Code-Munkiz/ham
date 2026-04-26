from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.browser_runtime import router as browser_runtime_router
from src.api.chat import router as chat_router
from src.api.capability_directory import router as capability_directory_router
from src.api.capability_library import router as capability_library_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.cursor_managed_deploy import router as cursor_managed_deploy_router
from src.api.cursor_managed_deploy_approval import router as cursor_managed_deploy_approval_router
from src.api.cursor_managed_missions import router as cursor_managed_missions_router
from src.api.cursor_managed_vercel import router as cursor_managed_vercel_router
from src.api.cursor_settings import router as cursor_settings_router
from src.api.cursor_skills import router as cursor_skills_router
from src.api.cursor_subagents import router as cursor_subagents_router
from src.api.hermes_gateway import router as hermes_gateway_router
from src.api.hermes_hub import router as hermes_hub_router
from src.api.hermes_runtime_inventory import router as hermes_runtime_inventory_router
from src.api.hermes_skills import router as hermes_skills_router
from src.api.models_catalog import router as models_catalog_router
from src.api.project_settings import router as project_settings_router
from src.api.workspace_files import router as workspace_files_router
from src.api.workspace_jobs import router as workspace_jobs_router
from src.api.workspace_tasks import router as workspace_tasks_router
from src.api.workspace_terminal import router as workspace_terminal_router
from src.api.workspace_conductor import router as workspace_conductor_router
from src.api.workspace_memory import router as workspace_memory_router
from src.api.workspace_operations import router as workspace_operations_router
from src.api.workspace_profiles import router as workspace_profiles_router
from src.api.workspace_skills import router as workspace_skills_router
from src.api.control_plane_runs import router as control_plane_runs_router
from src.ham.agent_profiles import agents_config_from_merged
from src.ham.clerk_auth import HamActor, clerk_authorization_is_clerk_session
from src.memory_heist import context_engine_dashboard_payload, discover_config
from src.persistence.project_store import get_project_store
from src.persistence.run_store import RunStore
from src.registry.droids import DEFAULT_DROID_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY

app = FastAPI(title="HAM API", version="0.1.0")

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # Packaged Electron loads the UI from file:// — fetch sends Origin: null (literal).
    "null",
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
    # PATCH required for /api/projects/{id} metadata updates (chat handoff repo save); browser preflight fails without it.
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(capability_directory_router)
app.include_router(capability_library_router)
app.include_router(browser_runtime_router)
app.include_router(cursor_settings_router)
app.include_router(cursor_managed_deploy_router)
app.include_router(cursor_managed_deploy_approval_router)
app.include_router(cursor_managed_vercel_router)
app.include_router(cursor_managed_missions_router)
app.include_router(cursor_skills_router)
app.include_router(cursor_subagents_router)
app.include_router(hermes_hub_router)
app.include_router(hermes_gateway_router)
app.include_router(hermes_runtime_inventory_router)
app.include_router(hermes_skills_router)
app.include_router(project_settings_router)
app.include_router(control_plane_runs_router)
app.include_router(models_catalog_router)
app.include_router(workspace_files_router)
app.include_router(workspace_jobs_router)
app.include_router(workspace_tasks_router)
app.include_router(workspace_terminal_router)
app.include_router(workspace_conductor_router)
app.include_router(workspace_memory_router)
app.include_router(workspace_skills_router)
app.include_router(workspace_profiles_router)
app.include_router(workspace_operations_router)

_store = RunStore()

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
        "hermes_skills_installed": "/api/hermes-skills/installed",
        "hermes_runtime_inventory": "/api/hermes-runtime/inventory",
        "hermes_gateway_snapshot": "/api/hermes-gateway/snapshot",
        "hermes_gateway_capabilities": "/api/hermes-gateway/capabilities",
        "hermes_gateway_stream": "/api/hermes-gateway/stream",
        "hermes_skills_capabilities": "/api/hermes-skills/capabilities",
        "hermes_skills_install_preview": "/api/hermes-skills/install/preview",
        "hermes_skills_install_apply": "/api/hermes-skills/install/apply",
        "chat_stream": "/api/chat/stream",
        "settings_write_status": "/api/settings/write-status",
        "project_agents": "/api/projects/{project_id}/agents",
        "control_plane_runs": "/api/control-plane-runs?project_id=<id>",
        "capability_directory": "/api/capability-directory",
        "capability_directory_bundles": "/api/capability-directory/bundles",
        "capability_library": "/api/capability-library/library?project_id=<id>",
        "capability_library_aggregate": "/api/capability-library/aggregate?project_id=<id>",
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


@app.get("/api/clerk-access-probe")
async def clerk_access_probe(
    _: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Lightweight check for the dashboard: same Clerk + email gate as other protected routes."""
    return {"ok": True, "clerk_gate_active": clerk_authorization_is_clerk_session()}


# ---------------------------------------------------------------------------
# Runs (CWD-scoped — the "current" project)
# ---------------------------------------------------------------------------


@app.get("/api/runs")
async def list_runs(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    limit: int = 50,
) -> dict:
    runs = _store.list_runs(limit=max(1, min(limit, 200)))
    return {"runs": [r.model_dump() for r in runs]}


@app.get("/api/runs/{run_id}")
async def get_run(
    run_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = _store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return record.model_dump()


# ---------------------------------------------------------------------------
# Profiles & Droids
# ---------------------------------------------------------------------------


@app.get("/api/profiles")
async def list_profiles(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    return {
        "profiles": [
            DEFAULT_PROFILE_REGISTRY.get(pid).model_dump()
            for pid in DEFAULT_PROFILE_REGISTRY.ids()
        ]
    }


@app.get("/api/droids")
async def list_droids(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
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
async def get_context_engine(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    """Snapshot for the API server's current working directory (repo root when started from repo)."""
    return context_engine_dashboard_payload(Path.cwd())


@app.get("/api/projects/{project_id}/context-engine")
async def get_project_context_engine(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return context_engine_dashboard_payload(Path(record.root))


@app.get("/api/projects/{project_id}/agents")
async def get_project_agents(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """HAM Agent Builder — effective profiles from merged Ham config (`.ham/settings.json` chain)."""
    record = get_project_store().get_project(project_id)
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
async def list_projects(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    return {"projects": [p.model_dump() for p in get_project_store().list_projects()]}


@app.post("/api/projects", status_code=201)
async def register_project(
    body: RegisterProjectRequest,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    root_path = Path(body.root)
    if not root_path.is_dir():
        raise HTTPException(
            status_code=422,
            detail=f"Root path does not exist or is not a directory: {body.root!r}",
        )
    record = get_project_store().make_record(
        name=body.name,
        root=body.root,
        description=body.description,
        metadata=body.metadata,
    )
    get_project_store().register(record)
    return record.model_dump()


@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return record.model_dump()


_DEFAULT_DEPLOY_APPROVAL_MODE_KEY = "default_deploy_approval_mode"
_DEFAULT_DEPLOY_APPROVAL_MODE_VALS = frozenset({"off", "audit", "soft", "hard"})


class PatchProjectRequest(BaseModel):
    """Shallow merge into ``ProjectRecord.metadata``. Use JSON ``null`` for a key to remove it."""

    metadata: dict[str, Any] = Field(default_factory=dict)


@app.patch("/api/projects/{project_id}")
async def patch_project(
    project_id: str,
    body: PatchProjectRequest,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    if _DEFAULT_DEPLOY_APPROVAL_MODE_KEY in body.metadata:
        v = body.metadata[_DEFAULT_DEPLOY_APPROVAL_MODE_KEY]
        if v is not None and v not in _DEFAULT_DEPLOY_APPROVAL_MODE_VALS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"metadata.{_DEFAULT_DEPLOY_APPROVAL_MODE_KEY} must be one of "
                    f"{sorted(_DEFAULT_DEPLOY_APPROVAL_MODE_VALS)} or null"
                ),
            )
    merged = {**record.metadata}
    for k, v in body.metadata.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    updated = record.model_copy(update={"metadata": merged})
    get_project_store().register(updated)
    return updated.model_dump()


@app.delete("/api/projects/{project_id}", status_code=204)
async def remove_project(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    if not get_project_store().remove(project_id):
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")


@app.get("/api/projects/{project_id}/status")
async def get_project_status(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    store = RunStore(root=Path(record.root))
    return {
        "project_id": project_id,
        "run_count": store.count(),
    }


@app.get("/api/projects/{project_id}/runs")
async def list_project_runs(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    limit: int = 50,
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    store = RunStore(root=Path(record.root))
    runs = store.list_runs(limit=max(1, min(limit, 200)))
    return {"runs": [r.model_dump() for r in runs]}
