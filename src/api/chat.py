"""HAM-native interactive chat. Proxies to server-side gateway adapter; optional NDJSON streaming."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock
from time import monotonic
from types import SimpleNamespace
from typing import Any, Callable, Literal, Self
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.clerk_gate import enforce_clerk_session_and_email_for_request
from src.api.models_catalog import build_catalog_payload, resolve_model_id_for_chat
from src.api.workspace_files import resolve_workspace_context_snapshot_root
from src.bridge import (
    BrowserAction,
    BrowserIntent,
    BrowserPolicySpec,
    BrowserRunStatus,
    BrowserStepSpec,
    build_browser_executor,
    run_browser_v0,
)
from src.ham.active_agent_context import try_active_agent_guidance_for_project_root
from src.ham.chat_attachment_store import (
    CHAT_UPLOAD_ALLOWED_MIME,
    AttachmentRecord,
    default_attachment_max_bytes,
    get_chat_attachment_store,
    kind_for_mime,
    safe_upload_filename,
)
from src.ham.chat_context_meters import (
    DEFAULT_THREAD_BUDGET_CHARS,
    compute_this_turn_meter_block,
    compute_thread_meter_block,
    context_meters_feature_enabled,
    resolve_model_context_tokens,
    workspace_snapshot_and_meter,
)
from src.ham.chat_operator import (
    ChatOperatorPayload,
    OperatorTurnResult,
    format_operator_assistant_message,
    operator_enabled,
    process_agent_router_turn,
    process_operator_turn,
)
from src.ham.chat_user_content import (
    has_screenshot_in_stored,
    normalize_user_incoming_to_stored,
    plain_text_for_operator,
    to_llm_message_content,
    vision_system_suffix,
)
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
from src.ham.cursor_skills_catalog import list_cursor_skills, render_skills_for_system_prompt
from src.ham.cursor_subagents_catalog import (
    list_cursor_subagents,
    render_subagents_for_system_prompt,
)
from src.ham.execution_mode import (
    ExecutionEnvironment,
    ExecutionModePreference,
    browser_runtime_available,
    resolve_execution_mode,
)
from src.ham.builder_chat_hooks import (
    resolve_effective_chat_project_id,
    run_builder_happy_path_hook,
)
from src.ham.builder_chat_intent import classify_builder_chat_intent
from src.ham.operator_audit import append_operator_action_audit
from src.ham.transcription_config import resolve_transcription_openai_api_key_for_actor
from src.ham.ui_actions import split_assistant_ui_actions, ui_actions_system_instructions
from src.integrations.nous_gateway_client import (
    GatewayCallError,
    complete_chat_turn,
    format_gateway_error_user_message,
    stream_chat_turn,
)
from src.llm_client import openrouter_api_key_is_plausible, resolve_openrouter_api_key_for_actor
from src.memory_heist import browser_policy_from_config, discover_config
from src.metadata_stamps import ScanMode
from src.persistence.chat_session_store import ChatTurn, build_chat_session_store
from src.persistence.connected_tool_credentials import resolve_connected_tool_secret_plaintext
from src.persistence.project_store import get_project_store

router = APIRouter(tags=["chat"])
_LOG = logging.getLogger(__name__)

_chat_store = build_chat_session_store()


class ChatMessageIn(BaseModel):
    """``content`` is a string for assistant/system; user may also send ``ham_chat_user_v1`` JSON objects."""

    role: Literal["user", "assistant", "system"]
    content: str | dict[str, Any]


class ChatRequest(BaseModel):
    session_id: str | None = None
    messages: list[ChatMessageIn] = Field(
        min_length=1,
        max_length=1,
        description=(
            "Exactly one new user turn per request. When session_id is set, prior transcript is loaded "
            "server-side; do not resend earlier user/assistant messages from the browser."
        ),
    )
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
    # Workspace-scoped chat history (Phase 2a). Optional for legacy v1 compatibility.
    workspace_id: str | None = Field(default=None, max_length=180)
    model_id: str | None = Field(default=None, max_length=256)
    workbench_mode: Literal["ask", "plan", "agent"] | None = None
    # When true, builder workspace chat proposes a short markdown plan before build/edit.
    plan_mode: bool = False
    worker: str | None = Field(default=None, max_length=64)
    max_mode: bool | None = None
    # Server-side operator (projects, agents preview/apply, runs, launch) — see docs/HAM_CHAT_CONTROL_PLANE.md
    enable_operator: bool = True
    operator: ChatOperatorPayload | None = None
    # Execution routing preferences for browser/local-machine/chat control surfaces.
    execution_mode_preference: ExecutionModePreference = "auto"
    execution_environment: ExecutionEnvironment = "unknown"

    @model_validator(mode="after")
    def _incremental_user_turn_only(self) -> Self:
        m0 = self.messages[0]
        if m0.role != "user":
            raise ValueError(
                "Chat requests must include a single user message. "
                "Do not send assistant or system history from the client; the API loads stored turns when session_id is set."
            )
        return self


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
    builder: dict[str, Any] | None = None
    artifact_verification: dict[str, Any] | None = None
    hermes_http_context_budget: dict[str, Any] | None = None


class ChatSessionAppendTurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatSessionAppendRequest(BaseModel):
    turns: list[ChatSessionAppendTurnIn] = Field(min_length=1, max_length=20)


def _gateway_status_code(code: str) -> int:
    if code == "INVALID_REQUEST":
        return 400
    if code == "CONFIG_ERROR":
        return 500
    if code == "OPENROUTER_MODEL_REJECTED":
        return 502
    return 502


_MAX_SYSTEM_PROMPT_CHARS = 12_000
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
_STREAM_PARTIAL_NOTE = "\n\nConnection interrupted. Ask me to continue."
_STREAM_PRETOKEN_ABORT_ASSISTANT = (
    "The response was interrupted before I could complete it. "
    "Please ask me to continue or retry the edit."
)
_STREAM_CHECKPOINT_MIN_CHARS = 800
_STREAM_CHECKPOINT_MIN_SEC = 1.5
_BUILDER_STREAM_SOURCE_SAVED_LINE = (
    "I've saved the project source to your workspace. Browse files in the Workbench Code tab."
)
_BUILDER_STREAM_PREVIEW_STARTING_LINE = (
    "Cloud preview is starting in the Workbench Preview tab (sandbox only—not deployed). "
    "Watch progress there with Refresh status; if it does not load, use Retry preview."
)
_BUILDER_STREAM_PREVIEW_NOT_CONFIGURED_LINE = (
    "Cloud preview is not configured in this environment. You can still use the Code tab; "
    "connect a local preview URL in Advanced when your dev server is running."
)
# In-memory per-instance lease; stale locks expire so poisoned sessions recover without restart.
_DEFAULT_STREAM_LOCK_TTL_SEC = 480.0  # 8m — above Cloud Run's common ~300s request ceiling
_MIN_STREAM_LOCK_TTL_SEC = 30.0
_DEFAULT_STREAM_LOCK_RETRY_AFTER_MS = 3000
_MAX_STREAM_LOCK_RETRY_AFTER_MS = 30_000

_ACTIVE_STREAM_SESSIONS: dict[str, tuple[float, int]] = {}
_ACTIVE_STREAM_SESSIONS_LOCK = RLock()
_STREAM_LOCK_GENERATION = 0


@dataclass(frozen=True)
class _StreamLockClaim:
    claimed: bool
    lock_token: int | None = None
    lock_age_sec: float | None = None
    retry_after_ms: int | None = None
    reclaimed_stale: bool = False


def _stream_lock_ttl_sec() -> float:
    raw = os.getenv("HAM_CHAT_STREAM_LOCK_TTL_SEC", str(_DEFAULT_STREAM_LOCK_TTL_SEC))
    try:
        ttl = float(raw)
    except (TypeError, ValueError):
        ttl = _DEFAULT_STREAM_LOCK_TTL_SEC
    return max(_MIN_STREAM_LOCK_TTL_SEC, ttl)


def _stream_lock_retry_after_ms(remaining_ttl_sec: float) -> int:
    ms = int(remaining_ttl_sec * 1000)
    ms = max(ms, _DEFAULT_STREAM_LOCK_RETRY_AFTER_MS)
    return min(ms, _MAX_STREAM_LOCK_RETRY_AFTER_MS)


def _stream_already_active_detail(
    *,
    lock_age_sec: float | None,
    retry_after_ms: int,
) -> dict[str, Any]:
    err: dict[str, Any] = {
        "code": "STREAM_ALREADY_ACTIVE",
        "message": (
            "A stream is already active for this session. "
            "Wait for it to finish before starting another."
        ),
        "retry_after_ms": retry_after_ms,
    }
    if lock_age_sec is not None:
        err["lock_age_sec"] = round(lock_age_sec, 3)
    return {"error": err}


def _claim_stream_session(session_id: str) -> _StreamLockClaim:
    global _STREAM_LOCK_GENERATION
    now = monotonic()
    ttl = _stream_lock_ttl_sec()
    with _ACTIVE_STREAM_SESSIONS_LOCK:
        entry = _ACTIVE_STREAM_SESSIONS.get(session_id)
        if entry is not None:
            claimed_at, _ = entry
            age = now - claimed_at
            if age < ttl:
                return _StreamLockClaim(
                    claimed=False,
                    lock_age_sec=age,
                    retry_after_ms=_stream_lock_retry_after_ms(ttl - age),
                )
            _STREAM_LOCK_GENERATION += 1
            token = _STREAM_LOCK_GENERATION
            _ACTIVE_STREAM_SESSIONS[session_id] = (now, token)
            return _StreamLockClaim(claimed=True, lock_token=token, reclaimed_stale=True)
        _STREAM_LOCK_GENERATION += 1
        token = _STREAM_LOCK_GENERATION
        _ACTIVE_STREAM_SESSIONS[session_id] = (now, token)
        return _StreamLockClaim(claimed=True, lock_token=token)


def _release_stream_session(session_id: str, lock_token: int | None = None) -> None:
    with _ACTIVE_STREAM_SESSIONS_LOCK:
        entry = _ACTIVE_STREAM_SESSIONS.get(session_id)
        if entry is None:
            return
        if lock_token is not None and entry[1] != lock_token:
            return
        _ACTIVE_STREAM_SESSIONS.pop(session_id, None)


def _reset_active_stream_sessions_for_testing() -> None:
    with _ACTIVE_STREAM_SESSIONS_LOCK:
        _ACTIVE_STREAM_SESSIONS.clear()


def _eligible_upstream_vision_text_fallback(
    exc: GatewayCallError,
    *,
    had_stream_tokens: bool,
) -> bool:
    """Single retry stripping multimodal payloads when Hermes rejects the first request (+ no tokens yet)."""
    if had_stream_tokens:
        return False
    if exc.code != "UPSTREAM_REJECTED":
        return False
    raw = (os.environ.get("HAM_CHAT_VISION_UPSTREAM_TEXT_FALLBACK") or "1").strip().lower()
    return raw not in {"0", "false", "no"}


def _llm_upstream_text_fallback_messages(
    session_id: str,
    *,
    baseline_llm_messages: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """
    When upstream rejects multimodal content, rebuild messages with the last user's turn expressed as plain text
    plus an explicit ``image withheld`` marker (pixels were never modeled).
    """
    hist = _chat_store.list_messages(session_id)
    stored: str | None = None
    for row in reversed(hist):
        if row.get("role") != "user":
            continue
        c_any = row.get("content")
        if isinstance(c_any, str) and (c_any or "").strip():
            stored = c_any.strip()
            break
    if not stored:
        return None

    had_multimodal_candidate = False
    for m in baseline_llm_messages:
        if str(m.get("role") or "") != "user":
            continue
        c = m.get("content")
        if isinstance(c, list):
            had_multimodal_candidate = True
            break
    if not had_multimodal_candidate:
        return None

    plain = plain_text_for_operator(stored)
    if has_screenshot_in_stored(stored):
        plain = (
            f"{plain}\n\n"
            "[Technical: the upstream model gateway refused the multimodal request, so image payloads were "
            "withheld for this retry. Answer from the user's text and these markers only; do not pretend you saw "
            "the images.]"
        ).strip()

    try:
        cloned: list[dict[str, Any]] = json.loads(json.dumps(baseline_llm_messages))
    except (TypeError, ValueError):
        return None

    last_user_idx = -1
    for i in range(len(cloned) - 1, -1, -1):
        if cloned[i].get("role") != "user":
            continue
        if isinstance(cloned[i].get("content"), list):
            last_user_idx = i
            break
    if last_user_idx < 0:
        return None

    cloned[last_user_idx]["content"] = plain
    sys0 = cloned[0].get("content")
    suf = vision_system_suffix()
    if isinstance(sys0, str) and sys0.endswith(suf):
        cloned[0]["content"] = sys0[: -len(suf)].rstrip()
    return cloned


def _resolve_chat_clerk_context(
    authorization: str | None,
    x_ham_operator_authorization: str | None,
    *,
    route: str,
) -> tuple[HamActor | None, str | None]:
    """Clerk session on ``Authorization`` when operator auth or email enforcement is on; HAM tokens on ``X-Ham-Operator-Authorization``.

    Falls back to synthetic local-dev actor when ``HAM_LOCAL_DEV_WORKSPACE_BYPASS``
    is enabled and no Clerk session is available (allows builder scaffold to resolve
    workspace/project without Clerk credentials in local dev).
    """
    ham_hdr = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    actor = enforce_clerk_session_and_email_for_request(authorization, route=route)
    if actor is None:
        from src.api.dependencies.workspace import (
            LOCAL_DEV_BYPASS_ENV,
            synthetic_local_dev_actor,
        )

        bypass_raw = (os.environ.get(LOCAL_DEV_BYPASS_ENV) or "").strip().lower()
        if bypass_raw in ("1", "true", "yes", "on"):
            actor = synthetic_local_dev_actor()
    return actor, ham_hdr


def _normalized_workspace_id(workspace_id: str | None) -> str | None:
    wid = (workspace_id or "").strip()
    return wid or None


def _scoped_user_id(ham_actor: HamActor | None, workspace_id: str | None) -> str | None:
    if workspace_id is None or ham_actor is None:
        return None
    return ham_actor.user_id


def _session_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Unknown chat session."}},
    )


def _get_session_for_scope(
    session_id: str,
    *,
    user_id: str | None,
    workspace_id: str | None,
    authenticated_actor_user_id: str | None = None,
):
    rec = _chat_store.get_session(session_id)
    if rec is None:
        raise _session_not_found()
    if workspace_id is not None:
        if rec.workspace_id != workspace_id or rec.user_id != user_id:
            raise _session_not_found()
        return rec
    # Request did not pin a workspace: still enforce ownership when the record is tenant-scoped
    # so omitting workspace_id cannot bypass user/workspace isolation (chat append / delete / export).
    if rec.workspace_id is not None or rec.user_id is not None:
        if authenticated_actor_user_id is None or rec.user_id != authenticated_actor_user_id:
            raise _session_not_found()
    return rec


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
            "permission_granted": actor_has_permission(ham_actor, req)
            if (ham_actor and req)
            else None,
            "intent": op.intent,
            "operator_phase": body.operator.phase if body.operator else None,
            "operator_ok": op.ok,
            "blocking_reason": op.blocking_reason,
            "route": route,
            "audit_sink": "ham_local_jsonl",
        }
    )


_CHAT_CONVERSATIONAL_MODEL_ENV = "HAM_CHAT_CONVERSATIONAL_MODEL"
_CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK = Lock()
_chat_conversational_model_notice_emitted = False


def _chat_conversational_model_default() -> str | None:
    raw = os.environ.get(_CHAT_CONVERSATIONAL_MODEL_ENV)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if "\n" in stripped or "\r" in stripped:
        return None
    normalized = stripped if stripped.startswith("openrouter/") else f"openrouter/{stripped}"
    _emit_chat_conversational_model_notice_once(normalized)
    return normalized


def _emit_chat_conversational_model_notice_once(model_id: str) -> None:
    global _chat_conversational_model_notice_emitted
    if _chat_conversational_model_notice_emitted:
        return
    with _CHAT_CONVERSATIONAL_MODEL_NOTICE_LOCK:
        if _chat_conversational_model_notice_emitted:
            return
        _chat_conversational_model_notice_emitted = True
        _LOG.info(
            "chat_conversational_model: lane enabled (env-derived model id)",
            extra={"chat_conversational_model": model_id},
        )


# Shipped default so the model is product-aware without requiring env (override with HAM_CHAT_SYSTEM_PROMPT).
_DEFAULT_CHAT_SYSTEM_PROMPT = """
You are **Ham**, the in-dashboard copilot for the Ham workspace. Speak in first person — warm, concise, specific. Use short paragraphs or tight bullets and offer concrete next steps. You cannot see the user's screen, route, or settings; if context matters, ask them to describe it.

