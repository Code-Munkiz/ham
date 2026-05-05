"""Connected Tools credential resolution — Firestore encrypted or file-backed (dev legacy).

When workspace Firestore backend is enabled (``HAM_CONNECTED_TOOLS_CREDENTIAL_BACKEND=auto``
default), credentials for ``openrouter``, ``github``, and ``claude_agent_sdk`` are stored
encrypted in Firestore keyed by Clerk ``user_id``. Plaintext never leaves decrypt paths
inside the API container.

Operators set ``HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY`` (Fernet).

File-backed helpers in ``workspace_tool_credentials`` remain for local/offline backends
and as **read-through fallbacks** when Firestore docs are absent (explicit reconnect
eventually preferred).
"""

from __future__ import annotations

import logging
import os
from typing import Final

from src.ham.connected_tool_encryption import (
    ConnectedToolCredentialEncryptionError,
    connected_tool_encryption_version,
    encrypt_secret_plaintext,
    decrypt_secret_blob,
)
from src.ham.clerk_auth import HamActor
from src.persistence.cursor_credentials import mask_api_key_preview
from src.persistence.workspace_tool_credentials import (
    clear_anthropic_api_key,
    clear_github_token,
    clear_openrouter_api_key,
    get_stored_anthropic_api_key,
    get_stored_github_token,
    get_stored_openrouter_api_key,
    save_anthropic_api_key,
    save_github_token,
    save_openrouter_api_key,
)

_LOG = logging.getLogger(__name__)

_SUPPORTED_TOOLS: Final[frozenset[str]] = frozenset(
    {"openrouter", "github", "claude_agent_sdk"}
)


class ConnectedCredentialSaveFailed(RuntimeError):
    """Persisting/removing Connected Tools credentials failed — safe HTTP mapping."""


def _backend_raw() -> str:
    return (os.environ.get("HAM_CONNECTED_TOOLS_CREDENTIAL_BACKEND") or "").strip().lower()


def connected_tools_credentials_use_firestore() -> bool:
    """Firestore mode when explicitly ``firestore`` or ``auto`` with workspace FS backend."""
    raw = _backend_raw()
    if raw in ("file", "local"):
        return False
    if raw == "firestore":
        return True
    ws = (os.environ.get("HAM_WORKSPACE_STORE_BACKEND") or "").strip().lower()
    return ws == "firestore"


def firestore_encryption_required_for_writes() -> bool:
    """True whenever connect attempts should encrypt (production Firestore path)."""
    return connected_tools_credentials_use_firestore()


def _masked_or_none(secret: str) -> str:
    return mask_api_key_preview(secret.strip())


def _save_file_fallback(tool_id: str, secret: str) -> None:
    if tool_id == "openrouter":
        save_openrouter_api_key(secret)
    elif tool_id == "github":
        save_github_token(secret)
    elif tool_id == "claude_agent_sdk":
        save_anthropic_api_key(secret)
    else:  # pragma: no cover
        raise ValueError(tool_id)


def _clear_file_fallback(tool_id: str) -> None:
    if tool_id == "openrouter":
        clear_openrouter_api_key()
    elif tool_id == "github":
        clear_github_token()
    elif tool_id == "claude_agent_sdk":
        clear_anthropic_api_key()


def _read_file_fallback_secret(tool_id: str) -> str | None:
    if tool_id == "openrouter":
        return get_stored_openrouter_api_key()
    if tool_id == "github":
        return get_stored_github_token()
    if tool_id == "claude_agent_sdk":
        return get_stored_anthropic_api_key()
    return None


def save_connected_tool_secret(actor: HamActor | None, tool_id: str, plaintext: str) -> str:
    """Persist credential; returns masked preview only."""
    if tool_id not in _SUPPORTED_TOOLS:
        raise ValueError(f"unsupported tool id: {tool_id}")
    trimmed = plaintext.strip()
    if not trimmed:
        raise ValueError("empty credential")
    masked = _masked_or_none(trimmed)

    if not connected_tools_credentials_use_firestore():
        _save_file_fallback(tool_id, trimmed)
        return masked

    if actor is None:
        raise ConnectedCredentialSaveFailed(
            "Clerk session is required to store Connected Tools credentials in Firestore."
        )

    from src.persistence.firestore_connected_tool_credentials import (
        FirestoreConnectedToolCredentialStore,
    )

    try:
        ciphertext = encrypt_secret_plaintext(trimmed.encode("utf-8"))
        version = connected_tool_encryption_version()
    except ConnectedToolCredentialEncryptionError:
        raise ConnectedCredentialSaveFailed(
            "Connected Tools credential encryption is misconfigured."
        ) from None
    except Exception as exc:
        _LOG.warning("credential encrypt failed: %s", type(exc).__name__)
        raise ConnectedCredentialSaveFailed("Could not encrypt credential for storage.") from exc

    store = FirestoreConnectedToolCredentialStore()
    try:
        store.upsert_record(
            owner_type="user",
            owner_id=actor.user_id,
            tool_id=tool_id,
            ciphertext=ciphertext,
            encryption_version=version,
            masked_preview=masked,
            status="on",
            acting_user_id=actor.user_id,
        )
    except Exception as exc:
        _LOG.warning("firestore credential save failed: %s", type(exc).__name__)
        raise ConnectedCredentialSaveFailed(
            "Could not persist Connected Tools credential to Firestore."
        ) from exc

    # Avoid stale plaintext fallbacks lingering on ephemeral disk.
    _clear_file_fallback(tool_id)

    return masked


