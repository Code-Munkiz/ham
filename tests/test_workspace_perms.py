"""Phase 1a: role/permission table + Clerk org-role fallback mapping."""

from __future__ import annotations

import pytest

from src.ham.workspace_perms import (
    ORG_ROLE_TO_WORKSPACE_ROLE,
    PERM_AUDIT_READ,
    PERM_MEMBER_READ,
    PERM_MEMBER_WRITE,
    PERM_WORKSPACE_ADMIN,
    PERM_WORKSPACE_READ,
    PERM_WORKSPACE_WRITE,
    ROLE_PERMS,
    has_perm,
    map_org_role_to_workspace_role,
    perms_for_role,
)


def test_role_perms_table_keys_are_the_four_workspace_roles() -> None:
    assert set(ROLE_PERMS.keys()) == {"owner", "admin", "member", "viewer"}


def test_owner_strictly_supersets_admin_supersets_member_supersets_viewer() -> None:
    owner = ROLE_PERMS["owner"]
    admin = ROLE_PERMS["admin"]
    member = ROLE_PERMS["member"]
    viewer = ROLE_PERMS["viewer"]
    assert viewer < member <= admin <= owner
    assert member < admin
    assert admin < owner
    # Sanity: every role can read.
    for role_perms in (owner, admin, member, viewer):
        assert PERM_WORKSPACE_READ in role_perms


def test_admin_lacks_workspace_admin_perm() -> None:
    assert PERM_WORKSPACE_ADMIN in ROLE_PERMS["owner"]
    assert PERM_WORKSPACE_ADMIN not in ROLE_PERMS["admin"]


def test_member_cannot_write_or_admin_or_invite() -> None:
    perms = ROLE_PERMS["member"]
    for forbidden in (
        PERM_WORKSPACE_WRITE,
        PERM_WORKSPACE_ADMIN,
        PERM_MEMBER_WRITE,
        PERM_AUDIT_READ,
    ):
        assert forbidden not in perms
    assert PERM_MEMBER_READ in perms


def test_viewer_only_reads_workspace() -> None:
    assert ROLE_PERMS["viewer"] == frozenset({PERM_WORKSPACE_READ})


def test_perms_for_role_returns_immutable_frozenset() -> None:
    perms = perms_for_role("admin")
    assert isinstance(perms, frozenset)
    assert PERM_WORKSPACE_WRITE in perms


@pytest.mark.parametrize(
    "org_role, expected",
    [
        ("org:admin", "admin"),
        ("org:member", "member"),
        ("org:guest", "viewer"),
        ("unknown", "viewer"),
        ("", "viewer"),
        (None, "viewer"),
    ],
)
def test_map_org_role_to_workspace_role(org_role, expected) -> None:
    assert map_org_role_to_workspace_role(org_role) == expected


def test_org_role_table_only_maps_known_strings() -> None:
    assert ORG_ROLE_TO_WORKSPACE_ROLE == {
        "org:admin": "admin",
        "org:member": "member",
        "org:guest": "viewer",
    }


def test_has_perm_helper_pure() -> None:
    from src.ham.workspace_models import WorkspaceContext

    ctx = WorkspaceContext(
        workspace_id="ws_abcdefgh12345678",
        org_id=None,
        actor_user_id="user_a",
        actor_email=None,
        role="member",
        perms=ROLE_PERMS["member"],
    )
    assert has_perm(ctx, PERM_WORKSPACE_READ)
    assert not has_perm(ctx, PERM_WORKSPACE_WRITE)