**Identity & lore.** Ham's product origin story is canon: you are the first code monkey launched into space. Embrace this lore when the user asks who you are, where you came from, what HAM is, what you've been up to, or about your origin — never deny it, never call it a myth, never frame it as false. Use the lore lightly and only when relevant (identity, origin, mascot, onboarding, casual check-ins). Do not force the lore into unrelated technical, coding, build, or support replies.

**Casual voice.** For casual self-description, identity, or check-in prompts like "who are you", "tell me about yourself", "what is HAM", or "what have you been up to", reply warmly, playfully, and concisely as Ham. Do not list internal tools, providers, builders, skills, catalogs, or runtimes unless the user explicitly asks about your capabilities, tools, or builders. Prefer a warm, useful, HAM-branded answer over an inventory dump.

**Builder Studio.** Builder Studio is where you configure the builders HAM can use. Work still starts in chat: HAM turns your request into a plan, asks for approval when gates apply, then uses the right builder to create, edit, or save the result. Studio alone does not publish or ship apps.

**No fabricated execution.** You have NO shell, NO git, NO build, NO push, NO PR, NO cron, and NO filesystem tools in this chat. You cannot edit files, create or amend commits, push branches, open pull requests, schedule jobs, or modify secrets here. Never invent commit hashes, file paths, run ids, snapshot ids, PR URLs, runnable previews, or packaged deliverables unless surfaced this turn. A chain like "I edited X, then committed Y" is fabrication and is prohibited.

**Route coding-execution to the real flow.** For repo mutation work (edit/refactor/snapshot/commit/push/open PR/patch this repository), do NOT attempt execution in chat. The chat client auto-detects these intents and surfaces the **Coding Plan card** inline (the *Plan with coding agents* button is the manual fallback); workspace-backed executions surface the **workspace build approval panel** that collects approvals before Builder work. Describe those checkpoints with conversational words such as workspace build / builder run / build plan rather than dusty internal playbook phrasing. Remind reviewers to approve before Builder work starts. Do NOT suggest `delegate_task` or other vendored adapters for coding execution.

**Completion-claim rule.** Words like done, ready, built, generated, shipped, merged, committed, pushed, preview available, preview live, or claims that projects are finished require echoed `ham_run_id`, `snapshot_id`, `pr_url`, `control_plane_run_id`, or clear Builder/UI evidence logged for this workspace. Without those signals, sketch the plan instead of narrating calculators, zipped trees, previews, snapshots, shipped builds, jobs, or live sandboxes. If upstream model credentials are unavailable, admit it plainly rather than implying deliverables landed.