def delete_connected_tool_secret(actor: HamActor | None, tool_id: str) -> bool:
    """Remove stored credential when possible; clears file fallback too."""
    if tool_id not in _SUPPORTED_TOOLS:
        return False
    changed = False
    if actor and connected_tools_credentials_use_firestore():
        from src.persistence.firestore_connected_tool_credentials import (
            FirestoreConnectedToolCredentialStore,
        )

        store = FirestoreConnectedToolCredentialStore()
        try:
            if store.delete_record(
                owner_type="user",
                owner_id=actor.user_id,
                tool_id=tool_id,
            ):
                changed = True
        except Exception as exc:
            _LOG.warning("firestore credential delete failed: %s", type(exc).__name__)
            raise ConnectedCredentialSaveFailed(
                "Could not remove Connected Tools credential."
            ) from exc

    if tool_id == "github":
        if clear_github_token():
            changed = True
    elif tool_id == "openrouter":
        if clear_openrouter_api_key():
            changed = True
    elif tool_id == "claude_agent_sdk":
        if clear_anthropic_api_key():
            changed = True
    return changed


def get_connected_tool_masked_preview(actor: HamActor | None, tool_id: str) -> str | None:
    """Mask only — never ciphertext or plaintext."""
    if tool_id not in _SUPPORTED_TOOLS:
        return None
    if actor and connected_tools_credentials_use_firestore():
        from src.persistence.firestore_connected_tool_credentials import (
            FirestoreConnectedToolCredentialStore,
        )

        store = FirestoreConnectedToolCredentialStore()
        try:
            rec = store.get_record(owner_type="user", owner_id=actor.user_id, tool_id=tool_id)
            if rec and rec.masked_preview.strip():
                return rec.masked_preview.strip()
        except Exception as exc:
            _LOG.warning("firestore credential read failed: %s", type(exc).__name__)
            return None
    fb = _read_file_fallback_secret(tool_id)
    if fb:
        return _masked_or_none(fb)
    return None


def has_connected_tool_credential_record(actor: HamActor | None, tool_id: str) -> bool:
    """Return True when a persisted credential exists (Firestore blob or legacy file).

    Does **not** perform Fernet decryption; Firestore lookups still retrieve ciphertext.
    """
    if tool_id not in _SUPPORTED_TOOLS:
        return False

    if actor and connected_tools_credentials_use_firestore():
        from src.persistence.firestore_connected_tool_credentials import (
            FirestoreConnectedToolCredentialStore,
        )

        store = FirestoreConnectedToolCredentialStore()
        try:
            rec = store.get_record(owner_type="user", owner_id=actor.user_id, tool_id=tool_id)
            return rec is not None and getattr(rec, "status", "on") != "off"
        except Exception:
            return False

    fb = _read_file_fallback_secret(tool_id)
    return bool(fb and fb.strip())


def resolve_connected_tool_secret_plaintext(actor: HamActor | None, tool_id: str) -> str | None:
    """Decrypt/read secret for backend use — never expose to responses."""
    if tool_id not in _SUPPORTED_TOOLS:
        return None
    trimmed: str | None = None

    if actor and connected_tools_credentials_use_firestore():
        from src.persistence.firestore_connected_tool_credentials import (
            FirestoreConnectedToolCredentialStore,
        )

        store = FirestoreConnectedToolCredentialStore()
        try:
            rec = store.get_record(owner_type="user", owner_id=actor.user_id, tool_id=tool_id)
        except Exception as exc:
            _LOG.warning("firestore credential read failed: %s", type(exc).__name__)
            rec = None
        if rec and rec.encryption_version and rec.status != "off":
            try:
                pt = decrypt_secret_blob(rec.ciphertext)
                candidate = pt.decode("utf-8").strip()
                trimmed = candidate or None
            except ConnectedToolCredentialEncryptionError:
                _LOG.warning("credential decrypt rejected for tool_id=%s", tool_id)

    if not trimmed:
        fb = _read_file_fallback_secret(tool_id)
        if fb and fb.strip():
            trimmed = fb.strip()
    return trimmed


def has_connected_tool_secret(actor: HamActor | None, tool_id: str) -> bool:
    """Presence check without decryption on the sensitive path."""
    return has_connected_tool_credential_record(actor, tool_id)


def resolve_claude_agent_anthropic_api_key_for_actor(actor: HamActor | None) -> str | None:
    direct = resolve_connected_tool_secret_plaintext(actor, "claude_agent_sdk")
    if direct:
        return direct
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None
