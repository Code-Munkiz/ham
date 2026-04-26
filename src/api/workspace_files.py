"""
HAM-owned workspace file tree + mutations for the Hermes Workspace Files UI.

Serves paths under HAM_WORKSPACE_FILES_ROOT (default: <repo>/.ham_workspace_sandbox).
Hardening (RBAC, audit, stricter policy) is follow-up; paths are kept under root via resolve check.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor

router = APIRouter(prefix="/api/workspace/files", tags=["workspace-files"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _workspace_root() -> Path:
    raw = (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    d = _repo_root() / ".ham_workspace_sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _resolve_safe(rel: str) -> Path:
    root = _workspace_root()
    rel = rel.replace("\\", "/").strip()
    if rel.startswith("/"):
        rel = rel[1:]
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:  # noqa: TRY003
        raise HTTPException(status_code=400, detail="Path escapes workspace root") from exc
    return target


class FileEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "folder"]
    children: list[FileEntry] | None = None


def _to_rel(path: Path) -> str:
    root = _workspace_root()
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path") from None


def _build_tree(p: Path) -> FileEntry:
    rel = _to_rel(p)
    if p.is_file():
        return FileEntry(name=p.name, path=rel, type="file", children=None)
    children: list[FileEntry] = []
    try:
        subs = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    for c in subs:
        if c.name.startswith("."):
            continue
        if c.is_dir():
            children.append(_build_tree(c))
        else:
            children.append(FileEntry(name=c.name, path=_to_rel(c), type="file", children=None))
    return FileEntry(name=p.name, path=rel, type="folder", children=children)


def _list_entry_payloads() -> list[dict[str, Any]]:
    root = _workspace_root()
    if not any(p for p in root.iterdir() if not (p.name == ".gitkeep" and p.is_file())):
        (root / ".gitkeep").write_text("", encoding="utf-8")
    out: list[dict[str, Any]] = []
    try:
        subs = sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    for c in subs:
        if c.name.startswith(".") and c.name != ".gitkeep":
            continue
        if c.is_dir() or c.is_file():
            out.append(_build_tree(c).model_dump())
    return out


@router.get(
    "",
    response_model=None,
    responses={200: {"content": {"application/json": {}}, "description": "list/read JSON"}},
)
def workspace_files_get(
    action: str | None = None,
    path: str | None = None,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any] | FileResponse:
    if action is None or action == "list":
        return {"entries": _list_entry_payloads()}

    if action == "read":
        if not path:
            raise HTTPException(status_code=400, detail="read requires path")
        t = _resolve_safe(path)
        if not t.is_file():
            raise HTTPException(status_code=404, detail="Not a file")
        try:
            text = t.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return {"content": text, "text": text}

    if action == "download":
        if not path:
            raise HTTPException(status_code=400, detail="download requires path")
        t = _resolve_safe(path)
        if not t.is_file():
            raise HTTPException(status_code=404, detail="Not a file")
        return FileResponse(str(t), filename=t.name)

    raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")


class FilePostBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: str
    path: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    content: str | None = None


@router.post("")
def workspace_files_post_json(
    body: FilePostBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    a = body.action
    if a == "delete":
        if not body.path:
            raise HTTPException(status_code=400, detail="delete requires path")
        t = _resolve_safe(body.path)
        if t.is_dir():
            shutil.rmtree(t, ignore_errors=False)
        elif t.is_file() or t.is_symlink():
            t.unlink()
        else:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}
    if a == "rename":
        if not body.from_ or not body.to:
            raise HTTPException(status_code=400, detail="rename requires from and to")
        src = _resolve_safe(body.from_)
        dst = _resolve_safe(body.to)
        if not src.exists():
            raise HTTPException(status_code=404, detail="from not found")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"ok": True}
    if a == "mkdir":
        if not body.path:
            raise HTTPException(status_code=400, detail="mkdir requires path")
        t = _resolve_safe(body.path)
        t.mkdir(parents=True, exist_ok=True)
        return {"ok": True}
    if a == "write":
        if not body.path:
            raise HTTPException(status_code=400, detail="write requires path")
        t = _resolve_safe(body.path)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(body.content or "", encoding="utf-8", newline="")
        return {"ok": True}
    raise HTTPException(status_code=400, detail=f"Unknown post action: {a!r}")


@router.post("/upload")
async def workspace_files_upload(
    file: UploadFile = File(...),
    path: str = Form(""),
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, bool]:
    """Multipart upload (action=upload + path + file) — HAM dev bridge."""
    name = (file.filename or "uploaded").rsplit("/")[-1].rsplit("\\")[-1]
    base = (path or "").replace("\\", "/").strip()
    if base:
        target = _resolve_safe(f"{base.rstrip('/')}/{name}")
    else:
        target = _resolve_safe(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    target.write_bytes(data)
    return {"ok": True}
