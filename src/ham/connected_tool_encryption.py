"""Symmetric encryption helpers for Connected Tools secrets at rest.

``HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY`` must be set (Fernet-compatible
URL-safe base64 key generated with ``cryptography.fernet.Fernet.generate_key()``).
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_ENCRYPTION_VERSION = "fernet-v1"


def connected_tool_encryption_version() -> str:
    return _ENCRYPTION_VERSION


def _encryption_key_material() -> str:
    return (os.environ.get("HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY") or "").strip()


def encryption_configured() -> bool:
    return bool(_encryption_key_material())


class ConnectedToolCredentialEncryptionError(RuntimeError):
    """Raised when encryption is mandatory but misconfigured."""

    pass


def require_fernet() -> Fernet:
    raw = _encryption_key_material()
    if not raw:
        raise ConnectedToolCredentialEncryptionError(
            "HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY must be configured to store "
            "Connected Tools credentials in Firestore. Generate one with Fernet.generate_key()"
            "and set it on the Ham API deployment (operators only; users never paste this)."
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ConnectedToolCredentialEncryptionError(
            "HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY is not valid Fernet key material."
        ) from exc


def encrypt_secret_plaintext(pt: bytes) -> str:
    fer = require_fernet()
    tok = fer.encrypt(pt)
    return tok.decode("ascii")


def decrypt_secret_blob(blob: str) -> bytes:
    fer = require_fernet()
    raw = blob.encode("ascii")
    try:
        return fer.decrypt(raw)
    except InvalidToken as exc:
        raise ConnectedToolCredentialEncryptionError(
            "Connected Tools credential ciphertext could not be decrypted."
        ) from exc
