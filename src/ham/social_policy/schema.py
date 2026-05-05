"""Pydantic schema for the persisted ``SocialPolicy`` document.

Lives in :mod:`src.ham.social_policy`. v1 is intentionally narrow:

* No raw chat IDs, no tokens, no env values, no gateway paths in any field.
* All free-form strings pass through :func:`src.ham.ham_x.redaction.redact_text`
  on validation; raw token-shaped strings are rejected outright.
* ``extra="forbid"`` everywhere so unknown keys never land in the store.
* ``live_autonomy_armed=True`` is rejected unless ``autopilot_mode="armed"``;
  the API layer additionally requires a separate confirmation phrase and
  the ``HAM_SOCIAL_LIVE_APPLY_TOKEN`` env to even consider that flip.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.ham.ham_x.redaction import redact_text

SOCIAL_POLICY_REL_PATH = ".ham/social_policy.json"

# Reject raw numeric chat / channel / user IDs — Telegram chat IDs are 6+ digit
# integers (often negative for groups). The store only accepts *labels*.
_RAW_NUMERIC_ID_RE = re.compile(r"(?<![A-Za-z])-?\d{6,}(?![A-Za-z])")
# Defense-in-depth: token-shaped opaque strings (very long, mixed) are rejected.
_TOKEN_SHAPE_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|bearer\s+[a-z0-9._~+/=-]{8,}|"
    r"sk-[a-z0-9_-]{10,}|gho_[a-z0-9_-]{10,}|ghp_[a-z0-9_-]{10,}|"
    r"[a-z0-9_./+=-]{48,})"
)
# Conservative tag regex: lower-case, alnum, dash, underscore, dot.
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _reject_raw_id_or_token(value: str, *, field: str) -> None:
    # Token-shape check first so labels like "sk-test1234567890abcdef" are
    # categorised as tokens (more specific) rather than mis-flagged as raw IDs
    # because of an embedded digit run.
    if _TOKEN_SHAPE_RE.search(value):
        raise ValueError(f"{field} contains a token-shaped string; tokens are forbidden.")
    if _RAW_NUMERIC_ID_RE.search(value):
        raise ValueError(f"{field} contains a raw numeric ID; use labels only.")


def redact_string_field(value: str, *, field: str, max_chars: int) -> str:
    """Validate and bound a free-form policy string.

    * Strips whitespace, enforces ``max_chars``.
    * Rejects raw IDs and token-shaped strings.
    * Returns the value verbatim (truncated). Redaction is applied at *read*
      time to bound exposure on response payloads, but stored strings should
      already be clean: the store rejects anything that looks like a secret.
    """
    text = (value or "").strip()
    if not text:
        return text
    if len(text) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters.")
    _reject_raw_id_or_token(text, field=field)
    # Round-trip through redact_text to confirm idempotency: if redaction would
    # mangle the value, reject it. This catches edge cases the regex above
    # missed (e.g. embedded API key shapes).
    redacted = redact_text(text)
    if redacted != text:
        raise ValueError(f"{field} contains content that triggers redaction; rewrite without secrets.")
    return text


def _validate_tag(tag: str, *, field: str) -> str:
    text = (tag or "").strip()
    if not text:
        raise ValueError(f"{field} entries must be non-empty.")
    if len(text) > 64:
        raise ValueError(f"{field} entries must be at most 64 characters.")
    if not _TAG_RE.match(text):
        raise ValueError(
            f"{field} entries must match [a-z0-9][a-z0-9._-]{{0,63}} (lower-case slug)."
        )
    # Defense-in-depth: even though the slug regex already restricts shape,
    # explicitly reject embedded raw numeric IDs (e.g. "chat-100123456789")
    # and obvious token shapes so we never silently store a smuggled secret.
    _reject_raw_id_or_token(text, field=field)
    return text


class PostingCaps(BaseModel):
    """Posting (broadcast) caps. Soft *intent* only; existing governor enforces."""

    model_config = ConfigDict(extra="forbid")

    max_per_day: int = Field(ge=0, le=50, default=1)
    max_per_run: int = Field(ge=0, le=5, default=1)
    min_spacing_minutes: int = Field(ge=0, le=720, default=120)


class ReplyCaps(BaseModel):
    """Reactive reply caps. Mirror :class:`HamXConfig` reactive knobs."""

    model_config = ConfigDict(extra="forbid")

    max_per_15m: int = Field(ge=0, le=20, default=5)
    max_per_hour: int = Field(ge=0, le=60, default=20)
    max_per_user_per_day: int = Field(ge=0, le=10, default=3)
    max_per_thread_per_day: int = Field(ge=0, le=10, default=5)
    min_seconds_between: int = Field(ge=0, le=600, default=60)
    batch_max_per_run: int = Field(ge=0, le=5, default=1)


class ContentStyle(BaseModel):
    """Tone / nature-of-content user preferences."""

    model_config = ConfigDict(extra="forbid")

    tone: Literal["neutral", "warm", "playful", "formal"] = "warm"
    length_preference: Literal["short", "standard", "long"] = "standard"
    emoji_policy: Literal["never", "sparingly", "free"] = "sparingly"
    nature_tags: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("nature_tags")
    @classmethod
    def _validate_nature_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in value:
            tag = _validate_tag(raw, field="content_style.nature_tags")
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
        return out


class SafetyRules(BaseModel):
    """Boundaries / blocked topics / failure stops."""

    model_config = ConfigDict(extra="forbid")

    blocked_topics: list[str] = Field(default_factory=list, max_length=32)
    block_links: bool = True
    min_relevance: float = Field(ge=0.0, le=1.0, default=0.75)
    consecutive_failure_stop: int = Field(ge=1, le=10, default=2)
    policy_rejection_stop: int = Field(ge=1, le=20, default=10)

    @field_validator("blocked_topics")
    @classmethod
    def _validate_blocked_topics(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in value:
            tag = _validate_tag(raw, field="safety_rules.blocked_topics")
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
        return out


class ChannelTarget(BaseModel):
    """Allowed delivery target identified by *label*, never raw IDs."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["home_channel", "test_group"]
    enabled: bool = False


