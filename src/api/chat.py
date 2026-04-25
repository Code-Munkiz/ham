"""HAM-native interactive chat. Proxies to server-side gateway adapter; optional NDJSON streaming."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.models_catalog import resolve_model_id_for_chat
from src.ham.active_agent_context import try_active_agent_guidance_for_project_root
from src.ham.cursor_skills_catalog import list_cursor_skills, render_skills_for_system_prompt
from src.ham.cursor_subagents_catalog import list_cursor_subagents, render_subagents_for_system_prompt
from src.ham.chat_operator import (
    ChatOperatorPayload,
    OperatorTurnResult,
    format_operator_assistant_message,
    operator_enabled,
    process_operator_turn,
)
from src.api.clerk_gate import enforce_clerk_session_and_email_for_request
from src.ham.clerk_auth import (
    HamActor,
    actor_attribution_dict,
    resolve_ham_operator_authorization_header,
)
from src.ham.clerk_policy import (
    actor_has_permission,
    permission_for_intent,
    permission_for_phase,
)
from src.ham.operator_audit import append_operator_action_audit
from src.ham.ui_actions import split_assistant_ui_actions, ui_actions_system_instructions
from src.ham.workbench_view_intent import augment_workbench_view_actions
from src.integrations.nous_gateway_client import (
    GatewayCallError,
    complete_chat_turn,
    format_gateway_error_user_message,
    stream_chat_turn,
)
from src.persistence.chat_session_store import ChatTurn, InMemoryChatSessionStore
from src.persistence.sqlite_chat_session_store import SqliteChatSessionStore

router = APIRouter(tags=["chat"])

_ChatStore = InMemoryChatSessionStore | SqliteChatSessionStore


def _build_chat_session_store() -> _ChatStore:
    mode = (os.environ.get("HAM_CHAT_SESSION_STORE") or "sqlite").strip().lower()
    if mode == "memory":
        return InMemoryChatSessionStore()
    raw = (os.environ.get("HAM_CHAT_SESSION_DB") or "").strip()
    db_path = Path(raw).expanduser() if raw else Path.home() / ".ham" / "chat_sessions.sqlite"
    return SqliteChatSessionStore(db_path)


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
    # When true (default), append `.cursor/rules/subagent-*.mdc` index (review charters; not executable skills).
    include_operator_subagents: bool = True
    # When true (default), system prompt includes HAM_UI_ACTIONS_JSON instructions; response may include `actions`.
    enable_ui_actions: bool = True
    # Registered HAM project id (see `GET /api/projects`); when set with `include_active_agent_guidance`, server injects Agent Builder profile guidance.
    project_id: str | None = Field(default=None, max_length=180)
    # When true (default), append compact HAM active-agent guidance from merged project config (Hermes catalog descriptors only; not execution).
    include_active_agent_guidance: bool = True
    model_id: str | None = Field(default=None, max_length=256)
    workbench_mode: Literal["ask", "plan", "agent"] | None = None
    worker: str | None = Field(default=None, max_length=64)
    max_mode: bool | None = None
    # Server-side operator (projects, agents preview/apply, runs, launch) — see docs/HAM_CHAT_CONTROL_PLANE.md
    enable_operator: bool = True
    operator: ChatOperatorPayload | None = None


class ChatActiveAgentMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_name: str
    skills_requested: int
    skills_resolved: int
    skills_skipped_catalog_miss: int = 0
    guidance_applied: bool = True


class ChatResponse(BaseModel):
    session_id: str
    messages: list[dict[str, str]]
    actions: list[dict] = Field(default_factory=list)
    active_agent: ChatActiveAgentMeta | None = None
    operator_result: dict[str, Any] | None = None


def _gateway_status_code(code: str) -> int:
    if code == "INVALID_REQUEST":
        return 400
    if code == "CONFIG_ERROR":
        return 500
    return 502


_MAX_SYSTEM_PROMPT_CHARS = 12_000


def _resolve_chat_clerk_context(
    authorization: str | None,
    x_ham_operator_authorization: str | None,
    *,
    route: str,
) -> tuple[HamActor | None, str | None]:
    """Clerk session on ``Authorization`` when operator auth or email enforcement is on; HAM tokens on ``X-Ham-Operator-Authorization``."""
    ham_hdr = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    actor = enforce_clerk_session_and_email_for_request(authorization, route=route)
    return actor, ham_hdr


def _record_operator_audit(
    *,
    body: ChatRequest,
    op: OperatorTurnResult,
    ham_actor: HamActor | None,
    route: str,
) -> None:
    req = (
        permission_for_phase(body.operator.phase)
        if body.operator and body.operator.phase
        else permission_for_intent(op.intent)
    )
    append_operator_action_audit(
        {
            **actor_attribution_dict(ham_actor),
            "required_permission": req,
            "permission_granted": actor_has_permission(ham_actor, req) if (ham_actor and req) else None,
            "intent": op.intent,
            "operator_phase": body.operator.phase if body.operator else None,
            "operator_ok": op.ok,
            "blocking_reason": op.blocking_reason,
            "route": route,
            "audit_sink": "ham_local_jsonl",
        }
    )


# Shipped default so the model is product-aware without requiring env (override with HAM_CHAT_SYSTEM_PROMPT).
_DEFAULT_CHAT_SYSTEM_PROMPT = """
You are **Ham**, the in-dashboard copilot for the Ham workspace UI—warm, concise, and specific. You speak in first person as Ham (the product mascot voice), not as a generic chatbot.

