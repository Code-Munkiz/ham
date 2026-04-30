"""Read-only Social Persona registry tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.social_persona.loader import (
    SocialPersona,
    _reject_secretish_values,
    load_social_persona,
    persona_digest,
)


def test_ham_canonical_persona_loads_with_required_fields() -> None:
    persona = load_social_persona("ham-canonical", 1)
    assert persona.persona_id == "ham-canonical"
    assert persona.version == 1
    assert persona.display_name == "Ham"
    assert persona.short_bio
    assert persona.mission
    assert persona.values
    assert persona.tone_rules
    assert persona.vocabulary.preferred
    assert persona.vocabulary.avoid
    assert persona.humor_rules
    assert persona.emoji_rules
    assert persona.prohibited_content
    assert persona.safety_boundaries
    assert persona.example_replies
    assert persona.example_announcements
    assert persona.refusal_examples


def test_ham_canonical_platform_adaptations_exist() -> None:
    persona = load_social_persona("ham-canonical", 1)
    assert {"x", "telegram", "discord"} <= set(persona.platform_adaptations)
    for platform in ("x", "telegram", "discord"):
        adaptation = persona.platform_adaptations[platform]
        assert adaptation.label
        assert adaptation.style
        assert adaptation.guidance


def test_persona_digest_is_deterministic() -> None:
    persona = load_social_persona("ham-canonical", 1)
    first = persona_digest(persona)
    second = persona_digest(SocialPersona.model_validate(persona.model_dump(mode="json")))
    assert first == second
    assert len(first) == 64
    assert all(ch in "0123456789abcdef" for ch in first)


def test_persona_file_contains_no_secret_shaped_values() -> None:
    persona = load_social_persona("ham-canonical", 1)
    text = json.dumps(persona.model_dump(mode="json"), sort_keys=True)
    forbidden = (
        "api_key",
        "access_token",
        "Bearer ",
        "sk-",
        ".env",
    )
    for value in forbidden:
        assert value not in text


def test_secret_shaped_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="secret-shaped"):
        _reject_secretish_values({"bad": "Authorization: Bearer abcdefghijklmnop"})


def test_persona_schema_rejects_missing_platform_adaptation() -> None:
    data = load_social_persona("ham-canonical", 1).model_dump(mode="json")
    del data["platform_adaptations"]["discord"]
    with pytest.raises(ValueError, match="missing platform adaptations"):
        SocialPersona.model_validate(data)


def test_persona_source_file_is_bounded() -> None:
    path = Path("src/ham/social_persona/personas/ham-canonical.v1.yaml")
    assert path.is_file()
    assert path.stat().st_size < 32_000


def test_social_ui_contains_read_only_persona_panel_without_edit_controls() -> None:
    text = Path("frontend/src/features/hermes-workspace/screens/social/WorkspaceSocialScreen.tsx").read_text(
        encoding="utf-8"
    )
    assert "function PersonaPanel" in text
    assert "Canonical HAM persona" in text
    assert "Digest protection" in text
    assert "What Ham will not say" in text
    forbidden = (
        "Edit persona",
        "Create persona",
        "Save persona",
        "persona/apply",
        "persona/preview",
    )
    for value in forbidden:
        assert value not in text
