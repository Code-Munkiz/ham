"""Schema-level tests for the persisted Social Policy document.

These tests cover *only* the Pydantic shapes in
:mod:`src.ham.social_policy.schema`. They do not touch the file system,
the API surface, or any provider transport.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    ChannelTarget,
    ContentStyle,
    PersonaRef,
    PostingCaps,
    ProviderPolicy,
    ReplyCaps,
    SafetyRules,
    SocialPolicy,
    SocialPolicyChanges,
    redact_string_field,
)


def _minimal_policy(**overrides: object) -> SocialPolicy:
    base = {
        "persona": PersonaRef(persona_id="ham-canonical", persona_version=1),
        "providers": {
            "x": ProviderPolicy(provider_id="x"),
            "telegram": ProviderPolicy(provider_id="telegram"),
            "discord": ProviderPolicy(provider_id="discord"),
        },
    }
    base.update(overrides)
    return SocialPolicy(**base)  # type: ignore[arg-type]


def test_default_policy_validates_with_safe_zero_intent() -> None:
    policy = DEFAULT_SOCIAL_POLICY
    assert policy.schema_version == 1
    assert policy.autopilot_mode == "off"
    assert policy.live_autonomy_armed is False
    for prov in ("x", "telegram", "discord"):
        provider = policy.providers[prov]
        assert provider.posting_mode == "off"
        assert provider.reply_mode == "off"
        assert provider.posting_actions_allowed == []
        assert provider.targets == []


def test_extra_keys_are_forbidden_everywhere() -> None:
    with pytest.raises(ValidationError):
        SocialPolicy.model_validate(
            {
                "schema_version": 1,
                "persona": {"persona_id": "ham-canonical", "persona_version": 1},
                "providers": {},
                "unknown_field": True,
            }
        )
    with pytest.raises(ValidationError):
        ProviderPolicy.model_validate({"provider_id": "x", "rogue": 1})
    with pytest.raises(ValidationError):
        ChannelTarget.model_validate({"label": "home_channel", "raw_id": -100123456})


def test_provider_policy_dict_key_must_match_provider_id() -> None:
    with pytest.raises(ValidationError):
        SocialPolicy.model_validate(
            {
                "schema_version": 1,
                "persona": {"persona_id": "ham-canonical", "persona_version": 1},
                "providers": {
                    "x": {"provider_id": "telegram"},
                },
                "autopilot_mode": "off",
                "live_autonomy_armed": False,
            }
        )


def test_live_autonomy_armed_requires_autopilot_armed() -> None:
    # armed = True without autopilot_mode = "armed"  -> reject
    with pytest.raises(ValidationError):
        _minimal_policy(live_autonomy_armed=True, autopilot_mode="off")
    with pytest.raises(ValidationError):
        _minimal_policy(live_autonomy_armed=True, autopilot_mode="manual_only")
    # armed = True AND autopilot_mode = "armed" -> ok
    policy = _minimal_policy(live_autonomy_armed=True, autopilot_mode="armed")
    assert policy.live_autonomy_armed is True


def test_channel_target_label_only_no_raw_ids() -> None:
    target = ChannelTarget(label="home_channel", enabled=True)
    assert target.label == "home_channel"
    with pytest.raises(ValidationError):
        ChannelTarget(label="not_in_enum", enabled=True)  # type: ignore[arg-type]


def test_provider_policy_dedupes_actions_and_targets() -> None:
    provider = ProviderPolicy(
        provider_id="telegram",
        posting_actions_allowed=["post", "post", "reply", "reply", "quote"],
        targets=[
            ChannelTarget(label="home_channel", enabled=True),
            ChannelTarget(label="home_channel", enabled=False),
            ChannelTarget(label="test_group", enabled=True),
        ],
    )
    assert provider.posting_actions_allowed == ["post", "reply", "quote"]
    assert [t.label for t in provider.targets] == ["home_channel", "test_group"]


def test_caps_have_strict_bounds() -> None:
    with pytest.raises(ValidationError):
        PostingCaps(max_per_day=-1)
    with pytest.raises(ValidationError):
        PostingCaps(max_per_day=51)  # above hard ceiling
    with pytest.raises(ValidationError):
        ReplyCaps(max_per_15m=-1)
    with pytest.raises(ValidationError):
        ReplyCaps(max_per_hour=61)  # above hard ceiling
    with pytest.raises(ValidationError):
        SafetyRules(min_relevance=1.5)
    SafetyRules(min_relevance=0.0)
    SafetyRules(min_relevance=1.0)


def test_blocked_topics_and_nature_tags_are_slug_validated_and_dedupe() -> None:
    # Lowercase slugs accepted; duplicates removed.
    safety = SafetyRules(blocked_topics=["politics", "politics", "self-harm", "self-harm"])
    assert safety.blocked_topics == ["politics", "self-harm"]

    style = ContentStyle(nature_tags=["news", "news", "deep-dive"])
    assert style.nature_tags == ["news", "deep-dive"]

    # Uppercase rejected by the slug validator (no auto-lowercase).
    with pytest.raises(ValidationError):
        SafetyRules(blocked_topics=["Politics"])


def test_blocked_topics_reject_invalid_slugs() -> None:
    with pytest.raises(ValidationError):
        SafetyRules(blocked_topics=["WITH SPACES"])
    with pytest.raises(ValidationError):
        SafetyRules(blocked_topics=["a" * 65])  # too long
    with pytest.raises(ValidationError):
        SafetyRules(blocked_topics=["bad/char"])  # disallowed char


def test_persona_ref_persona_id_is_slug_validated() -> None:
    PersonaRef(persona_id="ham-canonical", persona_version=1)
    with pytest.raises(ValidationError):
        PersonaRef(persona_id="HAS UPPERCASE", persona_version=1)
    with pytest.raises(ValidationError):
        PersonaRef(persona_id="ham!bang", persona_version=1)
    with pytest.raises(ValidationError):
        PersonaRef(persona_id="ham-canonical", persona_version=0)
    with pytest.raises(ValidationError):
        PersonaRef(persona_id="ham-canonical", persona_version=10_001)


def test_redact_string_field_rejects_raw_ids_and_token_shapes() -> None:
    # Plain text passes.
    assert redact_string_field("hello world", field="x", max_chars=64) == "hello world"

    # Raw numeric IDs (Telegram chat shape) blocked.
    with pytest.raises(ValueError, match="raw numeric ID"):
        redact_string_field("chat -100123456789", field="x", max_chars=128)
    with pytest.raises(ValueError, match="raw numeric ID"):
        redact_string_field("123456789", field="x", max_chars=128)

    # Token-shaped strings blocked.
    with pytest.raises(ValueError, match="token-shaped"):
        redact_string_field(
            "Bearer abcdef12345abcdef12345",
            field="x",
            max_chars=256,
        )
    with pytest.raises(ValueError, match="token-shaped"):
        redact_string_field("sk-test1234567890abcdef", field="x", max_chars=128)
    with pytest.raises(ValueError, match="token-shaped"):
        redact_string_field("api_key=somethingrandom123456", field="x", max_chars=128)

    # Length bound enforced.
    with pytest.raises(ValueError, match="exceeds"):
        redact_string_field("a" * 100, field="x", max_chars=10)


def test_changes_payload_has_patch_returns_true() -> None:
    changes = SocialPolicyChanges(policy=DEFAULT_SOCIAL_POLICY)
    assert changes.has_patch() is True


def test_default_policy_has_three_provider_slots_and_safe_caps() -> None:
    assert set(DEFAULT_SOCIAL_POLICY.providers.keys()) == {"x", "telegram", "discord"}
    for provider in DEFAULT_SOCIAL_POLICY.providers.values():
        assert provider.posting_caps.max_per_day <= 50
        assert provider.reply_caps.max_per_hour <= 60
