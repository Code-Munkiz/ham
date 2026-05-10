"""Workspace operator gate for the shared Cursor Connected Tool.

PR #237 closed the ``/api/cursor/credentials`` POST/DELETE routes to non-operators.
This module locks the parallel Connected Tools paths so a normal signed-in user
cannot rotate or wipe the deployment-global Cursor team key via
``POST /api/workspace/tools/cursor/connect`` or
``POST /api/workspace/tools/cursor/disconnect``, and the listing
(``GET /api/workspace/tools``) does not surface connect/disconnect actions or a
credential preview to non-operators.

Operator allowlist semantics match ``src/ham/clerk_operator.py``:

- Clerk auth NOT enforced (local dev) → caller is treated as operator
- Clerk auth enforced + ``HAM_WORKSPACE_OPERATOR_EMAILS`` empty → nobody is operator
- Clerk auth enforced + allowlist populated → only listed emails are operators
"""

from __future__ import annotations

import pathlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("HAM_CURSOR_CREDENTIALS_FILE", raising=False)


@pytest.fixture
def normie_actor() -> Any:
    from src.ham.clerk_auth import HamActor

    return HamActor(
        user_id="user_normie",
        org_id=None,
        session_id="sess_n",
        email="normie@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def operator_actor() -> Any:
    from src.ham.clerk_auth import HamActor

    return HamActor(
        user_id="user_operator",
        org_id=None,
        session_id="sess_o",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def enforce_clerk_with_operator_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")


def _client_with_actor(actor: Any) -> TestClient:
    from src.api.clerk_gate import get_ham_clerk_actor
    from src.api.server import app, fastapi_app

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    from src.api.server import fastapi_app

    fastapi_app.dependency_overrides.clear()


def _cursor_entry(client: TestClient) -> dict[str, Any]:
    res = client.get("/api/workspace/tools")
    assert res.status_code == 200
    body = res.json()
    return next(t for t in body["tools"] if t["id"] == "cursor")


def test_normie_cursor_connect_returns_403_and_does_not_change_saved_key(
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_existing_team_key")

    client = _client_with_actor(normie_actor)
    res = client.post(
        "/api/workspace/tools/cursor/connect",
        json={"api_key": "cur_" + "a" * 40},
    )
    assert res.status_code == 403
    body = res.json()
    assert body["error_code"] == "WORKSPACE_OPERATOR_REQUIRED"
    assert body["ok"] is False
    assert "cur_" + "a" * 40 not in str(body)
    assert cc.get_effective_cursor_api_key() == "crsr_existing_team_key"


def test_normie_cursor_disconnect_returns_403_and_does_not_clear_saved_key(
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_existing_team_key")

    client = _client_with_actor(normie_actor)
    res = client.post("/api/workspace/tools/cursor/disconnect")
    assert res.status_code == 403
    assert res.json()["error_code"] == "WORKSPACE_OPERATOR_REQUIRED"
    assert cc.get_effective_cursor_api_key() == "crsr_existing_team_key"


def test_operator_cursor_connect_succeeds_when_key_validates(
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.persistence import cursor_credentials as cc

    monkeypatch.setattr(
        "src.api.workspace_tools.validate_cursor_api_key",
        lambda _: True,
    )

    client = _client_with_actor(operator_actor)
    res = client.post(
        "/api/workspace/tools/cursor/connect",
        json={"api_key": "cur_" + "a" * 40},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body.get("credential_preview")
    assert cc.get_effective_cursor_api_key() == "cur_" + "a" * 40


def test_operator_cursor_disconnect_clears_saved_key(
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_to_be_cleared")

    client = _client_with_actor(operator_actor)
    res = client.post("/api/workspace/tools/cursor/disconnect")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert cc.get_effective_cursor_api_key() is None


def test_normie_workspace_tools_listing_hides_cursor_connect_actions(
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_team_key_for_listing")

    client = _client_with_actor(normie_actor)
    cur = _cursor_entry(client)
    assert cur["safe_actions"] == ["check_status"]
    assert cur["connect_kind"] == "none"
    assert cur.get("credential_preview") is None
    assert "managed by your workspace operator" in (cur.get("setup_hint") or "")


def test_operator_workspace_tools_listing_shows_full_cursor_actions(
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_team_key_for_listing_op")

    client = _client_with_actor(operator_actor)
    cur = _cursor_entry(client)
    assert "connect" in cur["safe_actions"]
    assert "disconnect" in cur["safe_actions"]
    assert "check_status" in cur["safe_actions"]
    assert cur["connect_kind"] == "api_key"
    assert cur.get("credential_preview")


def test_clerk_disabled_treats_caller_as_operator_for_cursor_connect(
    monkeypatch: pytest.MonkeyPatch,
    cleanup_overrides: None,
) -> None:
    """Local dev (no Clerk auth): single-tenant fallback keeps connect/disconnect available."""
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_OPERATOR_EMAILS", raising=False)
    monkeypatch.setattr(
        "src.api.workspace_tools.validate_cursor_api_key",
        lambda _: True,
    )

    from src.persistence import cursor_credentials as cc

    client = _client_with_actor(None)
    cur = _cursor_entry(client)
    assert "connect" in cur["safe_actions"]
    assert "disconnect" in cur["safe_actions"]

    res = client.post(
        "/api/workspace/tools/cursor/connect",
        json={"api_key": "cur_" + "b" * 40},
    )
    assert res.status_code == 200
    assert cc.get_effective_cursor_api_key() == "cur_" + "b" * 40

    res2 = client.post("/api/workspace/tools/cursor/disconnect")
    assert res2.status_code == 200
    assert cc.get_effective_cursor_api_key() is None
