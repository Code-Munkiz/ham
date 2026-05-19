"""Phase 2 — Subsystem 1: Planner.

Turns a user message + project context into a Plan via the user's BYO
OpenRouter key.  Returns None when no key is configured (caller falls
back to legacy regex flow per ADR-0009).  Raises PlannerOutputInvalidError
after the retry budget is exhausted (one retry with a stricter prompt).

On success the Plan and a PlanApprovalRecord(state="proposed") are written
to BuilderPlanStore.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 1
ADR: docs/adr/0009-planner-byo-openrouter-with-regex-fallback.md
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.ham.builder_error_codes import INTERNAL_ERROR, make_error
from src.ham.builder_plan import Plan, PlanApprovalRecord, Step
from src.llm_client import (
    complete_chat_messages_openrouter,
    normalized_openrouter_api_key,
    resolve_openrouter_model_name_for_chat,
)
from src.persistence.builder_plan_store import (
    BuilderPlanStoreProtocol,
    get_builder_plan_store,
)

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local helpers (pattern from builder_plan.py / builder_runtime_job_store.py)
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class PlannerOutputInvalidError(Exception):
    """Raised when the LLM's JSON output fails to parse as a Plan twice."""


# ---------------------------------------------------------------------------
# Planner system prompt
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM_PROMPT = """\
You are the HAM builder planner. Given the user's message and project context,
produce a Plan describing the steps required to implement the request.

Output ONLY a JSON object matching this exact schema (no markdown, no prose):

{
  "steps": [
    {
      "title": "<short imperative goal, ≤ 60 chars>",
      "description": "<rationale, ≤ 200 chars>",
      "requires_approval": false
    }
  ],
  "destructive": false,
  "planner_confidence": "high"
}

Rules:
- steps: 1–10 ordered Steps.  Each step is a coarse imperative goal.
- requires_approval: true only for Steps that DELETE or OVERWRITE user data.
- destructive: true if ANY step has requires_approval=true.
- planner_confidence: "high" | "medium" | "low".
  Use "low" when the request is ambiguous.
- Do NOT include plan_id, workspace_id, project_id, or created_at.
  The caller adds those.
- Output only the JSON object, nothing else.
"""

_PLANNER_SYSTEM_PROMPT_STRICT = (
    _PLANNER_SYSTEM_PROMPT
    + "\n\nYour previous response was not valid JSON for the Plan schema. "
    "Output ONLY the JSON object, starting with { and ending with }. "
    "No markdown code blocks, no commentary."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Extract the first {...} block from an LLM response.

    LLMs sometimes wrap the JSON in triple-backtick code fences.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    # Find outermost {...}
    start = text.find("{")
    if start == -1:
        return text.strip()
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:].strip()


def _get_planner_model() -> str:
    override = (os.environ.get("HAM_PLANNER_MODEL") or "").strip()
    if not override:
        return resolve_openrouter_model_name_for_chat()
    if override.startswith("openrouter/"):
        return override
    return f"openrouter/{override}"


def _parse_plan_from_raw(
    raw_text: str,
    *,
    user_message: str,
    project_id: str,
    workspace_id: str,
    source_snapshot_id: str | None,
    planner_model: str,
) -> Plan:
    """Parse JSON output from the LLM and build a Plan.

    Raises ValidationError if the JSON does not match the Plan schema.
    """
    json_str = _extract_json(raw_text)
    payload: dict[str, Any] = json.loads(json_str)

    # Inject provenance fields (caller provides; LLM must not set them)
    payload.setdefault("workspace_id", workspace_id)
    payload.setdefault("project_id", project_id)
    payload.setdefault("user_message", user_message)
    payload.setdefault("source_snapshot_id", source_snapshot_id)
    payload.setdefault("planner_model", planner_model)
    payload.setdefault("created_at", _utc_now_iso())

    # Normalise steps list if present
    steps_raw = payload.get("steps", [])
    if not isinstance(steps_raw, list):
        raise ValidationError.from_exception_data(
            title="Plan",
            line_errors=[],
        )
    payload["steps"] = steps_raw

    return Plan.model_validate(payload)


def _build_messages(
    user_message: str,
    conversation_history: list[Any],
    *,
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Assemble the message list for the planner LLM call.

    Keeps last 4 turns of conversation history (per the design spec).
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # Include last 4 turns of conversation history
    history_tail = conversation_history[-8:] if conversation_history else []
    for turn in history_tail:
        # Support both dict and Pydantic model (ChatTurn from Phase 0)
        if isinstance(turn, dict):
            role = turn.get("role", "user")
            content = turn.get("content", "")
        else:
            role = getattr(turn, "role", "user")
            content = getattr(turn, "content", "")
        messages.append({"role": str(role), "content": str(content)})

    # Current user request
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def produce_plan(
    *,
    user_message: str,
    project_id: str,
    workspace_id: str,
    requested_by: str,
    conversation_history: list[Any],
    source_snapshot_id: str | None = None,
    store: BuilderPlanStoreProtocol | None = None,
) -> Plan | None:
    """Turn a user message into a Plan.

    Returns:
        Plan — on success (written to store).
        None — when no OpenRouter key is configured (caller uses legacy flow).

    Raises:
        PlannerOutputInvalidError — when the LLM output fails Pydantic
            validation twice.
    """
    api_key = normalized_openrouter_api_key()
    if not api_key:
        _LOG.debug("No OpenRouter key configured — skipping Planner (ADR-0009 fallback)")
        return None

    plan_store = store or get_builder_plan_store()
    planner_model = _get_planner_model()

    # --- Attempt 1 ---
    messages = _build_messages(user_message, conversation_history, system_prompt=_PLANNER_SYSTEM_PROMPT)
    raw: str = ""
    try:
        raw = complete_chat_messages_openrouter(
            messages,
            model_override=planner_model,
            api_key_override=api_key,
        )
        plan = _parse_plan_from_raw(
            raw,
            user_message=user_message,
            project_id=project_id,
            workspace_id=workspace_id,
            source_snapshot_id=source_snapshot_id,
            planner_model=planner_model,
        )
    except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as first_exc:
        _LOG.warning(
            "Planner first attempt failed (%s: %s) — retrying with stricter prompt",
            type(first_exc).__name__,
            first_exc,
        )
        # --- Attempt 2 (stricter prompt) ---
        messages2 = _build_messages(
            user_message, conversation_history, system_prompt=_PLANNER_SYSTEM_PROMPT_STRICT
        )
        try:
            raw2 = complete_chat_messages_openrouter(
                messages2,
                model_override=planner_model,
                api_key_override=api_key,
            )
            plan = _parse_plan_from_raw(
                raw2,
                user_message=user_message,
                project_id=project_id,
                workspace_id=workspace_id,
                source_snapshot_id=source_snapshot_id,
                planner_model=planner_model,
            )
        except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as second_exc:
            raise PlannerOutputInvalidError(
                f"Planner could not produce a valid Plan after 2 attempts. "
                f"Second error: {type(second_exc).__name__}: {second_exc}"
            ) from second_exc

    # Persist on success
    plan_store.upsert_plan(plan)
    plan_store.upsert_approval_record(
        PlanApprovalRecord(plan_id=plan.plan_id, state="proposed")
    )
    _LOG.info(
        "Planner produced plan %s with %d steps (requested_by=%s)",
        plan.plan_id,
        len(plan.steps),
        requested_by,
    )
    return plan
