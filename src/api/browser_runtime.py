from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.browser_runtime.service import get_browser_runtime_manager
from src.ham.browser_runtime.sessions import (
    BrowserPolicyError,
    BrowserScreenshotTooLargeError,
    BrowserSessionConflictError,
    BrowserSessionError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnerMismatchError,
)

# Same Clerk + email gate as other dashboard routes when HAM enforces session/email.
router = APIRouter(
    prefix="/api/browser",
    tags=["browser-runtime"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


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


class BrowserClickXYBody(BrowserOwnerBody):
    x: float
    y: float
    button: str = Field(default="left")


class BrowserScrollBody(BrowserOwnerBody):
    delta_x: float = 0.0
    delta_y: float = 0.0


class BrowserKeyBody(BrowserOwnerBody):
    key: str = Field(min_length=1, max_length=64)


class BrowserStreamStartBody(BrowserOwnerBody):
    requested_transport: str = Field(default="webrtc", max_length=64)


class BrowserStreamOfferBody(BrowserOwnerBody):
    sdp: str = Field(min_length=1, max_length=500_000)
    type: str = Field(min_length=1, max_length=32)


class BrowserStreamCandidateBody(BrowserOwnerBody):
    candidate: str = Field(min_length=1, max_length=10_000)


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


@router.post("/sessions/{session_id}/actions/click-xy")
def click_xy_browser_session(session_id: str, body: BrowserClickXYBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.click_xy(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            x=body.x,
            y=body.y,
            button=body.button,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/actions/scroll")
def scroll_browser_session(session_id: str, body: BrowserScrollBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.scroll(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            delta_x=body.delta_x,
            delta_y=body.delta_y,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/actions/key")
def key_browser_session(session_id: str, body: BrowserKeyBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.key_press(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            key=body.key.strip(),
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


@router.post("/sessions/{session_id}/stream/start")
def start_browser_stream(session_id: str, body: BrowserStreamStartBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.start_stream(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            requested_transport=body.requested_transport.strip(),
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/sessions/{session_id}/stream/state")
def browser_stream_state(session_id: str, owner_key: str) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.get_stream_state(
            session_id=session_id,
            owner_key=owner_key.strip(),
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/stream/offer")
def browser_stream_offer(session_id: str, body: BrowserStreamOfferBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.handle_webrtc_offer(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            sdp=body.sdp,
            offer_type=body.type,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/stream/candidate")
def browser_stream_candidate(session_id: str, body: BrowserStreamCandidateBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.handle_webrtc_candidate(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
            candidate=body.candidate,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/sessions/{session_id}/stream/stop")
def stop_browser_stream(session_id: str, body: BrowserOwnerBody) -> dict[str, Any]:
    manager = get_browser_runtime_manager()
    try:
        return manager.stop_stream(
            session_id=session_id,
            owner_key=body.owner_key.strip(),
        )
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

