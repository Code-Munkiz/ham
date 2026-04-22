"""Read-only harness capability registry — shape and invariants only."""

from __future__ import annotations

import pytest

from src.ham.harness_capabilities import (
    HARNESS_CAPABILITIES,
    IMPLEMENTED_PROVIDERS,
    all_harness_capability_providers,
    get_harness_capability,
)
from src.persistence.control_plane_run import ControlPlaneProvider


def test_registry_keys_and_implemented() -> None:
    assert set(all_harness_capability_providers()) == {"cursor_cloud_agent", "factory_droid", "opencode_cli"}
    assert IMPLEMENTED_PROVIDERS == {"cursor_cloud_agent", "factory_droid"}
    oc = get_harness_capability("opencode_cli")
    assert oc is not None
    assert oc.implemented is False
    assert oc.registry_status == "planned_candidate"
    for p in ControlPlaneProvider:
        row = get_harness_capability(p.value)
        assert row is not None
        assert row.implemented is True
        assert row.audit_sink is not None


def test_get_unknown_returns_none() -> None:
    assert get_harness_capability("nope_harness") is None


def test_frozen_row_immutable() -> None:
    row = get_harness_capability("factory_droid")
    assert row is not None
    with pytest.raises(AttributeError):
        row.implemented = False  # type: ignore[misc]
