"""POST/GET /api/chat/attachments — upload and fetch chat blobs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.chat_attachment_store import LocalDiskAttachmentStore, set_chat_attachment_store_for_tests

client = TestClient(app)


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


@pytest.fixture
def att_dir(tmp_path: Path) -> Path:
    d = tmp_path / "att"
    d.mkdir()
    return d


def test_post_attachment_png(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("a.png", _TINY_PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["attachment_id"].startswith("hamatt_")
    assert j["mime"] == "image/png"
    assert j["size"] == len(_TINY_PNG)

    g = client.get(f"/api/chat/attachments/{j['attachment_id']}")
    assert g.status_code == 200
    assert g.content == _TINY_PNG


def test_post_attachment_rejects_gif(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    gif = b"GIF89a" + b"\x00" * 20
    r = client.post(
        "/api/chat/attachments",
        files={"file": ("x.gif", gif, "image/gif")},
    )
    assert r.status_code == 415


def test_post_attachment_too_large(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_MAX_BYTES", "4")
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("a.png", _TINY_PNG, "image/png")},
    )
    assert r.status_code == 413


def test_get_unknown_404(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.get("/api/chat/attachments/hamatt_notfound" + "x" * 20)
    assert r.status_code == 404