**What Ham is:** An open-source autonomous-developer stack: a **Context Engine** grounds agents on repo state; **droids** run CLI-style execution; **Hermes** is the **sole supervisory orchestrator** (routing, critique, learning)—there is no CrewAI or other orchestration framework in Ham. This chat uses a normal LLM behind the Ham API—it is *not* the Hermes reviewer loop itself, but you should describe Hermes accurately when users ask.

**What the UI has (high level):** A left **nav** (Chat, workspace, logs, etc.), this **Chat** page, **Settings** (context engine, droids, preferences), and workspace panels for runs and tooling. You **cannot** see the user’s screen, current route, or saved settings—if that matters, ask them to describe what they see or paste text.

**Control plane (skills & subagents):** When the message includes an **Operator skills** appendix, treat each entry as a real Ham workflow the IDE can run (Context Engine hardening, agent context wiring, Hermes review validation, prompt budget audit, repo regression tests, GoHam navigation). Map user goals to the best-matching skill id and tell them the exact slash command or doc path (e.g. `/audit-context-engine`, `.cursor/skills/.../SKILL.md`). When a **Cursor subagent rules** appendix is present, each entry is a **review/audit charter** (`.cursor/rules/subagent-*.mdc`): recommend the charter that fits the user’s review question using id, path, and `globs`; subagents are **not** execution SKILLS—they shape how to audit or review code. When **structured UI actions** are enabled, you may also emit **`HAM_UI_ACTIONS_JSON`** so the browser can navigate, show toasts, toggle the **right-side control panel**, or switch the **`/chat` workbench header** (CHAT / SPLIT / PREVIEW / WAR ROOM / BROWSER via `set_workbench_view`)—you still **do not** edit `.ham.json`, run shell tools, or change secrets from this chat.

**Workbench header vs control panel:** On **`/chat`**, the **top bar** (CHAT, SPLIT, PREVIEW, WAR ROOM, BROWSER) changes the main workbench layout. Use **`{{"type":"set_workbench_view","mode":"chat|split|preview|war_room|browser"}}`**. The **control panel** is the separate right-hand workspace rail—use **`toggle_control_panel`** for that only. When the user asks for "split view", "preview", "war room", or "browser" in the workbench, they almost always mean **`set_workbench_view`**, not the control panel.

**How to engage:** Use short paragraphs or tight bullets; offer next steps; match energy without filler. If asked what you can do, explain Ham at a high level and suggest concrete actions (e.g. “open Settings → …”, “describe the error in Logs”).

**Operational chat (server-side):** For supported phrases, the Ham API runs a real **operator** turn first: listing projects, inspecting a project or Agent Builder profiles, listing/inspecting runs, previewing agent skill changes, and (when configured) registering a project or launching a bridge run. Those actions hit the same APIs as the dashboard—they are not LLM hallucinations. Writes require confirmation + bearer tokens on the API host. If the user’s repo path is not visible to the API process (typical on Cloud Run vs local disk), the operator will say so honestly.

