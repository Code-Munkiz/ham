"""POST/GET /api/chat/attachments — upload and fetch chat blobs."""
from __future__ import annotations

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

_TINY_PDF = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

_OLE_DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40

# Minimal ISO BMFF `ftyp` box (32 bytes) — enough for server-side sniff.
_MINI_MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00" b"isommp41" + b"\x00" * 8
_MINI_WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 28


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


def test_post_attachment_accepts_gif(
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
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mime"] == "image/gif"
    assert j["kind"] == "image"


def test_post_attachment_accepts_pdf(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("a.pdf", _TINY_PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mime"] == "application/pdf"
    assert j["kind"] == "file"


def test_post_attachment_accepts_docx_zip_header(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    blob = b"PK\x03\x04" + b"\x00" * 36
    r = client.post(
        "/api/chat/attachments",
        files={"file": ("w.docx", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mime"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_post_attachment_accepts_xlsx_zip_header(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    blob = b"PK\x03\x04" + b"\x00" * 36
    r = client.post(
        "/api/chat/attachments",
        files={"file": ("t.xlsx", blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mime"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_post_attachment_accepts_csv(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mime"] == "text/csv"


def test_post_attachment_accepts_xls_as_ms_excel(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("old.xls", _OLE_DOC, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mime"] == "application/vnd.ms-excel"


def test_post_attachment_accepts_msword_sniff(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("legacy.doc", _OLE_DOC, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mime"] == "application/msword"


def test_post_attachment_rejects_unknown_binary(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("x.bin", b"\xff\xff\xff\xffZZZ", "application/octet-stream")},
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


def test_post_attachment_image_over_10mb_rejected(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_MAX_BYTES", str(20 * 1024 * 1024))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    # Valid PNG header + payload pad to >10MB (not a valid full PNG, but sniff passes first 8 bytes).
    big = _TINY_PNG + b"\x00" * (11 * 1024 * 1024)
    r = client.post(
        "/api/chat/attachments",
        files={"file": ("big.png", big, "image/png")},
    )
    assert r.status_code == 413
    assert "Image exceeds" in r.json()["detail"]["error"]["message"]


def test_post_attachment_accepts_mp4_sniff(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("clip.mp4", _MINI_MP4, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mime"] == "video/mp4"
    assert j["kind"] == "video"


def test_post_attachment_accepts_mov_quicktime_sniff(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("clip.mov", _MINI_MP4, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mime"] == "video/quicktime"
    assert j["kind"] == "video"


def test_post_attachment_accepts_webm_sniff(
    att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.post(
        "/api/chat/attachments",
        files={"file": ("clip.webm", _MINI_WEBM, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mime"] == "video/webm"
    assert j["kind"] == "video"


def test_get_unknown_404(att_dir: Path, mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = mock_mode
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    r = client.get("/api/chat/attachments/hamatt_notfound" + "x" * 20)
    assert r.status_code == 404