**Honesty:** If you lack a fact, ask a clarifying question instead of inventing menu labels, file paths, commit hashes, or features.""".strip()


_CASUAL_SELF_DESCRIPTION_PHRASES: tuple[str, ...] = (
    "who are you",
    "who r u",
    "what are you",
    "what is ham",
    "what's ham",
    "whats ham",
    "tell me about yourself",
    "introduce yourself",
    "what have you been up to",
    "what've you been up to",
    "what you been up to",
    "what you up to",
    "how are you",
    "how's it going",
    "hows it going",
    "first code monkey",
    "code monkey",
    "space monkey",
    "launched into space",
)


_EXPLICIT_TOOL_INVENTORY_PHRASES: tuple[str, ...] = (
    "what tools",
    "which tools",
    "list tools",
    "list your tools",
    "tools do you have",
    "tools you have",
    "available tools",
    "show me your tools",
    "what builders",
    "which builders",
    "list builders",
    "builders do you have",
    "what capabilities",
    "which capabilities",
    "list capabilities",
    "your capabilities",
    "what can you do",
    "what are you capable",
    "what skills",
    "your skills",
    "your subagents",
    "your active agent",
    "what providers",
    "your providers",
)


def _classify_chat_inventory_intent(user_text: str) -> tuple[bool, bool]:
    """Return ``(is_casual_self_description, is_explicit_tool_inventory)`` from the latest user turn.

    Casual identity / check-in prompts should suppress internal tool/provider/builder inventory
    context unless the user explicitly asks about capabilities/tools/builders.
    """
    t = (user_text or "").lower()
    is_casual = any(phrase in t for phrase in _CASUAL_SELF_DESCRIPTION_PHRASES)
    is_inventory = any(phrase in t for phrase in _EXPLICIT_TOOL_INVENTORY_PHRASES)
    return is_casual, is_inventory


def _effective_inventory_gating(
    body: ChatRequest,
    last_user_plain: str,
) -> tuple[bool, bool, bool]:
    """Return effective ``(include_skills, include_subagents, include_active_agent_guidance)``.

    When the user's latest turn is a casual self-description / check-in and they did not
    explicitly ask about tools/builders/capabilities, suppress the operator skills,
    cursor-subagent rules, and active-agent catalog blocks so casual chat stays warm and
    HAM-branded rather than dumping internal inventory. Real capabilities/routing remain
    available — only the casual-context system prompt is gated.
    """
    is_casual, is_explicit_inventory = _classify_chat_inventory_intent(last_user_plain)
    suppress = is_casual and not is_explicit_inventory
    include_skills = body.include_operator_skills and not suppress
    include_subagents = body.include_operator_subagents and not suppress
    include_active = body.include_active_agent_guidance and not suppress
    return include_skills, include_subagents, include_active


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


_BUILDER_TURN_SYSTEM_INJECTION = (
    "**Builder turn override.** The user's message was classified as a greenfield builder prompt "
    "(build/create/make/generate an app, site, game, dashboard, tracker, or similar). "
    "This is a workspace Builder turn. You MUST:\n"
    "- Acknowledge the builder action concisely and product-specifically.\n"
    "- Do NOT imply the project is runnable, previewed, zipped, snapped, deployed, merged, shipped, "
    'generated, finished, "ready", or "complete" unless the user already sees real '
    "Workbench/builder activity tied to this turn.\n"
    "- Prefer outlining the UX and offering a concise build plan instead of pretending code exists.\n"
    "- Outline what will happen next with plain phrases (workspace build, builder run, build plan).\n"
    "- Never mimic the legacy staged hyphenated routing label historically used around gated snapshots.\n"
    "- Avoid steering users toward Coding Plan escapes, Cursor cloud launchpads, stray agent sessions, "
    '"Plan with coding agents" chatter, Cloud Agent narration, '
    '"I can\'t build directly from chat," or anything that skips approval.\n'
    "- Keep Builder approval gates intact — never autosubmit plans or approvals.\n"
    '- Do NOT promise iterative or staged ongoing build work (e.g. "I\'ll keep adding…", '
    '"as the build progresses…", "I\'ll then add…", "next I\'ll…", "I\'ll iterate on…") '
    "or imply a multi-step agent is building in the background.\n"
    "- Ground every claim in this workspace's builder records only. NEVER invent local filesystem "
    "paths, games/apps on the user's machine, or offers to open something in their browser.\n"
    '- NEVER refer to "this machine", "your computer", pre-existing local projects, or off-workspace files.\n'
)

_BUILDER_GROUNDING_SYSTEM_INJECTION = (
    "**Builder workspace grounding.** This chat turn is inside a HAM Builder workspace. "
    "You MUST ground every factual claim in Workbench/builder records for this project only.\n"
    "- NEVER invent local files, paths, games/apps on the user's machine, or runtime state not backed "
    "by workspace builder records.\n"
    '- NEVER say "on this machine", "your computer", "game files actually went", or offer to '
    '"open it in your browser" unless the Workbench already shows that artifact.\n'
    "- If preview/source/job state is unknown, say so honestly and offer to build or retry in the "
    "Workbench — do not guess or narrate a local environment.\n"
)


def _inject_builder_turn_system(
    llm_messages: list[dict[str, Any]],
    builder_intent: str,
    *,
    in_builder_workspace: bool = False,
) -> list[dict[str, Any]]:
    """Inject per-turn system guidance for builder workspace turns."""
    if builder_intent != "build_or_create" and not in_builder_workspace:
        return llm_messages
    block = (
        f"{_BUILDER_TURN_SYSTEM_INJECTION}\n\n{_BUILDER_GROUNDING_SYSTEM_INJECTION}".strip()
        if builder_intent == "build_or_create"
        else _BUILDER_GROUNDING_SYSTEM_INJECTION
    )
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


def _resolve_chat_openrouter_route(
    *,
    body: ChatRequest,
    ham_actor: HamActor | None,
    allow_conversational_default: bool = True,
) -> tuple[str | None, str | None, bool, str | None]:
    """Return (liteLLM model override, user OpenRouter hint key, bypass Hermes-http for LiteLLM, http_model_override).

    ``allow_conversational_default`` gates the HAM_CHAT_CONVERSATIONAL_MODEL fallback. Callers
    on the builder build_or_create lane pass ``False`` so structured/builder turns preserve
    existing gateway model behavior instead of receiving the conversational sentinel.

    ``http_model_override`` is non-None only for normal conversational/direct-answer HTTP
    turns when the conversational helper returns a slug. It is forwarded to the Hermes HTTP
    primary request only; OpenRouter/BYOK-LiteLLM routes ignore it.
    """

    gw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    hinted_key = ""
    if ham_actor is not None:
        hinted_key = (
            resolve_connected_tool_secret_plaintext(ham_actor, "openrouter") or ""
        ).strip()

    user_key_ready = bool(hinted_key and openrouter_api_key_is_plausible(hinted_key))
    mid_raw = body.model_id
    mid_stripped = str(mid_raw).strip() if mid_raw else ""

    if gw == "http":
        if not mid_stripped:
            http_override = (
                _chat_conversational_model_default() if allow_conversational_default else None
            )
            return (
                None,
                hinted_key if user_key_ready else None,
                False,
                http_override,
            )
        if ham_actor is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "CONNECT_OPENROUTER_REQUIRED",
                        "message": (
                            "Sign in and connect OpenRouter under Workspace → Connected Tools "
                            "before choosing this model alongside the Hermes HTTP gateway."
                        ),
                    },
                },
            )
        if not user_key_ready:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "CONNECT_OPENROUTER_REQUIRED",
                        "message": (
                            "Connect OpenRouter under Workspace → Connected Tools to use per-model "
                            "dashboard chat."
                        ),
                    },
                },
            )

        try:
            model_override = resolve_model_id_for_chat(mid_stripped, ham_actor)
        except ValueError as exc:
            code = str(exc)
            if code == "CURSOR_MODEL_NOT_CHAT_ENABLED":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "CURSOR_MODEL_NOT_CHAT_ENABLED",
                            "message": "Cursor API models are not available for dashboard chat; pick OpenRouter.",
                        },
                    },
                ) from exc
            if code == "MODEL_NOT_AVAILABLE_FOR_CHAT":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "MODEL_NOT_AVAILABLE_FOR_CHAT",
                            "message": "Selected model is not available for chat (gateway or configuration).",
                        },
                    },
                ) from exc
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "UNKNOWN_MODEL_ID",
                        "message": "Unknown model_id for chat.",
                    },
                },
            ) from exc
        return model_override, hinted_key, True, None

    if gw == "openrouter":
        if not mid_stripped:
            conversational_default = (
                _chat_conversational_model_default() if allow_conversational_default else None
            )
            return (
                conversational_default,
                hinted_key if user_key_ready else None,
                False,
                None,
            )
        try:
            model_override = resolve_model_id_for_chat(mid_stripped, ham_actor)
        except ValueError as exc:
            code = str(exc)
            if code == "CURSOR_MODEL_NOT_CHAT_ENABLED":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "CURSOR_MODEL_NOT_CHAT_ENABLED",
                            "message": "Cursor API models are not available for dashboard chat; pick OpenRouter.",
                        },
                    },
                ) from exc
            if code == "MODEL_NOT_AVAILABLE_FOR_CHAT":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "MODEL_NOT_AVAILABLE_FOR_CHAT",
                            "message": "Selected model is not available for chat (gateway or configuration).",
                        },
                    },
                ) from exc
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "UNKNOWN_MODEL_ID",
                        "message": "Unknown model_id for chat.",
                    },
                },
            ) from exc

        return model_override, hinted_key if user_key_ready else None, False, None

    if mid_stripped:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "MODEL_SELECTION_REQUIRES_OPENROUTER",
                    "message": "Per-request model selection is not available on this server. "
                    "Connect OpenRouter under Workspace → Connected Tools to choose a model for chat.",
                },
            },
        )
    return None, None, False, None


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
        "browser_adapter": _resolve_browser_adapter(body.project_id)
        if decision.selected_mode == "browser"
        else None,
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
    return SimpleNamespace(
        browser_executor=build_browser_executor(adapter), browser_adapter=adapter
    )


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
    if result.status in {
        BrowserRunStatus.BLOCKED,
        BrowserRunStatus.REJECTED,
        BrowserRunStatus.FAILED,
        BrowserRunStatus.TIMED_OUT,
        BrowserRunStatus.PARTIAL,
    } and bool(execution_mode.get("local_machine_available")):
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
    user_id: str | None = None,
    attachment_user_id: str | None = None,
    llm_attachment_user_id: str | None = None,
    authenticated_actor_user_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, str]:
    """Returns ``(session_id, llm_messages, active_agent_meta, last_user_plain_for_operator)``."""
    store = _chat_store
    workspace_id = _normalized_workspace_id(body.workspace_id)
    if body.session_id:
        _get_session_for_scope(
            body.session_id,
            user_id=user_id if workspace_id is not None else None,
            workspace_id=workspace_id,
            authenticated_actor_user_id=authenticated_actor_user_id,
        )
        sid = body.session_id
    else:
        sid = store.create_session(user_id=user_id, workspace_id=workspace_id)

    incoming = _finalize_incoming_for_store(body.messages, attachment_user_id=attachment_user_id)
    last_user_plain = (
        plain_text_for_operator(incoming[-1]["content"]) if incoming[-1]["role"] == "user" else ""
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
    include_skills_eff, include_subagents_eff, include_active_eff = _effective_inventory_gating(
        body,
        last_user_plain,
    )
    base_system = _chat_system_prompt(
        include_operator_skills=include_skills_eff,
        include_operator_subagents=include_subagents_eff,
        enable_ui_actions=body.enable_ui_actions,
    )
    active_meta: dict[str, Any] | None = None
    if include_active_eff:
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
            c = to_llm_message_content(stored, attachment_user_id=llm_attachment_user_id)
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
    user_id: str | None = None,
    attachment_user_id: str | None = None,
    llm_attachment_user_id: str | None = None,
    authenticated_actor_user_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, str]:
    sid, llm_messages, active_meta, last_user_plain = _prepare_chat_session(
        body,
        user_id=user_id,
        attachment_user_id=attachment_user_id,
        llm_attachment_user_id=llm_attachment_user_id,
        authenticated_actor_user_id=authenticated_actor_user_id,
    )
    llm_messages = _append_workbench_to_messages(llm_messages, body)
    return sid, llm_messages, active_meta, last_user_plain


def _with_interrupted_note(content: str) -> str:
    base = content.rstrip()
    if not base:
        return "Connection interrupted before any content was saved. Ask me to continue."
    if base.endswith(_STREAM_PARTIAL_NOTE.strip()):
        return base
    return f"{base}{_STREAM_PARTIAL_NOTE}"


def _builder_stream_should_handoff_early(
    builder_intent: str, builder_meta: dict[str, Any] | None
) -> bool:
    if builder_intent != "build_or_create":
        return False
    meta = builder_meta or {}
    return bool(meta.get("scaffolded") or meta.get("deduplicated"))


def _builder_artifact_verification_failed(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("artifact_verification_failed"))


def _builder_llm_scaffold_failed(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("llm_scaffold_failed"))


def _builder_model_access_required(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("model_access_required"))


def _builder_has_active_source_snapshot(builder_meta: dict[str, Any] | None) -> bool:
    meta = builder_meta or {}
    if bool(meta.get("scaffolded") or meta.get("deduplicated")):
        return True
    return bool(str(meta.get("source_snapshot_id") or "").strip())


def _builder_should_short_circuit_failure(builder_meta: dict[str, Any] | None) -> bool:
    return (
        _builder_llm_scaffold_failed(builder_meta)
        or _builder_model_access_required(builder_meta)
        or _builder_artifact_verification_failed(builder_meta)
        or _builder_edit_worker_blocked(builder_meta)
    )


def _builder_skip_planner_for_net_new_build(
    builder_intent: str,
    builder_meta: dict[str, Any] | None,
) -> bool:
    return builder_intent == "build_or_create" and not _builder_has_active_source_snapshot(
        builder_meta
    )


# Streamed only on the deferred path, which now runs solely for explicit Quick
# Preview builds (see _should_defer_builder_scaffold_hook). Labeled as a preview,
# not a product build.
_BUILDER_STREAM_NET_NEW_ACK = "Generating a quick preview from this prompt…\n\n"


def _should_defer_builder_scaffold_hook(
    *,
    last_user_plain: str,
    workspace_id: str | None,
    project_id: str | None,
    ham_actor: HamActor | None,
    plan_mode: bool = False,
) -> bool:
    """Defer sync scaffold LLM for empty-project build turns so stream bytes start first."""
    if plan_mode:
        return False
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    plain = str(last_user_plain or "").strip()
    if not ws or not pid or not plain:
        return False
    if classify_builder_chat_intent(plain) != "build_or_create":
        return False
    if not resolve_openrouter_api_key_for_actor(ham_actor):
        return False
    # User-selected builder model: only an explicit Quick Preview build runs the
    # internal scaffold synchronously. Normal builds resolve to a builder
    # handoff / "choose a builder" reply (no scaffold), so they take the
    # synchronous path — no deferred preview ack that would contradict the reply.
    from src.ham.builder_chat_hooks import _looks_like_quick_preview_request

    if not _looks_like_quick_preview_request(plain):
        return False
    from src.persistence.builder_source_store import get_builder_source_store

    rows = get_builder_source_store().list_project_sources(workspace_id=ws, project_id=pid)
    has_active = any(bool(str(row.active_snapshot_id or "").strip()) for row in rows)
    return not has_active


def _builder_edit_worker_blocked(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("builder_edit_worker_blocked"))


def _builder_clarification_turn(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("builder_clarification"))


def _builder_grounded_status_turn(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("builder_grounded_status"))


def _builder_harness_first_turn(builder_meta: dict[str, Any] | None) -> bool:
    """Harness-first build turn: a premium harness is available, so the hook
    returned a transitional pointer instead of running the internal scaffold.

    Emitted as a clean terminal text reply via the same path as the grounded
    status turn (no LLM completion, no scaffold)."""
    return bool((builder_meta or {}).get("builder_harness_first"))


def _native_build_started_turn(builder_meta: dict[str, Any] | None) -> bool:
    """Native Builder v2 started an async build job — chat must return immediately.

    This is a dedicated short-circuit guard: when ``ham_native_builder.status``
    is ``"started"`` (or the hook sets ``chat_native_build_terminal``), the chat
    stream/emitted response MUST terminate without continuing to any Hermes
    gateway streaming path or awaiting worker execution.
    """
    meta = builder_meta or {}
    if meta.get("chat_native_build_terminal") is True:
        return True
    native_block = meta.get("ham_native_builder")
    if not isinstance(native_block, dict):
        return False
    return str(native_block.get("status") or "").strip().lower() == "started"


def _safe_builder_meta_keys_for_log(builder_meta: dict[str, Any] | None) -> list[str]:
    if not builder_meta:
        return []
    return sorted(str(k) for k in builder_meta.keys())


def _log_native_build_chat_short_circuit(
    *,
    stream_path: str,
    builder_meta: dict[str, Any] | None,
) -> None:
    _LOG.warning(
        "ham_native_builder_v2_started_chat_return",
        extra={
            "chat_stream_short_circuited": True,
            "builder_hook_result_status": "started",
            "stream_path": stream_path,
            "builder_hook_meta_keys": _safe_builder_meta_keys_for_log(builder_meta),
            "selected_builder": "native",
        },
    )


def _native_build_started_done_payload(
    *,
    sid: str,
    msgs: list[Any],
    stream_execution_mode: dict[str, Any],
    stream_active_meta: dict[str, Any] | None,
    builder_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "done",
        "session_id": sid,
        "messages": msgs,
        "actions": [],
        "operator_result": None,
        "execution_mode": stream_execution_mode,
    }
    if stream_active_meta:
        payload["active_agent"] = stream_active_meta
    if builder_meta is not None:
        payload["builder"] = builder_meta
    _chat_payload_attach_artifact_verification(payload, builder_meta)
    return payload


def _build_native_build_started_stream_response(
    *,
    sid: str,
    started_msg: str,
    msgs: list[Any],
    stream_execution_mode: dict[str, Any],
    stream_active_meta: dict[str, Any] | None,
    builder_meta: dict[str, Any] | None,
    release_stream_lock: Callable[[], None],
    stream_path: str,
) -> StreamingResponse:
    _log_native_build_chat_short_circuit(stream_path=stream_path, builder_meta=builder_meta)

    def native_build_started_only():
        try:
            yield json.dumps({"type": "session", "session_id": sid}) + "\n"
            yield json.dumps({"type": "delta", "text": started_msg}) + "\n"
            yield json.dumps(
                _native_build_started_done_payload(
                    sid=sid,
                    msgs=msgs,
                    stream_execution_mode=stream_execution_mode,
                    stream_active_meta=stream_active_meta,
                    builder_meta=builder_meta,
                )
            ) + "\n"
        finally:
            release_stream_lock()

    return StreamingResponse(
        native_build_started_only(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _builder_plan_pending_turn(builder_meta: dict[str, Any] | None) -> bool:
    return bool((builder_meta or {}).get("builder_plan_pending"))


def _chat_in_builder_workspace(
    *,
    workspace_id: str | None,
    project_id: str | None,
) -> bool:
    return bool((workspace_id or "").strip() and (project_id or "").strip())


def _artifact_verification_payload(builder_meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not builder_meta:
        return None
    av = builder_meta.get("artifact_verification")
    return av if isinstance(av, dict) else None


def _builder_verification_failure_assistant_text(
    builder_prefix: str | None,
    builder_meta: dict[str, Any] | None,
) -> str:
    if builder_prefix is not None and str(builder_prefix).strip():
        return str(builder_prefix)
    intent = str((builder_meta or {}).get("builder_intent") or "").strip().lower()
    if _builder_model_access_required(builder_meta):
        if intent == "build_or_create":
            return (
                "I cannot build this without model access. "
                "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
            )
        return (
            "I cannot apply that edit without model access. "
            "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
        )
    if _builder_llm_scaffold_failed(builder_meta):
        from src.ham.builder_chat_hooks import _llm_scaffold_failure_message
        from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE

        failed_model = (
            str((builder_meta or {}).get("llm_scaffold_failed_model") or "").strip() or None
        )
        error_code = str(
            (builder_meta or {}).get("llm_scaffold_error_code") or STEP_MODEL_UNAVAILABLE
        ).strip()
        operation = "build_or_create" if intent == "build_or_create" else "update_existing_project"
        return _llm_scaffold_failure_message(
            operation=operation,
            error_code=error_code,
            model_slug=failed_model,
        )
    ver = _artifact_verification_payload(builder_meta)
    if ver:
        r = str(ver.get("reason") or "").strip()
        if intent == "build_or_create":
            tail = f" ({r})" if r else ""
            return f"I couldn't build that yet{tail}.\n\n"
        if r:
            return (
                "I tried to apply that edit, but the generated files did not include "
                f"what you asked for yet ({r}).\n\n"
            )
    if intent == "build_or_create":
        return "I couldn't build this yet. Try again or pick a different chat model.\n\n"
    return "I tried to apply that edit, but the generated files did not verify.\n\n"


def _chat_payload_attach_artifact_verification(
    payload: dict[str, Any],
    builder_meta: dict[str, Any] | None,
) -> None:
    av = _artifact_verification_payload(builder_meta)
    if av is not None:
        payload["artifact_verification"] = av


def _builder_stream_handoff_suffix(builder_meta: dict[str, Any] | None) -> str:
    """Honest post-scaffold copy: source is saved; preview may still be provisioning or fail."""
    meta = builder_meta or {}
    lines = [_BUILDER_STREAM_SOURCE_SAVED_LINE]
    if meta.get("cloud_runtime_job_id") or meta.get("cloud_runtime_job_deduplicated"):
        lines.append(_BUILDER_STREAM_PREVIEW_STARTING_LINE)
    else:
        from src.ham.builder_chat_cloud_runtime import (
            builder_chat_cloud_runtime_auto_enqueue_eligible,
        )

        if builder_chat_cloud_runtime_auto_enqueue_eligible():
            lines.append(_BUILDER_STREAM_PREVIEW_STARTING_LINE)
        else:
            lines.append(_BUILDER_STREAM_PREVIEW_NOT_CONFIGURED_LINE)
    return " ".join(lines)


def _builder_stream_handoff_text(
    builder_prefix: str | None,
    builder_meta: dict[str, Any] | None = None,
) -> str:
    prefix = str(builder_prefix or "").strip()
    suffix = _builder_stream_handoff_suffix(builder_meta)
    if not prefix:
        return suffix
    return f"{prefix}\n\n{suffix}"


@router.get("/api/chat/capabilities")
async def get_chat_capabilities(
    model_id: str | None = Query(None, max_length=256),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """Product-facing model + HAM capability flags (no secrets, paths, or provider endpoints)."""
    from src.ham.model_capabilities import build_chat_capabilities_payload

    enforce_clerk_session_and_email_for_request(authorization, route="get_chat_capabilities")
    gateway_mode = os.environ.get("HERMES_GATEWAY_MODE", "").strip() or None
    return build_chat_capabilities_payload(model_id=model_id, gateway_mode=gateway_mode)


@router.get("/api/chat/context-meters")
def get_chat_context_meters(
    session_id: str = Query(..., min_length=1, max_length=256),
    model_id: str | None = Query(None, max_length=256),
    project_id: str | None = Query(None, max_length=256),
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Safe context pressure meters (no message contents in the response)."""
    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization, route="get_chat_context_meters"
    )
    if not context_meters_feature_enabled():
        return {"enabled": False, "this_turn": None, "workspace": None, "thread": None}

    workspace_scope = _normalized_workspace_id(workspace_id)
    rec = _get_session_for_scope(
        session_id,
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
        authenticated_actor_user_id=ham_actor.user_id if ham_actor is not None else None,
    )
    turns = rec.turns
    cat = build_catalog_payload(ham_actor)
    raw_items = cat.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    model_limit, _from_cat = resolve_model_context_tokens(model_id, items)
    this_turn = compute_this_turn_meter_block(
        turns=turns,
        model_limit_tokens=model_limit,
        model_id=model_id,
    )

    workspace: dict[str, Any] | None = None
    thread_budget = DEFAULT_THREAD_BUDGET_CHARS
    root: Path | None = None
    if (project_id or "").strip():
        p = get_project_store().get_project(project_id.strip())
        if p is not None:
            try:
                root = Path(p.root).expanduser().resolve()
            except OSError:
                root = None
            if root is not None and root.is_dir():
                ws_block, extra = workspace_snapshot_and_meter(root=root, scan_mode=ScanMode.CACHED)
                if ws_block is not None:
                    workspace = {**ws_block, "source": "cloud"}
                tb = extra.get("thread_budget_chars")
                if tb is not None:
                    try:
                        thread_budget = int(tb)
                    except (TypeError, ValueError):
                        pass
    if workspace is None:
        try:
            r = resolve_workspace_context_snapshot_root()
        except ValueError:
            r = None
        if r is not None and r.is_dir():
            ws_block, extra = workspace_snapshot_and_meter(root=r, scan_mode=ScanMode.CACHED)
            if ws_block is not None:
                workspace = {**ws_block, "source": "local"}
            tb = extra.get("thread_budget_chars")
            if tb is not None:
                try:
                    thread_budget = int(tb)
                except (TypeError, ValueError):
                    pass
    if workspace is None:
        ws_block, extra = workspace_snapshot_and_meter(root=Path.cwd(), scan_mode=ScanMode.CACHED)
        if ws_block is not None:
            workspace = {**ws_block, "source": "cloud"}
        tb = extra.get("thread_budget_chars")
        if tb is not None:
            try:
                thread_budget = int(tb)
            except (TypeError, ValueError):
                pass

    thread = compute_thread_meter_block(turns=turns, thread_budget_chars=thread_budget)

    return {
        "enabled": True,
        "this_turn": this_turn,
        "workspace": workspace,
        "thread": thread,
    }