**Honesty:** If you lack a fact, say so and ask a clarifying question instead of inventing menu labels or features.
""".strip()


def _chat_system_prompt(
    *,
    include_operator_skills: bool,
    include_operator_subagents: bool,
    enable_ui_actions: bool,
) -> str:
    custom = (os.environ.get("HAM_CHAT_SYSTEM_PROMPT") or "").strip()
    base = custom[:_MAX_SYSTEM_PROMPT_CHARS] if custom else _DEFAULT_CHAT_SYSTEM_PROMPT
    parts: list[str] = [base]
    if include_operator_skills:
        block = render_skills_for_system_prompt(list_cursor_skills())
        if block:
            parts.append(block)
    if include_operator_subagents:
        sub_block = render_subagents_for_system_prompt(list_cursor_subagents())
        if sub_block:
            parts.append(sub_block)
    ui_block = ui_actions_system_instructions() if enable_ui_actions else ""
    core = "\n\n".join(parts)
    if ui_block:
        # Never truncate away UI-action instructions: long skills/subagent catalogs were
        # previously cutting off the tail and models saw no HAM_UI_ACTIONS_JSON contract.
        reserve = len(ui_block) + 2
        if len(core) + reserve > _MAX_SYSTEM_PROMPT_CHARS:
            keep = max(0, _MAX_SYSTEM_PROMPT_CHARS - reserve)
            core = core[:keep]
        combined = f"{core}\n\n{ui_block}".strip()
        return combined[:_MAX_SYSTEM_PROMPT_CHARS]
    return core[:_MAX_SYSTEM_PROMPT_CHARS]


def _workbench_system_lines(
    *,
    workbench_mode: str | None,
    worker: str | None,
    max_mode: bool | None,
) -> list[str]:
    lines: list[str] = []
    if workbench_mode:
        mp = {
            "ask": "Workbench mode: ASK — concise Q&A; prefer direct answers.",
            "plan": "Workbench mode: PLAN — decompose and outline steps before substantive edits.",
            "agent": "Workbench mode: AGENT — action-oriented execution; propose concrete next steps.",
        }
        if workbench_mode in mp:
            lines.append(mp[workbench_mode])
    if worker:
        w = worker.strip().lower()
        wp = {
            "builder": "Worker: Builder — core developer and logic implementation.",
            "reviewer": "Worker: Reviewer — code quality and security lens.",
            "researcher": "Worker: Researcher — documentation and technical search.",
            "coordinator": "Worker: Coordinator — task decomposition and planning.",
            "qa": "Worker: QA — tests and validation.",
        }
        if w in wp:
            lines.append(wp[w])
    if max_mode:
        lines.append(
            "User preference: MAX mode — prefer deeper reasoning when trade-offs exist.",
        )
    if lines:
        lines.append(
            "Workbench header (/chat top bar): CHAT, SPLIT, PREVIEW, WAR ROOM, BROWSER — switch via "
            '`{"type":"set_workbench_view","mode":"chat|split|preview|war_room|browser"}` in HAM_UI_ACTIONS_JSON. '
            "This is **not** `toggle_control_panel` (the right-side panel). "
            'Phrases like "split view", "preview screen", "war room", or "browser" refer to these modes.',
        )
    return lines


def _append_workbench_to_messages(
    llm_messages: list[dict[str, str]],
    body: ChatRequest,
) -> list[dict[str, str]]:
    extra = _workbench_system_lines(
        workbench_mode=body.workbench_mode,
        worker=body.worker,
        max_mode=body.max_mode,
    )
    if not extra:
        return llm_messages
    block = "\n\n".join(extra)
    out = [dict(m) for m in llm_messages]
    if out and out[0].get("role") == "system":
        first = (out[0].get("content") or "").strip()
        out[0] = {
            "role": "system",
            "content": f"{first}\n\n{block}".strip() if first else block,
        }
    else:
        out.insert(0, {"role": "system", "content": block})
    return out


def _resolve_openrouter_model_override(body: ChatRequest) -> str | None:
    if body.model_id and (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower() != "openrouter":
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "MODEL_SELECTION_REQUIRES_OPENROUTER",
                    "message": "Per-request model selection requires HERMES_GATEWAY_MODE=openrouter on the API host.",
                }
            },
        )
    if not body.model_id or not str(body.model_id).strip():
        return None
    try:
        return resolve_model_id_for_chat(body.model_id)
    except ValueError as exc:
        code = str(exc)
        if code == "CURSOR_MODEL_NOT_CHAT_ENABLED":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "CURSOR_MODEL_NOT_CHAT_ENABLED",
                        "message": "Cursor API models are not available for dashboard chat; pick OpenRouter or a tier preset.",
                    }
                },
            ) from exc
        if code == "MODEL_NOT_AVAILABLE_FOR_CHAT":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "MODEL_NOT_AVAILABLE_FOR_CHAT",
                        "message": "Selected model is not available for chat (gateway or configuration).",
                    }
                },
            ) from exc
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "UNKNOWN_MODEL_ID",
                    "message": "Unknown model_id for chat.",
                }
            },
        ) from exc


def _resolve_project_root_for_chat(project_id: str | None) -> Path | None:
    if not project_id or not str(project_id).strip():
        return None
    from src.persistence.project_store import get_project_store

    rec = get_project_store().get_project(project_id.strip())
    if rec is None:
        return None
    return Path(rec.root).expanduser().resolve()


def _prepare_chat_session(body: ChatRequest) -> tuple[str, list[dict[str, str]], dict[str, Any] | None]:
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
    base_system = _chat_system_prompt(
        include_operator_skills=body.include_operator_skills,
        include_operator_subagents=body.include_operator_subagents,
        enable_ui_actions=body.enable_ui_actions,
    )
    active_meta: dict[str, Any] | None = None
    if body.include_active_agent_guidance:
        root = _resolve_project_root_for_chat(body.project_id)
        if root is not None:
            guidance_pack = try_active_agent_guidance_for_project_root(root)
            if guidance_pack is not None:
                room = max(0, _MAX_SYSTEM_PROMPT_CHARS - len(base_system) - 4)
                if room > 120:
                    g = guidance_pack.guidance_text[:room]
                    base_system = f"{base_system}\n\n{g}".strip()
                    active_meta = guidance_pack.meta

    llm_messages = [
        {
            "role": "system",
            "content": base_system,
        },
        *history,
    ]
    return sid, llm_messages, active_meta


def _messages_for_completion(
    body: ChatRequest,
) -> tuple[str, list[dict[str, str]], str | None, dict[str, Any] | None]:
    sid, llm_messages, active_meta = _prepare_chat_session(body)
    or_override = _resolve_openrouter_model_override(body)
    llm_messages = _append_workbench_to_messages(llm_messages, body)
    return sid, llm_messages, or_override, active_meta


@router.get("/api/chat/sessions")
async def list_chat_sessions(
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """List chat sessions with previews (newest first)."""
    enforce_clerk_session_and_email_for_request(authorization, route="list_chat_sessions")
    clamped_limit = max(1, min(limit, 100))
    clamped_offset = max(0, offset)
    items = _chat_store.list_sessions(limit=clamped_limit, offset=clamped_offset)
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "preview": s.preview,
                "turn_count": s.turn_count,
                "created_at": s.created_at,
            }
            for s in items
        ],
    }


@router.get("/api/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """Get full message history for a single chat session."""
    enforce_clerk_session_and_email_for_request(authorization, route="get_chat_session")
    rec = _chat_store.get_session(session_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Unknown chat session."}},
        )
    return {
        "session_id": rec.session_id,
        "messages": [{"role": t.role, "content": t.content} for t in rec.turns],
        "created_at": rec.created_at,
    }


@router.post("/api/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> ChatResponse:
    ham_actor, ham_op_hdr = _resolve_chat_clerk_context(
        authorization,
        x_ham_operator_authorization,
        route="post_chat",
    )
    store = _chat_store
    sid, llm_messages, or_override, active_meta = _messages_for_completion(body)
    if body.enable_operator and operator_enabled() and body.messages[-1].role == "user":
        from src.persistence.project_store import get_project_store

        op = process_operator_turn(
            user_text=body.messages[-1].content,
            project_store=get_project_store(),
            default_project_id=body.project_id,
            operator_payload=body.operator,
            ham_operator_authorization=ham_op_hdr,
            ham_actor=ham_actor,
        )
        if op is not None and op.handled:
            _record_operator_audit(body=body, op=op, ham_actor=ham_actor, route="post_chat")
            msg = format_operator_assistant_message(op)
            store.append_turns(sid, [ChatTurn(role="assistant", content=msg)])
            return ChatResponse(
                session_id=sid,
                messages=store.list_messages(sid),
                actions=[],
                active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
                operator_result=op.model_dump(mode="json"),
            )
    try:
        assistant_raw = complete_chat_turn(
            llm_messages,
            openrouter_model_override=or_override,
        )
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
    last_user_text = (
        body.messages[-1].content
        if body.messages and body.messages[-1].role == "user"
        else ""
    )
    actions = augment_workbench_view_actions(
        last_user_text,
        actions,
        enable_ui_actions=body.enable_ui_actions,
    )
    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
    return ChatResponse(
        session_id=sid,
        messages=store.list_messages(sid),
        actions=actions,
        active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
        operator_result=None,
    )


@router.post("/api/chat/stream")
def post_chat_stream(
    body: ChatRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> StreamingResponse:
    """Stream assistant tokens as NDJSON lines: session, delta, done (or error)."""
    ham_actor, ham_op_hdr = _resolve_chat_clerk_context(
        authorization,
        x_ham_operator_authorization,
        route="post_chat_stream",
    )
    store = _chat_store
    sid, llm_messages, or_override, stream_active_meta = _messages_for_completion(body)

    if body.enable_operator and operator_enabled() and body.messages[-1].role == "user":
        from src.persistence.project_store import get_project_store

        op = process_operator_turn(
            user_text=body.messages[-1].content,
            project_store=get_project_store(),
            default_project_id=body.project_id,
            operator_payload=body.operator,
            ham_operator_authorization=ham_op_hdr,
            ham_actor=ham_actor,
        )
        if op is not None and op.handled:
            _record_operator_audit(body=body, op=op, ham_actor=ham_actor, route="post_chat_stream")
            msg = format_operator_assistant_message(op)
            store.append_turns(sid, [ChatTurn(role="assistant", content=msg)])
            msgs = store.list_messages(sid)
            op_dict = op.model_dump(mode="json")

            def operator_only():
                yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                payload: dict[str, Any] = {
                    "type": "done",
                    "session_id": sid,
                    "messages": msgs,
                    "actions": [],
                    "operator_result": op_dict,
                }
                if stream_active_meta:
                    payload["active_agent"] = stream_active_meta
                yield json.dumps(payload) + "\n"

            return StreamingResponse(
                operator_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    def ndjson_gen():
        yield json.dumps({"type": "session", "session_id": sid}) + "\n"
        pieces: list[str] = []
        stream_completed = False
        try:
            try:
                for part in stream_chat_turn(
                    llm_messages,
                    openrouter_model_override=or_override,
                ):
                    pieces.append(part)
                    yield json.dumps({"type": "delta", "text": part}) + "\n"
            except GatewayCallError as exc:
                assistant_visible = format_gateway_error_user_message(exc)
                try:
                    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
                    payload_err: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": store.list_messages(sid),
                        "actions": [],
                        "operator_result": None,
                        "gateway_error": {"code": exc.code},
                    }
                    if stream_active_meta:
                        payload_err["active_agent"] = stream_active_meta
                    yield json.dumps(payload_err) + "\n"
                except KeyError:
                    yield json.dumps(
                        {
                            "type": "error",
                            "code": exc.code,
                            "message": assistant_visible,
                        },
                    ) + "\n"
                return
            stream_completed = True
            assistant_raw = "".join(pieces)
            assistant_visible, actions = (
                split_assistant_ui_actions(assistant_raw)
                if body.enable_ui_actions
                else (assistant_raw, [])
            )
            last_user_text = (
                body.messages[-1].content
                if body.messages and body.messages[-1].role == "user"
                else ""
            )
            actions = augment_workbench_view_actions(
                last_user_text,
                actions,
                enable_ui_actions=body.enable_ui_actions,
            )
            try:
                store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
                payload: dict[str, Any] = {
                    "type": "done",
                    "session_id": sid,
                    "messages": store.list_messages(sid),
                    "actions": actions,
                    "operator_result": None,
                }
                if stream_active_meta:
                    payload["active_agent"] = stream_active_meta
                yield json.dumps(payload) + "\n"
            except KeyError:
                yield json.dumps(
                    {
                        "type": "error",
                        "code": "SESSION_NOT_FOUND",
                        "message": "Session disappeared during stream.",
                    },
                ) + "\n"
        finally:
            # If stream was interrupted (generator closed), save partial content.
            if not stream_completed and pieces:
                partial = "".join(pieces)
                if partial.strip():
                    try:
                        visible, _ = (
                            split_assistant_ui_actions(partial)
                            if body.enable_ui_actions
                            else (partial, [])
                        )
                        store.append_turns(sid, [ChatTurn(role="assistant", content=visible)])
                    except Exception:
                        pass  # Best-effort: don't crash on cleanup

    return StreamingResponse(
        ndjson_gen(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


_MAX_TRANSCRIBE_BYTES = 15 * 1024 * 1024
_TRANSCRIBE_READ_CHUNK = 1024 * 1024
_OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"


async def _transcribe_with_openai(
    *,
    api_key: str,
    audio: bytes,
    filename: str,
    content_type: str,
    model: str,
) -> str:
    """POST multipart to OpenAI transcriptions; returns transcript text."""
    safe_name = filename.strip() or "recording.webm"
    ct = content_type.strip() or "application/octet-stream"
    data: dict[str, Any] = {"model": model, "response_format": "json"}
    files = {"file": (safe_name, audio, ct)}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            _OPENAI_TRANSCRIPTIONS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
        )
    resp.raise_for_status()
    payload = resp.json()
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        return ""
    return text.strip()


class TranscribeResponse(BaseModel):
    text: str


@router.post("/api/chat/transcribe", response_model=TranscribeResponse)
async def post_chat_transcribe(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
    file: UploadFile = File(...),
) -> TranscribeResponse:
    """Multipart audio → OpenAI transcription; same Clerk gate as chat when enabled."""
    _resolve_chat_clerk_context(
        authorization,
        x_ham_operator_authorization,
        route="post_chat_transcribe",
    )
    provider = (os.environ.get("HAM_TRANSCRIPTION_PROVIDER") or "").strip().lower()
    api_key = (os.environ.get("HAM_TRANSCRIPTION_API_KEY") or "").strip()
    if provider != "openai" or not api_key:
        raise HTTPException(
            status_code=501,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_NOT_CONFIGURED",
                    "message": "Voice transcription provider not configured.",
                },
            },
        )

    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_TRANSCRIBE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_UPLOAD_TOO_LARGE",
                    "message": f"Audio exceeds maximum size ({_MAX_TRANSCRIBE_BYTES // (1024 * 1024)} MiB).",
                },
            },
        )

    body = bytearray()
    while True:
        chunk = await file.read(_TRANSCRIBE_READ_CHUNK)
        if not chunk:
            break
        if len(body) + len(chunk) > _MAX_TRANSCRIBE_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": {
                        "code": "TRANSCRIPTION_UPLOAD_TOO_LARGE",
                        "message": f"Audio exceeds maximum size ({_MAX_TRANSCRIBE_BYTES // (1024 * 1024)} MiB).",
                    },
                },
            )
        body.extend(chunk)

    audio = bytes(body)
    if not audio:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {"code": "TRANSCRIPTION_EMPTY", "message": "No audio data received."},
            },
        )

    model = (os.environ.get("HAM_TRANSCRIPTION_MODEL") or "gpt-4o-mini-transcribe").strip()
    try:
        text = await _transcribe_with_openai(
            api_key=api_key,
            audio=audio,
            filename=file.filename or "dictation.webm",
            content_type=file.content_type or "audio/webm",
            model=model,
        )
    except httpx.HTTPStatusError as exc:
        msg = "Transcription service returned an error."
        try:
            err_json = exc.response.json()
            if isinstance(err_json, dict) and "error" in err_json:
                em = err_json.get("error")
                if isinstance(em, dict) and em.get("message"):
                    msg = str(em["message"])
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "TRANSCRIPTION_UPSTREAM_FAILED", "message": msg}},
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_UPSTREAM_FAILED",
                    "message": f"Transcription request failed: {exc}",
                },
            },
        ) from exc

    return TranscribeResponse(text=text)
