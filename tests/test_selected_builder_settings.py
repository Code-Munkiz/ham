"""selected_builder persistence + validation in the coding-agent access settings
(user-selected builder model). Settings-layer only — no server import needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.coding_agent_access_settings import (
    _DEFAULTS,
    _raw_to_policy,
    _policy_to_response,
    CodingAgentAccessSettingsPatch,
)
from src.ham.coding_router.types import WorkspaceAgentPolicy


def test_default_policy_has_no_selected_builder() -> None:
    assert WorkspaceAgentPolicy().selected_builder is None
    assert _DEFAULTS["selected_builder"] is None


def test_raw_to_policy_parses_valid_selected_builder() -> None:
    policy = _raw_to_policy({"selected_builder": "opencode"})
    assert policy.selected_builder == "opencode"
    # Existing flags / preference_mode are preserved.
    assert policy.allow_cursor is True
    assert policy.preference_mode == "recommended"


@pytest.mark.parametrize("value", ["", "nonsense", "openai", "internal_scaffold", 123, None])
def test_raw_to_policy_coerces_unknown_selected_builder_to_none(value: object) -> None:
    policy = _raw_to_policy({"selected_builder": value})
    assert policy.selected_builder is None


def test_policy_response_includes_selected_builder() -> None:
    policy = _raw_to_policy({"selected_builder": "factory_droid"})
    resp = _policy_to_response("ws_x", policy)
    assert resp["selected_builder"] == "factory_droid"


def test_patch_model_accepts_valid_selected_builders() -> None:
    for v in ("cursor", "claude", "opencode", "factory_droid"):
        patch = CodingAgentAccessSettingsPatch(selected_builder=v)
        assert patch.selected_builder == v


def test_patch_model_rejects_hermes_as_selectable_builder() -> None:
    with pytest.raises(ValidationError):
        CodingAgentAccessSettingsPatch(selected_builder="hermes_agent")


def test_patch_model_accepts_null_selected_builder_for_clear() -> None:
    patch = CodingAgentAccessSettingsPatch(selected_builder=None)
    assert patch.selected_builder is None
    assert "selected_builder" in patch.model_fields_set


def test_patch_model_rejects_unknown_selected_builder() -> None:
    with pytest.raises(ValidationError):
        CodingAgentAccessSettingsPatch(selected_builder="not_a_builder")
