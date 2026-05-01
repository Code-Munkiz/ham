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
    monkeypatch.delenv("HAM_CHAT_VISION_FORWARD", raising=False)

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


def test_normalize_v2_http_gateway_forwards_images_by_default(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP Hermes path mirrors OpenRouter: multimodal unless HAM_CHAT_VISION_FORWARD=0."""
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.delenv("HAM_CHAT_VISION_FORWARD", raising=False)

    store = get_chat_attachment_store()
    aid = store.new_id()
    png = b"\x89PNG\r\n\x1a\n" + b"y" * 12
    store.put(
        png,
        AttachmentRecord(
            id=aid,
            filename="b.png",
            mime="image/png",
            size=len(png),
            owner_key="",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "what color",
        "attachments": [{"id": aid, "name": "b.png", "mime": "image/png", "kind": "image"}],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    parts = mod.to_llm_message_content(s)
    assert isinstance(parts, list)
    urls = [
        str(p["image_url"]["url"])
        for p in parts
        if isinstance(p, dict) and p.get("type") == "image_url"
    ]
    assert len(urls) == 1 and urls[0].startswith("data:image/png;base64,")


def test_normalize_v2_http_respects_vision_forward_off(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HAM_CHAT_VISION_FORWARD", "0")

    store = get_chat_attachment_store()
    aid = store.new_id()
    store.put(
        b"\x89PNG\r\n\x1a\n",
        AttachmentRecord(
            id=aid,
            filename="c.png",
            mime="image/png",
            size=8,
            owner_key="",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "hi",
        "attachments": [{"id": aid, "name": "c.png", "mime": "image/png", "kind": "image"}],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    out = mod.to_llm_message_content(s)
    assert isinstance(out, str)
    assert "HAM_CHAT_VISION_FORWARD=0" in out
    assert "image_url" not in out


def test_normalize_v2_gif_data_url_keeps_gif(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.delenv("HAM_CHAT_VISION_FORWARD", raising=False)

    store = get_chat_attachment_store()
    aid = store.new_id()
    gif_hdr = b"GIF87a\x01\x00\x01\x00\x80\x01\x00" + b"\x00" * 54
    store.put(
        gif_hdr,
        AttachmentRecord(
            id=aid,
            filename="p.gif",
            mime="image/gif",
            size=len(gif_hdr),
            owner_key="",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "x",
        "attachments": [{"id": aid, "name": "p.gif", "mime": "image/gif", "kind": "image"}],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    parts = mod.to_llm_message_content(s)
    assert isinstance(parts, list)
    img_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "image_url"]
    assert len(img_parts) == 1
    assert str(img_parts[0]["image_url"]["url"]).startswith("data:image/gif;base64,")


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


def test_normalize_v2_caps_extra_images_even_when_below_upload_limit(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.delenv("HAM_CHAT_VISION_FORWARD", raising=False)
    monkeypatch.setenv("HAM_CHAT_VISION_MAX_IMAGES", "1")

    store = get_chat_attachment_store()
    blobs = [
        b"\x89PNG\r\n\x1a\n" + bytes([71 + idx] * 25)
        for idx in range(2)
    ]
    aids: list[str] = []
    for i, png in enumerate(blobs):
        aid = store.new_id()
        aids.append(aid)
        store.put(
            png,
            AttachmentRecord(
                id=aid,
                filename=f"im{i}.png",
                mime="image/png",
                size=len(png),
                owner_key="",
                kind="image",
            ),
        )

    doc = {
        "h": "ham_chat_user_v2",
        "text": "both",
        "attachments": [
            {"id": aids[0], "name": "a.png", "mime": "image/png", "kind": "image"},
            {"id": aids[1], "name": "b.png", "mime": "image/png", "kind": "image"},
        ],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    parts = mod.to_llm_message_content(s)
    assert isinstance(parts, list)
    img_count = sum(1 for p in parts if isinstance(p, dict) and p.get("type") == "image_url")
    assert img_count == 1


def test_normalize_v2_http_respects_vision_mode_off(temp_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.chat_attachment_store import get_chat_attachment_store

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HAM_CHAT_VISION_MODE", "off")
    monkeypatch.delenv("HAM_CHAT_VISION_FORWARD", raising=False)

    store = get_chat_attachment_store()
    aid = store.new_id()
    store.put(
        b"\x89PNG\r\n\x1a\n",
        AttachmentRecord(
            id=aid,
            filename="c.png",
            mime="image/png",
            size=8,
            owner_key="",
            kind="image",
        ),
    )
    doc = {
        "h": "ham_chat_user_v2",
        "text": "hi",
        "attachments": [{"id": aid, "name": "c.png", "mime": "image/png", "kind": "image"}],
    }
    s = mod.normalize_user_incoming_to_stored(doc, attachment_user_id=None)
    out = mod.to_llm_message_content(s)
    assert isinstance(out, str)
    assert "HAM_CHAT_VISION_MODE is off" in out
    assert "image_url" not in out
