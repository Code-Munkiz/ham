"""Tests for structured chat user payloads (v1 data URLs, v2 attachment ids)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.chat_attachment_store import (
    AttachmentRecord,
    LocalDiskAttachmentStore,
    set_chat_attachment_store_for_tests,
)
from src.ham import chat_user_content as mod


@pytest.fixture
def temp_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from src.ham import chat_user_content as c

    store = LocalDiskAttachmentStore(tmp_path)
    set_chat_attachment_store_for_tests(store)
    monkeypatch.setattr(c, "get_chat_attachment_store", lambda: store)
    return tmp_path


def test_normalize_v2_roundtrip(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "openrouter")
    monkeypatch.setenv("HAM_CHAT_VISION_FORWARD", "1")

    store = get_chat_attachment_store()
    assert isinstance(store, LocalDiskAttachmentStore)
    aid = store.new_id()
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    store.put(
        png,
        AttachmentRecord(
            id=aid,
            filename="a.png",
            mime="image/png",
            size=len(png),
            owner_key="",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "see",
        "attachments": [
            {
                "id": aid,
                "name": "a.png",
                "mime": "image/png",
                "kind": "image",
            },
        ],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    assert mod.try_parse_stored_v2(s) is not None
    parts = mod.to_llm_message_content(s)
    assert isinstance(parts, list)
    assert any(p.get("type") == "image_url" for p in parts if isinstance(p, dict))


def test_v1_still_parses() -> None:
    tiny = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    doc = {
        "h": "ham_chat_user_v1",
        "text": "x",
        "images": [
            {"name": "p.png", "mime": "image/png", "data_url": tiny},
        ],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    assert "ham_chat_user_v1" in s


def test_v2_rejects_wrong_user(temp_store: Path) -> None:
    store = LocalDiskAttachmentStore(temp_store)
    set_chat_attachment_store_for_tests(store)
    aid = store.new_id()
    store.put(
        b"\x89PNG\r\n\x1a\n",
        AttachmentRecord(
            id=aid,
            filename="a.png",
            mime="image/png",
            size=8,
            owner_key="user-a",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "x",
        "attachments": [
            {
                "id": aid,
                "name": "a.png",
                "mime": "image/png",
                "kind": "image",
            },
        ],
    }
    with pytest.raises(ValueError, match="not available"):
        mod.normalize_user_incoming_to_stored(doc, attachment_user_id="user-b")


def test_v2_allows_owner(temp_store: Path) -> None:
    store = LocalDiskAttachmentStore(temp_store)
    set_chat_attachment_store_for_tests(store)
    aid = store.new_id()
    store.put(
        b"\x89PNG\r\n\x1a\n",
        AttachmentRecord(
            id=aid,
            filename="a.png",
            mime="image/png",
            size=8,
            owner_key="user-a",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "x",
        "attachments": [
            {
                "id": aid,
                "name": "a.png",
                "mime": "image/png",
                "kind": "image",
            },
        ],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id="user-a")
    assert "ham_chat_user_v2" in s
