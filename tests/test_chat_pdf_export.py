"""Chat transcript PDF export — endpoint, sanitization, auth parity with session GET."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
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
    cd = ex.headers.get("content-disposition") or ""
    assert "attachment" in cd.lower()
    assert ".pdf" in cd.lower()
    body = ex.content
    assert body[:4] == b"%PDF"
    assert b"gs://b" not in body
    assert b"C:\\\\Users" not in body and b"C:\\Users" not in body
    assert b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in body


def test_export_pdf_401_when_clerk_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    res = client.get(f"/api/chat/sessions/{uuid.uuid4()}/export.pdf")
    assert res.status_code == 401
