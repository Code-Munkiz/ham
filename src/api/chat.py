"""HAM-native interactive chat (non-streaming MVP). Proxies to server-side gateway adapter."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn
from src.persistence.chat_session_store import ChatTurn, InMemoryChatSessionStore

router = APIRouter(tags=["chat"])

_chat_store = InMemoryChatSessionStore()


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    session_id: str | None = None
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    client_request_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    session_id: str
    messages: list[dict[str, str]]


def _gateway_status_code(code: str) -> int:
    if code == "INVALID_REQUEST":
        return 400
    if code == "CONFIG_ERROR":
        return 500
    return 502


@router.post("/api/chat", response_model=ChatResponse)
async def post_chat(body: ChatRequest) -> ChatResponse:
    store = _chat_store

    if body.session_id:
        if store.get_session(body.session_id) is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "SESSION_NOT_FOUND",
                        "message": "Unknown chat session.",
                    }
                },
            )
        sid = body.session_id
    else:
        sid = store.create_session()

    incoming = [m.model_dump() for m in body.messages]
    try:
        store.append_turns(sid, incoming)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "Unknown chat session.",
                }
            },
        )

    history = store.list_messages(sid)
    try:
        assistant_text = complete_chat_turn(history)
    except GatewayCallError as exc:
        raise HTTPException(
            status_code=_gateway_status_code(exc.code),
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_text)])
    return ChatResponse(session_id=sid, messages=store.list_messages(sid))