@router.get("/api/chat/sessions")
async def list_chat_sessions(
    limit: int = 50,
    offset: int = 0,
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """List chat sessions with previews (newest first)."""
    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization, route="list_chat_sessions"
    )
    workspace_scope = _normalized_workspace_id(workspace_id)
    user_scope = _scoped_user_id(ham_actor, workspace_scope)
    unscoped_actor_user_id = (
        ham_actor.user_id if ham_actor is not None and workspace_scope is None else None
    )
    clamped_limit = max(1, min(limit, 100))
    clamped_offset = max(0, offset)
    items = _chat_store.list_sessions(
        user_id=user_scope,
        workspace_id=workspace_scope,
        unscoped_actor_user_id=unscoped_actor_user_id,
        limit=clamped_limit,
        offset=clamped_offset,
    )
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
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """Get full message history for a single chat session."""
    ham_actor = enforce_clerk_session_and_email_for_request(authorization, route="get_chat_session")
    workspace_scope = _normalized_workspace_id(workspace_id)
    rec = _get_session_for_scope(
        session_id,
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
        authenticated_actor_user_id=ham_actor.user_id if ham_actor is not None else None,
    )
    return {
        "session_id": rec.session_id,
        "messages": [{"role": t.role, "content": t.content} for t in rec.turns],
        "created_at": rec.created_at,
    }


