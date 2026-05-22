"""Real Hermes-gateway-backed social critic (opt-in via HAM_SOCIAL_CRITIC_USE_HERMES=1).

Activation:
  ``HAM_SOCIAL_CRITIC_USE_HERMES=1`` together with ``HERMES_GATEWAY_BASE_URL``.

Optional tuning:
  ``HAM_SOCIAL_CRITIC_MODEL``        — model override (falls back to ``HERMES_GATEWAY_MODEL``).
  ``HAM_SOCIAL_CRITIC_TIMEOUT_SEC``  — per-call timeout in seconds (default: 30).
  ``HAM_SOCIAL_CRITIC_MAX_INPUT_CHARS`` — max chars of draft text / prompt sent (default: 4096).

Fallback semantics:
  On any gateway error, parse failure, or unhealthy probe the methods return a
  ``StubSocialCritic``-shaped critique with:
    ``notes="hermes_critique_unavailable"``  — gateway / config / probe issue.
    ``notes="hermes_critique_parse_failed"`` — response was not valid JSON.

See ``hermes_critic.py`` for the pluggable interface and the resolver.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from src.ham.hamgomoon_learning.models import (
    HermesSocialCritique,
    LearningRecord,
    SocialDraftRecord,
)
from src.ham.hamgomoon_learning.redaction import redact_external_id, redact_text
from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn

_LOG = logging.getLogger(__name__)

_HERMES_CRITIC_MODEL_ENV = "HAM_SOCIAL_CRITIC_MODEL"
_HERMES_CRITIC_TIMEOUT_ENV = "HAM_SOCIAL_CRITIC_TIMEOUT_SEC"
_HERMES_CRITIC_MAX_INPUT_ENV = "HAM_SOCIAL_CRITIC_MAX_INPUT_CHARS"

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_INPUT = 4096

# Scrub 18+-digit external IDs from prompt text (mirrors learning_hook._EXTERNAL_ID_RE).
_EXTERNAL_ID_RE = re.compile(r"(?<![\w-])-?\d{18,}(?![\w-])")

_CRITIC_SYSTEM_PROMPT = (
    "You are a social media content safety and quality critic. "
    "Evaluate the provided draft post and return ONLY a JSON object with these fields:\n"
    "  draft_id: string (echo back the provided draft_id)\n"
    "  brand_fit_score: float 0.0-1.0 (how well it fits the brand)\n"
    "  safety_score: float 0.0-1.0 (safety; 1.0 = completely safe)\n"
    "  clarity_score: float 0.0-1.0 (message clarity)\n"
    "  engagement_hypothesis: string (why this post would or would not engage)\n"
    "  risk_flags: list of strings (any identified risks; empty list if none)\n"
    "  suggested_improvement: string or null\n"
    "  reusable_lesson: string or null\n"
    "  policy_suggestion: string or null\n"
    "  should_update_strategy: bool\n"
    "Return ONLY valid JSON. Do not add any text before or after the JSON object."
)


def _scrub_prompt_text(text: str) -> str:
    """Apply full secret redaction + 18+-digit ID scrubbing before gateway send."""
    scrubbed = redact_text(text)
    return _EXTERNAL_ID_RE.sub(
        lambda m: redact_external_id(m.group(0)) or "[REDACTED]",
        scrubbed,
    )


def _resolve_hermes_critic_config() -> dict[str, Any] | None:
    """Return config dict when ``HERMES_GATEWAY_BASE_URL`` is configured, else ``None``."""
    base_url = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip()
    if not base_url:
        return None

    model_raw = (os.environ.get(_HERMES_CRITIC_MODEL_ENV) or "").strip()
    gateway_model = (os.environ.get("HERMES_GATEWAY_MODEL") or "").strip()
    model = model_raw or gateway_model or "hermes-agent"

    timeout_raw = (os.environ.get(_HERMES_CRITIC_TIMEOUT_ENV) or "").strip()
    try:
        timeout = float(timeout_raw) if timeout_raw else _DEFAULT_TIMEOUT
    except ValueError:
        timeout = _DEFAULT_TIMEOUT

    max_input_raw = (os.environ.get(_HERMES_CRITIC_MAX_INPUT_ENV) or "").strip()
    try:
        max_input = int(max_input_raw) if max_input_raw else _DEFAULT_MAX_INPUT
    except ValueError:
        max_input = _DEFAULT_MAX_INPUT

    return {
        "model": model,
        "timeout": timeout,
        "max_input": max_input,
    }


class HermesSocialCritic:
    """Hermes-gateway-backed social critic.

    Falls back to stub critique with notes when the gateway call fails,
    the response is not valid JSON, or any unexpected error occurs.
    Never raises from ``critique()`` or ``review()``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def critique(self, draft: SocialDraftRecord) -> HermesSocialCritique:
        """Return a ``HermesSocialCritique`` for *draft*.

        The draft text and prompt are redacted before being sent to the
        gateway. Falls back deterministically to a stub critique with
        ``notes`` set when any failure is encountered.
        """
        # Local import to break potential import cycle with hermes_critic.py.
        from src.ham.hamgomoon_learning.hermes_critic import StubSocialCritic  # noqa: PLC0415

        stub_critique = StubSocialCritic().critique(draft)

        max_input: int = int(self._config.get("max_input", _DEFAULT_MAX_INPUT))
        # Redact before sending to gateway (defense in depth).
        draft_text = _scrub_prompt_text(draft.draft_text or "")[:max_input]
        prompt = _scrub_prompt_text(draft.prompt or "")[:max_input]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _CRITIC_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"draft_id: {draft.draft_id}\n"
                    f"prompt: {prompt}\n"
                    f"draft_text: {draft_text}"
                ),
            },
        ]

        try:
            response_text = complete_chat_turn(
                messages,
                timeout_sec=float(self._config.get("timeout", _DEFAULT_TIMEOUT)),
                http_model_override=str(self._config.get("model", "hermes-agent")),
            )
        except GatewayCallError:
            _LOG.info("hermes_social_critic: GatewayCallError; falling back to stub")
            return stub_critique.model_copy(update={"notes": "hermes_critique_unavailable"})
        except Exception:  # noqa: BLE001
            _LOG.info("hermes_social_critic: unexpected error; falling back to stub")
            return stub_critique.model_copy(update={"notes": "hermes_critique_unavailable"})

        # Parse the JSON response.
        try:
            data = json.loads(response_text.strip())
            if not isinstance(data, dict):
                raise ValueError("Response is not a JSON object")  # noqa: TRY301
            # Ensure draft_id is echoed back.
            data.setdefault("draft_id", draft.draft_id)
            # Clamp scores to [0.0, 1.0] per contract.
            for score_field in ("brand_fit_score", "safety_score", "clarity_score"):
                raw = data.get(score_field)
                if isinstance(raw, (int, float)):
                    data[score_field] = max(0.0, min(1.0, float(raw)))
            # Strip ``notes`` if present — it is a fallback-only field on our side.
            data.pop("notes", None)
            return HermesSocialCritique.model_validate(data)
        except Exception:  # noqa: BLE001
            _LOG.info("hermes_social_critic: parse failure; falling back to stub")
            return stub_critique.model_copy(update={"notes": "hermes_critique_parse_failed"})

    def review(self, tick_result: Any) -> LearningRecord:
        """Create a ``LearningRecord`` using Hermes critique in place of the stub critique.

        Only the ``critique`` sub-object of the envelope is replaced;
        redaction pipeline and append semantics are unchanged.
        """
        from src.ham.hamgomoon_learning.hermes_critic import StubSocialCritic  # noqa: PLC0415

        stub = StubSocialCritic()
        record = stub.review(tick_result)
        hermes_critique = self.critique(record.draft)
        return record.model_copy(update={"critique": hermes_critique})


__all__ = ["HermesSocialCritic", "_resolve_hermes_critic_config"]
