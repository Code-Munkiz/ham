"""
HAM workspace Memory: JSON-backed memory items (local v0; not a full Memory Heist replacement).

**Storage:** ``<workspace_root>/.ham/workspace_state/memory.json``

**Semantics:** user-authored notes / preferences. Search is substring on title+body+tags.
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

router = APIRouter(prefix="/api/workspace/memory", tags=["workspace-memory"])

_lock = threading.Lock()
StatePath: Path | None = None

MemoryKind = Literal["note", "preference"]


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
    StatePath = d / "memory.json"
    return StatePath


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"items": {}, "settings": {"notes": ""}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"items": {}, "settings": {"notes": ""}}
        data.setdefault("items", {})
        data.setdefault("settings", {"notes": ""})
        return data
    except (OSError, json.JSONDecodeError):
        return {"items": {}, "settings": {"notes": ""}}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


class MemoryItemOut(BaseModel):
    id: str
    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    kind: MemoryKind = "note"
    archived: bool = False
    createdAt: float
    updatedAt: float


def _to_item(d: dict[str, Any]) -> MemoryItemOut:
    tags = d.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return MemoryItemOut(
        id=d["id"],
        title=(d.get("title", "") or "")[:2000],
        body=(d.get("body", "") or "")[:100_000],
        tags=[str(t)[:200] for t in tags if str(t).strip()][:50],
        kind="preference" if d.get("kind") == "preference" else "note",
        archived=bool(d.get("archived", False)),
        createdAt=float(d.get("createdAt", 0)),
        updatedAt=float(d.get("updatedAt", 0)),
    )


class CreateMemoryBody(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    body: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    kind: MemoryKind = "note"


class PatchMemoryBody(BaseModel):
    title: str | None = Field(default=None, max_length=2000)
    body: str | None = Field(default=None, max_length=100_000)
    tags: list[str] | None = None
    kind: MemoryKind | None = None
    archived: bool | None = None


@router.get("/items")
def list_items(
    q: str | None = None,
    archived: bool = False,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    items: list[MemoryItemOut] = []
    ql = (q or "").strip().lower()
    for mid, v in raw.get("items", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", mid)
        o = _to_item(v)
        if o.archived != archived:
            continue
        if ql:
            blob = f"{o.title} {o.body} {' '.join(o.tags)}".lower()
            if ql not in blob:
                continue
        items.append(o)
    items.sort(key=lambda x: -x.updatedAt)
    return {"items": [x.model_dump() for x in items]}


@router.post("/items", status_code=201)
def create_item(
    body: CreateMemoryBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    now = time.time()
    mid = str(uuid.uuid4())
    tags = [t.strip() for t in body.tags if t.strip()][:50]
    rec = {
        "id": mid,
        "title": body.title.strip(),
        "body": body.body.strip(),
        "tags": tags,
        "kind": body.kind,
        "archived": False,
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("items", {})[mid] = rec
        _save(data)
    return _to_item(rec).model_dump()


@router.get("/items/{item_id}")
def get_item(
    item_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    v = raw.get("items", {}).get(item_id)
    if not v or not isinstance(v, dict):
        raise HTTPException(status_code=404, detail="Memory item not found")
    v = dict(v)
    v.setdefault("id", item_id)
    return _to_item(v).model_dump()


@router.patch("/items/{item_id}")
def patch_item(
    item_id: str,
    body: PatchMemoryBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        items = raw.setdefault("items", {})
        a = items.get(item_id)
        if not a or not isinstance(a, dict):
            raise HTTPException(status_code=404, detail="Memory item not found")
        if body.title is not None:
            a["title"] = body.title.strip()
        if body.body is not None:
            a["body"] = body.body.strip()
        if body.tags is not None:
            a["tags"] = [t.strip() for t in body.tags if t.strip()][:50]
        if body.kind is not None:
            a["kind"] = body.kind
        if body.archived is not None:
            a["archived"] = body.archived
        a["updatedAt"] = time.time()
        _save(raw)
        out = dict(a)
        out.setdefault("id", item_id)
    return _to_item(out).model_dump()


@router.delete("/items/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> None:
    with _lock:
        raw = _load()
        items = raw.setdefault("items", {})
        if item_id not in items:
            raise HTTPException(status_code=404, detail="Memory item not found")
        del items[item_id]
        _save(raw)