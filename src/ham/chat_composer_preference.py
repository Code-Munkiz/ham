"""Resolve persisted chat composer ``model_id`` against gateway mode + BYOK (mirrors chat routing rules)."""

from __future__ import annotations

from dataclasses import dataclass

from src.api.models_catalog import (
    _RESERVED_OPENROUTER_CATALOG_IDS,
    build_catalog_payload,
    get_gateway_mode_for_chat,
    resolve_model_id_for_chat,
)
from src.ham.clerk_auth import HamActor
from src.llm_client import openrouter_api_key_is_plausible
from src.persistence.connected_tool_credentials import resolve_connected_tool_secret_plaintext


@dataclass(frozen=True)
class PreferencePutOutcome:
    """persist_id: normalized catalog id to store (None = Hermes default)."""

    persist_id: str | None
    cleared: bool
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None


def _user_key_ready(actor: HamActor | None) -> bool:
    if actor is None:
        return False
    k = (resolve_connected_tool_secret_plaintext(actor, "openrouter") or "").strip()
    return bool(k and openrouter_api_key_is_plausible(k))


def _item_for_id(payload: dict, mid: str) -> dict | None:
    for it in payload["items"]:
        if it.get("id") == mid:
            return it if isinstance(it, dict) else None
    return None


def _could_be_openrouter_picker_id(model_id: str) -> bool:
    mid = model_id.strip()
    if not mid:
        return False
    if mid.startswith("cursor:"):
        return False
    if mid in _RESERVED_OPENROUTER_CATALOG_IDS:
        return True
    return "/" in mid


def _stale_due_to_gateway_or_byok(
    *,
    item: dict,
    gateway_mode: str,
    user_key_ready: bool,
) -> bool:
    """True when row is gated by HTTP Hermes default / missing BYOK / mock tiers, not by modality."""
    if item.get("supports_chat"):
        return False
    dr = str(item.get("disabled_reason") or "")
    dl = dr.lower()
    if "not text-in" in dl or "text-in compatible" in dl:
        return False
    if gateway_mode == "http" and not user_key_ready:
        return bool(
            "hermes_gateway_mode=http" in dl
            or "http/sse" in dl
            or "connect openrouter" in dl
            or "connected tools" in dl
            or "inactive while hermes_gateway_mode=http" in dl
        )
    if gateway_mode == "mock":
        return "mock" in dl and "gateway" in dl
    return False


def _stale_missing_item(
    *,
    model_id: str,
    gateway_mode: str,
    user_key_ready: bool,
) -> bool:
    if gateway_mode != "http" or user_key_ready:
        return False
    return _could_be_openrouter_picker_id(model_id)


def effective_chat_model_id_for_actor(
    *,
    ham_actor: HamActor | None,
    raw_model_id: str | None,
) -> str | None:
    """
    Effective preference for GET (read-only normalize). Returns None for Hermes default.
    Does not mutate storage.
    """
    if not raw_model_id or not str(raw_model_id).strip():
        return None
    mid = str(raw_model_id).strip()
    if mid.startswith("cursor:"):
        return None
    gw = get_gateway_mode_for_chat()
    user_key = _user_key_ready(ham_actor)
    payload = build_catalog_payload(ham_actor)
    item = _item_for_id(payload, mid)
    if item is None:
        if _stale_missing_item(model_id=mid, gateway_mode=gw, user_key_ready=user_key):
            return None
        return None
    if not item.get("supports_chat"):
        if _stale_due_to_gateway_or_byok(item=item, gateway_mode=gw, user_key_ready=user_key):
            return None
        return None
    if gw == "http" and not user_key:
        return None
    try:
        resolve_model_id_for_chat(mid, ham_actor)
    except ValueError:
        return None
    return mid


def resolve_preference_put(
    *,
    ham_actor: HamActor | None,
    raw_model_id: str | None,
) -> PreferencePutOutcome:
    """
    Decide persisted value for PUT. Stale BYOK / mode → persist null, cleared True, 200.

    422 only for cursor:*, unknown ids, or never-chat-capable (e.g. non-text modality) rows.
    """
    if raw_model_id is None or not str(raw_model_id).strip():
        return PreferencePutOutcome(persist_id=None, cleared=False)

    mid = str(raw_model_id).strip()
    if mid.startswith("cursor:"):
        return PreferencePutOutcome(
            persist_id=None,
            cleared=False,
            http_status=422,
            error_code="CURSOR_MODEL_NOT_PERSISTABLE",
            error_message="Cursor API models cannot be stored as the chat model preference.",
        )

    gw = get_gateway_mode_for_chat()
    user_key = _user_key_ready(ham_actor)
    payload = build_catalog_payload(ham_actor)
    item = _item_for_id(payload, mid)

    if item is None:
        if _stale_missing_item(model_id=mid, gateway_mode=gw, user_key_ready=user_key):
            return PreferencePutOutcome(persist_id=None, cleared=True)
        return PreferencePutOutcome(
            persist_id=None,
            cleared=False,
            http_status=422,
            error_code="UNKNOWN_MODEL_ID",
            error_message="Unknown model_id for chat preference.",
        )

    if not item.get("supports_chat"):
        if _stale_due_to_gateway_or_byok(item=item, gateway_mode=gw, user_key_ready=user_key):
            return PreferencePutOutcome(persist_id=None, cleared=True)
        return PreferencePutOutcome(
            persist_id=None,
            cleared=False,
            http_status=422,
            error_code="MODEL_NOT_AVAILABLE_FOR_CHAT",
            error_message="Selected model is not available for chat.",
        )

    if gw == "http" and not user_key:
        return PreferencePutOutcome(persist_id=None, cleared=True)

    try:
        resolve_model_id_for_chat(mid, ham_actor)
    except ValueError as exc:
        code = str(exc)
        if code == "CURSOR_MODEL_NOT_CHAT_ENABLED":
            return PreferencePutOutcome(
                persist_id=None,
                cleared=False,
                http_status=422,
                error_code="CURSOR_MODEL_NOT_PERSISTABLE",
                error_message="Cursor API models cannot be stored as the chat model preference.",
            )
        if code == "MODEL_NOT_AVAILABLE_FOR_CHAT":
            return PreferencePutOutcome(
                persist_id=None,
                cleared=False,
                http_status=422,
                error_code="MODEL_NOT_AVAILABLE_FOR_CHAT",
                error_message="Selected model is not available for chat.",
            )
        return PreferencePutOutcome(
            persist_id=None,
            cleared=False,
            http_status=422,
            error_code="UNKNOWN_MODEL_ID",
            error_message="Unknown model_id for chat preference.",
        )

    return PreferencePutOutcome(persist_id=mid, cleared=False)
