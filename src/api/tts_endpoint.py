"""
tts_endpoint.py

Text-to-speech endpoint for Ham API.
Uses Edge TTS (pure Python, Cloud Run compatible).

Auth: no Clerk/operator gate on /api/tts/* (same posture as e.g. public health-style probes).
Protect at the network edge (API allowlists, rate limits) if needed.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from models.edge_tts_wrapper import TextToSpeechEngine

router = APIRouter(prefix="/api/tts", tags=["tts"])


def _tts_enabled() -> bool:
    raw = (os.environ.get("HAM_TTS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _tts_max_chars() -> int:
    raw = (os.environ.get("HAM_TTS_MAX_CHARS") or "2000").strip()
    try:
        n = int(raw)
    except ValueError:
        return 2000
    return max(1, min(n, 50_000))  # hard ceiling to avoid absurd env values


def _allowed_neural_voices() -> frozenset[str]:
    """Only Microsoft Edge neural voice IDs we ship in `TextToSpeechEngine` (no arbitrary SSML `name=`)."""
    return frozenset(TextToSpeechEngine.VOICES.values())


def _normalize_voice(v: Optional[str]) -> str:
    chosen = (v or "en-US-JennyNeural").strip()
    if chosen not in _allowed_neural_voices():
        raise HTTPException(
            status_code=400,
            detail="Unsupported voice (use a known Edge neural voice id)",
        )
    return chosen


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US-JennyNeural"


@router.get("/health")
def tts_health() -> dict[str, Any]:
    """
    Cheap probe: whether TTS is exposed and enabled on this process.
    Does not call Microsoft/Edge (no network) — use before showing “TTS available” in UI.
    """
    if not _tts_enabled():
        return {
            "ok": True,
            "available": False,
            "reason": "disabled",
        }
    return {
        "ok": True,
        "available": True,
        "generate_path": "/api/tts/generate",
        "engine": "edge",
    }


@router.post("/generate")
async def generate_tts(request: TTSRequest) -> Response:
    """
    Generate speech audio from text.

    Returns:
        MP3 body (`audio/mpeg`). Clients should use `response.blob()` in the browser.
    """
    if not _tts_enabled():
        raise HTTPException(status_code=503, detail="TTS is disabled (HAM_TTS_ENABLED=0)")

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    text = request.text.strip()
    cap = _tts_max_chars()
    if len(text) > cap:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds limit ({cap} characters; set HAM_TTS_MAX_CHARS)",
        )

    voice = _normalize_voice(request.voice)

    try:
        tts = TextToSpeechEngine(voice=voice)
        audio_bytes = await tts.generate(text, voice)

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=tts.mp3"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")
