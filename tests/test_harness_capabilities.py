"""Read-only harness capability registry — shape and invariants only."""

from __future__ import annotations

import pytest

from src.ham.harness_capabilities import (
    HARNESS_CAPABILITIES,
    IMPLEMENTED_PROVIDERS,
    PLANNED_CANDIDATE_PROVIDERS,
    all_harness_capability_providers,
    get_harness_capability,
    is_provider_launchable,
)
from src.persistence.control_plane_run import ControlPlaneProvider


def test_registry_keys_and_implemented() -> None:
    assert set(all_harness_capability_providers()) == {
        "cursor_cloud_agent",
        "factory_droid",
        "claude_code",
        "claude_agent",
        "opencode_cli",
    }
    assert IMPLEMENTED_PROVIDERS == {
        "cursor_cloud_agent",
        "factory_droid",
        "claude_agent",
    }
    assert PLANNED_CANDIDATE_PROVIDERS == {"claude_code"}
    oc = get_harness_capability("opencode_cli")
    assert oc is not None
    assert oc.implemented is False
    assert oc.registry_status == "scaffolded"
    assert oc.integration_modes == {
        "serve": "planned_primary",
        "acp": "planned_fast_follow",
        "cli": "diagnostic_only",
    }
    assert oc.capabilities.get("live_execution") is False
    cc = get_harness_capability("claude_code")
    assert cc is not None
    assert cc.implemented is False
    assert cc.registry_status == "planned_candidate"
    ca = get_harness_capability("claude_agent")
    assert ca is not None
    assert ca.implemented is True
    assert ca.registry_status == "implemented"
    assert ca.audit_sink == "claude_agent_jsonl"
    for p in ControlPlaneProvider:
        row = get_harness_capability(p.value)
        assert row is not None
        if row.registry_status == "scaffolded":
            assert row.implemented is False
            continue
        assert row.implemented is True
        assert row.audit_sink is not None


def test_planned_candidates_have_no_audit_sink_or_runtime_seam() -> None:
    """Planned rows must not advertise an audit sink (no ControlPlaneProviderAuditRef value yet)."""
    for key in PLANNED_CANDIDATE_PROVIDERS:
        row = get_harness_capability(key)
        assert row is not None, key
        assert row.implemented is False, key
        assert row.audit_sink is None, key
        assert row.harness_family == "local_cli_planned", key


def test_planned_candidates_not_in_control_plane_enum() -> None:
    """Planned candidates must not appear in ControlPlaneProvider until an adapter PR lands."""
    enum_values = {p.value for p in ControlPlaneProvider}
    for key in PLANNED_CANDIDATE_PROVIDERS:
        assert key not in enum_values, key


def test_planned_candidates_are_not_launchable() -> None:
    """is_provider_launchable() must return False for planned candidates and unknown keys."""
    for key in PLANNED_CANDIDATE_PROVIDERS:
        assert is_provider_launchable(key) is False, key
    assert is_provider_launchable("nope_harness") is False
    assert is_provider_launchable("") is False


def test_scaffolded_providers_are_not_launchable() -> None:
    """Scaffolded providers (e.g. opencode_cli) are wired into shared tables but
    not yet executable, so is_provider_launchable() must still return False."""
    assert is_provider_launchable("opencode_cli") is False


def test_implemented_providers_are_launchable() -> None:
    """All implemented providers must remain launchable."""
    assert is_provider_launchable("cursor_cloud_agent") is True
    assert is_provider_launchable("factory_droid") is True
    assert is_provider_launchable("claude_agent") is True


def test_claude_agent_in_control_plane_enum() -> None:
    """claude_agent is a first-class ControlPlaneProvider after Mission 2 promotion."""
    assert "claude_agent" in {p.value for p in ControlPlaneProvider}


def test_get_unknown_returns_none() -> None:
    assert get_harness_capability("nope_harness") is None


def test_frozen_row_immutable() -> None:
    row = get_harness_capability("factory_droid")
    assert row is not None
    with pytest.raises(AttributeError):
        row.implemented = False  # type: ignore[misc]
