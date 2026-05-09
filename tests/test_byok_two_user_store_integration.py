"""Two-actor Connected Tools isolation using encrypted cred rows + patched Firestore store.

Patches ``FirestoreConnectedToolCredentialStore.{get_record,delete_record}`` with an
in-memory map (no real GCP). Rows use production ``encrypt_secret_plaintext`` /
``decrypt_secret_blob`` flows so ciphertext is opaque in the fixture map.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from fastapi.testclient import TestClient

from src.api.chat import ChatMessageIn, ChatRequest, _resolve_chat_openrouter_route
from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.connected_tool_encryption import (
    connected_tool_encryption_version,
    encrypt_secret_plaintext,
)
from src.ham.transcription_config import resolve_transcription_openai_api_key_for_actor
from src.persistence.connected_tool_credentials import (
    delete_connected_tool_secret,
    get_connected_tool_masked_preview,
    resolve_connected_tool_secret_plaintext,
)
from src.persistence.cursor_credentials import mask_api_key_preview
from src.persistence.firestore_connected_tool_credentials import (
    StoredConnectedToolCredential,
    document_id_for,
)
from src.api import workspace_tools as workspace_tools_module
from src.api.server import fastapi_app


def _make_actor(uid: str) -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _fixed_clerk_context(
    actor: HamActor | None,
):
    def _resolver(
        authorization: str | None = None,
        x_ham_operator_authorization: str | None = None,
        *,
        route: str,
    ) -> tuple[HamActor | None, str | None]:
        return (actor, None)

    return _resolver


def test_workspace_tools_module_documents_cursor_carve_out() -> None:
    doc = (workspace_tools_module.__doc__ or "")
    assert "Cursor" in doc
    assert "partitioned per Clerk user" in doc
    assert "OpenRouter" in doc


_KEY_OR_ALPHA = (
    "sk-or-v1byok-isolation-proof-user-alpha-distinct-plaintext-required-minimum-length-xxxx"
)
_KEY_OR_BRAVO = (
    "sk-or-v2byok-isolation-proof-user-bravo-distinct-plaintext-required-minimum-length-xxxx"
)
_KEY_STT_ALPHA = (
    "sk-proj-byok-isolation-proof-user-alpha-stt-distinct-plaintext-required-minimum-length-xxxx"
)
_KEY_STT_BRAVO = (
    "sk-proj-byok-isolation-proof-user-bravo-stt-distinct-plaintext-required-minimum-length-xxxx"
)


@pytest.fixture()
def encrypted_mem_firestore(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "firestore")
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY", key)
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "0")
    monkeypatch.delenv("HAM_TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)

    mem: dict[str, StoredConnectedToolCredential] = {}

    def _put_row(user_id: str, tool_id: str, plaintext: str) -> None:
        doc_id = document_id_for("user", user_id, tool_id)
        mem[doc_id] = StoredConnectedToolCredential(
            owner_type="user",
            owner_id=user_id,
            tool_id=tool_id,
            masked_preview=mask_api_key_preview(plaintext),
            ciphertext=encrypt_secret_plaintext(plaintext.encode("utf-8")),
            encryption_version=connected_tool_encryption_version(),
            status="on",
        )

    def get_record(_self: object, *, owner_type: str, owner_id: str, tool_id: str):
        doc_id = document_id_for(owner_type, owner_id, tool_id)
        return mem.get(doc_id)

    def delete_record(_self: object, *, owner_type: str, owner_id: str, tool_id: str) -> bool:
        doc_id = document_id_for(owner_type, owner_id, tool_id)
        if doc_id in mem:
            del mem[doc_id]
            return True
        return False

    from src.persistence.firestore_connected_tool_credentials import (
        FirestoreConnectedToolCredentialStore,
    )

    monkeypatch.setattr(FirestoreConnectedToolCredentialStore, "get_record", get_record)
    monkeypatch.setattr(FirestoreConnectedToolCredentialStore, "delete_record", delete_record)

    yield SimpleNamespace(
        mem=mem,
        put_row=_put_row,
    )


@pytest.mark.integration
class TestEncryptedMemStoreTwoActors:
    def test_alpha_openrouter_decrypt_never_equals_bravo(
        self, encrypted_mem_firestore
    ):
        ua = _make_actor("clerk_actor_alpha_openrouter_isolation_test")
        ub = _make_actor("clerk_actor_bravo_openrouter_isolation_test")
        encrypted_mem_firestore.put_row(ua.user_id, "openrouter", _KEY_OR_ALPHA)
        encrypted_mem_firestore.put_row(ub.user_id, "openrouter", _KEY_OR_BRAVO)

        a_plain = resolve_connected_tool_secret_plaintext(ua, "openrouter") or ""
        b_plain = resolve_connected_tool_secret_plaintext(ub, "openrouter") or ""
        assert a_plain.strip() != b_plain.strip()
        assert "user-alpha-distinct-plaintext" in a_plain
        assert "user-bravo-distinct-plaintext" in b_plain
        assert resolve_connected_tool_secret_plaintext(ua, "openrouter") == a_plain.strip()

    def test_bravo_masked_preview_missing_when_only_alpha_connected_openrouter(
        self, encrypted_mem_firestore
    ):
        ua = _make_actor("clerk_actor_only_alpha_openrouter_masked")
        ub = _make_actor("clerk_actor_bravo_no_openrouter_cred")
        encrypted_mem_firestore.put_row(ua.user_id, "openrouter", _KEY_OR_ALPHA)

        beta_prev = get_connected_tool_masked_preview(ub, "openrouter")
        alpha_prev = get_connected_tool_masked_preview(ua, "openrouter")
        assert beta_prev is None or beta_prev.strip() == ""
        assert alpha_prev not in ("", None)
        assert beta_prev != alpha_prev

    def test_delete_alpha_openrouter_does_not_remove_bravo_openrouter(self, monkeypatch):
        monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "firestore")
        key = Fernet.generate_key().decode("ascii")
        monkeypatch.setenv("HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY", key)

        ua = _make_actor("del_alpha_openrouter")
        ub = _make_actor("keep_bravo_openrouter")
        doc: dict[str, StoredConnectedToolCredential] = {}

        def _upsert(alpha_user: HamActor, plain: str) -> None:
            doc[document_id_for("user", alpha_user.user_id, "openrouter")] = (
                StoredConnectedToolCredential(
                    owner_type="user",
                    owner_id=alpha_user.user_id,
                    tool_id="openrouter",
                    masked_preview=mask_api_key_preview(plain),
                    ciphertext=encrypt_secret_plaintext(plain.encode()),
                    encryption_version=connected_tool_encryption_version(),
                    status="on",
                )
            )

        _upsert(ua, _KEY_OR_ALPHA)
        _upsert(ub, _KEY_OR_BRAVO)

        def get_record(_self: object, *, owner_type: str, owner_id: str, tool_id: str):
            did = document_id_for(owner_type, owner_id, tool_id)
            return doc.get(did)

        def delete_record(_self: object, *, owner_type: str, owner_id: str, tool_id: str) -> bool:
            did = document_id_for(owner_type, owner_id, tool_id)
            return bool(doc.pop(did, None))

        from src.persistence.firestore_connected_tool_credentials import (
            FirestoreConnectedToolCredentialStore,
        )

        monkeypatch.setattr(FirestoreConnectedToolCredentialStore, "get_record", get_record)
        monkeypatch.setattr(FirestoreConnectedToolCredentialStore, "delete_record", delete_record)

        assert delete_connected_tool_secret(ua, "openrouter") is True

        ua_prev = get_connected_tool_masked_preview(ua, "openrouter")
        assert ua_prev is None or ua_prev == ""
        b_after = resolve_connected_tool_secret_plaintext(ub, "openrouter")
        assert b_after == _KEY_OR_BRAVO

    def test_stt_decrypt_scoped_between_two_connected_users(self, encrypted_mem_firestore):
        ua = _make_actor("clerk_actor_alpha_openai_transcribe_iso")
        ub = _make_actor("clerk_actor_bravo_openai_transcribe_iso")
        encrypted_mem_firestore.put_row(ua.user_id, "openai_transcription", _KEY_STT_ALPHA)
        encrypted_mem_firestore.put_row(ub.user_id, "openai_transcription", _KEY_STT_BRAVO)

        assert (
            resolve_transcription_openai_api_key_for_actor(ua).strip().count("alpha-stt-distinct-plaintext") == 1
        )
        assert (
            resolve_transcription_openai_api_key_for_actor(ub).strip().count("bravo-stt-distinct-plaintext") == 1
        )
        alpha_key = resolve_transcription_openai_api_key_for_actor(ua) or ""
        bravo_key = resolve_transcription_openai_api_key_for_actor(ub) or ""
        assert bravo_key not in alpha_key
        assert alpha_key not in bravo_key


@pytest.mark.integration
class TestHttpOpenRouterRouteActorBound:
    def test_hinted_litellm_key_follows_logged_in_actor(
        self, monkeypatch: pytest.MonkeyPatch, encrypted_mem_firestore
    ):
        monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
        ua = _make_actor("hint_openrouter_user_alpha_iso")
        ub = _make_actor("hint_openrouter_user_bravo_iso")
        encrypted_mem_firestore.put_row(ua.user_id, "openrouter", _KEY_OR_ALPHA)
        encrypted_mem_firestore.put_row(ub.user_id, "openrouter", _KEY_OR_BRAVO)

        body = ChatRequest(
            messages=[ChatMessageIn(role="user", content="hi isolation")],
            model_id="tier:auto",
        )
        with patch("src.api.chat.resolve_model_id_for_chat", return_value="openrouter/resolved-mm"):
            oa, hinted_a, _bypass_a = _resolve_chat_openrouter_route(body=body, ham_actor=ua)
            ob, hinted_b, _bypass_b = _resolve_chat_openrouter_route(body=body, ham_actor=ub)

        assert oa == ob == "openrouter/resolved-mm"
        assert hinted_a.strip() != hinted_b.strip()
        assert hinted_a.strip() == _KEY_OR_ALPHA
        assert hinted_b.strip() == _KEY_OR_BRAVO

    def test_user_without_own_openrouter_must_not_pick_model_on_http_gateway(
        self, monkeypatch: pytest.MonkeyPatch, encrypted_mem_firestore
    ):
        monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
        ua = _make_actor("solo_openrouter_cred_http_gate")
        ub = _make_actor("no_openrouter_cred_http_gate")
        encrypted_mem_firestore.put_row(ua.user_id, "openrouter", _KEY_OR_ALPHA)

        body = ChatRequest(
            messages=[ChatMessageIn(role="user", content="hi iso")],
            model_id="tier:auto",
        )
        with patch("src.api.chat.resolve_model_id_for_chat", return_value="openrouter/from-key"):
            _resolve_chat_openrouter_route(body=body, ham_actor=ua)

            with pytest.raises(HTTPException) as exc_info:
                _resolve_chat_openrouter_route(body=body, ham_actor=ub)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"]["code"] == "CONNECT_OPENROUTER_REQUIRED"


@pytest.mark.integration
class TestWorkspaceToolsMaskedOpenRouterIsolation:
    def test_get_workspace_tools_masked_preview_follows_actor_not_peer(
        self, encrypted_mem_firestore
    ):
        ua = _make_actor("ws_tools_openrouter_masked_alpha_iso")
        ub = _make_actor("ws_tools_openrouter_masked_bravo_iso")
        encrypted_mem_firestore.put_row(ua.user_id, "openrouter", _KEY_OR_ALPHA)
        encrypted_mem_firestore.put_row(ub.user_id, "openrouter", _KEY_OR_BRAVO)

        client = TestClient(fastapi_app)

        async def dep_a():
            return ua

        async def dep_b():
            return ub

        secret_fragment = "user-alpha-distinct-plaintext-required-minimum-length"
        try:
            fastapi_app.dependency_overrides[get_ham_clerk_actor] = dep_a
            ja = client.get("/api/workspace/tools").json()
            fastapi_app.dependency_overrides[get_ham_clerk_actor] = dep_b
            jb = client.get("/api/workspace/tools").json()
        finally:
            fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

        ora = next(t for t in ja["tools"] if t["id"] == "openrouter")
        orb = next(t for t in jb["tools"] if t["id"] == "openrouter")

        preview_a = (ora.get("credential_preview") or "").strip()
        preview_b = (orb.get("credential_preview") or "").strip()
        assert preview_a
        assert preview_b
        assert preview_a != preview_b
        assert secret_fragment not in str(jb)
        assert secret_fragment.replace("alpha", "bravo") not in str(ja)

        ra = repr(ja) + repr(jb)
        assert _KEY_OR_ALPHA not in ra and _KEY_OR_BRAVO not in ra


@pytest.mark.integration
class TestTranscribeIsolation:
    def test_actor_without_stt_cred_gets_structured_configure_error_even_if_peer_connected(
        self, monkeypatch: pytest.MonkeyPatch, encrypted_mem_firestore
    ):
        ua = _make_actor("transcribe_only_alpha_connected")
        ub = _make_actor("transcribe_bravo_must_fail")
        encrypted_mem_firestore.put_row(ua.user_id, "openai_transcription", _KEY_STT_ALPHA)

        from src.api import chat as chat_mod

        client = TestClient(fastapi_app)

        captured: dict[str, str] = {}

        async def fake_transcribe(*, api_key: str, **kwargs: object) -> str:
            captured["api_key_used"] = api_key
            return "ok transcript"

        with patch.object(chat_mod, "_transcribe_with_openai", new=fake_transcribe):
            with patch.object(
                chat_mod,
                "_resolve_chat_clerk_context",
                new=_fixed_clerk_context(ua),
            ):
                alpha_resp = client.post(
                    "/api/chat/transcribe",
                    files={"file": ("a.webm", b"\xff\x00meta", "audio/webm")},
                )
            assert alpha_resp.status_code == 200

            assert "alpha-stt-distinct-plaintext" in captured.get("api_key_used", "")
            captured.clear()

            with patch.object(
                chat_mod,
                "_resolve_chat_clerk_context",
                new=_fixed_clerk_context(ub),
            ):
                bravo_resp = client.post(
                    "/api/chat/transcribe",
                    files={"file": ("b.webm", b"\xff\x00meta", "audio/webm")},
                )

            assert bravo_resp.status_code == 503
            detail = bravo_resp.json().get("detail") or {}
            assert detail.get("error", {}).get("code") == "CONNECT_STT_PROVIDER_REQUIRED"