class ProviderPolicy(BaseModel):
    """Per-provider intent: posting + reply mode, caps, allowed actions, targets."""

    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["x", "telegram", "discord"]
    posting_mode: Literal["off", "preview", "approval_required", "autopilot"] = "off"
    reply_mode: Literal["off", "preview", "approval_required", "autopilot"] = "off"
    posting_caps: PostingCaps = Field(default_factory=PostingCaps)
    reply_caps: ReplyCaps = Field(default_factory=ReplyCaps)
    posting_actions_allowed: list[Literal["post", "quote", "reply"]] = Field(
        default_factory=list,
        max_length=3,
    )
    targets: list[ChannelTarget] = Field(default_factory=list, max_length=4)

    @field_validator("posting_actions_allowed", mode="before")
    @classmethod
    def _dedupe_actions(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        seen: set[Any] = set()
        out: list[Any] = []
        for action in value:
            if action in seen:
                continue
            seen.add(action)
            out.append(action)
        return out

    @field_validator("targets")
    @classmethod
    def _dedupe_targets(cls, value: list[ChannelTarget]) -> list[ChannelTarget]:
        seen: set[str] = set()
        out: list[ChannelTarget] = []
        for target in value:
            if target.label in seen:
                continue
            seen.add(target.label)
            out.append(target)
        return out


class PersonaRef(BaseModel):
    """Reference to a versioned :class:`SocialPersona` (no inline copy)."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str = Field(min_length=1, max_length=128)
    persona_version: int = Field(ge=1, le=10_000)

    @field_validator("persona_id")
    @classmethod
    def _validate_persona_id(cls, value: str) -> str:
        return _validate_tag(value, field="persona.persona_id")


class SocialPolicy(BaseModel):
    """Persisted user intent for HAMgomoon / Ham social behavior."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    persona: PersonaRef
    content_style: ContentStyle = Field(default_factory=ContentStyle)
    safety_rules: SafetyRules = Field(default_factory=SafetyRules)
    providers: dict[Literal["x", "telegram", "discord"], ProviderPolicy] = Field(
        default_factory=dict,
    )
    autopilot_mode: Literal["off", "manual_only", "armed"] = "off"
    live_autonomy_armed: bool = False

    @field_validator("providers")
    @classmethod
    def _providers_keys_match(
        cls,
        value: dict[str, ProviderPolicy],
    ) -> dict[str, ProviderPolicy]:
        for key, provider in value.items():
            if provider.provider_id != key:
                raise ValueError(
                    f"providers[{key!r}].provider_id={provider.provider_id!r} does not match key.",
                )
        return value

    @model_validator(mode="after")
    def _live_autonomy_requires_armed(self) -> SocialPolicy:
        if self.live_autonomy_armed and self.autopilot_mode != "armed":
            raise ValueError(
                "live_autonomy_armed=True requires autopilot_mode='armed'.",
            )
        return self


class SocialPolicyChanges(BaseModel):
    """Patch payload for preview / apply.

    Currently v1 accepts a *full* ``SocialPolicy`` replacement under
    ``policy``. A leaf-level patcher can be added in a later phase without
    breaking this contract — preview/apply already work in terms of
    document-replacement semantics.
    """

    model_config = ConfigDict(extra="forbid")

    policy: SocialPolicy

    def has_patch(self) -> bool:  # parity with SettingsChanges.has_patch
        return True


DEFAULT_SOCIAL_POLICY = SocialPolicy(
    persona=PersonaRef(persona_id="ham-canonical", persona_version=1),
    providers={
        "x": ProviderPolicy(provider_id="x"),
        "telegram": ProviderPolicy(provider_id="telegram"),
        "discord": ProviderPolicy(provider_id="discord"),
    },
)


def _redact_string(value: Any, *, max_chars: int = 256) -> Any:
    if isinstance(value, str):
        return redact_text(value)[:max_chars]
    return value


def policy_to_safe_dict(policy: SocialPolicy) -> dict[str, Any]:
    """Return a JSON-serialisable, redacted snapshot for response payloads."""
    raw = policy.model_dump(mode="json")
    style = raw.get("content_style") or {}
    if isinstance(style, dict):
        style["nature_tags"] = [_redact_string(t, max_chars=64) for t in style.get("nature_tags", [])]
    safety = raw.get("safety_rules") or {}
    if isinstance(safety, dict):
        safety["blocked_topics"] = [
            _redact_string(t, max_chars=64) for t in safety.get("blocked_topics", [])
        ]
    return raw
