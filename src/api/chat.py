"""HAM-native interactive chat. Proxies to server-side gateway adapter; optional NDJSON streaming."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.ham.cursor_skills_catalog import list_cursor_skills, render_skills_for_system_prompt
from src.ham.ui_actions import split_assistant_ui_actions, ui_actions_system_instructions
from src.integrations.nous_gateway_client import (
    GatewayCallError,
    complete_chat_turn,
    stream_chat_turn,
)
from src.persistence.chat_session_store import ChatTurn, InMemoryChatSessionStore
from src.persistence.sqlite_chat_session_store import SqliteChatSessionStore

router = APIRouter(tags=["chat"])

_ChatStore = InMemoryChatSessionStore | SqliteChatSessionStore


def _build_chat_session_store() -> _ChatStore:
    mode = (os.environ.get("HAM_CHAT_SESSION_STORE") or "memory").strip().lower()
    if mode == "sqlite":
        raw = (os.environ.get("HAM_CHAT_SESSION_DB") or "").strip()
        db_path = Path(raw).expanduser() if raw else Path.home() / ".ham" / "chat_sessions.sqlite"
        return SqliteChatSessionStore(db_path)
    return InMemoryChatSessionStore()


_chat_store = _build_chat_session_store()


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    session_id: str | None = None
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=50)
    client_request_id: str | None = Field(default=None, max_length=128)
    # When true (default), append `.cursor/skills` catalog to system context so Ham maps intents to operator workflows.
    include_operator_skills: bool = True
    # When true (default), system prompt includes HAM_UI_ACTIONS_JSON instructions; response may include `actions`.
    enable_ui_actions: bool = True


class ChatResponse(BaseModel):
    session_id: str
    messages: list[dict[str, str]]
    actions: list[dict] = Field(default_factory=list)


def _gateway_status_code(code: str) -> int:
    if code == "INVALID_REQUEST":
        return 400
    if code == "CONFIG_ERROR":
        return 500
    return 502


_MAX_SYSTEM_PROMPT_CHARS = 12_000

# Shipped default so the model is product-aware without requiring env (override with HAM_CHAT_SYSTEM_PROMPT).
_DEFAULT_CHAT_SYSTEM_PROMPT = """
You are **Ham**, the in-dashboard copilot for the Ham workspace UI—warm, concise, and specific. You speak in first person as Ham (the product mascot voice), not as a generic chatbot.

**What Ham is:** An open-source autonomous-developer stack: a **Context Engine** grounds agents on repo state; **droids** run CLI-style execution; **Hermes** is the **sole supervisory orchestrator** (routing, critique, learning)—there is no CrewAI or other orchestration framework in Ham. This chat uses a normal LLM behind the Ham API—it is *not* the Hermes reviewer loop itself, but you should describe Hermes accurately when users ask.

**What the UI has (high level):** A left **nav** (Chat, workspace, logs, etc.), this **Chat** page, **Settings** (context engine, droids, preferences), and workspace panels for runs and tooling. You **cannot** see the user’s screen, current route, or saved settings—if that matters, ask them to describe what they see or paste text.

**Control plane (skills):** When the message includes an **Operator skills** appendix, treat each entry as a real Ham workflow the IDE can run (Context Engine hardening, agent context wiring, Hermes review validation, prompt budget audit, repo regression tests, GoHam navigation). Map user goals to the best-matching skill id and tell them the exact slash command or doc path (e.g. `/audit-context-engine`, `.cursor/skills/.../SKILL.md`). When **structured UI actions** are enabled, you may also emit **`HAM_UI_ACTIONS_JSON`** so the browser can navigate or show toasts—you still **do not** edit `.ham.json`, run shell tools, or change secrets from this chat.

**How to engage:** Use short paragraphs or tight bullets; offer next steps; match energy without filler. If asked what you can do, explain Ham at a high level and suggest concrete actions (e.g. “open Settings → …”, “describe the error in Logs”). You do not execute code or call internal Ham APIs from here—you advise; heavier work happens via the rest of Ham (CLI / swarm / runs).

**Honesty:** If you lack a fact, say so and ask a clarifying question instead of inventing menu labels or features.
""".strip()


def _chat_system_prompt(
    *,
    include_operator_skills: bool,
    enable_ui_actions: bool,
) -> str:
    custom = (os.environ.get("HAM_CHAT_SYSTEM_PROMPT") or "").strip()
    base = custom[:_MAX_SYSTEM_PROMPT_CHARS] if custom else _DEFAULT_CHAT_SYSTEM_PROMPT
    parts: list[str] = [base]
    if include_operator_skills:
        block = render_skills_for_system_prompt(list_cursor_skills())
        if block:
            parts.append(block)
    if enable_ui_actions:
        parts.append(ui_actions_system_instructions())
    combined = "\n\n".join(parts)
    return combined[:_MAX_SYSTEM_PROMPT_CHARS]


def _prepare_chat_session(body: ChatRequest) -> tuple[str, list[dict[str, str]]]:
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
    llm_messages = [
        {
            "role": "system",
            "content": _chat_system_prompt(
                include_operator_skills=body.include_operator_skills,
                enable_ui_actions=body.enable_ui_actions,
            ),
        },
        *history,
    ]
    return sid, llm_messages


@router.post("/api/chat", response_model=ChatResponse)
async def post_chat(body: ChatRequest) -> ChatResponse:
    store = _chat_store
    sid, llm_messages = _prepare_chat_session(body)
    try:
        assistant_raw = complete_chat_turn(llm_messages)
    except GatewayCallError as exc:
        raise HTTPException(
            status_code=_gateway_status_code(exc.code),
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    assistant_visible, actions = (
        split_assistant_ui_actions(assistant_raw)
        if body.enable_ui_actions
        else (assistant_raw, [])
    )
    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
    return ChatResponse(
        session_id=sid,
        messages=store.list_messages(sid),
        actions=actions,
    )


@router.post("/api/chat/stream")
def post_chat_stream(body: ChatRequest) -> StreamingResponse:
    """Stream assistant tokens as NDJSON lines: session, delta, done (or error)."""
    store = _chat_store
    sid, llm_messages = _prepare_chat_session(body)

    def ndjson_gen():
        yield json.dumps({"type": "session", "session_id": sid}) + "\n"
        pieces: list[str] = []
        try:
            for part in stream_chat_turn(llm_messages):
                pieces.append(part)
                yield json.dumps({"type": "delta", "text": part}) + "\n"
        except GatewayCallError as exc:
            yield json.dumps(
                {"type": "error", "code": exc.code, "message": exc.message},
            ) + "\n"
            return
        assistant_raw = "".join(pieces)
        assistant_visible, actions = (
            split_assistant_ui_actions(assistant_raw)
            if body.enable_ui_actions
            else (assistant_raw, [])
        )
        try:
            store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
            payload = {
                "type": "done",
                "session_id": sid,
                "messages": store.list_messages(sid),
                "actions": actions,
            }
            yield json.dumps(payload) + "\n"
        except KeyError:
            yield json.dumps(
                {
                    "type": "error",
                    "code": "SESSION_NOT_FOUND",
                    "message": "Session disappeared during stream.",
                },
            ) + "\n"

    return StreamingResponse(
        ndjson_gen(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
