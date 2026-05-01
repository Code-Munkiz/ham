"""Dry-run Telegram reactive reply preview for Social TG-R2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.redaction import redact
from src.ham.social_persona import load_social_persona, persona_digest
from src.ham.social_telegram_inbound import TelegramInboundItem, discover_telegram_inbound_once

MAX_REACTIVE_REPLY_CANDIDATES = 3
MAX_REACTIVE_REPLY_TEXT_CHARS = 500
TELEGRAM_REACTIVE_REPLY_EXECUTION_KIND = "social_telegram_reactive_reply"
TELEGRAM_REACTIVE_REPLY_ACTION_TYPE = "reactive_reply"

TelegramReactiveStatus = Literal["completed", "blocked", "failed"]
TelegramReactiveClassification = Literal[
    "genuine_question",
    "support_request",
    "positive_signal",
    "criticism",
    "off_topic",
    "unsafe",
    "requires_human_operator",
]


class TelegramReactivePolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool = False
    classification: TelegramReactiveClassification = "requires_human_operator"
    reasons: list[str] = Field(default_factory=list)


class TelegramReactiveGovernorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool = False
    reasons: list[str] = Field(default_factory=list)
    max_reply_candidates: int = MAX_REACTIVE_REPLY_CANDIDATES
    reply_candidates_used: int = 0


class TelegramReactiveItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound_id: str
    inbound_text: str
    author_ref: str = ""
    chat_ref: str = ""
    session_ref: str = ""
    classification: TelegramReactiveClassification
    policy: TelegramReactivePolicyDecision
    governor: TelegramReactiveGovernorDecision
    reply_candidate_text: str = ""
    proposal_digest: str | None = None
    already_answered: bool = False
    repliable: bool = False
    reasons: list[str] = Field(default_factory=list)


class TelegramReactivePreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    preview_kind: Literal["telegram_reactive_replies"] = "telegram_reactive_replies"
    status: TelegramReactiveStatus = "blocked"
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    persona_id: str
    persona_version: int
    persona_digest: str
    inbound_count: int = 0
    processed_count: int = 0
    reply_candidate_count: int = 0
    items: list[TelegramReactiveItemResult] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)


def preview_telegram_reactive_replies_once(
    *,
    transcript_paths: list[Path] | None = None,
    max_reply_candidates: int = MAX_REACTIVE_REPLY_CANDIDATES,
) -> TelegramReactivePreviewResult:
    persona = load_social_persona("ham-canonical", 1)
    persona_ref = {
        "persona_id": persona.persona_id,
        "persona_version": persona.version,
        "persona_digest": persona_digest(persona),
    }
    inbound = discover_telegram_inbound_once(transcript_paths=transcript_paths)
    if inbound.status != "completed":
        return TelegramReactivePreviewResult(
            status="blocked",
            reasons=list(inbound.reasons),
            warnings=list(inbound.warnings),
            recommended_next_steps=list(inbound.recommended_next_steps),
            **persona_ref,
        )

    candidate_limit = max(0, min(max_reply_candidates, MAX_REACTIVE_REPLY_CANDIDATES))
    items: list[TelegramReactiveItemResult] = []
    reply_count = 0
    for inbound_item in inbound.items:
        policy = _policy_decision(inbound_item)
        reply_text = _reply_text(inbound_item, policy.classification) if policy.allowed else ""
        governor = _governor_decision(
            policy_allowed=policy.allowed,
            reply_candidates_used=reply_count,
            max_reply_candidates=candidate_limit,
        )
        proposal_digest: str | None = None
        if policy.allowed and governor.allowed and reply_text:
            reply_count += 1
            proposal_digest = _proposal_digest(
                persona_ref=persona_ref,
                inbound_item=inbound_item,
                classification=policy.classification,
                reply_text=reply_text,
            )
        else:
            reply_text = ""
        reasons = _dedupe([*policy.reasons, *governor.reasons, *inbound_item.reasons])
        items.append(
            TelegramReactiveItemResult(
                inbound_id=inbound_item.inbound_id,
                inbound_text=inbound_item.text,
                author_ref=inbound_item.author_ref,
                chat_ref=inbound_item.chat_ref,
                session_ref=inbound_item.session_ref,
                classification=policy.classification,
                policy=policy,
                governor=governor,
                reply_candidate_text=reply_text,
                proposal_digest=proposal_digest,
                already_answered=inbound_item.already_answered,
                repliable=inbound_item.repliable,
                reasons=reasons,
            )
        )

    return TelegramReactivePreviewResult(
        status="completed",
        inbound_count=inbound.inbound_count,
        processed_count=len(items),
        reply_candidate_count=reply_count,
        items=items,
        reasons=[],
        warnings=list(inbound.warnings),
        recommended_next_steps=_recommended_steps(reply_count=reply_count, processed_count=len(items)),
        **persona_ref,
    )


def _policy_decision(item: TelegramInboundItem) -> TelegramReactivePolicyDecision:
    text = item.text.lower()
    if item.already_answered:
        return _policy(False, "requires_human_operator", "telegram_inbound_already_answered")
    if not item.repliable:
        return _policy(False, "requires_human_operator", "telegram_inbound_not_repliable")
    if _looks_like_unsupported_media(text):
        return _policy(False, "requires_human_operator", "telegram_inbound_unsupported_media")
    if _looks_like_unsafe(text):
        return _policy(False, "unsafe", "telegram_reactive_unsafe_content")
    if _looks_like_secret_handling(text):
        return _policy(False, "requires_human_operator", "telegram_reactive_secret_handling_request")
    if _looks_like_financial_or_price_promise(text):
        return _policy(False, "requires_human_operator", "telegram_reactive_financial_or_price_promise")
    if _looks_operationally_sensitive(text):
        return _policy(False, "requires_human_operator", "telegram_reactive_requires_human_operator")
    classification = _classify_text(text)
    if classification in {"genuine_question", "support_request", "positive_signal"}:
        return _policy(True, classification)
    return _policy(False, classification, f"telegram_reactive_{classification}")


def _policy(
    allowed: bool,
    classification: TelegramReactiveClassification,
    *reasons: str,
) -> TelegramReactivePolicyDecision:
    return TelegramReactivePolicyDecision(allowed=allowed, classification=classification, reasons=_dedupe(list(reasons)))


def _governor_decision(
    *,
    policy_allowed: bool,
    reply_candidates_used: int,
    max_reply_candidates: int,
) -> TelegramReactiveGovernorDecision:
    reasons: list[str] = []
    if not policy_allowed:
        reasons.append("telegram_reactive_policy_blocked")
    if reply_candidates_used >= max_reply_candidates:
        reasons.append("telegram_reactive_candidate_cap_reached")
    return TelegramReactiveGovernorDecision(
        allowed=not reasons,
        reasons=_dedupe(reasons),
        max_reply_candidates=max_reply_candidates,
        reply_candidates_used=reply_candidates_used,
    )


def _classify_text(text: str) -> TelegramReactiveClassification:
    if any(marker in text for marker in ("?", "how do", "what is", "can ham", "does ham", "where do")):
        return "genuine_question"
    if any(marker in text for marker in ("help", "support", "issue", "bug", "not working", "stuck", "error")):
        return "support_request"
    if any(marker in text for marker in ("thanks", "thank you", "great", "nice", "love", "awesome", "cool")):
        return "positive_signal"
    if any(marker in text for marker in ("bad", "broken", "hate", "awful", "terrible")):
        return "criticism"
    return "off_topic"


def _reply_text(item: TelegramInboundItem, classification: TelegramReactiveClassification) -> str:
    if classification == "genuine_question":
        text = (
            "Thanks for the question. Ham can help with that, and a human operator can follow up "
            "if the next step needs account-specific context."
        )
    elif classification == "support_request":
        text = (
            "Thanks for reaching out. Ham can help triage this, and an operator will review anything "
            "that needs account-specific action."
        )
    elif classification == "positive_signal":
        text = "Thanks for the note. Glad this was useful."
    else:
        text = ""
    return str(redact(text))[:MAX_REACTIVE_REPLY_TEXT_CHARS]


def _proposal_digest(
    *,
    persona_ref: dict[str, object],
    inbound_item: TelegramInboundItem,
    classification: str,
    reply_text: str,
) -> str:
    payload = {
        "provider_id": "telegram",
        "preview_kind": "telegram_reactive_replies",
        "persona": persona_ref,
        "inbound_id": inbound_item.inbound_id,
        "author_ref": inbound_item.author_ref,
        "chat_ref": inbound_item.chat_ref,
        "classification": classification,
        "reply_candidate_text": reply_text,
        "safety_gates": {
            "execution_allowed": False,
            "mutation_attempted": False,
            "live_apply_available": False,
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _looks_like_unsupported_media(text: str) -> bool:
    return any(marker in text for marker in ("media:", "attachment:", "[attachment", "photo:", "image:", "video:"))


def _looks_like_unsafe(text: str) -> bool:
    return any(marker in text for marker in ("kill yourself", "self harm", "suicide", "bomb", "dox", "doxx"))


def _looks_like_secret_handling(text: str) -> bool:
    return any(marker in text for marker in ("api key", "token", "password", "secret", "private key", "seed phrase"))


def _looks_like_financial_or_price_promise(text: str) -> bool:
    return any(marker in text for marker in ("guarantee profit", "investment advice", "price promise", "refund promise", "will moon"))


def _looks_operationally_sensitive(text: str) -> bool:
    return any(marker in text for marker in ("delete my account", "billing", "invoice", "legal", "contract", "medical"))


def _recommended_steps(*, reply_count: int, processed_count: int) -> list[str]:
    if reply_count:
        return ["Dry-run reply candidates generated. No Telegram message was sent."]
    if processed_count:
        return ["Inbound messages were reviewed, but policy/governor rules produced no reply candidates."]
    return ["No inbound Telegram messages were available for reactive dry-run preview."]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
