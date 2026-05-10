"""Hosted Settings privacy gate: ``GET /api/cursor/credentials-status`` and rotate/clear endpoints
must hide every operator detail (env names, file paths, key preview, operator email, internal
route mapping) from non-operator workspace users, and must 403 rotate/clear from non-operators.

Operator-only diagnostic surfaces are gated by ``HAM_WORKSPACE_OPERATOR_EMAILS`` (see
``src/ham/clerk_operator.py``). When Clerk auth is **not** enforced (local dev), every caller
is treated as an operator — these tests therefore enable Clerk session enforcement to model
the deployed staging posture before asserting the normie response shape.
"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

_FORBIDDEN_NORMIE_SUBSTRINGS = (
    "CURSOR_API_KEY",
    "HAM_CURSOR_CREDENTIALS_FILE",
    "cursor_credentials.json",
    "/root/",
    "/api/cursor/models",
    "/api/cursor/agents/launch",
    "crsr_",
    "apiKeyName",
    "wired_for",
    "dashboard_chat_note",
    "storage_path",
    "storage_override_env",
    "key_created_at",
    "user_email",
    "masked_preview",
)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test gets its own ~/.ham so file-state never leaks across tests."""
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
    """Override the Clerk dependency to return ``actor`` without doing JWT verification.

    The unwrapped FastAPI instance lives at ``server.fastapi_app`` (the module's ``app``
    is the ASGI middleware wrapper). ``dependency_overrides`` must be set on the
    FastAPI instance, not the wrapper.
    """
    from src.api.clerk_gate import get_ham_clerk_actor
    from src.api.server import app, fastapi_app

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    from src.api.server import fastapi_app

    fastapi_app.dependency_overrides.clear()


def test_normie_credentials_status_omits_operator_fields(
    monkeypatch: pytest.MonkeyPatch,
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_secret_team_key_value_xxx")

    client = _client_with_actor(normie_actor)
    res = client.get("/api/cursor/credentials-status")
    assert res.status_code == 200
    body = res.json()
    raw = json.dumps(body)

    assert body == {
        "kind": "cursor_credentials_status",
        "configured": True,
        "status": "connected",
        "account_label": "Connected",
        "diagnostics_visible": False,
    }
    for needle in _FORBIDDEN_NORMIE_SUBSTRINGS:
        assert needle not in raw, f"normie payload leaked operator detail: {needle!r}"


def test_normie_credentials_status_unconfigured_payload(
    monkeypatch: pytest.MonkeyPatch,
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    client = _client_with_actor(normie_actor)
    res = client.get("/api/cursor/credentials-status")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "kind": "cursor_credentials_status",
        "configured": False,
        "status": "needs_setup",
        "account_label": None,
        "diagnostics_visible": False,
    }


def test_normie_post_credentials_returns_403_workspace_operator_required(
    monkeypatch: pytest.MonkeyPatch,
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    client = _client_with_actor(normie_actor)
    res = client.post("/api/cursor/credentials", json={"api_key": "crsr_xyz_attempted"})
    assert res.status_code == 403
    body = res.json()
    assert body["detail"]["error"]["code"] == "WORKSPACE_OPERATOR_REQUIRED"
    raw = json.dumps(body)
    assert "crsr_xyz_attempted" not in raw


def test_normie_delete_credentials_returns_403_workspace_operator_required(
    monkeypatch: pytest.MonkeyPatch,
    normie_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_team_key_should_remain")

    client = _client_with_actor(normie_actor)
    res = client.delete("/api/cursor/credentials")
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "WORKSPACE_OPERATOR_REQUIRED"
    assert cc.get_effective_cursor_api_key() == "crsr_team_key_should_remain"


def test_operator_credentials_status_returns_full_payload(
    monkeypatch: pytest.MonkeyPatch,
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    import src.api.cursor_settings as cs
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_operator_visible_key_xxx")

    def fake_me(api_key: str) -> dict[str, Any]:
        return {
            "apiKeyName": "team-key",
            "userEmail": "operator@example.test",
            "createdAt": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(cs, "_fetch_cursor_me", fake_me)

    client = _client_with_actor(operator_actor)
    res = client.get("/api/cursor/credentials-status")
    assert res.status_code == 200
    body = res.json()
    assert body["diagnostics_visible"] is True
    assert body["configured"] is True
    assert body["source"] == "ui"
    assert body["masked_preview"] is not None
    assert body["api_key_name"] == "team-key"
    assert body["user_email"] == "operator@example.test"
    assert body["key_created_at"] == "2026-01-01T00:00:00Z"
    assert body["storage_path"].endswith("cursor_credentials.json")
    assert "wired_for" in body
    assert body["wired_for"]["models_list"] is True


def test_operator_post_credentials_succeeds_when_cursor_verifies(
    monkeypatch: pytest.MonkeyPatch,
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    import src.api.cursor_settings as cs
    from src.persistence import cursor_credentials as cc

    monkeypatch.setattr(cs, "_fetch_cursor_me", lambda key: {"apiKeyName": "ok"})

    client = _client_with_actor(operator_actor)
    res = client.post("/api/cursor/credentials", json={"api_key": "crsr_new_team_key"})
    assert res.status_code == 204
    assert cc.get_effective_cursor_api_key() == "crsr_new_team_key"


def test_operator_delete_credentials_clears_saved_key(
    monkeypatch: pytest.MonkeyPatch,
    operator_actor: Any,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_to_be_cleared")

    client = _client_with_actor(operator_actor)
    res = client.delete("/api/cursor/credentials")
    assert res.status_code == 204
    assert cc.get_effective_cursor_api_key() is None


def test_clerk_disabled_treats_caller_as_operator(
    monkeypatch: pytest.MonkeyPatch,
    cleanup_overrides: None,
) -> None:
    """Local dev (no Clerk auth): single-tenant fallback keeps full diagnostic UI working."""
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_WORKSPACE_OPERATOR_EMAILS", raising=False)

    import src.api.cursor_settings as cs
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_dev_key_xx")
    monkeypatch.setattr(cs, "_fetch_cursor_me", lambda key: {"apiKeyName": "dev"})

    client = _client_with_actor(None)
    res = client.get("/api/cursor/credentials-status")
    assert res.status_code == 200
    body = res.json()
    assert body["diagnostics_visible"] is True
    assert body["source"] == "ui"


def test_operator_email_not_in_allowlist_is_normie(
    monkeypatch: pytest.MonkeyPatch,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    from src.ham.clerk_auth import HamActor
    from src.persistence import cursor_credentials as cc

    cc.save_cursor_api_key("crsr_team_key_yyy")

    other = HamActor(
        user_id="user_other",
        org_id=None,
        session_id="sess_x",
        email="someone-else@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )
    client = _client_with_actor(other)
    res = client.get("/api/cursor/credentials-status")
    body = res.json()
    assert body["diagnostics_visible"] is False
    assert "masked_preview" not in body
    assert "user_email" not in body
