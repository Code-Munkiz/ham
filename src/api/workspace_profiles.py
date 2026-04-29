"""
HAM workspace Profiles: JSON-backed agent-style profiles (local v0).

**Storage:** ``<workspace_root>/.ham/workspace_state/profiles.json``

**Semantics:** name, emoji, model label, system prompt; one optional ``defaultProfileId``.
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

router = APIRouter(prefix="/api/workspace/profiles", tags=["workspace-profiles"])

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
    StatePath = d / "profiles.json"
    return StatePath


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"profiles": {}, "defaultProfileId": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"profiles": {}, "defaultProfileId": None}
        data.setdefault("profiles", {})
        if "defaultProfileId" not in data:
            data["defaultProfileId"] = None
        return data
    except (OSError, json.JSONDecodeError):
        return {"profiles": {}, "defaultProfileId": None}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


class ProfileOut(BaseModel):
    id: str
    name: str
    emoji: str = "🤖"
    model: str = "ham-local"
    systemPrompt: str = ""
    isDefault: bool = False
    createdAt: float
    updatedAt: float


def _to_profile(d: dict[str, Any], default_id: str | None) -> ProfileOut:
    pid = d.get("id", "")
    return ProfileOut(
        id=pid,
        name=(d.get("name", "Profile") or "Profile")[:200],
        emoji=(str(d.get("emoji", "🤖") or "🤖"))[:8],
        model=(d.get("model", "ham-local") or "ham-local")[:200],
        systemPrompt=(d.get("systemPrompt", "") or "")[:16_000],
        isDefault=bool(default_id and pid == default_id),
        createdAt=float(d.get("createdAt", 0)),
        updatedAt=float(d.get("updatedAt", 0)),
    )


class CreateProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    emoji: str = Field(default="🤖", max_length=8)
    model: str = Field(default="ham-local", max_length=200)
    systemPrompt: str = Field(default="", max_length=16_000)


class PatchProfileBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    emoji: str | None = Field(default=None, max_length=8)
    model: str | None = Field(default=None, max_length=200)
    systemPrompt: str | None = Field(default=None, max_length=16_000)


@router.get("")
def list_profiles(
    q: str | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    def_id: str | None = raw.get("defaultProfileId")
    if not isinstance(def_id, str) or not def_id:
        def_id = None
    ql = (q or "").strip().lower()
    out: list[ProfileOut] = []
    for pid, v in raw.get("profiles", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", pid)
        o = _to_profile(v, def_id)
        if ql and ql not in f"{o.name} {o.systemPrompt} {o.model} {o.emoji}".lower():
            continue
        out.append(o)
    out.sort(key=lambda x: -x.updatedAt)
    return {"profiles": [x.model_dump() for x in out], "defaultProfileId": def_id}


@router.post("", status_code=201)
def create_profile(
    body: CreateProfileBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    now = time.time()
    pid = str(uuid.uuid4())
    em = (body.emoji or "🤖").strip() or "🤖"
    rec = {
        "id": pid,
        "name": body.name.strip(),
        "emoji": em[:8],
        "model": (body.model or "ham-local").strip() or "ham-local",
        "systemPrompt": body.systemPrompt.strip()[:16_000],
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("profiles", {})[pid] = rec
        if not data.get("defaultProfileId"):
            data["defaultProfileId"] = pid
        _save(data)
    return _to_profile(rec, data.get("defaultProfileId")).model_dump()


@router.get("/{profile_id}")
def get_profile(
    profile_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    def_id: str | None = raw.get("defaultProfileId")
    if not isinstance(def_id, str):
        def_id = None
    v = raw.get("profiles", {}).get(profile_id)
    if not v or not isinstance(v, dict):
        raise HTTPException(status_code=404, detail="Profile not found")
    v = dict(v)
    v.setdefault("id", profile_id)
    return {**_to_profile(v, def_id).model_dump()}


@router.patch("/{profile_id}")
def patch_profile(
    profile_id: str,
    body: PatchProfileBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        profs = raw.setdefault("profiles", {})
        a = profs.get(profile_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Profile not found")
        if body.name is not None:
            a["name"] = body.name.strip()
        if body.emoji is not None:
            a["emoji"] = (body.emoji.strip() or "🤖")[:8]
        if body.model is not None:
            a["model"] = body.model.strip() or "ham-local"
        if body.systemPrompt is not None:
            a["systemPrompt"] = body.systemPrompt.strip()[:16_000]
        a["updatedAt"] = time.time()
        _save(raw)
        def_id: str | None = raw.get("defaultProfileId")
        if not isinstance(def_id, str):
            def_id = None
        out = dict(a)
        out.setdefault("id", profile_id)
    return _to_profile(out, def_id).model_dump()


@router.post("/{profile_id}/set-default", status_code=200)
def set_default(
    profile_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        if profile_id not in raw.get("profiles", {}):
            raise HTTPException(status_code=404, detail="Profile not found")
        raw["defaultProfileId"] = profile_id
        _save(raw)
    return {"ok": True, "defaultProfileId": profile_id}


@router.delete("/{profile_id}", status_code=204)
def delete_profile(
    profile_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> None:
    with _lock:
        raw = _load()
        profs = raw.setdefault("profiles", {})
        if profile_id not in profs:
            raise HTTPException(status_code=404, detail="Profile not found")
        del profs[profile_id]
        if raw.get("defaultProfileId") == profile_id:
            first = next(iter(profs.keys()), None)
            raw["defaultProfileId"] = first
        _save(raw)

