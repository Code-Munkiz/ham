from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.ham.browser_runtime.service import get_browser_runtime_manager
from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserScreenshotTooLargeError,
    BrowserSessionConflictError,
    BrowserSessionError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)

router = APIRouter(prefix="/api/browser", tags=["browser-runtime"])


class BrowserCreateSessionBody(BaseModel):
    owner_key: str = Field(min_length=1, max_length=128)
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)


class BrowserOwnerBody(BaseModel):
    owner_key: str = Field(min_length=1, max_length=128)


class BrowserNavigateBody(BrowserOwnerBody):
    url: str = Field(min_length=1, max_length=4096)


class BrowserClickBody(BrowserOwnerBody):
    selector: str = Field(min_length=1, max_length=2048)


class BrowserTypeBody(BrowserOwnerBody):
    selector: str = Field(min_length=1, max_length=2048)
    text: str = Field(min_length=0, max_length=4000)
    clear_first: bool = True


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BrowserPolicyError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, BrowserSessionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BrowserSessionOwnerMismatchError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, BrowserSessionConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BrowserScreenshotTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, BrowserSessionError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Browser runtime internal error.")


@router.get("/policy")
def browser_runtime_policy() -> dict[str, Any]:
    return get_browser_runtime_manager().policy_snapshot()


@router.post("/sessions")
def create_browser_session(body: BrowserCreateSessionBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.create_session(
            owner_key=body.owner_key.strip(),
            viewport_width=body.viewport_width,
            viewport_height=body.viewport_height,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/sessions/{session_id}")
def get_browser_session_state(session_id: str, owner_key: str) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.get_state(session_id=session_id, owner_key=owner_key.strip())
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/navigate")
def navigate_browser_session(session_id: str, body: BrowserNavigateBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.navigate(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            url=body.url.strip(),
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/actions/click")
def click_browser_session(session_id: str, body: BrowserClickBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.click(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            selector=body.selector,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/actions/type")
def type_browser_session(session_id: str, body: BrowserTypeBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.type_text(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            selector=body.selector,
            text=body.text,
            clear_first=body.clear_first,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/screenshot")
def screenshot_browser_session(session_id: str, body: BrowserOwnerBody) -> Response:
    manager = get_browser_runtime_manager()
    try:
        image = manager.screenshot_png(session_id=session_id, owner_key=body.owner_key.strip())
        return Response(content=image, media_type="image/png")
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/reset")
def reset_browser_session(session_id: str, body: BrowserOwnerBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.reset(session_id=session_id, owner_key=body.owner_key.strip())
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.delete("/sessions/{session_id}")
def close_browser_session(session_id: str, owner_key: str) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        manager.close_session(session_id=session_id, owner_key=owner_key.strip())
        return {"ok": True, "session_id": session_id}
    except Exception as exc:
        raise _to_http_error(exc) from exc

