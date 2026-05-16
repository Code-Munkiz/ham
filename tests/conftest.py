"""Shared pytest fixtures.

Autouse fixtures here run for every test in this directory, ensuring
process-wide singletons are reset between tests so env-var changes take effect.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_opencode_readiness_cache() -> None:
    """Reset the opencode readiness cache before each test.

    ``check_opencode_readiness`` caches its result at module level. Tests that
    monkeypatch ``HAM_OPENCODE_ENABLED``, ``ANTHROPIC_API_KEY``, etc. require a
    fresh probe so the monkeypatched env is actually read.
    """
    from src.ham.worker_adapters.opencode_adapter import reset_opencode_readiness_cache

    reset_opencode_readiness_cache()
    yield
    reset_opencode_readiness_cache()


@pytest.fixture(autouse=True)
def _reset_cp_run_store_singleton() -> None:
    """Reset the ControlPlaneRunStore singleton before and after each test.

    Tests that monkeypatch HAM_CONTROL_PLANE_RUNS_DIR rely on fresh store
    instantiation. Without this reset, a singleton built in a prior test
    still points to that test's tmp_path dir and silently misses new writes.
    Tests that explicitly call set_control_plane_run_store_for_tests() are
    unaffected — the reset simply clears the cached instance so the next
    call to get_control_plane_run_store() picks up the current env vars.
    """
    from src.persistence.control_plane_run import set_control_plane_run_store_for_tests

    set_control_plane_run_store_for_tests(None)
    yield
    set_control_plane_run_store_for_tests(None)