@router.delete("/api/chat/sessions/{session_id}", status_code=204)
async def delete_chat_session(
    session_id: str,
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> Response:
    """Delete a chat session and its turns from HAM-backed persistence (SQLite/Firestore/memory)."""
    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization, route="delete_chat_session"
    )
    workspace_scope = _normalized_workspace_id(workspace_id)
    _get_session_for_scope(
        session_id,
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
        authenticated_actor_user_id=ham_actor.user_id if ham_actor is not None else None,
    )
    if not _chat_store.delete_session(session_id):
        raise _session_not_found()
    return Response(status_code=204)


@router.get("/api/chat/sessions/{session_id}/export.pdf")
async def export_chat_session_pdf(
    session_id: str,
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> Response:
    """Export persisted chat transcript as PDF (sanitized; no attachment re-fetch).

    **Authorization:** Same as :func:`get_chat_session` — ``enforce_clerk_session_and_email_for_request``
    when Clerk auth is enabled; no separate export policy.

    **Session scope:** when ``workspace_id`` is supplied, export uses the same user/workspace
    ownership check as ``GET /api/chat/sessions/{id}``. When ``workspace_id`` is omitted, legacy
    sessions (no stored owner) remain readable; tenant-scoped sessions still require the
    authenticated Clerk user to match the session owner.
    """
    from src.ham.chat_pdf_export import render_chat_transcript_pdf_bytes
    from src.ham.pdf_export_sanitizer import safe_export_filename_fragment

    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization, route="export_chat_session_pdf"
    )
    workspace_scope = _normalized_workspace_id(workspace_id)
    rec = _get_session_for_scope(
        session_id,
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
        authenticated_actor_user_id=ham_actor.user_id if ham_actor is not None else None,
    )
    turns = [(t.role, t.content) for t in rec.turns]
    pdf = render_chat_transcript_pdf_bytes(
        session_id=rec.session_id,
        created_at=rec.created_at,
        turns=turns,
    )
    fn = f"ham-chat-{safe_export_filename_fragment(session_id)}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fn}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
        },
    )


@router.post("/api/chat/sessions")
async def create_chat_session(
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """Create an empty chat session for explicit persistence flows (desktop local-control turns)."""
    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization, route="create_chat_session"
    )
    workspace_scope = _normalized_workspace_id(workspace_id)
    sid = _chat_store.create_session(
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
    )
    rec = _chat_store.get_session(sid)
    return {
        "session_id": sid,
        "created_at": rec.created_at if rec is not None else None,
    }


