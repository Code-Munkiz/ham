"""Chat composer preference API: membership, isolation, stale BYOK recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.server import fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.chat_composer_preference_store import (
    LocalJsonChatComposerPreferenceStore,
    _scope_doc_id,
    preference_scope_key,
)
from src.persistence.workspace_store import InMemoryWorkspaceStore, new_workspace_id

import src.api.workspace_chat_composer_preference as wcp_pref


def _now() -> datetime:
    return datetime.now(UTC)


def _actor(uid: str) -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id="sess",
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _seed_personal_workspace(store: InMemoryWorkspaceStore, user_id: str) -> str:
    now = _now()
    wid = new_workspace_id()
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=wid,
            org_id=None,
            owner_user_id=user_id,
            name="Personal",
            slug="personal",
            description="",
            status="active",
            created_by=user_id,
            created_at=now,
            updated_at=now,
        ),
    )
    store.upsert_member(
        WorkspaceMember(
            user_id=user_id,
            workspace_id=wid,
            role="owner",
            added_by=user_id,
            added_at=now,
        ),
    )
    return wid


@pytest.fixture()
def pref_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    store = InMemoryWorkspaceStore()
    wid_a = _seed_personal_workspace(store, "user_a")
    wid_b = _seed_personal_workspace(store, "user_b")
    store_shared = InMemoryWorkspaceStore()
    wid_shared = _seed_personal_workspace(store_shared, "user_a")
    store_shared.upsert_member(
        WorkspaceMember(
            user_id="user_b",
            workspace_id=wid_shared,
            role="member",
            added_by="user_a",
            added_at=_now(),
        ),
    )

    local_store = LocalJsonChatComposerPreferenceStore(tmp_path)
    monkeypatch.setattr(wcp_pref, "_PREF_STORE", local_store)

    def _dep_store() -> InMemoryWorkspaceStore:
        return store

    def _dep_store_shared() -> InMemoryWorkspaceStore:
        return store_shared

    yield {
        "store": store,
        "store_shared": store_shared,
        "wid_a": wid_a,
        "wid_b": wid_b,
        "wid_shared": wid_shared,
        "dep_store": _dep_store,
        "dep_store_shared": _dep_store_shared,
        "tmp": tmp_path,
    }

    fastapi_app.dependency_overrides.pop(get_workspace_store, None)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)


def test_preference_get_404_when_workspace_unknown(pref_client):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store"]
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    c = TestClient(fastapi_app)
    r = c.get("/api/workspaces/ws_notexist000000000/chat-composer-preference")
    assert r.status_code == 404
    assert "HAM_WORKSPACE_NOT_FOUND" in r.text or "not found" in r.text.lower()


def test_preference_user_isolation(pref_client):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store"]
    wid_a = pref_client["wid_a"]
    wid_b = pref_client["wid_b"]

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    c = TestClient(fastapi_app)
    with patch(
        "src.api.models_catalog.has_connected_tool_credential_record",
        return_value=True,
    ), patch(
        "src.api.models_catalog.resolve_connected_tool_secret_plaintext",
        return_value="sk-or-v1-hamtest-user-isolation-key-long-enough-00000000",
    ), patch(
        "src.ham.chat_composer_preference.resolve_connected_tool_secret_plaintext",
        return_value="sk-or-v1-hamtest-user-isolation-key-long-enough-00000000",
    ):
        r = c.put(
            f"/api/workspaces/{wid_a}/chat-composer-preference",
            json={"model_id": "tier:auto"},
        )
    assert r.status_code == 200
    assert r.json().get("model_id") == "tier:auto"

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_b")
    r2 = c.get(f"/api/workspaces/{wid_b}/chat-composer-preference")
    assert r2.status_code == 200
    assert r2.json().get("model_id") is None

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    with patch(
        "src.api.models_catalog.has_connected_tool_credential_record",
        return_value=True,
    ), patch(
        "src.api.models_catalog.resolve_connected_tool_secret_plaintext",
        return_value="sk-or-v1-hamtest-user-isolation-key-long-enough-00000000",
    ), patch(
        "src.ham.chat_composer_preference.resolve_connected_tool_secret_plaintext",
        return_value="sk-or-v1-hamtest-user-isolation-key-long-enough-00000000",
    ):
        r3 = c.get(f"/api/workspaces/{wid_a}/chat-composer-preference")
    assert r3.json().get("model_id") == "tier:auto"


def test_put_cursor_rejected(pref_client):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store"]
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    c = TestClient(fastapi_app)
    wid = pref_client["wid_a"]
    r = c.put(
        f"/api/workspaces/{wid}/chat-composer-preference",
        json={"model_id": "cursor:composer-2"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "CURSOR_MODEL_NOT_PERSISTABLE"


def test_put_unknown_id(pref_client):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store"]
    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    c = TestClient(fastapi_app)
    wid = pref_client["wid_a"]
    r = c.put(
        f"/api/workspaces/{wid}/chat-composer-preference",
        json={"model_id": "not-a-real-ham-model-id-xx"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "UNKNOWN_MODEL_ID"


def test_stale_http_without_byok_clears(pref_client, monkeypatch: pytest.MonkeyPatch):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store"]
    wid = pref_client["wid_a"]
    actor = _actor("user_a")

    key = preference_scope_key(user_id="user_a", workspace_id=wid)
    doc_id = _scope_doc_id(key)
    raw_path = pref_client["tmp"] / f"{doc_id}.json"
    raw_path.write_text(
        '{"model_id": "openai/gpt-4o-mini", "schema_version": 1}',
        encoding="utf-8",
    )

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    c = TestClient(fastapi_app)
    r = c.get(f"/api/workspaces/{wid}/chat-composer-preference")
    assert r.status_code == 200
    assert r.json()["model_id"] is None

    r2 = c.put(
        f"/api/workspaces/{wid}/chat-composer-preference",
        json={"model_id": "openai/gpt-4o-mini"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["model_id"] is None
    assert body.get("cleared") is True


def test_shared_workspace_different_prefs(pref_client):
    fastapi_app.dependency_overrides[get_workspace_store] = pref_client["dep_store_shared"]
    ws = pref_client["wid_shared"]
    key_a = "sk-or-v1-test-ham-byok-key-isolation-aaaaaaaaaaaaaaaaaa"
    key_b = "sk-or-v1-test-ham-byok-key-isolation-bbbbbbbbbbbbbbbbbb"

    def _patches(key: str):
        return (
            patch("src.api.models_catalog.has_connected_tool_credential_record", return_value=True),
            patch("src.api.models_catalog.resolve_connected_tool_secret_plaintext", return_value=key),
            patch("src.ham.chat_composer_preference.resolve_connected_tool_secret_plaintext", return_value=key),
        )

    pa0, pa1, pa2 = _patches(key_a)
    pb0, pb1, pb2 = _patches(key_b)

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    c = TestClient(fastapi_app)
    with pa0, pa1, pa2:
        ra = c.put(
            f"/api/workspaces/{ws}/chat-composer-preference",
            json={"model_id": "tier:auto"},
        )
        assert ra.status_code == 200

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_b")
    with pb0, pb1, pb2:
        rb = c.put(
            f"/api/workspaces/{ws}/chat-composer-preference",
            json={"model_id": "openrouter:default"},
        )
        assert rb.status_code == 200

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_a")
    with pa0, pa1, pa2:
        ga = c.get(f"/api/workspaces/{ws}/chat-composer-preference")
    assert ga.json()["model_id"] == "tier:auto"

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: _actor("user_b")
    with pb0, pb1, pb2:
        gb = c.get(f"/api/workspaces/{ws}/chat-composer-preference")
    assert gb.json()["model_id"] == "openrouter:default"
