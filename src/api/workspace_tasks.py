"""
HAM workspace tasks: JSON-backed task cards with Kanban-friendly statuses.

**Storage:** ``<workspace_root>/.ham/workspace_state/tasks.json``
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor

router = APIRouter(prefix="/api/workspace/tasks", tags=["workspace-tasks"])

_lock = threading.Lock()
TasksStatePath: Path | None = None


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
    global TasksStatePath
    if TasksStatePath is not None:
        return TasksStatePath
    root = _workspace_root()
    d = root / ".ham" / "workspace_state"
    d.mkdir(parents=True, exist_ok=True)
    TasksStatePath = d / "tasks.json"
    return TasksStatePath


def _load() -> dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {"tasks": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tasks": {}}


def _save(data: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


TaskStatus = Literal["todo", "in_progress", "done"]


class TaskOut(BaseModel):
    id: str
    title: str
    body: str = ""
    status: TaskStatus
    dueAt: str | None = None  # ISO date string (YYYY-MM-DD) or full ISO
    createdAt: float
    updatedAt: float


def _to_task(data: dict[str, Any]) -> TaskOut:
    return TaskOut(
        id=data["id"],
        title=data.get("title", "Task"),
        body=data.get("body", "") or "",
        status=data.get("status", "todo"),
        dueAt=data.get("dueAt"),
        createdAt=float(data.get("createdAt", 0)),
        updatedAt=float(data.get("updatedAt", 0)),
    )


def _task_to_dict(tid: str) -> dict[str, Any]:
    with _lock:
        raw = _load()
    t = raw.get("tasks", {}).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    td = dict(t)
    td.setdefault("id", tid)
    return _to_task(td).model_dump()


def _parse_due(due: str | None) -> float | None:
    if not due or not str(due).strip():
        return None
    s = str(due).strip()
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T23:59:59").timestamp()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (OSError, ValueError):
        return None


def _is_overdue(task: dict[str, Any], now: float) -> bool:
    if task.get("status") == "done":
        return False
    ts = _parse_due(task.get("dueAt"))
    if ts is None:
        return False
    return ts < now


class CreateTaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="")
    status: TaskStatus = "todo"
    dueAt: str | None = None


class PatchTaskBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    status: TaskStatus | None = None
    dueAt: str | None = None


@router.get("/summary")
def tasks_summary(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    with _lock:
        raw = _load()
    tasks: dict[str, Any] = raw.get("tasks", {})
    total = 0
    in_progress = 0
    done = 0
    overdue = 0
    for t in tasks.values():
        if not isinstance(t, dict):
            continue
        total += 1
        s = t.get("status", "todo")
        if s == "in_progress":
            in_progress += 1
        elif s == "done":
            done += 1
        if _is_overdue(t, now):
            overdue += 1
    done_pct = int(round(100.0 * done / total)) if total else 0
    return {
        "total": total,
        "inProgress": in_progress,
        "overdue": overdue,
        "done": done,
        "donePercent": done_pct,
    }


@router.get("")
def list_tasks(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    q: str | None = Query(default=None),
    status: TaskStatus | None = Query(default=None, description="Filter by single status"),
    includeDone: bool = Query(default=True),
) -> dict[str, Any]:
    with _lock:
        raw = _load()
    items: list[TaskOut] = []
    for tid, v in raw.get("tasks", {}).items():
        if not isinstance(v, dict):
            continue
        v = dict(v)
        v.setdefault("id", tid)
        t = _to_task(v)
        if not includeDone and t.status == "done":
            continue
        if status and t.status != status:
            continue
        if q and q.strip():
            blob = f"{t.title} {t.body}".lower()
            if q.lower() not in blob:
                continue
        items.append(t)
    items.sort(key=lambda x: (-x.updatedAt, x.title.lower()))
    return {"tasks": [x.model_dump() for x in items]}


@router.post("", status_code=201)
def create_task(
    body: CreateTaskBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    now = time.time()
    tid = str(uuid.uuid4())
    rec = {
        "id": tid,
        "title": body.title.strip(),
        "body": (body.body or "").strip(),
        "status": body.status,
        "dueAt": body.dueAt.strip() if body.dueAt else None,
        "createdAt": now,
        "updatedAt": now,
    }
    with _lock:
        data = _load()
        data.setdefault("tasks", {})[tid] = rec
        _save(data)
    return _to_task(rec).model_dump()


@router.get("/{task_id}")
def get_task(
    task_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    return _task_to_dict(task_id)


@router.patch("/{task_id}")
def patch_task(
    task_id: str,
    body: PatchTaskBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    with _lock:
        raw = _load()
        tasks = raw.setdefault("tasks", {})
        t = tasks.get(task_id)
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")
        if body.title is not None:
            t["title"] = body.title.strip()
        if body.body is not None:
            t["body"] = body.body.strip() if body.body else ""
        if body.status is not None:
            t["status"] = body.status
        if body.dueAt is not None:
            t["dueAt"] = body.dueAt.strip() if body.dueAt else None
        t["updatedAt"] = time.time()
        _save(raw)
    return _task_to_dict(task_id)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> None:
    with _lock:
        raw = _load()
        tasks = raw.setdefault("tasks", {})
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        del tasks[task_id]
        _save(raw)
