"""Phase 1a: Clerk JWT ``workspaces`` custom claim extraction + back-compat."""

from __future__ import annotations

from src.ham.clerk_auth import (
    _EMPTY_WORKSPACES_CLAIM,
    HamActor,
    extract_workspaces_claim,
)


def test_extract_workspaces_claim_returns_empty_mapping_when_missing() -> None:
    out = extract_workspaces_claim({"sub": "user_a"})
    assert dict(out) == {}
    assert out is _EMPTY_WORKSPACES_CLAIM


def test_extract_workspaces_claim_returns_empty_when_not_a_dict() -> None:
    out = extract_workspaces_claim({"sub": "user_a", "workspaces": "not-a-dict"})
    assert dict(out) == {}
    out2 = extract_workspaces_claim({"sub": "user_a", "workspaces": []})
    assert dict(out2) == {}


def test_extract_workspaces_claim_keeps_only_string_keys_and_supported_value_shapes() -> None:
    out = extract_workspaces_claim(
        {
            "sub": "user_a",
            "workspaces": {
                "ws_abc12345": "admin",
                "ws_def67890": ["audit:read", "workspace:read"],
                "ws_ghi23456": ("owner",),
                "": "leading-empty-key-discarded",
                42: "non-string-key-discarded",
                "ws_drop_me": {"shape": "not-supported"},
                "ws_drop_int": 42,
            },
        }
    )
    d = dict(out)
    assert d["ws_abc12345"] == "admin"
    assert d["ws_def67890"] == ["audit:read", "workspace:read"]
    assert d["ws_ghi23456"] == ("owner",)
    assert "" not in d
    assert "ws_drop_me" not in d
    assert "ws_drop_int" not in d
    assert 42 not in d


def test_extract_workspaces_claim_returns_immutable_mapping() -> None:
    out = extract_workspaces_claim({"workspaces": {"ws_x": "admin"}})
    try:
        out["ws_y"] = "owner"  # type: ignore[index]
        assert False, "expected immutable mapping"
    except TypeError:
        pass


def test_ham_actor_default_workspaces_claim_is_empty_mapping() -> None:
    """Back-compat: existing call sites that construct HamActor without the
    new field must continue to work and observe an empty mapping."""
    actor = HamActor(
        user_id="user_a",
        org_id=None,
        session_id=None,
        email=None,
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )
    assert dict(actor.workspaces_claim) == {}
    # Frozen dataclass + immutable default.
    try:
        actor.workspaces_claim = {"ws_x": "admin"}  # type: ignore[misc]
        assert False, "frozen dataclass should reject reassignment"
    except Exception:
        pass


def test_ham_actor_explicit_workspaces_claim_sticks() -> None:
    actor = HamActor(
        user_id="user_a",
        org_id="org_x",
        session_id=None,
        email="a@x.com",
        permissions=frozenset(),
        org_role="org:admin",
        raw_permission_claim="permissions",
        workspaces_claim={"ws_abc12345": "owner"},
    )
    assert dict(actor.workspaces_claim) == {"ws_abc12345": "owner"}
