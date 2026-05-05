"""Connected Tools Firestore facade — ciphertext + masking (no real Firestore IO)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from src.ham.clerk_auth import HamActor
from src.persistence.connected_tool_credentials import (
    save_connected_tool_secret,
)
from src.persistence.firestore_connected_tool_credentials import (
    FirestoreConnectedToolCredentialStore,
)


@pytest.fixture
def actor() -> HamActor:
    return HamActor(
        user_id="user_cred_unit",
        org_id=None,
        session_id="s1",
        email="u@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def test_save_firestore_writes_ciphertext_not_plaintext(monkeypatch, actor: HamActor) -> None:
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "firestore")
    monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "test-proj")
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY", key)
    secret = "sk-ant-api03-" + "x" * 32
    captured: dict[str, object] = {}

    def _upsert(*_args, **kwargs: object) -> None:
        captured.update(kwargs)

    with patch.object(FirestoreConnectedToolCredentialStore, "upsert_record", _upsert):
        masked = save_connected_tool_secret(actor, "claude_agent_sdk", secret)

    assert secret not in str(captured)
    assert secret not in captured.get("ciphertext", "")
    assert masked
    assert "sk-ant" in masked or "•" in masked or "*" in masked


def test_save_file_backend_does_not_touch_firestore(monkeypatch, tmp_path, actor: HamActor) -> None:
    monkeypatch.delenv("HAM_WORKSPACE_STORE_BACKEND", raising=False)
    monkeypatch.setenv("HAM_CONNECTED_TOOLS_CREDENTIAL_BACKEND", "file")
    fp = tmp_path / "w.json"
    monkeypatch.setenv("HAM_WORKSPACE_TOOL_CREDENTIALS_FILE", str(fp))

    called: list[str] = []

    def _boom(**_k: object) -> None:
        called.append("upsert")

    with patch.object(FirestoreConnectedToolCredentialStore, "upsert_record", _boom):
        save_connected_tool_secret(actor, "github", "ghp_" + "a" * 36)

    assert not called
    text = fp.read_text(encoding="utf-8")
    assert "ghp_" in text
