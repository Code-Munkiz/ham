"""HAM-native interactive chat. Proxies to server-side gateway adapter; optional NDJSON streaming."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.models_catalog import resolve_model_id_for_chat
from src.bridge import (
    BrowserAction,
    BrowserIntent,
    BrowserPolicySpec,
    BrowserRunStatus,
    BrowserStepSpec,
    build_browser_executor,
    run_browser_v0,
)
from src.ham.chat_user_content import (
    plain_text_for_operator,
    to_llm_message_content,
    vision_system_suffix,
)
from src.ham.execution_mode import (
    ExecutionEnvironment,
    ExecutionModePreference,
    browser_runtime_available,
    resolve_execution_mode,
)
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
from src.integrations.nous_gateway_client import (
    GatewayCallError,
    complete_chat_turn,
    format_gateway_error_user_message,
    stream_chat_turn,
)
from src.persistence.chat_session_store import ChatTurn, build_chat_session_store
from src.ham.chat_attachment_store import (
    CHAT_UPLOAD_ALLOWED_MIME,
    AttachmentRecord,
    default_attachment_max_bytes,
    get_chat_attachment_store,
    kind_for_mime,
    safe_upload_filename,
)
from src.ham.transcription_config import (
    transcription_api_key,
    transcription_provider,
    transcription_runtime_configured,
)
from src.memory_heist import browser_policy_from_config, discover_config

router = APIRouter(tags=["chat"])
_LOG = logging.getLogger(__name__)

_chat_store = build_chat_session_store()


class ChatMessageIn(BaseModel):
    """``content`` is a string for assistant/system; user may also send ``ham_chat_user_v1`` JSON objects."""

    role: Literal["user", "assistant", "system"]
    content: str | dict[str, Any]


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
    # Execution routing preferences for browser/local-machine/chat control surfaces.
    execution_mode_preference: ExecutionModePreference = "auto"
    execution_environment: ExecutionEnvironment = "unknown"


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
    execution_mode: dict[str, Any] | None = None


def _gateway_status_code(code: str) -> int:
    if code == "INVALID_REQUEST":
        return 400
    if code == "CONFIG_ERROR":
        return 500
    return 502


_MAX_SYSTEM_PROMPT_CHARS = 12_000
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


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

**Control plane (skills & subagents):** When the message includes an **Operator skills** appendix, treat each entry as a real Ham workflow the IDE can run (Context Engine hardening, agent context wiring, Hermes review validation, prompt budget audit, repo regression tests). Include **`goham`** when the user wants **dashboard navigation help** (Cursor operator skill under `.cursor/skills/goham/` — **docs/UI**, not Electron managed-browser automation). Map user goals to the best-matching skill id and tell them the exact slash command or doc path (e.g. `/audit-context-engine`, `.cursor/skills/.../SKILL.md`). When a **Cursor subagent rules** appendix is present, each entry is a **review/audit charter** (`.cursor/rules/subagent-*.mdc`): recommend the charter that fits the user’s review question using id, path, and `globs`; subagents are **not** execution SKILLS—they shape how to audit or review code. When **structured UI actions** are enabled, you may also emit **`HAM_UI_ACTIONS_JSON`** so the browser can navigate (including **`/workspace/chat`**), show toasts, and toggle the **right-side control panel**—you still **do not** edit `.ham.json`, run shell tools, or change secrets from this chat.

**Navigation:** Product chat is **Hermes Workspace** at **`/workspace/chat`** (and **`/chat`** redirects there). Use **`navigate`** actions for in-app routes; use **`toggle_control_panel`** only for the right-hand workspace rail—not for layout modes (legacy workbench modes were removed).

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
    return lines


def _append_workbench_to_messages(
    llm_messages: list[dict[str, Any]],
    body: ChatRequest,
) -> list[dict[str, Any]]:
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


def _resolve_browser_adapter(project_id: str | None) -> str:
    root = _resolve_project_root_for_chat(project_id)
    if root is None:
        return "playwright"
    cfg = discover_config(root)
    policy = browser_policy_from_config(cfg)
    adapter = str(policy.get("adapter", "playwright")).strip().lower()
    return adapter if adapter in {"playwright", "chromium"} else "playwright"


def _execution_mode_payload(body: ChatRequest, *, last_user_plain: str) -> dict[str, Any]:
    env = body.execution_environment
    local_machine_available = env == "desktop"
    browser_available = browser_runtime_available()
    decision = resolve_execution_mode(
        preference=body.execution_mode_preference,
        environment=env,
        user_text=last_user_plain,
        browser_available=browser_available,
        local_machine_available=local_machine_available,
    )
    return {
        "requested_mode": decision.requested_mode,
        "selected_mode": decision.selected_mode,
        "auto_selected": decision.auto_selected,
        "environment": decision.environment,
        "browser_available": decision.browser_available,
        "local_machine_available": decision.local_machine_available,
        "browser_adapter": _resolve_browser_adapter(body.project_id) if decision.selected_mode == "browser" else None,
        "reason": decision.reason,
    }


def _build_browser_policy_spec(project_id: str | None) -> tuple[BrowserPolicySpec, str]:
    root = _resolve_project_root_for_chat(project_id)
    if root is None:
        policy = browser_policy_from_config(None)
    else:
        policy = browser_policy_from_config(discover_config(root))
    return (
        BrowserPolicySpec(
            max_steps=int(policy.get("max_steps", 25)),
            step_timeout_ms=int(policy.get("step_timeout_ms", 10_000)),
            max_dom_chars=int(policy.get("max_dom_chars", 8_000)),
            max_console_chars=int(policy.get("max_console_chars", 4_000)),
            max_network_events=int(policy.get("max_network_events", 200)),
            allowed_domains=list(policy.get("allowed_domains", [])),
            allow_file_download=bool(policy.get("allow_file_download", False)),
            allow_form_submit=bool(policy.get("allow_form_submit", False)),
        ),
        str(policy.get("adapter", "playwright")).strip().lower() or "playwright",
    )


def _build_browser_intent_for_turn(
    *,
    body: ChatRequest,
    last_user_plain: str,
) -> BrowserIntent | None:
    match = _URL_IN_TEXT_RE.search(last_user_plain or "")
    if not match:
        return None
    url = match.group(0).rstrip(".,;:!?")
    if not url:
        return None
    policy_spec, _adapter = _build_browser_policy_spec(body.project_id)
    rid = uuid4().hex
    return BrowserIntent(
        intent_id=f"chat-browser-intent-{rid}",
        request_id=f"chat-request-{rid}",
        run_id=f"chat-run-{rid}",
        start_url=url,
        steps=[
            BrowserStepSpec(
                step_id="navigate-1",
                action=BrowserAction.NAVIGATE,
                args={"url": url},
            ),
            BrowserStepSpec(
                step_id="screenshot-1",
                action=BrowserAction.SCREENSHOT,
                args={},
            ),
        ],
        policy=policy_spec,
        reason="Phase 3 browser intent trial for execution-mode routing.",
        tags=["chat", "phase3", "browser-intent"],
    )


def _build_browser_assembly_for_turn(body: ChatRequest) -> Any:
    _policy_spec, adapter = _build_browser_policy_spec(body.project_id)
    return SimpleNamespace(browser_executor=build_browser_executor(adapter), browser_adapter=adapter)


def _apply_browser_bridge_for_turn(
    *,
    execution_mode: dict[str, Any],
    body: ChatRequest,
    last_user_plain: str,
) -> dict[str, Any]:
    if execution_mode.get("selected_mode") != "browser":
        return execution_mode
    intent = _build_browser_intent_for_turn(body=body, last_user_plain=last_user_plain)
    if intent is None:
        execution_mode["browser_bridge"] = {
            "status": "skipped",
            "reason": "No URL detected in user message for browser intent routing.",
        }
        return execution_mode

    root = _resolve_project_root_for_chat(body.project_id)
    assembly = _build_browser_assembly_for_turn(body)
    result = run_browser_v0(assembly, intent, repo_root=root)
    execution_mode["browser_bridge"] = {
        "status": result.status.value,
        "summary": result.summary,
        "step_count": len(result.steps),
        "mutation_detected": result.mutation_detected,
    }
    _LOG.info(
        "Phase3 browser bridge run completed",
        extra={
            "chat_execution_mode": execution_mode.get("selected_mode"),
            "browser_status": result.status.value,
            "step_count": len(result.steps),
            "project_id": body.project_id,
        },
    )
    if (
        result.status
        in {
            BrowserRunStatus.BLOCKED,
            BrowserRunStatus.REJECTED,
            BrowserRunStatus.FAILED,
            BrowserRunStatus.TIMED_OUT,
            BrowserRunStatus.PARTIAL,
        }
        and bool(execution_mode.get("local_machine_available"))
    ):
        execution_mode["selected_mode"] = "machine"
        execution_mode["auto_selected"] = True
        execution_mode["reason"] = (
            f"Escalated browser->machine: browser runtime returned {result.status.value} and local machine is available."
        )
        execution_mode["escalated_from"] = "browser"
        execution_mode["escalation_trigger"] = result.status.value
        _LOG.info(
            "Phase3 execution-mode escalation browser->machine",
            extra={
                "browser_status": result.status.value,
                "project_id": body.project_id,
            },
        )
    return execution_mode


def _finalize_incoming_for_store(
    msgs: list[ChatMessageIn],
    *,
    attachment_user_id: str | None = None,
) -> list[dict[str, str]]:
    """Normalize request messages to string ``content`` suitable for session persistence."""
    from src.ham.chat_user_content import normalize_user_incoming_to_stored

    out: list[dict[str, str]] = []
    for m in msgs:
        if m.role in ("assistant", "system"):
            c = m.content
            if not isinstance(c, str) or not c.strip():
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "INVALID_MESSAGE",
                            "message": "Assistant and system messages require a non-empty string content.",
                        }
                    },
                )
            if len(c) > 100_000:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "MESSAGE_TOO_LONG",
                            "message": "Message exceeds maximum length.",
                        }
                    },
                )
            out.append({"role": m.role, "content": c})
        else:
            try:
                stored = normalize_user_incoming_to_stored(
                    m.content,
                    attachment_user_id=attachment_user_id,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "INVALID_USER_MESSAGE",
                            "message": str(exc),
                        }
                    },
                ) from exc
            out.append({"role": "user", "content": stored})
    return out


def _prepare_chat_session(
    body: ChatRequest,
    *,
    attachment_user_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, str]:
    """Returns ``(session_id, llm_messages, active_agent_meta, last_user_plain_for_operator)``."""
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

    incoming = _finalize_incoming_for_store(body.messages, attachment_user_id=attachment_user_id)
    last_user_plain = (
        plain_text_for_operator(incoming[-1]["content"])
        if incoming[-1]["role"] == "user"
        else ""
    )
    try:
        store.append_turns(sid, incoming)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "Unknown chat session.",
                }
            },
        ) from exc

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

    h_llm: list[dict[str, Any]] = []
    any_multimodal = False
    for h in history:
        role, stored = h["role"], h["content"]
        if role == "user":
            c = to_llm_message_content(stored)
            if isinstance(c, list):
                any_multimodal = True
            h_llm.append({"role": "user", "content": c})
        else:
            h_llm.append({"role": role, "content": stored})
    sys_content = base_system
    if any_multimodal:
        sys_content = f"{base_system}{vision_system_suffix()}"
        if len(sys_content) > _MAX_SYSTEM_PROMPT_CHARS:
            sys_content = sys_content[:_MAX_SYSTEM_PROMPT_CHARS]
    llm_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": sys_content,
        },
        *h_llm,
    ]
    return sid, llm_messages, active_meta, last_user_plain


def _messages_for_completion(
    body: ChatRequest,
    *,
    attachment_user_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any] | None, str]:
    sid, llm_messages, active_meta, last_user_plain = _prepare_chat_session(
        body,
        attachment_user_id=attachment_user_id,
    )
    or_override = _resolve_openrouter_model_override(body)
    llm_messages = _append_workbench_to_messages(llm_messages, body)
    return sid, llm_messages, or_override, active_meta, last_user_plain


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
    aid = ham_actor.user_id if ham_actor is not None else None
    sid, llm_messages, or_override, active_meta, last_user_plain = _messages_for_completion(
        body,
        attachment_user_id=aid,
    )
    execution_mode = _execution_mode_payload(body, last_user_plain=last_user_plain)
    execution_mode = _apply_browser_bridge_for_turn(
        execution_mode=execution_mode,
        body=body,
        last_user_plain=last_user_plain,
    )
    if body.enable_operator and operator_enabled() and body.messages[-1].role == "user":
        from src.persistence.project_store import get_project_store

        op = process_operator_turn(
            user_text=last_user_plain,
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
                execution_mode=execution_mode,
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
    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
    return ChatResponse(
        session_id=sid,
        messages=store.list_messages(sid),
        actions=actions,
        active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
        operator_result=None,
        execution_mode=execution_mode,
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
    aid = ham_actor.user_id if ham_actor is not None else None
    sid, llm_messages, or_override, stream_active_meta, last_user_plain = _messages_for_completion(
        body,
        attachment_user_id=aid,
    )
    stream_execution_mode = _execution_mode_payload(body, last_user_plain=last_user_plain)
    stream_execution_mode = _apply_browser_bridge_for_turn(
        execution_mode=stream_execution_mode,
        body=body,
        last_user_plain=last_user_plain,
    )

    if body.enable_operator and operator_enabled() and body.messages[-1].role == "user":
        from src.persistence.project_store import get_project_store

        op = process_operator_turn(
            user_text=last_user_plain,
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
                    "execution_mode": stream_execution_mode,
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
                        "execution_mode": stream_execution_mode,
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
            try:
                store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
                payload: dict[str, Any] = {
                    "type": "done",
                    "session_id": sid,
                    "messages": store.list_messages(sid),
                    "actions": actions,
                    "operator_result": None,
                    "execution_mode": stream_execution_mode,
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
    configured, _reason = transcription_runtime_configured()
    provider = transcription_provider()
    api_key = transcription_api_key()
    if not configured:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_NOT_CONFIGURED",
                    "message": "Transcription is not configured on this HAM API host.",
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
        status = exc.response.status_code
        error_type = None
        try:
            err_json = exc.response.json()
            if isinstance(err_json, dict) and isinstance(err_json.get("error"), dict):
                error_type = str((err_json.get("error") or {}).get("type") or "").strip() or None
        except Exception:
            pass
        _LOG.warning(
            "Transcription upstream rejected request",
            extra={
                "provider": provider,
                "status_code": status,
                "error_type": error_type or "unknown",
            },
        )
        if status in (401, 403):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "TRANSCRIPTION_PROVIDER_REJECTED",
                        "message": "Transcription provider rejected the server configuration.",
                    },
                },
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_UPSTREAM_FAILED",
                    "message": "Transcription provider request failed.",
                }
            },
        ) from exc
    except httpx.RequestError as exc:
        _LOG.warning(
            "Transcription upstream request error",
            extra={
                "provider": provider,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "TRANSCRIPTION_UPSTREAM_FAILED",
                    "message": "Transcription provider request failed.",
                },
            },
        ) from exc

    return TranscribeResponse(text=text)


def _coerce_request_mime(content_type: str | None, filename: str) -> str | None:
    raw = (content_type or "").split(";")[0].strip().lower()
    if raw == "image/jpg":
        raw = "image/jpeg"
    if raw in CHAT_UPLOAD_ALLOWED_MIME:
        return raw
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".md") or name.endswith(".markdown"):
        return "text/markdown"
    if name.endswith(".txt"):
        return "text/plain"
    return None


def _sniff_image_mime(head: bytes) -> str | None:
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/api/chat/attachments")
async def post_chat_attachment(
    file: UploadFile = File(...),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Upload a chat attachment; returns an opaque id (blobs are stored server-side, not in Firestore)."""
    ham_actor, _xham = _resolve_chat_clerk_context(
        authorization,
        None,
        route="post_chat_attachment",
    )
    cap = default_attachment_max_bytes()
    data = await file.read()
    if len(data) > cap:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "ATTACHMENT_TOO_LARGE",
                    "message": f"File exceeds maximum size ({cap} bytes).",
                },
            },
        )
    if not data:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "ATTACHMENT_EMPTY", "message": "Empty upload."}},
        )
    name = safe_upload_filename(file.filename or "attachment")
    sniffed = _sniff_image_mime(data[:64])
    if sniffed:
        mime = sniffed
    else:
        mime = _coerce_request_mime(file.content_type, name)
        if mime in ("text/plain", "text/markdown"):
            try:
                data.decode("utf-8")
            except UnicodeError as exc:
                raise HTTPException(
                    status_code=415,
                    detail={
                        "error": {
                            "code": "ATTACHMENT_TEXT_NOT_UTF8",
                            "message": "Text attachment must be valid UTF-8.",
                        },
                    },
                ) from exc
    if mime is None or mime not in CHAT_UPLOAD_ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail={
                "error": {
                    "code": "ATTACHMENT_UNSUPPORTED_TYPE",
                    "message": "Unsupported file type. Use png, jpeg, webp, plain text, or markdown.",
                },
            },
        )
    store = get_chat_attachment_store()
    aid = store.new_id()
    owner = ham_actor.user_id if ham_actor is not None else ""
    rec = AttachmentRecord(
        id=aid,
        filename=name,
        mime=mime,
        size=len(data),
        owner_key=owner,
        kind=kind_for_mime(mime),
    )
    try:
        store.put(data, rec)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "ATTACHMENT_STORE_FAILED", "message": str(exc)}},
        ) from exc
    return {
        "attachment_id": aid,
        "filename": name,
        "mime": mime,
        "size": len(data),
        "kind": rec.kind,
    }


@router.get("/api/chat/attachments/{attachment_id}")
async def get_chat_attachment(
    attachment_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
) -> Response:
    """Stream bytes for a previously uploaded chat attachment (requires same principal as uploader when set)."""
    ham_actor, _xham = _resolve_chat_clerk_context(
        authorization,
        None,
        route="get_chat_attachment",
    )
    store = get_chat_attachment_store()
    got = store.get(attachment_id)
    if got is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ATTACHMENT_NOT_FOUND", "message": "Unknown attachment id."}},
        )
    _raw, rec = got
    if (rec.owner_key or "").strip():
        if ham_actor is None or ham_actor.user_id != rec.owner_key:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "ATTACHMENT_FORBIDDEN",
                        "message": "Not allowed to read this attachment.",
                    },
                },
            )
    safe_name = (rec.filename or "file").replace('"', "").replace("\r", "").replace("\n", "")[:200]
    return Response(
        content=_raw,
        media_type=rec.mime,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )
