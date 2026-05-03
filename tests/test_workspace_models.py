"""Phase 1a: Pydantic shape + validator coverage for workspace models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.ham.workspace_models import (
    DESCRIPTION_MAX_LEN,
    NAME_MAX_LEN,
    WORKSPACE_ID_PREFIX,
    OrgRecord,
    UserRecord,
    WorkspaceContext,
    WorkspaceMember,
    WorkspaceRecord,
    is_valid_slug,
    is_valid_workspace_id,
    normalize_email,
)


def _now() -> datetime:
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Alice@Example.com ") == "alice@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_is_valid_slug_accepts_lower_alnum_with_optional_hyphens() -> None:
    assert is_valid_slug("acme")
    assert is_valid_slug("acme-prod-1")
    assert is_valid_slug("a")
    assert is_valid_slug("a1")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "Acme",
        "-leading",
        "trailing-",
        "double--hyphen",
        "spaces here",
        "x" * 49,
        "under_score",
    ],
)
def test_is_valid_slug_rejects_bad_inputs(bad: str) -> None:
    assert not is_valid_slug(bad)


def test_is_valid_workspace_id_accepts_well_formed() -> None:
    assert is_valid_workspace_id(f"{WORKSPACE_ID_PREFIX}abcdefgh12345678")
    assert not is_valid_workspace_id("abcdefgh12345678")
    assert not is_valid_workspace_id(f"{WORKSPACE_ID_PREFIX}short")
    assert not is_valid_workspace_id(f"{WORKSPACE_ID_PREFIX}HASUPPERS12345678")


def test_user_record_normalizes_email() -> None:
    u = UserRecord(
        user_id="user_x",
        email="  Bob@Example.com ",
        display_name="Bob",
        photo_url=None,
        primary_org_id=None,
        created_at=_now(),
        last_seen_at=_now(),
    )
    assert u.email == "bob@example.com"


def test_org_record_basic_shape() -> None:
    o = OrgRecord(org_id="org_x", name="Acme", clerk_slug="acme", created_at=_now())
    assert o.schema_version == 1


def test_workspace_record_validates_id_and_slug() -> None:
    rec = WorkspaceRecord(
        workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
        org_id="org_x",
        owner_user_id="user_a",
        name="Acme Prod",
        slug="acme-prod",
        description="",
        status="active",
        created_by="user_a",
        created_at=_now(),
        updated_at=_now(),
    )
    assert rec.status == "active"

    with pytest.raises(ValueError):
        WorkspaceRecord(
            workspace_id="bad-id",
            org_id=None,
            owner_user_id="user_a",
            name="Bad",
            slug="acme",
            created_by="user_a",
            created_at=_now(),
            updated_at=_now(),
        )

    with pytest.raises(ValueError):
        WorkspaceRecord(
            workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
            org_id=None,
            owner_user_id="user_a",
            name="Bad",
            slug="BadSlug",
            created_by="user_a",
            created_at=_now(),
            updated_at=_now(),
        )


def test_workspace_record_rejects_oversize_fields() -> None:
    with pytest.raises(ValueError):
        WorkspaceRecord(
            workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
            org_id=None,
            owner_user_id="user_a",
            name="x" * (NAME_MAX_LEN + 1),
            slug="acme",
            created_by="user_a",
            created_at=_now(),
            updated_at=_now(),
        )
    with pytest.raises(ValueError):
        WorkspaceRecord(
            workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
            org_id=None,
            owner_user_id="user_a",
            name="ok",
            slug="acme",
            description="x" * (DESCRIPTION_MAX_LEN + 1),
            created_by="user_a",
            created_at=_now(),
            updated_at=_now(),
        )


def test_workspace_member_validates_workspace_id() -> None:
    with pytest.raises(ValueError):
        WorkspaceMember(
            user_id="user_a",
            workspace_id="bad-id",
            role="member",
            added_by="user_a",
            added_at=_now(),
        )


def test_workspace_context_is_frozen_and_has_perm_works() -> None:
    ctx = WorkspaceContext(
        workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
        org_id="org_x",
        actor_user_id="user_a",
        actor_email="alice@example.com",
        role="admin",
        perms=frozenset({"workspace:read", "workspace:write"}),
        org_role="org:admin",
        raw={"membership_source": "workspace_member"},
    )
    assert ctx.has_perm("workspace:read")
    assert not ctx.has_perm("audit:read")
    with pytest.raises(Exception):
        ctx.role = "owner"  # type: ignore[misc]


def test_workspace_context_attribution_keys_match_audit_contract() -> None:
    ctx = WorkspaceContext(
        workspace_id=f"{WORKSPACE_ID_PREFIX}abcdefgh12345678",
        org_id=None,
        actor_user_id="user_a",
        actor_email=None,
        role="owner",
        perms=frozenset({"workspace:read"}),
    )
    attribution = ctx.attribution()
    assert set(attribution.keys()) == {
        "workspace_id",
        "org_id",
        "user_id",
        "email",
        "role",
        "org_role",
        "perms",
    }
    # Must NOT carry secret material.
    forbidden_keys = {"token", "api_key", "access_token", "refresh_token", "secret"}
    assert forbidden_keys.isdisjoint(attribution.keys())
