"""GET /api/chat/capabilities — conservative flags, semantics, no secret leakage."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.model_capabilities import build_chat_capabilities_payload

client = TestClient(app)


def test_build_payload_document_context_is_extraction_not_native_pdf() -> None:
    p = build_chat_capabilities_payload(model_id="acme/small-model", gateway_mode="openrouter")
    assert p["capabilities"]["document_text_context"] is True
    assert p["capabilities"]["native_pdf"] is False
    assert p["document_context_mode"] == "ham_bounded_text_extraction"
    lims = " ".join(p["limitations"])
    assert "text-extracted" in lims
    assert "not OCRed" in lims or "OCR" in lims
    assert "Video" in lims or "video" in lims


def test_known_vision_model_enables_image_input() -> None:
    res = client.get("/api/chat/capabilities", params={"model_id": "openai/gpt-4o"})
    assert res.status_code == 200
    body = res.json()
    assert body["capabilities"]["image_input"] is True
    assert body["model"]["id"] == "openai/gpt-4o"


def test_unknown_model_conservative() -> None:
    res = client.get(
        "/api/chat/capabilities",
        params={"model_id": "obscure/text-only-7b-instruct"},
    )
    assert res.status_code == 200
    b = res.json()
    assert b["capabilities"]["image_input"] is False
    assert b["capabilities"]["text_chat"] is True
    assert b["capabilities"]["video_input"] is False
    assert b["capabilities"]["audio_input"] is False


def test_capabilities_endpoint_no_secret_or_path_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://192.168.1.50:8642/internal/hermes")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-key")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", r"C:\secret\svc.json")
    res = client.get("/api/chat/capabilities", params={"model_id": "x/y"})
    assert res.status_code == 200
    raw = json.dumps(res.json())
    assert "192.168" not in raw
    assert "8642" not in raw
    assert "sk-or-v1" not in raw
    assert "GOOGLE_APPLICATION" not in raw
    assert "gs://" not in raw
    assert r"svc.json" not in raw


def test_mock_gateway_disables_image_even_if_id_matches_vision_pattern() -> None:
    """Registry stays conservative in mock/dev gateway mode."""
    res = client.get("/api/chat/capabilities", params={"model_id": "openai/gpt-4o"})
    assert res.status_code == 200
    # Default test env may not set HERMES_GATEWAY_MODE; build_payload directly:
    p = build_chat_capabilities_payload(model_id="openai/gpt-4o", gateway_mode="mock")
    assert p["capabilities"]["image_input"] is False
