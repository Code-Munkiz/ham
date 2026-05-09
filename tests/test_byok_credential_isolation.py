"""Isolation checks for per-user Connected Tools BYOK (Firestore-scoped paths mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from src.ham.clerk_auth import HamActor
from src.ham.transcription_config import resolve_transcription_openai_api_key_for_actor
from src.persistence.connected_tool_credentials import get_connected_tool_masked_preview
from src.persistence.firestore_connected_tool_credentials import (
    StoredConnectedToolCredential,
)


def _actor(uid: str) -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def test_openrouter_masked_preview_scoped_to_clerk_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "firestore")
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY", key)

    def _get(
        self: object,
        *,
        owner_type: str,
        owner_id: str,
        tool_id: str,
    ) -> StoredConnectedToolCredential | None:
        if tool_id != "openrouter":
            return None

        masked = "sk-or•AAA" if owner_id == "user_a" else "sk-or•BBB"
        return StoredConnectedToolCredential(
            owner_type=owner_type,
            owner_id=owner_id,
            tool_id=tool_id,
            masked_preview=masked,
            ciphertext="ct",
            encryption_version="test",
            status="on",
        )

    ua, ub = _actor("user_a"), _actor("user_b")
    with patch(
        "src.persistence.firestore_connected_tool_credentials.FirestoreConnectedToolCredentialStore.get_record",
        _get,
    ):
        assert get_connected_tool_masked_preview(ua, "openrouter") == "sk-or•AAA"
        assert get_connected_tool_masked_preview(ub, "openrouter") == "sk-or•BBB"


def test_transcription_resolver_prefers_matching_user_connected_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No platform transcription env — only mocked per-user plaintext."""

    monkeypatch.delenv("HAM_TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)

    def fake_plain(actor: HamActor | None, tool_id: str) -> str | None:
        if tool_id != "openai_transcription" or actor is None:
            return None
        if actor.user_id == "user_a":
            return "sk-realistic-openai-xxxxx-user-a"
        if actor.user_id == "user_b":
            return "sk-realistic-openai-xxxxx-user-b"
        return None

    with patch(
        "src.ham.transcription_config.resolve_connected_tool_secret_plaintext",
        fake_plain,
    ):
        ua, ub = _actor("user_a"), _actor("user_b")
        assert "user-a" in (resolve_transcription_openai_api_key_for_actor(ua) or "")
        assert "user-b" in (resolve_transcription_openai_api_key_for_actor(ub) or "")
