"""
FastAPI TestClient harness for Phase 1b workspace routes.

Provides a tiny, dependency-injected app exposing **only** the Phase 1b
routers (``me`` + ``workspaces``) plus a bypass for the workspace store
fixture. Keeps tests fast and isolated from the rest of the API surface
(chat, social, hermes, …).

Public helpers:

- :func:`make_test_app(store, *, actor=None)` — return a ready-to-test app.
- :func:`actor_for_user(user_id, …)` — minimal :class:`HamActor` factory.
- :func:`seed_two_workspaces(store, …)` — populate a clean store with two
  workspaces under different orgs and a personal workspace.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.me import router as me_router
from src.api.workspaces import router as workspaces_router
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import (
    MembershipRecord,
    OrgRecord,
    UserRecord,
    WorkspaceMember,
    WorkspaceRecord,
)
from src.persistence.workspace_store import (
    InMemoryWorkspaceStore,
    WorkspaceStore,
    new_workspace_id,
)


def actor_for_user(
    user_id: str,
    *,
    email: str | None = None,
    org_id: str | None = None,
    org_role: str | None = "org:member",
    permissions: frozenset[str] | None = None,
    raw_permission_claim: str | None = "permissions",
    workspaces_claim: dict[str, Any] | None = None,
    session_id: str | None = "sess_test",
) -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=org_id,
        session_id=session_id,
        email=email,
        permissions=permissions if permissions is not None else frozenset(),
        org_role=org_role,
        raw_permission_claim=raw_permission_claim,
        workspaces_claim=workspaces_claim or {},
    )


def make_test_app(
    store: WorkspaceStore,
    *,
    actor: HamActor | None = None,
) -> FastAPI:
    """Build a minimal app with only the two Phase 1b routers + DI overrides.

    Pass ``actor=None`` to simulate "no Clerk session" (then the route
    behavior depends on env: hosted → 401; local-dev bypass on → synthetic
    actor; off → 401).
    """
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(workspaces_router)

    async def _override_actor() -> HamActor | None:
        return actor

    def _override_store() -> WorkspaceStore:
        return store

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    app.dependency_overrides[get_workspace_store] = _override_store
    return app


def client_for(
    store: WorkspaceStore,
    *,
    actor: HamActor | None = None,
) -> TestClient:
    return TestClient(make_test_app(store, actor=actor))


def fresh_store() -> InMemoryWorkspaceStore:
    return InMemoryWorkspaceStore()


def seed_two_workspaces(
    store: WorkspaceStore,
    *,
    org_a: str = "org_a",
    org_b: str = "org_b",
    owner_a: str = "user_alice",
    owner_b: str = "user_bob",
) -> dict[str, str]:
    """Seed two orgs + two workspaces (one per org) + a personal workspace.

    Returns a dict of named ids: ``ws_a``, ``ws_b``, ``ws_personal``,
    ``org_a``, ``org_b``, ``owner_a``, ``owner_b``.
    """
    now = datetime.now(UTC)
    store.upsert_org(OrgRecord(org_id=org_a, name="Org A", clerk_slug="org-a", created_at=now))
    store.upsert_org(OrgRecord(org_id=org_b, name="Org B", clerk_slug="org-b", created_at=now))
    store.upsert_user(
        UserRecord(
            user_id=owner_a,
            email="alice@example.com",
            primary_org_id=org_a,
            created_at=now,
            last_seen_at=now,
        ),
    )
    store.upsert_user(
        UserRecord(
            user_id=owner_b,
            email="bob@example.com",
            primary_org_id=org_b,
            created_at=now,
            last_seen_at=now,
        ),
    )
    store.upsert_membership(
        MembershipRecord(user_id=owner_a, org_id=org_a, org_role="org:admin", joined_at=now),
    )
    store.upsert_membership(
        MembershipRecord(user_id=owner_b, org_id=org_b, org_role="org:admin", joined_at=now),
    )

    ws_a = new_workspace_id()
    ws_b = new_workspace_id()
    ws_personal = new_workspace_id()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_a,
            org_id=org_a,
            owner_user_id=owner_a,
            name="Alpha",
            slug="alpha",
            description="",
            created_by=owner_a,
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=owner_a,
            workspace_id=ws_a,
            role="owner",
            added_by=owner_a,
            added_at=now,
        ),
    )
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_b,
            org_id=org_b,
            owner_user_id=owner_b,
            name="Beta",
            slug="beta",
            description="",
            created_by=owner_b,
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=owner_b,
            workspace_id=ws_b,
            role="owner",
            added_by=owner_b,
            added_at=now,
        ),
    )
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=ws_personal,
            org_id=None,
            owner_user_id=owner_a,
            name="Alice Personal",
            slug="alice-personal",
            description="",
            created_by=owner_a,
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=owner_a,
            workspace_id=ws_personal,
            role="owner",
            added_by=owner_a,
            added_at=now,
        ),
    )
    return {
        "ws_a": ws_a,
        "ws_b": ws_b,
        "ws_personal": ws_personal,
        "org_a": org_a,
        "org_b": org_b,
        "owner_a": owner_a,
        "owner_b": owner_b,
    }


def isolate_audit(monkeypatch, tmp_path: Any) -> Any:
    """Redirect operator audit JSONL into a temp path; return that path."""
    audit_path = tmp_path / "operator_actions.jsonl"
    monkeypatch.setenv("HAM_OPERATOR_AUDIT_FILE", str(audit_path))
    return audit_path


def isolate_envs(monkeypatch) -> None:
    """Default each test to hosted-mode-off + local-dev-bypass-on disabled.

    Tests opt into specific modes explicitly.
    """
    for k in (
        "HAM_CLERK_REQUIRE_AUTH",
        "HAM_LOCAL_DEV_WORKSPACE_BYPASS",
        "HAM_WORKSPACE_MEMBER_WRITES",
        "HAM_WORKSPACE_ROUTES_ENABLED",
    ):
        monkeypatch.delenv(k, raising=False)


def assert_no_secret_keys(payload: Any) -> None:
    """Recursively verify ``payload`` carries no banned secret keys."""
    banned = {"token", "api_key", "access_token", "refresh_token", "secret"}

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                ks = str(k).lower()
                assert ks not in banned, f"banned key {k!r} at {path}"
                _walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(payload, "$")


# Sanity guard so ``import os`` is referenced (some linters complain otherwise);
# and so `pytest` collection of this helper file doesn't fail.
_ = os.name


__all__ = [
    "actor_for_user",
    "assert_no_secret_keys",
    "client_for",
    "fresh_store",
    "isolate_audit",
    "isolate_envs",
    "make_test_app",
    "seed_two_workspaces",
]
