"""Unit tests for ``edge_tts``-backed wrapper (mocks, no real Microsoft network)."""
from __future__ import annotations

import pytest

from models.edge_tts_wrapper import TextToSpeechEngine


class _FakeComm:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"\x00\x01\x02"}


def test_text_to_speech_engine_collects_audio_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("models.edge_tts_wrapper.edge_tts.Communicate", _FakeComm)
    import asyncio

    eng = TextToSpeechEngine("en-US-JennyNeural")
    out = asyncio.run(eng.generate("Hello"))
    assert out == b"\x00\x01\x02"


def test_rate_and_pitch_strings() -> None:
    assert TextToSpeechEngine._rate_string(1.0) == "+0%"
    assert TextToSpeechEngine._rate_string(0.5) == "-50%"
    assert TextToSpeechEngine._pitch_string(0) == "+0Hz"
    assert TextToSpeechEngine._pitch_string(-3) == "-3Hz"


def test_default_voice_in_allowlist() -> None:
    assert "en-US-JennyNeural" in TextToSpeechEngine.VOICES.values()
