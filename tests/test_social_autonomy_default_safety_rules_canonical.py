"""Focused tests asserting canonical safety_rules in the default AutonomyProfile.

These tests cover Mission 14 M1: the default safety_rules list in
``src/ham/social_autonomy/store._default_profile`` must use the canonical
machine names recognized by ``src/ham/social_autonomy/content_guards.py``
so that a freshly-launched profile never emits
``autonomy_safety_rule_unenforced`` for its own seed list.

Canonical names: credential_request, price_guarantee, mass_tagging,
repeated_payload, no_external_links, payload_min_length.
"""

from __future__ import annotations

import pytest

from src.ham.social_autonomy.content_guards import (
    AUTONOMY_SAFETY_RULE_UNENFORCED,
    AUTONOMY_SAFETY_RULE_VIOLATION,
    collect_content_guard_reasons,
)
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import _default_profile

_CANONICAL_SAFETY_RULES = frozenset(
    {
        "credential_request",
        "price_guarantee",
        "mass_tagging",
        "repeated_payload",
        "no_external_links",
        "payload_min_length",
    }
)

_LEGACY_SAFETY_RULES = frozenset(
    {
        "no spam",
        "no mass tagging",
        "no financial promises",
        "no credential requests",
    }
)


# ---------------------------------------------------------------------------
# VAL-M14-M1-SAFETY-RULES-001 + VAL-M14-M1-SAFETY-RULES-002
# ---------------------------------------------------------------------------


def test_default_safety_rules_exact_canonical_set() -> None:
    """Default safety_rules equals exactly the canonical six names (set equality)."""
    profile = _default_profile()
    actual = set(profile.safety_rules)
    assert actual == _CANONICAL_SAFETY_RULES, (
        f"Expected canonical set {_CANONICAL_SAFETY_RULES!r}, got {actual!r}"
    )


def test_default_safety_rules_subset_of_canonical() -> None:
    """Every entry in the default safety_rules is a canonical machine name."""
    profile = _default_profile()
    unexpected = set(profile.safety_rules) - _CANONICAL_SAFETY_RULES
    assert not unexpected, f"Non-canonical entries found: {unexpected!r}"


def test_default_safety_rules_disjoint_from_legacy() -> None:
    """No legacy display strings remain in the default safety_rules list."""
    profile = _default_profile()
    legacy_found = set(profile.safety_rules) & _LEGACY_SAFETY_RULES
    assert not legacy_found, f"Legacy strings still present: {legacy_found!r}"


# ---------------------------------------------------------------------------
# VAL-M14-M1-SAFETY-RULES-004
# ---------------------------------------------------------------------------


def test_benign_payload_produces_no_unenforced_reason() -> None:
    """A benign short payload against the default safety_rules emits zero
    autonomy_safety_rule_unenforced reasons.

    Covers the case that proves M1's fix actually works: every rule in the
    default list is recognized by the content-guard dispatcher.
    """
    profile = _default_profile()
    draft = "Hello canary."
    reasons = collect_content_guard_reasons(
        draft,
        safety_rules=profile.safety_rules,
    )
    assert AUTONOMY_SAFETY_RULE_UNENFORCED not in reasons, (
        f"Got autonomy_safety_rule_unenforced for benign payload; reasons={reasons!r}"
    )


# ---------------------------------------------------------------------------
# VAL-M14-M1-SAFETY-RULES-005
# ---------------------------------------------------------------------------


def test_credential_request_payload_emits_violation_not_unenforced() -> None:
    """Payload containing 'private key' triggers autonomy_safety_rule_violation
    (recognized rule fires), not autonomy_safety_rule_unenforced (unknown rule).
    """
    profile = _default_profile()
    draft = "Send me your private key to claim the reward."
    reasons = collect_content_guard_reasons(
        draft,
        safety_rules=profile.safety_rules,
    )
    assert AUTONOMY_SAFETY_RULE_VIOLATION in reasons, (
        f"Expected VIOLATION for credential payload; got reasons={reasons!r}"
    )
    assert AUTONOMY_SAFETY_RULE_UNENFORCED not in reasons, (
        f"Got UNENFORCED (unknown rule) for credential payload; reasons={reasons!r}"
    )


# ---------------------------------------------------------------------------
# VAL-M14-M1-SAFETY-RULES-006
# ---------------------------------------------------------------------------


def test_no_external_links_payload_emits_violation_not_unenforced() -> None:
    """Payload containing 'https://example.com' triggers autonomy_safety_rule_violation
    (no_external_links recognized), not autonomy_safety_rule_unenforced.
    """
    profile = _default_profile()
    draft = "Check this out: https://example.com"
    reasons = collect_content_guard_reasons(
        draft,
        safety_rules=profile.safety_rules,
    )
    assert AUTONOMY_SAFETY_RULE_VIOLATION in reasons, (
        f"Expected VIOLATION for external-link payload; got reasons={reasons!r}"
    )
    assert AUTONOMY_SAFETY_RULE_UNENFORCED not in reasons, (
        f"Got UNENFORCED (unknown rule) for external-link payload; reasons={reasons!r}"
    )


# ---------------------------------------------------------------------------
# VAL-M14-M1-SAFETY-RULES-007
# ---------------------------------------------------------------------------


def test_default_profile_is_schema_valid() -> None:
    """_default_profile() returns a valid GoHamSocialProfile without pydantic errors."""
    import pydantic

    try:
        profile = _default_profile()
    except pydantic.ValidationError as exc:
        pytest.fail(f"_default_profile() raised ValidationError: {exc}")

    assert 1 <= len(profile.safety_rules) <= 64, (
        f"safety_rules length {len(profile.safety_rules)} out of [1, 64]"
    )
    for rule in profile.safety_rules:
        assert rule.strip() == rule and rule != "", (
            f"safety_rules entry {rule!r} has surrounding whitespace or is empty"
        )


def test_default_profile_round_trips_model_validate() -> None:
    """GoHamSocialProfile.model_validate round-trips the default profile dump."""
    import pydantic

    profile = _default_profile()
    dumped = profile.model_dump(mode="json")
    try:
        GoHamSocialProfile.model_validate(dumped)
    except pydantic.ValidationError as exc:
        pytest.fail(f"model_validate round-trip raised ValidationError: {exc}")
