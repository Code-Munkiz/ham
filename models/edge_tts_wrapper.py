"""
edge_tts_wrapper.py

Microsoft Edge text-to-speech via the maintained ``edge-tts`` package (WebSocket + current
``Sec-MS-GEC``/DRM flow). The previous HTTP POST to ``speech.platform.bing.com/.../v1`` is stale
and returns 404; do not reintroduce it.

No local models; Cloud Run / Linux compatible. Requires network egress to Microsoft.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import edge_tts

logger = logging.getLogger(__name__)


class TextToSpeechEngine:
    """
    Edge TTS — delegates to ``edge_tts.Communicate`` (audio-24khz-48kbitrate-mono-mp3 / MPEG).
    """

    VOICES = {
        "en-US": "en-US-JennyNeural",
        "en-GB": "en-GB-SoniaNeural",
        "es-ES": "es-ES-ElviraNeural",
        "fr-FR": "fr-FR-DeniseNeural",
        "de-DE": "de-DE-KatjaNeural",
    }

    def __init__(self, voice: str = "en-US-JennyNeural"):
        self.voice = voice

    @staticmethod
    def _rate_string(speed: float) -> str:
        """Map ``speed`` (0.5–2.0 style) to edge-tts ``rate`` like ``+0%`` or ``-25%``."""
        try:
            pct = int(round((float(speed) - 1.0) * 100))
        except (TypeError, ValueError):
            pct = 0
        pct = max(-100, min(100, pct))
        return f"{pct:+d}%"

    @staticmethod
    def _pitch_string(pitch: float) -> str:
        """Map ``pitch`` to edge-tts ``pitch`` like ``+0Hz`` (service expects Hz steps)."""
        try:
            hz = float(pitch)
        except (TypeError, ValueError):
            hz = 0.0
        return f"{hz:+.0f}Hz"

    async def generate(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> bytes:
        use_voice = voice or self.voice
        rate = self._rate_string(speed)
        pitch_s = self._pitch_string(pitch)
        comm: edge_tts.Communicate = edge_tts.Communicate(
            text,
            use_voice,
            rate=rate,
            volume="+0%",
            pitch=pitch_s,
        )
        out = bytearray()
        try:
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    out.extend(chunk["data"])
        except Exception as e:
            logger.exception("edge-tts Communicate failed")
            raise RuntimeError("TTS generation failed") from e
        if not out:
            raise RuntimeError("TTS generation failed: no audio data")
        return bytes(out)

    def generate_base64(self, text: str, voice: Optional[str] = None) -> str:
        """Synchronous base64: prefer ``async`` ``generate`` in server code; this uses asyncio.run."""
        import asyncio

        audio_bytes = asyncio.run(self.generate(text, voice))
        return base64.b64encode(audio_bytes).decode("utf-8")

    def list_voices(self) -> list[str]:
        return list(self.VOICES.keys())
