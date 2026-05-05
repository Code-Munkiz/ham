"""Phase 1a: local-dev synthetic actor + bypass-flag semantics.

These tests cover the *pure* behaviour of the helpers in
``src.api.dependencies.workspace`` without spinning up a FastAPI app — the
deps themselves are exercised end-to-end in Phase 1b's API tests.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from src.api.dependencies.workspace import (
    LOCAL_DEV_BYPASS_ENV,
    LOCAL_DEV_EMAIL,
    LOCAL_DEV_USER_ID,
    _local_dev_bypass_enabled,
    synthetic_local_dev_actor,
)


def test_synthetic_actor_has_stable_identity() -> None:
    a = synthetic_local_dev_actor()
    assert a.user_id == LOCAL_DEV_USER_ID
    assert a.email == LOCAL_DEV_EMAIL
    assert a.org_id is None
    assert "ham:admin" in a.permissions
    assert a.org_role == "org:admin"
    assert a.raw_permission_claim == "local_dev_bypass"
    # Default workspaces_claim is empty
    assert dict(a.workspaces_claim) == {}


@pytest.mark.parametrize("on_value", ["true", "1", "yes", "on", "TRUE", "On"])
def test_local_dev_bypass_enabled_for_truthy_values(monkeypatch, on_value) -> None:
    monkeypatch.setenv(LOCAL_DEV_BYPASS_ENV, on_value)
    assert _local_dev_bypass_enabled() is True


@pytest.mark.parametrize("off_value", ["", "false", "0", "no", "off", "garbage"])
def test_local_dev_bypass_disabled_for_falsy_values(monkeypatch, off_value) -> None:
    monkeypatch.setenv(LOCAL_DEV_BYPASS_ENV, off_value)
    assert _local_dev_bypass_enabled() is False


def test_local_dev_bypass_disabled_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv(LOCAL_DEV_BYPASS_ENV, raising=False)
    assert _local_dev_bypass_enabled() is False


def test_synthetic_actor_can_resolve_personal_workspace() -> None:
    """End-to-end: synthetic dev actor + personal workspace → owner role."""
    from datetime import datetime

    from src.ham.workspace_models import WorkspaceRecord
    from src.ham.workspace_resolver import resolve_workspace_context
    from src.persistence.workspace_store import (
        InMemoryWorkspaceStore,
        new_workspace_id,
    )

    s = InMemoryWorkspaceStore()
    wid = new_workspace_id()
    now = datetime.now(UTC)
    s.create_workspace(
        WorkspaceRecord(
            workspace_id=wid,
            org_id=None,
            owner_user_id=LOCAL_DEV_USER_ID,
            name="Local Dev",
            slug="local-dev",
            description="",
            status="active",
            created_by=LOCAL_DEV_USER_ID,
            created_at=now,
            updated_at=now,
        ),
    )
    ctx = resolve_workspace_context(synthetic_local_dev_actor(), wid, s)
    assert ctx.role == "owner"
    assert "workspace:admin" in ctx.perms