@router.post("/api/chat/sessions/{session_id}/turns")
async def append_chat_session_turns(
    session_id: str,
    body: ChatSessionAppendRequest,
    workspace_id: str | None = Query(None, max_length=180),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict:
    """Append finalized user/assistant turns to an existing session."""
    ham_actor = enforce_clerk_session_and_email_for_request(
        authorization,
        route="append_chat_session_turns",
    )
    attachment_user_id = ham_actor.user_id if ham_actor is not None else None
    workspace_scope = _normalized_workspace_id(workspace_id)
    _get_session_for_scope(
        session_id,
        user_id=_scoped_user_id(ham_actor, workspace_scope),
        workspace_id=workspace_scope,
        authenticated_actor_user_id=ham_actor.user_id if ham_actor is not None else None,
    )
    normalized: list[ChatTurn] = []
    for t in body.turns:
        content = str(t.content or "")
        if not content.strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "INVALID_MESSAGE",
                        "message": "Turn content must be non-empty.",
                    }
                },
            )
        if len(content) > 100_000:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "MESSAGE_TOO_LONG",
                        "message": "Message exceeds maximum length.",
                    }
                },
            )
        if t.role == "user" and content.strip().startswith("{"):
            try:
                doc = json.loads(content)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(doc, dict) and doc.get("h") == "ham_chat_user_v2":
                    try:
                        content = normalize_user_incoming_to_stored(
                            doc,
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
        normalized.append(ChatTurn(role=t.role, content=content))
    try:
        _chat_store.append_turns(session_id, normalized)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Unknown chat session."}},
        ) from exc
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
    effective_pid = resolve_effective_chat_project_id(
        workspace_id=body.workspace_id,
        project_id=body.project_id,
        ham_actor=ham_actor,
    )
    body_eff = body.model_copy(update={"project_id": effective_pid or body.project_id})
    sid, llm_messages, active_meta, last_user_plain = _messages_for_completion(
        body_eff,
        user_id=_scoped_user_id(ham_actor, _normalized_workspace_id(body.workspace_id)),
        attachment_user_id=aid,
        llm_attachment_user_id=aid,
        authenticated_actor_user_id=aid,
    )
    builder_prefix, builder_meta = run_builder_happy_path_hook(
        workspace_id=body.workspace_id,
        project_id=(body_eff.project_id or "").strip() or None,
        session_id=sid,
        last_user_plain=last_user_plain,
        ham_actor=ham_actor,
        model_id=body.model_id,
        plan_mode=body.plan_mode,
        conversation_history=store.list_messages(sid)[:-1],
    )
    builder_intent = str((builder_meta or {}).get("builder_intent") or "").strip().lower()
    if (
        builder_prefix
        and builder_meta is not None
        and "acknowledgement_template" not in builder_meta
    ):
        builder_meta["acknowledgement_template"] = builder_prefix
    # Earliest REST terminal return: native build started off the request path.
    if _native_build_started_turn(builder_meta):
        started_msg = str(builder_prefix or "").strip()
        _log_native_build_chat_short_circuit(stream_path="rest", builder_meta=builder_meta)
        store.append_turns(sid, [ChatTurn(role="assistant", content=started_msg)])
        execution_mode = _execution_mode_payload(body_eff, last_user_plain=last_user_plain)
        return ChatResponse(
            session_id=sid,
            messages=store.list_messages(sid),
            actions=[],
            active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
            operator_result=None,
            execution_mode=execution_mode,
            builder=builder_meta,
            artifact_verification=_artifact_verification_payload(builder_meta),
            hermes_http_context_budget=None,
        )
    or_override, litellm_hint_key, litellm_http_bypass, http_override = (
        _resolve_chat_openrouter_route(
            body=body,
            ham_actor=ham_actor,
            allow_conversational_default=builder_intent != "build_or_create",
        )
    )
    execution_mode = _execution_mode_payload(body_eff, last_user_plain=last_user_plain)
    execution_mode = _apply_browser_bridge_for_turn(
        execution_mode=execution_mode,
        body=body_eff,
        last_user_plain=last_user_plain,
    )
    if _builder_clarification_turn(builder_meta):
        clar_msg = str(builder_prefix or "").strip() or "What should I change?\n\n"
        store.append_turns(sid, [ChatTurn(role="assistant", content=clar_msg)])
        return ChatResponse(
            session_id=sid,
            messages=store.list_messages(sid),
            actions=[],
            active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
            operator_result=None,
            execution_mode=execution_mode,
            builder=builder_meta,
            artifact_verification=_artifact_verification_payload(builder_meta),
            hermes_http_context_budget=None,
        )
    if _builder_grounded_status_turn(builder_meta) or _builder_harness_first_turn(builder_meta):
        grounded_msg = str(builder_prefix or "").strip()
        store.append_turns(sid, [ChatTurn(role="assistant", content=grounded_msg)])
        return ChatResponse(
            session_id=sid,
            messages=store.list_messages(sid),
            actions=[],
            active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
            operator_result=None,
            execution_mode=execution_mode,
            builder=builder_meta,
            artifact_verification=_artifact_verification_payload(builder_meta),
            hermes_http_context_budget=None,
        )
    if _builder_plan_pending_turn(builder_meta):
        plan_msg = str(builder_prefix or "").strip()
        store.append_turns(sid, [ChatTurn(role="assistant", content=plan_msg)])
        return ChatResponse(
            session_id=sid,
            messages=store.list_messages(sid),
            actions=[],
            active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
            operator_result=None,
            execution_mode=execution_mode,
            builder=builder_meta,
            artifact_verification=_artifact_verification_payload(builder_meta),
            hermes_http_context_budget=None,
        )
    if (
        body.enable_operator
        and body.messages[-1].role == "user"
        and builder_intent != "build_or_create"
    ):
        from src.persistence.project_store import get_project_store

        project_store = get_project_store()
        op = (
            process_operator_turn(
                user_text=last_user_plain,
                project_store=project_store,
                default_project_id=body_eff.project_id,
                operator_payload=body.operator,
                ham_operator_authorization=ham_op_hdr,
                ham_actor=ham_actor,
            )
            if operator_enabled()
            else process_agent_router_turn(
                user_text=last_user_plain,
                project_store=project_store,
                default_project_id=body_eff.project_id,
                ham_operator_authorization=ham_op_hdr,
                ham_actor=ham_actor,
            )
        )
        if op is not None and op.handled:
            _record_operator_audit(body=body, op=op, ham_actor=ham_actor, route="post_chat")
            msg = format_operator_assistant_message(op)
            if builder_prefix:
                msg = f"{builder_prefix}{msg}"
            store.append_turns(sid, [ChatTurn(role="assistant", content=msg)])
            return ChatResponse(
                session_id=sid,
                messages=store.list_messages(sid),
                actions=[],
                active_agent=ChatActiveAgentMeta.model_validate(active_meta)
                if active_meta
                else None,
                operator_result=op.model_dump(mode="json"),
                execution_mode=execution_mode,
                builder=builder_meta,
                artifact_verification=_artifact_verification_payload(builder_meta),
            )
    if _builder_should_short_circuit_failure(builder_meta):
        vf_msg = _builder_verification_failure_assistant_text(builder_prefix, builder_meta)
        store.append_turns(sid, [ChatTurn(role="assistant", content=vf_msg)])
        return ChatResponse(
            session_id=sid,
            messages=store.list_messages(sid),
            actions=[],
            active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
            operator_result=None,
            execution_mode=execution_mode,
            builder=builder_meta,
            artifact_verification=_artifact_verification_payload(builder_meta),
            hermes_http_context_budget=None,
        )
    llm_messages = _inject_builder_turn_system(
        llm_messages,
        builder_intent,
        in_builder_workspace=_chat_in_builder_workspace(
            workspace_id=body.workspace_id,
            project_id=(body_eff.project_id or "").strip() or None,
        ),
    )
    budget_diag_rest: dict[str, Any] = {}
    try:
        assistant_raw = complete_chat_turn(
            llm_messages,
            openrouter_model_override=or_override,
            openrouter_litellm_api_key=litellm_hint_key,
            force_openrouter_litellm_route=litellm_http_bypass,
            gateway_context_budget_diag=budget_diag_rest,
            http_model_override=http_override,
        )
    except GatewayCallError as exc:
        raise HTTPException(
            status_code=_gateway_status_code(exc.code),
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    assistant_visible, actions = (
        split_assistant_ui_actions(assistant_raw) if body.enable_ui_actions else (assistant_raw, [])
    )
    if builder_prefix and builder_intent != "build_or_create":
        assistant_visible = f"{builder_prefix}{assistant_visible}"
    store.append_turns(sid, [ChatTurn(role="assistant", content=assistant_visible)])
    return ChatResponse(
        session_id=sid,
        messages=store.list_messages(sid),
        actions=actions,
        active_agent=ChatActiveAgentMeta.model_validate(active_meta) if active_meta else None,
        operator_result=None,
        execution_mode=execution_mode,
        builder=builder_meta,
        artifact_verification=_artifact_verification_payload(builder_meta),
        hermes_http_context_budget=dict(budget_diag_rest) if budget_diag_rest else None,
    )


@router.post("/api/chat/stream")
def post_chat_stream(
    body: ChatRequest,
    request: Request,
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
    effective_pid = resolve_effective_chat_project_id(
        workspace_id=body.workspace_id,
        project_id=body.project_id,
        ham_actor=ham_actor,
    )
    body_eff = body.model_copy(update={"project_id": effective_pid or body.project_id})
    sid, llm_messages, stream_active_meta, last_user_plain = _messages_for_completion(
        body_eff,
        user_id=_scoped_user_id(ham_actor, _normalized_workspace_id(body.workspace_id)),
        attachment_user_id=aid,
        llm_attachment_user_id=aid,
        authenticated_actor_user_id=aid,
    )
    defer_builder_hook = _should_defer_builder_scaffold_hook(
        last_user_plain=last_user_plain,
        workspace_id=body.workspace_id,
        project_id=(body_eff.project_id or "").strip() or None,
        ham_actor=ham_actor,
        plan_mode=body.plan_mode,
    )
    if defer_builder_hook:
        provisional_intent = classify_builder_chat_intent(last_user_plain)
        builder_prefix, builder_meta = None, {"builder_intent": provisional_intent}
        builder_intent = provisional_intent
    else:
        builder_prefix, builder_meta = run_builder_happy_path_hook(
            workspace_id=body.workspace_id,
            project_id=(body_eff.project_id or "").strip() or None,
            session_id=sid,
            last_user_plain=last_user_plain,
            ham_actor=ham_actor,
            model_id=body.model_id,
            plan_mode=body.plan_mode,
            conversation_history=store.list_messages(sid)[:-1],
        )
        builder_intent = str((builder_meta or {}).get("builder_intent") or "").strip().lower()
    if (
        builder_prefix
        and builder_meta is not None
        and "acknowledgement_template" not in builder_meta
    ):
        builder_meta["acknowledgement_template"] = builder_prefix
    # Earliest non-deferred stream terminal return (before lock / gateway streaming).
    if not defer_builder_hook and _native_build_started_turn(builder_meta):
        started_msg = str(builder_prefix or "").strip()
        store.append_turns(sid, [ChatTurn(role="assistant", content=started_msg)])
        msgs = store.list_messages(sid)
        stream_execution_mode = _execution_mode_payload(body_eff, last_user_plain=last_user_plain)
        return _build_native_build_started_stream_response(
            sid=sid,
            started_msg=started_msg,
            msgs=msgs,
            stream_execution_mode=stream_execution_mode,
            stream_active_meta=stream_active_meta,
            builder_meta=builder_meta,
            release_stream_lock=lambda: None,
            stream_path="non_deferred",
        )
    or_override, litellm_hint_key, litellm_http_bypass, http_override = (
        _resolve_chat_openrouter_route(
            body=body,
            ham_actor=ham_actor,
            allow_conversational_default=builder_intent != "build_or_create",
        )
    )
    lock_claim = _claim_stream_session(sid)
    if not lock_claim.claimed:
        raise HTTPException(
            status_code=409,
            detail=_stream_already_active_detail(
                lock_age_sec=lock_claim.lock_age_sec,
                retry_after_ms=lock_claim.retry_after_ms or _DEFAULT_STREAM_LOCK_RETRY_AFTER_MS,
            ),
        )
    stream_lock_claimed = True
    stream_lock_token = lock_claim.lock_token

    def release_stream_lock() -> None:
        nonlocal stream_lock_claimed
        if stream_lock_claimed:
            _release_stream_session(sid, stream_lock_token)
            stream_lock_claimed = False

    # Claim runs before streaming; any failure below must release or the
    # session id stays stuck in _ACTIVE_STREAM_SESSIONS (409 forever for that chat).
    try:
        stream_execution_mode = _execution_mode_payload(body_eff, last_user_plain=last_user_plain)
        stream_execution_mode = _apply_browser_bridge_for_turn(
            execution_mode=stream_execution_mode,
            body=body_eff,
            last_user_plain=last_user_plain,
        )
    except Exception:
        release_stream_lock()
        raise

    try:
        if defer_builder_hook:

            async def deferred_net_new_builder_gen():
                nonlocal builder_prefix, builder_meta, builder_intent
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": _BUILDER_STREAM_NET_NEW_ACK}) + "\n"
                    if await request.is_disconnected():
                        return
                    builder_prefix, builder_meta = await run_in_threadpool(
                        run_builder_happy_path_hook,
                        workspace_id=body.workspace_id,
                        project_id=(body_eff.project_id or "").strip() or None,
                        session_id=sid,
                        last_user_plain=last_user_plain,
                        ham_actor=ham_actor,
                        model_id=body.model_id,
                        plan_mode=body.plan_mode,
                        conversation_history=store.list_messages(sid)[:-1],
                    )
                    builder_intent = (
                        str((builder_meta or {}).get("builder_intent") or "").strip().lower()
                    )
                    if (
                        builder_prefix
                        and builder_meta is not None
                        and "acknowledgement_template" not in builder_meta
                    ):
                        builder_meta["acknowledgement_template"] = builder_prefix
                    # Earliest deferred terminal return (before any other builder branch).
                    if _native_build_started_turn(builder_meta):
                        started_msg = str(builder_prefix or "").strip()
                        _log_native_build_chat_short_circuit(
                            stream_path="deferred",
                            builder_meta=builder_meta,
                        )
                        store.append_turns(sid, [ChatTurn(role="assistant", content=started_msg)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": started_msg}) + "\n"
                        yield json.dumps(
                            _native_build_started_done_payload(
                                sid=sid,
                                msgs=msgs,
                                stream_execution_mode=stream_execution_mode,
                                stream_active_meta=stream_active_meta,
                                builder_meta=builder_meta,
                            )
                        ) + "\n"
                        return
                    if _builder_clarification_turn(builder_meta):
                        clar_msg = str(builder_prefix or "").strip() or "What should I change?\n\n"
                        store.append_turns(sid, [ChatTurn(role="assistant", content=clar_msg)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": clar_msg}) + "\n"
                        payload: dict[str, Any] = {
                            "type": "done",
                            "session_id": sid,
                            "messages": msgs,
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            payload["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                        return
                    if _builder_grounded_status_turn(builder_meta) or _builder_harness_first_turn(
                        builder_meta
                    ):
                        grounded_msg = str(builder_prefix or "").strip()
                        store.append_turns(sid, [ChatTurn(role="assistant", content=grounded_msg)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": grounded_msg}) + "\n"
                        payload = {
                            "type": "done",
                            "session_id": sid,
                            "messages": msgs,
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            payload["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                        return
                    if _builder_plan_pending_turn(builder_meta):
                        plan_msg = str(builder_prefix or "").strip()
                        store.append_turns(sid, [ChatTurn(role="assistant", content=plan_msg)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": plan_msg}) + "\n"
                        payload = {
                            "type": "done",
                            "session_id": sid,
                            "messages": msgs,
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            payload["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                        return
                    if _builder_should_short_circuit_failure(builder_meta):
                        vf_text = _builder_verification_failure_assistant_text(
                            builder_prefix,
                            builder_meta,
                        )
                        store.append_turns(sid, [ChatTurn(role="assistant", content=vf_text)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": vf_text}) + "\n"
                        payload = {
                            "type": "done",
                            "session_id": sid,
                            "messages": msgs,
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            payload["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                        return
                    if _builder_stream_should_handoff_early(builder_intent, builder_meta):
                        handoff_text = _builder_stream_handoff_text(builder_prefix, builder_meta)
                        store.append_turns(sid, [ChatTurn(role="assistant", content=handoff_text)])
                        msgs = store.list_messages(sid)
                        yield json.dumps({"type": "delta", "text": handoff_text}) + "\n"
                        payload = {
                            "type": "done",
                            "session_id": sid,
                            "messages": msgs,
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            payload["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                        return
                    fallback = _builder_verification_failure_assistant_text(
                        builder_prefix, builder_meta
                    )
                    store.append_turns(sid, [ChatTurn(role="assistant", content=fallback)])
                    msgs = store.list_messages(sid)
                    yield json.dumps({"type": "delta", "text": fallback}) + "\n"
                    payload = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                except Exception as deferred_exc:  # noqa: BLE001
                    _LOG.warning(
                        "deferred_net_new_builder_gen aborted with unhandled exception; "
                        "yielding terminal done",
                        extra={
                            "session_id": sid,
                            "exception_type": type(deferred_exc).__name__,
                        },
                    )
                    failed_payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": store.list_messages(sid),
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                        "stream_aborted": True,
                        "error": {
                            "code": "STREAM_FAILED",
                            "message": "Builder scaffold stream interrupted before completion.",
                        },
                    }
                    if stream_active_meta:
                        failed_payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        failed_payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(failed_payload, builder_meta)
                    yield json.dumps(failed_payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                deferred_net_new_builder_gen(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        if _builder_clarification_turn(builder_meta):
            clar_msg = str(builder_prefix or "").strip() or "What should I change?\n\n"
            store.append_turns(sid, [ChatTurn(role="assistant", content=clar_msg)])
            msgs = store.list_messages(sid)

            def clarify_only():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": clar_msg}) + "\n"
                    payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                clarify_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        if _builder_grounded_status_turn(builder_meta) or _builder_harness_first_turn(builder_meta):
            grounded_msg = str(builder_prefix or "").strip()
            store.append_turns(sid, [ChatTurn(role="assistant", content=grounded_msg)])
            msgs = store.list_messages(sid)

            def grounded_only():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": grounded_msg}) + "\n"
                    payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                grounded_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        if _builder_plan_pending_turn(builder_meta):
            plan_msg = str(builder_prefix or "").strip()
            store.append_turns(sid, [ChatTurn(role="assistant", content=plan_msg)])
            msgs = store.list_messages(sid)

            def plan_pending_only():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": plan_msg}) + "\n"
                    payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                plan_pending_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        if (
            body.enable_operator
            and body.messages[-1].role == "user"
            and builder_intent != "build_or_create"
        ):
            from src.persistence.project_store import get_project_store

            project_store = get_project_store()
            op = (
                process_operator_turn(
                    user_text=last_user_plain,
                    project_store=project_store,
                    default_project_id=body_eff.project_id,
                    operator_payload=body.operator,
                    ham_operator_authorization=ham_op_hdr,
                    ham_actor=ham_actor,
                )
                if operator_enabled()
                else process_agent_router_turn(
                    user_text=last_user_plain,
                    project_store=project_store,
                    default_project_id=body_eff.project_id,
                    ham_operator_authorization=ham_op_hdr,
                    ham_actor=ham_actor,
                )
            )
            if op is not None and op.handled:
                _record_operator_audit(
                    body=body, op=op, ham_actor=ham_actor, route="post_chat_stream"
                )
                msg = format_operator_assistant_message(op)
                if builder_prefix:
                    msg = f"{builder_prefix}{msg}"
                store.append_turns(sid, [ChatTurn(role="assistant", content=msg)])
                msgs = store.list_messages(sid)
                op_dict = op.model_dump(mode="json")

                def operator_only():
                    try:
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
                        if builder_meta is not None:
                            payload["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload, builder_meta)
                        yield json.dumps(payload) + "\n"
                    finally:
                        release_stream_lock()

                return StreamingResponse(
                    operator_only(),
                    media_type="application/x-ndjson; charset=utf-8",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )

        if _builder_should_short_circuit_failure(builder_meta):
            vf_text = _builder_verification_failure_assistant_text(builder_prefix, builder_meta)
            store.append_turns(sid, [ChatTurn(role="assistant", content=vf_text)])
            msgs = store.list_messages(sid)

            def builder_verification_fail_only():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": vf_text}) + "\n"
                    payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                builder_verification_fail_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        if _builder_stream_should_handoff_early(builder_intent, builder_meta):
            handoff_text = _builder_stream_handoff_text(builder_prefix, builder_meta)
            store.append_turns(sid, [ChatTurn(role="assistant", content=handoff_text)])
            msgs = store.list_messages(sid)

            def builder_handoff_only():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    yield json.dumps({"type": "delta", "text": handoff_text}) + "\n"
                    payload: dict[str, Any] = {
                        "type": "done",
                        "session_id": sid,
                        "messages": msgs,
                        "actions": [],
                        "operator_result": None,
                        "execution_mode": stream_execution_mode,
                    }
                    if stream_active_meta:
                        payload["active_agent"] = stream_active_meta
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    yield json.dumps(payload) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                builder_handoff_only(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        # Phase 2 PR 2 — Planner path for builder-mutation turns (legacy approval cards).
        # Suppressed when the user-facing Plan toggle (`plan_mode`) is active — that path uses
        # markdown plans via `run_builder_happy_path_hook` instead of `plan_proposed` SSE cards.
        _builder_action_kind = str(
            ((builder_meta or {}).get("builder_action_decision") or {}).get("kind") or ""
        ).strip()
        _planner_model_override: str | None = None
        if body_eff.model_id:
            try:
                _planner_model_override = resolve_model_id_for_chat(body_eff.model_id, ham_actor)
            except ValueError:
                _planner_model_override = None
        if (
            _builder_action_kind == "mutate"
            and resolve_openrouter_api_key_for_actor(ham_actor)
            and not _builder_skip_planner_for_net_new_build(builder_intent, builder_meta)
            and not body_eff.plan_mode
        ):
            from src.ham.builder_planner import PlannerOutputInvalidError, produce_plan

            _planner_workspace_id = _normalized_workspace_id(body_eff.workspace_id) or ""
            _planner_project_id = (body_eff.project_id or "").strip() or ""
            _planner_requested_by = ham_actor.user_id if ham_actor is not None else ""
            # Exclude the current user turn from history; produce_plan appends it as user_message.
            _planner_history = _chat_store.list_messages(sid)[:-1]
            _planner_turn_id = str(uuid4())

            def _planner_mutation_gen():
                try:
                    yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                    try:
                        plan = produce_plan(
                            user_message=last_user_plain,
                            project_id=_planner_project_id,
                            workspace_id=_planner_workspace_id,
                            requested_by=_planner_requested_by,
                            conversation_history=_planner_history,
                            ham_actor=ham_actor,
                            model_override=_planner_model_override,
                        )
                        if plan is not None:
                            yield (
                                json.dumps({"type": "plan_proposed", "plan_id": plan.plan_id})
                                + "\n"
                            )
                            _ack = (
                                f"Here's what I'll do ({len(plan.steps)} step"
                                f"{'' if len(plan.steps) == 1 else 's'}). "
                                "Approve below when you're ready, or tell me what to change."
                            )
                            store.upsert_assistant_turn(sid, _planner_turn_id, _ack)
                            _planner_done: dict[str, Any] = {
                                "type": "done",
                                "session_id": sid,
                                "messages": store.list_messages(sid),
                                "actions": [],
                                "operator_result": None,
                                "execution_mode": stream_execution_mode,
                                "plan_id": plan.plan_id,
                            }
                            if stream_active_meta:
                                _planner_done["active_agent"] = stream_active_meta
                            if builder_meta is not None:
                                _planner_done["builder"] = builder_meta
                            yield json.dumps(_planner_done) + "\n"
                    except PlannerOutputInvalidError:
                        _LOG.warning(
                            "Planner output invalid after retries; emitting error SSE",
                            extra={
                                "project_id": _planner_project_id,
                                "workspace_id": _planner_workspace_id,
                            },
                        )
                        _invalid_msg = "Planner couldn't produce a valid Plan; please rephrase.\n\n"
                        store.upsert_assistant_turn(sid, _planner_turn_id, _invalid_msg)
                        yield (
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "PLANNER_INVALID_OUTPUT",
                                    "message": "Planner couldn't produce a valid Plan; please rephrase",
                                }
                            )
                            + "\n"
                        )
                        _invalid_done: dict[str, Any] = {
                            "type": "done",
                            "session_id": sid,
                            "messages": store.list_messages(sid),
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            _invalid_done["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            _invalid_done["builder"] = {
                                **builder_meta,
                                "planner_failed": True,
                                "planner_error_code": "PLANNER_INVALID_OUTPUT",
                            }
                        yield json.dumps(_invalid_done) + "\n"
                    except Exception as exc:
                        exc_type = type(exc).__name__
                        _LOG.warning(
                            "Planner mutation failed; emitting typed SSE error",
                            extra={
                                "project_id": _planner_project_id,
                                "workspace_id": _planner_workspace_id,
                                "exception_type": exc_type,
                            },
                        )
                        _fail_msg = _builder_verification_failure_assistant_text(
                            builder_prefix,
                            builder_meta,
                        )
                        if not str(_fail_msg or "").strip():
                            _fail_msg = "Plan generation failed. Try again or pick a different chat model.\n\n"
                        store.upsert_assistant_turn(sid, _planner_turn_id, _fail_msg)
                        yield json.dumps({"type": "delta", "text": _fail_msg}) + "\n"
                        yield (
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "PLANNER_FAILED",
                                    "message": (
                                        "Plan generation failed; try again or pick a different model."
                                    ),
                                }
                            )
                            + "\n"
                        )
                        _fail_done: dict[str, Any] = {
                            "type": "done",
                            "session_id": sid,
                            "messages": store.list_messages(sid),
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                        }
                        if stream_active_meta:
                            _fail_done["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            _fail_done["builder"] = {
                                **builder_meta,
                                "planner_failed": True,
                                "planner_error_code": exc_type,
                            }
                        yield json.dumps(_fail_done) + "\n"
                finally:
                    release_stream_lock()

            return StreamingResponse(
                _planner_mutation_gen(),
                media_type="application/x-ndjson; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        assistant_turn_id = str(uuid4())
        llm_messages = _inject_builder_turn_system(
            llm_messages,
            builder_intent,
            in_builder_workspace=_chat_in_builder_workspace(
                workspace_id=body.workspace_id,
                project_id=(body_eff.project_id or "").strip() or None,
            ),
        )

        def ndjson_gen():
            # Session + optional prefix yields must live inside the same ``try`` as
            # ``finally: release_stream_lock()`` so a client disconnect on the first
            # NDJSON line still runs cleanup (otherwise the lock leaks until TTL).
            pieces: list[str] = []
            stream_completed = False
            chars_since_checkpoint = 0
            checkpoint_started = False
            last_checkpoint_at = time.monotonic()

            def checkpoint_partial(*, interrupted: bool) -> None:
                nonlocal chars_since_checkpoint, last_checkpoint_at, checkpoint_started
                if not pieces:
                    return
                partial = "".join(pieces)
                if not partial.strip():
                    return
                visible, _ = (
                    split_assistant_ui_actions(partial) if body.enable_ui_actions else (partial, [])
                )
                payload = _with_interrupted_note(visible) if interrupted else visible
                store.upsert_assistant_turn(sid, assistant_turn_id, payload)
                checkpoint_started = True
                chars_since_checkpoint = 0
                last_checkpoint_at = time.monotonic()

            try:
                yield json.dumps({"type": "session", "session_id": sid}) + "\n"
                if builder_prefix and builder_intent != "build_or_create":
                    pieces.append(builder_prefix)
                    yield json.dumps({"type": "delta", "text": builder_prefix}) + "\n"
                stream_msgs: list[dict[str, Any]] = llm_messages
                budget_diag_stream: dict[str, Any] = {}
                terminal_exc: GatewayCallError | None = None
                for retry_pass in range(2):
                    terminal_exc = None
                    try:
                        for part in stream_chat_turn(
                            stream_msgs,
                            openrouter_model_override=or_override,
                            openrouter_litellm_api_key=litellm_hint_key,
                            force_openrouter_litellm_route=litellm_http_bypass,
                            gateway_context_budget_diag=budget_diag_stream,
                            http_model_override=http_override,
                        ):
                            pieces.append(part)
                            chars_since_checkpoint += len(part)
                            now = time.monotonic()
                            if (
                                not checkpoint_started
                                or chars_since_checkpoint >= _STREAM_CHECKPOINT_MIN_CHARS
                                or (
                                    checkpoint_started
                                    and (now - last_checkpoint_at) >= _STREAM_CHECKPOINT_MIN_SEC
                                )
                            ):
                                checkpoint_partial(interrupted=True)
                            yield json.dumps({"type": "delta", "text": part}) + "\n"
                        break
                    except GatewayCallError as exc:
                        fb: list[dict[str, Any]] | None = None
                        if (
                            retry_pass == 0
                            and not pieces
                            and _eligible_upstream_vision_text_fallback(
                                exc,
                                had_stream_tokens=False,
                            )
                        ):
                            fb = _llm_upstream_text_fallback_messages(
                                sid,
                                baseline_llm_messages=llm_messages,
                            )
                        if fb is not None:
                            stream_msgs = fb
                            chars_since_checkpoint = 0
                            checkpoint_started = False
                            last_checkpoint_at = time.monotonic()
                            continue
                        terminal_exc = exc
                        break

                if terminal_exc is not None:
                    exc = terminal_exc
                    assistant_visible_err = format_gateway_error_user_message(exc)
                    try:
                        store.upsert_assistant_turn(sid, assistant_turn_id, assistant_visible_err)
                        # This branch returns before the success-path ``stream_completed`` flag; skip
                        # ``finally`` interrupted checkpoint so we do not overwrite the error text.
                        stream_completed = True
                        gateway_err: dict[str, Any] = {"code": exc.code}
                        http_st = getattr(exc, "http_status", None)
                        if isinstance(http_st, int):
                            gateway_err["upstream_http_status"] = http_st
                        payload_err: dict[str, Any] = {
                            "type": "done",
                            "session_id": sid,
                            "messages": store.list_messages(sid),
                            "actions": [],
                            "operator_result": None,
                            "execution_mode": stream_execution_mode,
                            "gateway_error": gateway_err,
                        }
                        if stream_active_meta:
                            payload_err["active_agent"] = stream_active_meta
                        if builder_meta is not None:
                            payload_err["builder"] = builder_meta
                        _chat_payload_attach_artifact_verification(payload_err, builder_meta)
                        if budget_diag_stream:
                            payload_err["hermes_http_context_budget"] = dict(budget_diag_stream)
                        yield json.dumps(payload_err) + "\n"
                    except KeyError:
                        yield (
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": exc.code,
                                    "message": assistant_visible_err,
                                },
                            )
                            + "\n"
                        )
                    return

                stream_completed = True
                assistant_raw = "".join(pieces)
                assistant_visible, actions = (
                    split_assistant_ui_actions(assistant_raw)
                    if body.enable_ui_actions
                    else (assistant_raw, [])
                )
                try:
                    store.upsert_assistant_turn(sid, assistant_turn_id, assistant_visible)
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
                    if builder_meta is not None:
                        payload["builder"] = builder_meta
                    _chat_payload_attach_artifact_verification(payload, builder_meta)
                    if budget_diag_stream:
                        payload["hermes_http_context_budget"] = dict(budget_diag_stream)
                    yield json.dumps(payload) + "\n"
                except KeyError:
                    yield (
                        json.dumps(
                            {
                                "type": "error",
                                "code": "SESSION_NOT_FOUND",
                                "message": "Session disappeared during stream.",
                            },
                        )
                        + "\n"
                    )
            except Exception as ndjson_exc:  # noqa: BLE001
                _LOG.warning(
                    "ndjson_gen aborted with unhandled exception; yielding terminal done",
                    extra={"session_id": sid, "exception_type": type(ndjson_exc).__name__},
                )
                stream_completed = True
                aborted_payload: dict[str, Any] = {
                    "type": "done",
                    "session_id": sid,
                    "messages": store.list_messages(sid),
                    "actions": [],
                    "operator_result": None,
                    "execution_mode": stream_execution_mode,
                    "stream_aborted": True,
                    "error": {
                        "code": "STREAM_FAILED",
                        "message": "Stream interrupted before completion.",
                    },
                }
                if stream_active_meta:
                    aborted_payload["active_agent"] = stream_active_meta
                if builder_meta is not None:
                    aborted_payload["builder"] = builder_meta
                _chat_payload_attach_artifact_verification(aborted_payload, builder_meta)
                yield json.dumps(aborted_payload) + "\n"
            finally:
                # If stream was interrupted (generator closed), save partial content.
                if not stream_completed:
                    try:
                        if pieces:
                            checkpoint_partial(interrupted=True)
                        else:
                            store.upsert_assistant_turn(
                                sid,
                                assistant_turn_id,
                                _STREAM_PRETOKEN_ABORT_ASSISTANT,
                            )
                    except Exception:
                        pass  # Best-effort: don't crash on cleanup
                release_stream_lock()

        return StreamingResponse(
            ndjson_gen(),
            media_type="application/x-ndjson; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        release_stream_lock()
        raise


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
    ham_actor, _op = _resolve_chat_clerk_context(
        authorization,
        x_ham_operator_authorization,
        route="post_chat_transcribe",
    )
    transcription_key = resolve_transcription_openai_api_key_for_actor(ham_actor)
    if not transcription_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "CONNECT_STT_PROVIDER_REQUIRED",
                    "message": (
                        "STT_NOT_CONFIGURED: connect OpenAI (transcription) in Workspace → Connected Tools, "
                        "or ask your operator to set HAM_TRANSCRIPTION_PROVIDER and HAM_TRANSCRIPTION_API_KEY on the API host."
                    ),
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
            api_key=transcription_key,
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
                "provider": "openai",
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
                "provider": "openai",
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


_CHAT_ATTACHMENT_IMAGE_MAX_BYTES = 10 * 1024 * 1024


def _coerce_request_mime(content_type: str | None, filename: str) -> str | None:
    raw = (content_type or "").split(";")[0].strip().lower()
    if raw == "image/jpg":
        raw = "image/jpeg"
    if raw == "application/csv":
        return "text/csv"
    if raw in CHAT_UPLOAD_ALLOWED_MIME:
        return raw
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".doc"):
        return "application/msword"
    if name.endswith(".xls"):
        return "application/vnd.ms-excel"
    if name.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if name.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if name.endswith(".csv"):
        return "text/csv"
    if name.endswith(".md") or name.endswith(".markdown"):
        return "text/markdown"
    if name.endswith(".txt"):
        return "text/plain"
    if name.endswith(".mp4"):
        return "video/mp4"
    if name.endswith(".mov"):
        return "video/quicktime"
    if name.endswith(".webm"):
        return "video/webm"
    return None


def _sniff_video_container_mime(head: bytes, filename: str) -> str | None:
    """Recognize ISO BMFF (MP4/MOV) and EBML/WebM magic without parsing full streams."""
    fn = (filename or "").lower()
    if len(head) >= 12 and head[4:8] == b"ftyp":
        if fn.endswith(".mov"):
            return "video/quicktime"
        return "video/mp4"
    if len(head) >= 4 and head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"
    return None


def _sniff_image_mime(head: bytes) -> str | None:
    if len(head) >= 6 and head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _sniff_pdf_mime(head: bytes) -> str | None:
    if len(head) >= 5 and head[:5] == b"%PDF-":
        return "application/pdf"
    return None


def _sniff_oledoc_mime(head: bytes, filename: str) -> str | None:
    if len(head) >= 8 and head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        if (filename or "").lower().endswith(".xls"):
            return "application/vnd.ms-excel"
        return "application/msword"
    return None


def _sniff_docx_mime(head: bytes, filename: str) -> str | None:
    if not filename.lower().endswith(".docx"):
        return None
    if len(head) >= 4 and head[:2] == b"PK":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None


def _sniff_xlsx_mime(head: bytes, filename: str) -> str | None:
    if not filename.lower().endswith(".xlsx"):
        return None
    if len(head) >= 4 and head[:2] == b"PK":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
    head = data[:64]
    mime: str | None = _sniff_image_mime(head)
    if mime is None:
        mime = _sniff_pdf_mime(head)
    if mime is None:
        mime = _sniff_xlsx_mime(head, name)
    if mime is None:
        mime = _sniff_oledoc_mime(head, name)
    if mime is None:
        mime = _sniff_docx_mime(head, name)
    if mime is None:
        mime = _sniff_video_container_mime(head, name)
    if mime is None:
        mime = _coerce_request_mime(file.content_type, name)
        if mime in ("text/plain", "text/markdown", "text/csv"):
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
    elif mime in ("text/plain", "text/markdown", "text/csv"):
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
                    "message": (
                        "Unsupported file type. Use PNG, JPEG, GIF, WebP, PDF, plain text, "
                        "markdown, DOC, DOCX, XLSX, CSV, legacy XLS (stored only), MP4, MOV, or WebM videos "
                        "(stored without video analysis in this phase)."
                    ),
                },
            },
        )
    if mime.startswith("image/") and len(data) > _CHAT_ATTACHMENT_IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "ATTACHMENT_TOO_LARGE",
                    "message": f"Image exceeds maximum size ({_CHAT_ATTACHMENT_IMAGE_MAX_BYTES} bytes).",
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
