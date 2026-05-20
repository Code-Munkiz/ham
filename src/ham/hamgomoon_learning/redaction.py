"""HAMgomoon-specific redaction (defense in depth on top of ham_x.redaction)."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)

_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I)
_AUTH_LINE_RE = re.compile(r"(?im)^\s*Authorization\s*:\s*.+$")
_XAI_RE = re.compile(r"\bxai-[A-Za-z0-9_-]{6,}\b")
_XOXB_RE = re.compile(r"\bxoxb-[A-Za-z0-9_-]{6,}\b")
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"\bbot[0-9]+:[A-Za-z0-9_-]{6,}\b")
_HAM_TOKEN_ENV_RE = re.compile(r"\bHAM_[A-Z0-9_]*TOKEN\s*=\s*\S+")
_URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
_QUERY_SECRET_KEYS = {"token", "auth", "key", "apikey", "api_key", "secret", "access_token"}
_BARE_QUERY_AUTH_RE = re.compile(
    r"\?(token|auth|key|apikey|api_key|secret|access_token)=([^\s&]+)",
    re.IGNORECASE,
)

_REDACTED = "[REDACTED]"


def _scrub_url_query(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if not parsed.scheme or not parsed.netloc or not parsed.query:
        return url
    params = []
    changed = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lk = key.lower()
        if lk in _QUERY_SECRET_KEYS or any(part in lk for part in ("token", "secret", "key", "auth")):
            params.append((key, _REDACTED))
            changed = True
        else:
            params.append((key, value))
    if not changed:
        return url
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(params),
            parsed.fragment,
        )
    )


def redact_text(text: str) -> str:
    """Scrub bearer tokens, xai-/xoxb- keys, Telegram bot tokens, env tokens, URL query auth."""
    if not text:
        return text
    out = _URL_RE.sub(lambda m: _scrub_url_query(m.group(0)), text)
    out = _AUTH_LINE_RE.sub(f"Authorization: {_REDACTED}", out)
    out = _BEARER_RE.sub(f"Bearer {_REDACTED}", out)
    out = _XAI_RE.sub(_REDACTED, out)
    out = _XOXB_RE.sub(_REDACTED, out)
    out = _TELEGRAM_BOT_TOKEN_RE.sub(_REDACTED, out)
    out = _HAM_TOKEN_ENV_RE.sub(lambda m: m.group(0).split("=", 1)[0] + "=" + _REDACTED, out)
    out = _BARE_QUERY_AUTH_RE.sub(lambda m: f"?{m.group(1)}={_REDACTED}", out)
    return out


def redact_external_id(value: str | None) -> str | None:
    """Collapse external IDs to last 6 chars prefixed by an ellipsis.

    Returns ``None`` for falsy inputs.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= 6:
        return f"…{value}"
    return f"…{value[-6:]}"


def _redact_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_text(value)


def _redact_draft(draft: SocialDraftRecord) -> SocialDraftRecord:
    return draft.model_copy(
        update={
            "prompt": redact_text(draft.prompt),
            "draft_text": redact_text(draft.draft_text),
        }
    )


def _redact_review(review: ReviewOutcome | None) -> ReviewOutcome | None:
    if review is None:
        return None
    return review.model_copy(
        update={
            "reviewer_note": _redact_optional_text(review.reviewer_note),
            "edited_text": _redact_optional_text(review.edited_text),
            "reason_tags": [redact_text(t) for t in review.reason_tags],
        }
    )


def _redact_delivery(delivery: DeliveryOutcome | None) -> DeliveryOutcome | None:
    if delivery is None:
        return None
    return delivery.model_copy(
        update={
            "external_platform_id": redact_external_id(delivery.external_platform_id),
            "error_category": _redact_optional_text(delivery.error_category),
        }
    )


def _redact_critique(critique: HermesSocialCritique | None) -> HermesSocialCritique | None:
    if critique is None:
        return None
    return critique.model_copy(
        update={
            "engagement_hypothesis": redact_text(critique.engagement_hypothesis),
            "risk_flags": [redact_text(t) for t in critique.risk_flags],
            "suggested_improvement": _redact_optional_text(critique.suggested_improvement),
            "reusable_lesson": _redact_optional_text(critique.reusable_lesson),
            "policy_suggestion": _redact_optional_text(critique.policy_suggestion),
        }
    )


def redact_learning_record(record: LearningRecord) -> LearningRecord:
    """Apply text + external-id redaction to every free-text field on a record."""
    return record.model_copy(
        update={
            "draft": _redact_draft(record.draft),
            "review": _redact_review(record.review),
            "delivery": _redact_delivery(record.delivery),
            "critique": _redact_critique(record.critique),
            "safe_future_hint": _redact_optional_text(record.safe_future_hint),
        }
    )


__all__ = ["redact_text", "redact_external_id", "redact_learning_record"]
