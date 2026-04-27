"""TTS API: health probe and /generate (mocked — no real Edge network in CI).

Uses the real FastAPI `app` from `src.api.server` (all routers as deployed), not an isolated
router import — this is the app-level mount test for /api/tts/*.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_tts_health_ok_when_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    r = client.get("/api/tts/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["available"] is True
    assert data.get("generate_path") == "/api/tts/generate"
    assert data.get("engine") == "edge"


def test_tts_health_unavailable_when_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "0")
    r = client.get("/api/tts/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["available"] is False
    assert data.get("reason") == "disabled"


def test_tts_generate_rejects_empty_body(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    r = client.post("/api/tts/generate", json={"text": "   "})
    assert r.status_code == 400


def test_tts_generate_disabled_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "0")
    r = client.post("/api/tts/generate", json={"text": "hi"})
    assert r.status_code == 503


def test_tts_routes_in_openapi_server_app(client: TestClient) -> None:
    """App-level: mounted routes appear on the same app instance browsers hit."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec.get("paths", {})
    assert "/api/tts/health" in paths
    assert "/api/tts/generate" in paths


def test_tts_generate_rejects_text_over_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    monkeypatch.setenv("HAM_TTS_MAX_CHARS", "5")
    r = client.post("/api/tts/generate", json={"text": "123456"})
    assert r.status_code == 400
    det = r.json().get("detail", "")
    text = det if isinstance(det, str) else str(det)
    assert "limit" in text.lower()


def test_tts_generate_rejects_unknown_voice(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")

    r = client.post("/api/tts/generate", json={"text": "hi", "voice": "not-a-valid-neural-voice"})
    assert r.status_code == 400


def test_tts_generate_returns_mp3_bytes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")

    async def fake_generate(self, text: str, voice=None, speed: float = 1.0, pitch: float = 0.0) -> bytes:
        return b"fake-mp3-payload"

    import src.api.tts_endpoint as te

    monkeypatch.setattr(te.TextToSpeechEngine, "generate", fake_generate)

    r = client.post("/api/tts/generate", json={"text": "Hello from test"})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert r.content == b"fake-mp3-payload"
