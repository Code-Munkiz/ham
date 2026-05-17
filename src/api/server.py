from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.browser_operator import router as browser_operator_router
from src.api.browser_runtime import router as browser_runtime_router
from src.api.capability_directory import router as capability_directory_router
from src.api.capability_library import router as capability_library_router
from src.api.chat import router as chat_router
from src.api.claude_agent_build import router as claude_agent_build_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.coding_agent_access_settings import router as coding_agent_access_settings_router
from src.api.coding_agents import router as coding_agents_router
from src.api.coding_conductor import router as coding_conductor_router
from src.api.coding_readiness import router as coding_readiness_router
from src.api.control_plane_runs import router as control_plane_runs_router
from src.api.custom_builders import router as custom_builders_router
from src.api.cursor_managed_deploy import router as cursor_managed_deploy_router
from src.api.cursor_managed_deploy_approval import router as cursor_managed_deploy_approval_router
from src.api.cursor_managed_missions import router as cursor_managed_missions_router
from src.api.cursor_managed_vercel import router as cursor_managed_vercel_router
from src.api.cursor_settings import router as cursor_settings_router
from src.api.cursor_skills import router as cursor_skills_router
from src.api.cursor_subagents import router as cursor_subagents_router
from src.api.droid_audit import router as droid_audit_router
from src.api.droid_build import router as droid_build_router
from src.api.goham_planner import router as goham_planner_router
from src.api.hermes_gateway import router as hermes_gateway_router
from src.api.hermes_hub import router as hermes_hub_router
from src.api.hermes_runtime_inventory import router as hermes_runtime_inventory_router
from src.api.hermes_skills import router as hermes_skills_router
from src.api.me import router as me_router
from src.api.media_generation import router as media_generation_router
from src.api.models_catalog import router as models_catalog_router
from src.api.opencode_build import router as opencode_build_router
from src.api.opencode_launch_proxy import router as opencode_launch_proxy_router
from src.api.pna_middleware import private_network_access_middleware
from src.api.project_settings import router as project_settings_router
from src.api.project_snapshots import router as project_snapshots_router
from src.api.social import router as social_router
from src.api.social_policy import router as social_policy_router
from src.api.tts_endpoint import router as tts_router
from src.api.workspace_conductor import router as workspace_conductor_router
from src.api.workspace_files import resolve_workspace_context_snapshot_root
from src.api.workspace_files import router as workspace_files_router
from src.api.workspace_health import router as workspace_health_router
from src.api.workspace_jobs import router as workspace_jobs_router
from src.api.workspace_memory import router as workspace_memory_router
from src.api.workspace_operations import router as workspace_operations_router
from src.api.workspace_profiles import router as workspace_profiles_router
from src.api.workspace_skills import router as workspace_skills_router
from src.api.workspace_tasks import router as workspace_tasks_router
from src.api.workspace_terminal import router as workspace_terminal_router
from src.api.workspace_tools import router as workspace_tools_router
from src.api.workspace_voice_settings import router as workspace_voice_settings_router
from src.api.workspaces import router as workspaces_router
from src.api.builder_sources import router as builder_sources_router
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
    # HAM Vercel production — local runtime (Files/Terminal) from this origin needs CORS on uvicorn.
    "https://ham-nine-mu.vercel.app",
    # Packaged Electron loads the UI from file:// — fetch sends Origin: null (literal).
    "null",
]


def _cors_allow_origins() -> list[str]:
    """Merge env list with defaults so one forgotten origin (e.g. Vercel) does not break others."""
    base = list(_DEFAULT_CORS)
    raw = (os.environ.get("HAM_CORS_ORIGINS") or "").strip()
    if not raw:
        return base
    extra = [o.strip() for o in raw.split(",") if o.strip()]
    return list(dict.fromkeys([*base, *extra]))


def _cors_allow_origin_regex() -> str | None:
    """Optional regex for origins (e.g. all Vercel previews). See HAM_CORS_ORIGIN_REGEX."""
    raw = (os.environ.get("HAM_CORS_ORIGIN_REGEX") or "").strip()
    return raw or None


_cors_kw: dict[str, Any] = {
    "allow_origins": _cors_allow_origins(),
    "allow_origin_regex": _cors_allow_origin_regex(),
    # Workspace adapters use hamApiFetch(..., credentials="include") for cross-origin Vercel → Cloud Run. Without this,
    # browsers omit Access-Control-Allow-Credentials and the response is treated as a CORS failure → "Failed to fetch".
    "allow_credentials": True,
    # PATCH required for /api/projects/{id} metadata updates (chat handoff repo save); browser preflight fails without it.
    "allow_methods": ["GET", "POST", "PATCH", "DELETE"],
    "allow_headers": ["*"],
}
# Starlette 0.45+ / 1.x: without this, OPTIONS with ``Access-Control-Request-Private-Network: true`` returns 400
# ("Disallowed CORS private-network") before our ``private_network_access_middleware`` can attach the allow header.
if "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters:
    _cors_kw["allow_private_network"] = True

app.add_middleware(CORSMiddleware, **_cors_kw)

