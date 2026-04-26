"""Workspace aggregate health for local runtime probes (CORS from Vercel + localhost UIs)."""

from __future__ import annotations

import os

from fastapi import APIRouter

from src.api.workspace_files import workspace_root_info

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/health")
def workspace_health() -> dict:
    """
    Lightweight probe for the browser to verify it reached the *local* HAM API.
    ``workspaceRootConfigured`` is True when HAM_WORKSPACE_ROOT or HAM_WORKSPACE_FILES_ROOT is set
    in the process environment (as opposed to falling through to the repo sandbox only).
    """
    raw = (os.environ.get("HAM_WORKSPACE_ROOT") or "").strip() or (os.environ.get("HAM_WORKSPACE_FILES_ROOT") or "").strip()
    info = workspace_root_info()
    return {
        "ok": True,
        "workspaceRootConfigured": bool(raw),
        "features": ["files", "terminal"],
        "workspaceRootPath": info["path"],
        "broadFilesystemAccess": info["broadFilesystemAccess"],
    }
