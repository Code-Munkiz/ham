"""
Local workspace file tree + mutations for the Hermes Files UI (the browser never touches the OS).

**Root directory (precedence):**

1. ``HAM_WORKSPACE_ROOT`` — preferred: any absolute folder, including a drive (e.g. Windows ``C:\\``) in operator mode.
2. ``HAM_WORKSPACE_FILES_ROOT`` — legacy alias if (1) is unset.
3. ``<ham_repo>/.ham_workspace_sandbox`` — default when neither env is set (local dev).

**Symlinks:** ``Path.resolve()`` is used; if a path resolves outside the configured root, requests fail
(``relative_to``). Symlinks *inside* the root that point outside may resolve to paths that cannot be
expressed under the root — those operations return 400, not a silent escape.

**Listing:** One directory level per ``list`` call; expand in the UI with ``path=`` for subfolders
(no recursive full-tree response — avoids full-drive walk).

The API process must run on the same machine as this tree (Vite dev proxy to local ``uvicorn`` is
the normal setup). A remote/Cloud API sees its own disk, not the user’s. Hardening (RBAC, audit) is
follow-up; path escape is blocked via ``Path.resolve`` + ``relative_to`` the workspace root.
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


def _using_env_workspace_root() -> bool:
    """True when HAM_WORKSPACE_ROOT or HAM_WORKSPACE_FILES_ROOT is set (not the repo sandbox)."""
    return bool(
        (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip()
        or (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    )


def configured_workspace_env_path_raw() -> str:
    """Same env precedence as Files: ``HAM_WORKSPACE_ROOT`` then ``HAM_WORKSPACE_FILES_ROOT`` (trimmed).

    Empty when neither is set — used by context snapshot (no sandbox / cwd fallback).
    """
    return (
        (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip()
        or (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    )


def resolve_workspace_context_snapshot_root() -> Path:
    """Resolve configured workspace root for context snapshots (no sandbox, no ``Path.cwd()``).

    Same **env precedence** as ``_workspace_root()`` when env is set; does **not** create directories
    or fall back to ``.ham_workspace_sandbox``.
    """
    raw = configured_workspace_env_path_raw()
    if not raw:
        msg = "Workspace root is not configured. Set HAM_WORKSPACE_ROOT (or HAM_WORKSPACE_FILES_ROOT) on this API process."
        raise ValueError("WORKSPACE_ROOT_NOT_CONFIGURED", msg)
    try:
        root = Path(raw).expanduser().resolve()
    except OSError:
        msg = "The configured workspace root could not be resolved."
        raise ValueError("WORKSPACE_ROOT_UNREADABLE", msg) from None
    if not root.exists():
        msg = "The configured workspace root does not exist on this host."
        raise ValueError("WORKSPACE_ROOT_MISSING", msg)
    if not root.is_dir():
        msg = "The configured workspace root is not a directory."
        raise ValueError("WORKSPACE_ROOT_NOT_DIRECTORY", msg)
    try:
        os.listdir(root)
    except OSError:
        msg = "The configured workspace root exists but cannot be read."
        raise ValueError("WORKSPACE_ROOT_UNREADABLE", msg) from None
    return root


def _workspace_root() -> Path:
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


def workspace_root_info() -> dict[str, Any]:
    """Exposed to ``/api/workspace/health`` — resolved path, env mode, and broad-root hint."""
    p = _workspace_root()
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    return {
        "path": str(resolved),
        "usingEnvWorkspace": _using_env_workspace_root(),
        "broadFilesystemAccess": is_broad_filesystem_root(resolved),
    }


def is_broad_filesystem_root(p: Path) -> bool:
    """
    Heuristic for operator warnings: full drive, POSIX root, or user home as configured root.
    Intentional “workstation” mode — not a hard block.
    """
    try:
        r = p.resolve()
    except OSError:
        return False
    s = str(r)
    if os.name == "nt":
        s2 = s.rstrip("/\\")
        if len(s2) == 2 and s2[0].isalpha() and s2[1] == ":":
            return True
    elif s in ("/",):
        return True
    try:
        home = Path.home().resolve()
        if r == home:
            return True
    except OSError:
        pass
    return False


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


def _list_shallow_relative(rel: str) -> list[dict[str, Any]]:
    """
    List direct children of ``rel`` (relative to workspace root). Folders are returned with
    ``children: null`` — the client loads a subtree with another ``list`` + ``path``.
    """
    rel = (rel or "").replace("\\", "/").strip()
    d = _resolve_safe(rel) if rel else _workspace_root()
    if not d.is_dir():
        raise HTTPException(status_code=400, detail="list path must be a directory")
    if not rel and not _using_env_workspace_root():
        try:
            names = {p.name for p in d.iterdir()}
        except OSError:
            names = set()
        if not names or names == {".gitkeep"}:
            try:
                (d / ".gitkeep").write_text("", encoding="utf-8")
            except OSError:
                pass
    out: list[dict[str, Any]] = []
    try:
        subs = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    for c in subs:
        if c.name.startswith("."):
            continue
        c_rel = _to_rel(c)
        if c.is_file():
            out.append(FileEntry(name=c.name, path=c_rel, type="file", children=None).model_dump())
        else:
            out.append(
                FileEntry(
                    name=c.name,
                    path=c_rel,
                    type="folder",
                    children=None,
                ).model_dump()
            )
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
        return {"entries": _list_shallow_relative(path or "")}

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