app.include_router(chat_router)
app.include_router(media_generation_router)
app.include_router(capability_directory_router)
app.include_router(capability_library_router)
app.include_router(browser_runtime_router)
app.include_router(browser_operator_router)
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
app.include_router(goham_planner_router)
app.include_router(project_settings_router)
app.include_router(project_snapshots_router)
app.include_router(social_router)
app.include_router(social_policy_router)
app.include_router(coding_agents_router)
app.include_router(control_plane_runs_router)
app.include_router(droid_audit_router)
app.include_router(droid_build_router)
app.include_router(claude_agent_build_router)
app.include_router(opencode_build_router)
app.include_router(opencode_launch_proxy_router)
app.include_router(coding_readiness_router)
app.include_router(coding_conductor_router)
app.include_router(custom_builders_router)
app.include_router(models_catalog_router)
app.include_router(workspace_health_router)
app.include_router(workspace_files_router)
app.include_router(workspace_jobs_router)
app.include_router(workspace_tasks_router)
app.include_router(workspace_terminal_router)
app.include_router(workspace_conductor_router)
app.include_router(workspace_memory_router)
app.include_router(workspace_skills_router)
app.include_router(workspace_tools_router)
app.include_router(workspace_profiles_router)
app.include_router(workspace_operations_router)
app.include_router(workspace_voice_settings_router)
app.include_router(builder_sources_router)
app.include_router(tts_router)

# Phase 1b: multi-user workspace primitive routers, mounted behind a
# soft-rollback flag (default ON). Set HAM_WORKSPACE_ROUTES_ENABLED=false to
# disable without redeploying the rest of the API. v1 endpoints are NOT
# affected either way.
_workspace_routes_enabled = (
    os.environ.get("HAM_WORKSPACE_ROUTES_ENABLED") or "true"
).strip().lower() in ("1", "true", "yes", "on")
if _workspace_routes_enabled:
    from src.api.workspace_chat_composer_preference import (
        router as workspace_chat_composer_preference_router,
    )

    app.include_router(me_router)
    app.include_router(workspaces_router)
    app.include_router(workspace_chat_composer_preference_router)
    app.include_router(coding_agent_access_settings_router)

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
        "coding_agent_providers": "/api/coding-agents/providers",
        "control_plane_runs": "/api/control-plane-runs?project_id=<id>",
        "capability_directory": "/api/capability-directory",
        "capability_directory_bundles": "/api/capability-directory/bundles",
        "capability_library": "/api/capability-library/library?project_id=<id>",
        "capability_library_aggregate": "/api/capability-library/aggregate?project_id=<id>",
        "tts_health": "/api/tts/health",
        "tts_generate": "/api/tts/generate",
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
            DEFAULT_PROFILE_REGISTRY.get(pid).model_dump() for pid in DEFAULT_PROFILE_REGISTRY.ids()
        ]
    }


@app.get("/api/droids")
async def list_droids(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    return {
        "droids": [
            DEFAULT_DROID_REGISTRY.get(did).model_dump() for did in DEFAULT_DROID_REGISTRY.ids()
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


@app.get("/api/workspace/context-snapshot")
async def get_workspace_context_snapshot(
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    """Context engine snapshot for ``HAM_WORKSPACE_ROOT`` / ``HAM_WORKSPACE_FILES_ROOT`` only (no cwd/sandbox).

    On Cloud Run without those env vars: 503 ``WORKSPACE_ROOT_NOT_CONFIGURED`` — no scan of ``/app``.
    """
    try:
        root = resolve_workspace_context_snapshot_root()
    except ValueError as exc:
        args = exc.args
        code = str(args[0]) if args else "WORKSPACE_ROOT_NOT_CONFIGURED"
        message = str(args[1]) if len(args) > 1 else "Workspace root is not available."
        if code == "WORKSPACE_ROOT_NOT_CONFIGURED":
            raise HTTPException(
                status_code=503,
                detail={"error": code, "message": message},
            ) from None
        raise HTTPException(
            status_code=400,
            detail={"error": code, "message": message},
        ) from None
    payload = context_engine_dashboard_payload(root)
    payload["context_source"] = "local"
    return payload


@app.get("/api/projects/{project_id}/context-engine")
async def get_project_context_engine(
    project_id: str,
    _ham_gate: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    raw_root = Path(record.root).expanduser()
    try:
        root_path = raw_root.resolve()
    except OSError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_ROOT_UNRESOLVABLE",
                    "message": "Registered project root could not be resolved on this API host.",
                }
            },
        )
    if not root_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_ROOT_MISSING",
                    "message": "Registered project root does not exist on this API host.",
                }
            },
        )
    if not root_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_ROOT_NOT_A_DIRECTORY",
                    "message": "Registered project root is not a directory on this API host.",
                }
            },
        )
    return context_engine_dashboard_payload(root_path)


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


# Outermost ASGI: Chrome "Private Network Access" — public HTTPS (e.g. Vercel) → http://127.0.0.1
# needs Access-Control-Allow-Private-Network. Default CORS includes production Vercel; merge via HAM_CORS_ORIGINS.
# Keep the FastAPI instance for OpenAPI and introspection; uvicorn entrypoint is the wrapped ASGI `app`.
fastapi_app = app
app = private_network_access_middleware(fastapi_app)
