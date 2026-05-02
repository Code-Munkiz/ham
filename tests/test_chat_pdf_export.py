"""Chat transcript PDF export — endpoint, sanitization, auth parity with session GET."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.chat_attachment_store import (
    AttachmentRecord,
    LocalDiskAttachmentStore,
    set_chat_attachment_store_for_tests,
)
from src.ham.pdf_export_sanitizer import redact_for_pdf_export, safe_export_filename_fragment

client = TestClient(app)


def test_redact_gs_paths_and_sk() -> None:
    raw = "See gs://my-bucket/secret/obj and sk-abcdefghijklmnopqrstuvwxyz0123456789foo end"
    out = redact_for_pdf_export(raw)
    assert "gs://my-bucket" not in out
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789foo" not in out
    assert "[redacted]" in out


def test_safe_export_filename_fragment() -> None:
    assert safe_export_filename_fragment("abcdef12-3456-7890-abcd-ef1234567890") == "abcdef12"
    assert safe_export_filename_fragment("") == "session"


def test_export_pdf_unknown_session_404() -> None:
    res = client.get(f"/api/chat/sessions/{uuid.uuid4()}/export.pdf")
    assert res.status_code == 404


def test_export_pdf_returns_pdf_and_redacts() -> None:
    c = client.post("/api/chat/sessions")
    assert c.status_code == 200
    sid = c.json()["session_id"]
    up = client.post(
        f"/api/chat/sessions/{sid}/turns",
        json={
            "turns": [
                {"role": "user", "content": "Read C:\\Users\\alice\\secret.txt and gs://b/x"},
                {
                    "role": "assistant",
                    "content": "OK Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
                },
            ],
        },
    )
    assert up.status_code == 200
    ex = client.get(f"/api/chat/sessions/{sid}/export.pdf")
    assert ex.status_code == 200
    assert ex.headers.get("content-type") == "application/pdf"
    assert (ex.headers.get("pragma") or "").lower() == "no-cache"
    cd = ex.headers.get("content-disposition") or ""
    assert "attachment" in cd.lower()
    assert ".pdf" in cd.lower()
    assert 'filename="ham-chat-' in cd.lower() or "filename=ham-chat-" in cd.lower()
    body = ex.content
    assert body[:4] == b"%PDF"
    assert b"gs://b" not in body
    assert b"C:\\\\Users" not in body and b"C:\\Users" not in body
    assert b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in body


def test_export_pdf_redacts_v2_attachment_file_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as json_mod

    from src.ham.chat_attachment_store import LocalDiskAttachmentStore, set_chat_attachment_store_for_tests

    att_dir = tmp_path / "att"
    att_dir.mkdir()
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(att_dir))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(att_dir))

    tiny_pdf = b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    store = LocalDiskAttachmentStore(att_dir)
    aid = store.new_id()
    store.put(
        tiny_pdf,
        AttachmentRecord(
            id=aid,
            filename="evil.pdf",
            mime="application/pdf",
            size=len(tiny_pdf),
            owner_key="",
            kind="file",
        ),
    )

    v2 = {
        "h": "ham_chat_user_v2",
        "text": "see files",
        "attachments": [
            {
                "id": aid,
                "name": r"C:\Secret\evil.pdf",
                "mime": "application/pdf",
                "kind": "file",
            },
        ],
    }
    c = client.post("/api/chat/sessions")
    assert c.status_code == 200
    sid = c.json()["session_id"]
    up = client.post(
        f"/api/chat/sessions/{sid}/turns",
        json={"turns": [{"role": "user", "content": json_mod.dumps(v2)}]},
    )
    assert up.status_code == 200
    ex = client.get(f"/api/chat/sessions/{sid}/export.pdf")
    assert ex.status_code == 200
    body = ex.content
    assert b"C:\\\\Secret" not in body and b"C:Secret" not in body


def test_chat_session_record_has_no_owner_field() -> None:
    """Documents authz: no per-user row ownership — export inherits GET session scope."""
    from dataclasses import fields

    from src.persistence.chat_session_store import ChatSessionRecord

    field_names = {f.name for f in fields(ChatSessionRecord)}
    assert "owner_key" not in field_names
    assert "owner_clerk_user_id" not in field_names


def test_export_pdf_401_when_clerk_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    res = client.get(f"/api/chat/sessions/{uuid.uuid4()}/export.pdf")
    assert res.status_code == 401
