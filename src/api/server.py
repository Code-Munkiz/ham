from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.persistence.run_store import RunStore
from src.registry.droids import DEFAULT_DROID_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY

app = FastAPI(title="HAM API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_store = RunStore()


@app.get("/api/status")
async def get_status() -> dict:
    return {
        "version": "0.1.0",
        "run_count": _store.count(),
    }


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
