"""Unit tests for :class:`CustomBuilderProfile` and its helpers."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from pydantic import ValidationError

from src.ham.custom_builder import (
    CustomBuilderProfile,
    public_dict,
    validate_profile,
)

_SECRET_LIKE_RE = re.compile(r"[A-Za-z0-9]{32,}")


def _minimal_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "builder_id": "game-builder",
        "workspace_id": "ws_abc",
        "owner_user_id": "user_owner",
        "name": "Game Builder",
        "created_at": "2026-05-16T12:00:00Z",
        "updated_at": "2026-05-16T12:00:00Z",
        "updated_by": "user_owner",
    }
    base.update(overrides)
    return base


def test_minimal_valid_profile() -> None:
    p = CustomBuilderProfile(**_minimal_kwargs())
    blob = p.model_dump()
    p2 = CustomBuilderProfile.model_validate(blob)
    assert p == p2
    assert p2.allowed_harnesses == ["opencode_cli"]
    assert p2.preferred_harness == "opencode_cli"
    assert p2.model_source == "ham_default"
    assert p2.permission_preset == "app_build"


def test_full_valid_profile() -> None:
    p = CustomBuilderProfile(
        **_minimal_kwargs(
            description="An app builder for a single-player puzzle game.",
            intent_tags=["game", "puzzle", "2d"],
            task_kinds=["feature", "fix", "refactor"],
            allowed_harnesses=["opencode_cli"],
            model_source="connected_tools_byok",
            model_ref="openrouter/anthropic/claude-sonnet-4.6",
            permission_preset="custom",
            allowed_paths=["src/**", "tests/**"],
            denied_paths=["secrets/**"],
            denied_operations=["rm", "deploy"],
            review_mode="always",
            deletion_policy="deny",
            external_network_policy="ask",
            enabled=True,
        )
    )
    assert p.intent_tags == ["game", "puzzle", "2d"]
    assert p.deletion_policy == "deny"
    assert p.external_network_policy == "ask"
    assert p.review_mode == "always"


def test_oversized_name_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(**_minimal_kwargs(name="x" * 81))


def test_oversized_description_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(**_minimal_kwargs(description="d" * 2001))


def test_oversized_intent_tags_rejected() -> None:
    too_many = [f"tag{i}" for i in range(17)]
    with pytest.raises(ValidationError):
        CustomBuilderProfile(**_minimal_kwargs(intent_tags=too_many))


@pytest.mark.parametrize(
    "bad_id",
    [
        "GameBuilder",
        "-leading-hyphen",
        "with space",
        "with.dot",
        "with/slash",
        "",
    ],
)
def test_invalid_builder_id_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(**_minimal_kwargs(builder_id=bad_id))


@pytest.mark.parametrize(
    "good_id",
    [
        "game-builder",
        "game_builder",
        "game-builder-2",
        "a",
        "0game",
    ],
)
def test_valid_builder_id_accepted(good_id: str) -> None:
    p = CustomBuilderProfile(**_minimal_kwargs(builder_id=good_id))
    assert p.builder_id == good_id


def test_secret_looking_model_ref_rejected() -> None:
    secret_like = "abc123XYZ" * 4
    assert _SECRET_LIKE_RE.search(secret_like)
    with pytest.raises(ValidationError) as exc:
        CustomBuilderProfile(**_minimal_kwargs(model_ref=secret_like))
    msg = str(exc.value).lower()
    assert "secret" in msg or "model_ref" in msg


@pytest.mark.parametrize(
    "good_ref",
    [
        "openrouter/anthropic/claude-sonnet-4.6",
        "byok:abc123-record-id",
        None,
    ],
)
def test_non_secret_model_ref_accepted(good_ref: str | None) -> None:
    p = CustomBuilderProfile(**_minimal_kwargs(model_ref=good_ref))
    assert p.model_ref == good_ref


def test_invalid_path_entry_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(
            **_minimal_kwargs(
                permission_preset="custom",
                allowed_paths=["src/ok", "bad path"],
            )
        )
    with pytest.raises(ValidationError):
        CustomBuilderProfile(
            **_minimal_kwargs(
                permission_preset="custom",
                denied_paths=["secrets;rm -rf /"],
            )
        )


def test_invalid_operation_entry_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(
            **_minimal_kwargs(
                permission_preset="custom",
                denied_operations=["rm -rf"],
            )
        )


def test_custom_preset_requires_scope() -> None:
    with pytest.raises(ValidationError) as exc:
        CustomBuilderProfile(**_minimal_kwargs(permission_preset="custom"))
    assert "custom preset" in str(exc.value).lower()
    p = CustomBuilderProfile(
        **_minimal_kwargs(
            permission_preset="custom",
            allowed_paths=["src/**"],
        )
    )
    assert p.permission_preset == "custom"


def test_default_allowed_harnesses_includes_opencode() -> None:
    p = CustomBuilderProfile(**_minimal_kwargs())
    assert p.allowed_harnesses == ["opencode_cli"]


def test_allowed_harnesses_must_contain_opencode_cli() -> None:
    with pytest.raises(ValidationError) as exc:
        CustomBuilderProfile(
            **_minimal_kwargs(allowed_harnesses=["claude_agent"]),
        )
    assert "opencode_cli" in str(exc.value)


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomBuilderProfile(**_minimal_kwargs(extra_field="x"))


def test_validate_profile_helper_accepts_valid_profile() -> None:
    p = CustomBuilderProfile(**_minimal_kwargs())
    validate_profile(p)


def test_validate_profile_helper_rejects_mutated_dict() -> None:
    p = CustomBuilderProfile(**_minimal_kwargs(permission_preset="app_build"))
    mutated = p.model_copy(update={"permission_preset": "custom"})
    with pytest.raises(ValidationError):
        validate_profile(mutated)


def test_public_dict_no_secret_leak() -> None:
    p = CustomBuilderProfile(
        **_minimal_kwargs(
            model_ref="openrouter/anthropic/claude-sonnet-4.6",
            intent_tags=["game", "puzzle"],
        )
    )
    blob = json.dumps(public_dict(p))
    matches = _SECRET_LIKE_RE.findall(blob)
    assert matches == [], f"public_dict leaks secret-shaped substrings: {matches!r}"


def test_public_dict_round_trips_through_model_validate() -> None:
    p = CustomBuilderProfile(**_minimal_kwargs())
    p2 = CustomBuilderProfile.model_validate(public_dict(p))
    assert p == p2
