from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.llm_client import (
    configure_litellm_env,
    get_openrouter_base_url,
    normalized_openrouter_api_key,
    openrouter_api_key_is_plausible,
    resolve_openrouter_model_name_for_chat,
)

router = APIRouter()

ActionType = Literal["observe", "scroll", "wait", "click_candidate", "done", "blocked"]
PlannerStatus = Literal["ok", "fallback", "error"]
PlannerMode = Literal["llm", "fallback"]

ALLOWED_ACTION_TYPES = {"observe", "scroll", "wait", "click_candidate", "done", "blocked"}
MAX_CANDIDATES = 20
MAX_TERMS = 12
MAX_TEXT = 240


class GohamPlannerCandidate(BaseModel):
    id: str = Field(max_length=80)
    text: str = Field(default="", max_length=120)
    tag: str = Field(default="", max_length=32)
    role: str | None = Field(default=None, max_length=48)
    risk: str = Field(default="low", max_length=24)
    score: float = 0
    safety: str = Field(default="safe", max_length=120)


class GohamPlannerRequest(BaseModel):
    goal: str = Field(max_length=MAX_TEXT)
    currentUrl: str = Field(max_length=MAX_TEXT)
    title: str = Field(default="", max_length=MAX_TEXT)
    requiredEvidenceTerms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    observedEvidenceTerms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    missingEvidenceTerms: list[str] = Field(default_factory=list, max_length=MAX_TERMS)
    candidates: list[GohamPlannerCandidate] = Field(default_factory=list, max_length=MAX_CANDIDATES)
    stepNumber: int = Field(ge=0, le=50)
    remainingBudget: int = Field(ge=0, le=50)


class GohamPlannerAction(BaseModel):
    type: ActionType
    candidate_id: str | None = Field(default=None, max_length=80)
    reason: str = Field(max_length=180)
    confidence: float = Field(ge=0.0, le=1.0)


class GohamPlannerResponse(BaseModel):
    kind: Literal["goham_planner_next_action"] = "goham_planner_next_action"
    schema_version: Literal[1] = 1
    status: PlannerStatus
    planner_mode: PlannerMode
    action: GohamPlannerAction
    warnings: list[str] = Field(default_factory=list)


def goham_llm_planner_enabled() -> bool:
    return (os.getenv("GOHAM_LLM_PLANNER_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _fallback_response(reason: str, *, status: PlannerStatus = "fallback") -> GohamPlannerResponse:
    return GohamPlannerResponse(
        status=status,
        planner_mode="fallback",
        action=GohamPlannerAction(
            type="done",
            reason="Use rules-first fallback planner.",
            confidence=0.0,
        ),
        warnings=[reason],
    )


def _compact_list(items: list[str], limit: int = MAX_TERMS) -> list[str]:
    out: list[str] = []
    for item in items[:limit]:
        s = re.sub(r"\s+", " ", str(item)).strip()
        if s:
            out.append(s[:80])
    return out


def _planner_prompt(body: GohamPlannerRequest) -> str:
    candidates = [
        {
            "id": c.id,
            "text": c.text[:100],
            "tag": c.tag,
            "role": c.role,
            "risk": c.risk,
            "score": c.score,
            "safety": c.safety,
        }
        for c in body.candidates[:MAX_CANDIDATES]
    ]
    payload = {
        "goal": body.goal,
        "current_url": body.currentUrl,
        "title": body.title,
        "required_evidence_terms": _compact_list(body.requiredEvidenceTerms),
        "observed_evidence_terms": _compact_list(body.observedEvidenceTerms),
        "missing_evidence_terms": _compact_list(body.missingEvidenceTerms),
        "step_number": body.stepNumber,
        "remaining_budget": body.remainingBudget,
        "candidates": candidates,
    }
    return (
        "You are GoHAM's safe research action planner. Return JSON only.\n"
        "You do not control a browser. You only propose the next action.\n"
        "Allowed action types: observe, scroll, wait, click_candidate, done, blocked.\n"
        "You cannot type, fill forms, submit, login, purchase, download, upload, install extensions, "
        "use selectors, use coordinates, run JavaScript, call tools, or invent URLs.\n"
        "Candidates are the only clickable targets. Choose click_candidate only when the id is present, "
        "risk is low, and safety is safe.\n"
        "If evidence is missing and a relevant safe candidate exists, prefer click_candidate. If no candidate is relevant, "
        "choose scroll or wait. If no safe useful action remains, choose done or blocked.\n"
        'Return exactly: {"type":"...","candidate_id":"... optional","reason":"short reason","confidence":0.0}\n'
        f"Planner input:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _call_planner_model(prompt: str) -> str:
    import litellm

    configure_litellm_env()
    api_key = normalized_openrouter_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if not openrouter_api_key_is_plausible(api_key):
        raise RuntimeError("OPENROUTER_API_KEY is not plausible")

    model = (os.getenv("GOHAM_LLM_PLANNER_MODEL") or "").strip()
    if not model:
        model = resolve_openrouter_model_name_for_chat()
    elif not model.startswith("openrouter/"):
        model = f"openrouter/{model}"

    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_base=get_openrouter_base_url(),
        api_key=api_key,
        max_tokens=180,
        timeout=12,
        temperature=0,
    )
    content = getattr(resp.choices[0].message, "content", "")
    return content if isinstance(content, str) else str(content or "")


def _validate_action(obj: dict[str, Any], body: GohamPlannerRequest) -> tuple[GohamPlannerAction | None, str | None]:
    typ = obj.get("type")
    if typ not in ALLOWED_ACTION_TYPES:
        return None, "unknown_action"
    reason = re.sub(r"\s+", " ", str(obj.get("reason") or "")).strip()
    if not reason:
        return None, "missing_reason"
    try:
        confidence = float(obj.get("confidence"))
    except (TypeError, ValueError):
        return None, "invalid_confidence"
    if not 0 <= confidence <= 1:
        return None, "invalid_confidence"

    candidate_id = obj.get("candidate_id")
    candidate_id = str(candidate_id).strip() if candidate_id is not None else None
    if typ == "click_candidate":
        if not candidate_id:
            return None, "missing_candidate_id"
        c = next((x for x in body.candidates if x.id == candidate_id), None)
        if c is None:
            return None, "unknown_candidate"
        if c.risk != "low":
            return None, "candidate_risk_not_low"
        if c.safety.strip().lower() != "safe":
            return None, "candidate_not_safe"

    if re.search(r"\b(type|keyboard|form|submit|login|download|upload|purchase|checkout|selector|coordinate|javascript)\b", reason, re.I):
        return None, "unsafe_reason"

    return GohamPlannerAction(type=typ, candidate_id=candidate_id, reason=reason[:180], confidence=confidence), None


@router.post("/api/goham/planner/next-action", response_model=GohamPlannerResponse)
async def goham_planner_next_action(body: GohamPlannerRequest) -> GohamPlannerResponse:
    if not goham_llm_planner_enabled():
        return _fallback_response("GOHAM_LLM_PLANNER_ENABLED is not true")

    try:
        raw = _call_planner_model(_planner_prompt(body))
    except Exception as exc:  # noqa: BLE001 - safe fallback boundary
        return _fallback_response(f"planner_model_unavailable: {type(exc).__name__}")

    obj = _extract_json_object(raw)
    if obj is None:
        return _fallback_response("malformed_model_output", status="error")

    action, reason = _validate_action(obj, body)
    if action is None:
        return _fallback_response(reason or "invalid_model_action", status="error")

    return GohamPlannerResponse(status="ok", planner_mode="llm", action=action, warnings=[])
