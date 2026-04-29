"""
HAM workspace Skills: JSON-backed skill catalog + install/enable (local v0).

**Storage:** ``<workspace_root>/.ham/workspace_state/skills.json``

**Semantics:** catalog entries with ``installed`` / ``enabled`` toggles. Not Hermes ``/api/skills``;
HAM-local bridge for Workspace UI only.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.hermes_skills_catalog import (
    catalog_note,
    catalog_schema_version,
    catalog_upstream_meta,
    get_catalog_entry_detail,
    list_catalog_entries,
)
from src.ham.hermes_skills_live import build_skills_installed_overlay

router = APIRouter(prefix="/api/workspace/skills", tags=["workspace-skills"])

_lock = threading.Lock()
StatePath: Path | None = None

_DEFAULT_CATALOG: list[dict[str, Any]] = [
    {
        "id": "ham-local-docs",
        "name": "Documentation helper",
        "description": "Summarize and search local docs (HAM-local v0; no tool execution).",
    },
    {
        "id": "ham-local-plan",
        "name": "Plan drafting",
        "description": "Structured planning prompts for the workspace (label-only).",
    },
]
_BUILTIN_SKILL_IDS = frozenset(c["id"] for c in _DEFAULT_CATALOG)


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
    StatePath = d / "skills.json"
    return StatePath


def _ensure_catalog(raw: dict[str, Any]) -> None:
    skills = raw.setdefault("skills", {})
    for c in _DEFAULT_CATALOG:
        sid = c["id"]
        if sid not in skills:
            now = time.time()
            skills[sid] = {
                "id": sid,
                "name": c["name"],
                "description": c.get("description", ""),
                "installed": False,
                "enabled": False,
                "config": "",
                "createdAt": now,
                "updatedAt": now,
            }


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        d: dict[str, Any] = {"skills": {}}
        _ensure_catalog(d)
        return d
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"skills": {}}
        data.setdefault("skills", {})
        _ensure_catalog(data)
        return data
    except (OSError, json.JSONDecodeError):
        return {"skills": {}}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


class SkillOut(BaseModel):
    id: str
    name: str
    description: str = ""
    installed: bool = False
    enabled: bool = False
    config: str = ""
    createdAt: float
    updatedAt: float


def _to_skill(d: dict[str, Any]) -> SkillOut:
    return SkillOut(
        id=d["id"],
        name=(d.get("name", "Skill") or "Skill")[:200],
        description=(d.get("description", "") or "")[:5000],
        installed=bool(d.get("installed", False)),
        enabled=bool(d.get("enabled", False)),
        config=(d.get("config", "") or "")[:8000],
        createdAt=float(d.get("createdAt", 0)),
        updatedAt=float(d.get("updatedAt", 0)),
    )


class CreateSkillBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class PatchSkillBody(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    installed: bool | None = None
    enabled: bool | None = None
    config: str | None = Field(default=None, max_length=8000)


@router.get("/items")
def list_skills(
    q: str | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    ql = (q or "").strip().lower()
    items: list[SkillOut] = []
    for sid, v in raw.get("skills", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", sid)
        o = _to_skill(v)
        if ql and ql not in f"{o.name} {o.description}".lower():
            continue
        items.append(o)
    items.sort(key=lambda x: x.name.lower())
    return {"skills": [x.model_dump() for x in items]}


@router.post("/items", status_code=201)
def create_custom_skill(
    body: CreateSkillBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    now = time.time()
    sid = str(uuid.uuid4())
    rec = {
        "id": sid,
        "name": body.name.strip(),
        "description": body.description.strip(),
        "installed": True,
        "enabled": True,
        "config": "",
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("skills", {})[sid] = rec
        _save(data)
    return _to_skill(rec).model_dump()


@router.get("/items/{skill_id}")
def get_skill(
    skill_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    v = raw.get("skills", {}).get(skill_id)
    if not v or not isinstance(v, dict):
        raise HTTPException(status_code=404, detail="Skill not found")
    v = dict(v)
    v.setdefault("id", skill_id)
    return _to_skill(v).model_dump()


@router.patch("/items/{skill_id}")
def patch_skill(
    skill_id: str,
    body: PatchSkillBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        skills = raw.setdefault("skills", {})
        a = skills.get(skill_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Skill not found")
        if body.name is not None:
            a["name"] = body.name.strip()
        if body.description is not None:
            a["description"] = body.description.strip()
        if body.installed is not None:
            a["installed"] = body.installed
        if body.enabled is not None:
            a["enabled"] = body.enabled
        if body.config is not None:
            a["config"] = body.config.strip()
        a["updatedAt"] = time.time()
        _save(raw)
        out = dict(a)
        out.setdefault("id", skill_id)
    return _to_skill(out).model_dump()


@router.delete("/items/{skill_id}", status_code=204)
def delete_skill(
    skill_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> None:
    with _lock:
        raw = _load()
        if skill_id in _BUILTIN_SKILL_IDS:
            raise HTTPException(status_code=400, detail="Cannot delete built-in catalog entry")
        skills = raw.setdefault("skills", {})
        if skill_id not in skills:
            raise HTTPException(status_code=404, detail="Skill not found")
        del skills[skill_id]
        _save(raw)


# --- Hermes static catalog + live overlay (same sources as /shop Skills tab, server-side only) ---


@router.get("/hermes-catalog")
def workspace_hermes_static_catalog(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    """Vendored Hermes-runtime skills catalog (read-only); mirrors GET /api/hermes-skills/catalog."""
    entries = list_catalog_entries()
    payload: dict[str, Any] = {
        "kind": "hermes_runtime_skills_catalog",
        "schema_version": catalog_schema_version(),
        "count": len(entries),
        "entries": entries,
        "readOnly": True,
        "source": "hermes_static_catalog",
    }
    up = catalog_upstream_meta()
    if up:
        payload["upstream"] = up
    note = catalog_note()
    if note:
        payload["catalog_note"] = note
    return payload


@router.get("/hermes-catalog/{catalog_id}")
def workspace_hermes_static_catalog_entry(
    catalog_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    """Single catalog entry; mirrors GET /api/hermes-skills/catalog/{catalog_id}."""
    detail = get_catalog_entry_detail(catalog_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "HERMES_SKILL_CATALOG_UNKNOWN",
                    "message": f"No Hermes catalog entry for id {catalog_id!r}.",
                }
            },
        )
    return {
        "kind": "hermes_runtime_skill_detail",
        "entry": detail,
        "readOnly": True,
        "source": "hermes_static_catalog",
    }


@router.get("/hermes-live-overlay")
def workspace_hermes_live_skills_overlay(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    """Read-only live Hermes install observation; same payload as GET /api/hermes-skills/installed."""
    return build_skills_installed_overlay()
