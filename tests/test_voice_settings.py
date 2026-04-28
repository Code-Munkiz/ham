"""HAM GET/PATCH /api/workspace/voice-settings."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.voice_settings_models import capabilities_payload


class _MemVoiceStore:
    def __init__(self) -> None:
        self.data: dict[str, dict] = {}

    def get_raw(self, scope_key: str):
        return self.data.get(scope_key)

    def put_raw(self, scope_key: str, data: dict) -> None:
        self.data[scope_key] = data


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    mem = _MemVoiceStore()

    import src.api.workspace_voice_settings as wvs

    monkeypatch.setattr(wvs, "_STORE", mem)
    return TestClient(app)


def test_get_returns_defaults_and_capabilities(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")

    r = client.get("/api/workspace/voice-settings")
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "ham_voice_settings"
    assert j["settings"]["tts"]["provider"] == "edge"
    assert j["settings"]["tts"]["voice"] == "en-US-JennyNeural"
    assert j["settings"]["stt"]["provider"] == "openai"
    assert j["capabilities"]["tts"]["available"] is True
    assert j["capabilities"]["stt"]["available"] is True
    assert any(v["id"] == "en-US-JennyNeural" for v in j["capabilities"]["tts"]["voices"])


def test_get_stt_unavailable_when_placeholder_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "PLACEHOLDER")
    r = client.get("/api/workspace/voice-settings")
    assert r.status_code == 200
    j = r.json()
    assert j["capabilities"]["stt"]["available"] is False
    assert j["capabilities"]["stt"]["reason"] == "not_configured"
    assert j["capabilities"]["stt"]["providers"][0]["reason"] == "not_configured"


def test_patch_saves_and_round_trips(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")

    r = client.patch(
        "/api/workspace/voice-settings",
        json={"tts": {"enabled": False, "voice": "de-DE-KatjaNeural"}},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["settings"]["tts"]["enabled"] is False
    assert j["settings"]["tts"]["voice"] == "de-DE-KatjaNeural"

    r2 = client.get("/api/workspace/voice-settings")
    assert r2.json()["settings"]["tts"]["enabled"] is False


def test_patch_rejects_bad_tts_provider(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    r = client.patch("/api/workspace/voice-settings", json={"tts": {"provider": "elevenlabs"}})
    assert r.status_code == 422


def test_patch_rejects_bad_stt_provider(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    r = client.patch("/api/workspace/voice-settings", json={"stt": {"provider": "local_whisper"}})
    assert r.status_code == 422


def test_patch_rejects_bad_voice(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "1")
    r = client.patch("/api/workspace/voice-settings", json={"tts": {"voice": "bogus-voice"}})
    assert r.status_code == 400


def test_patch_rejects_unknown_top_level_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    r = client.patch("/api/workspace/voice-settings", json={"tts": {"enabled": True}, "evil": 1})
    assert r.status_code == 422


def test_voice_settings_routes_in_openapi(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/api/workspace/voice-settings" in r.json().get("paths", {})


def test_capabilities_tts_off_when_ham_tts_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TTS_ENABLED", "0")
    caps = capabilities_payload()
    assert caps["tts"]["available"] is False
    assert caps["tts"]["providers"][0]["available"] is False
