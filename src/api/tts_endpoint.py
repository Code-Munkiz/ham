"""
tts_endpoint.py

Text-to-speech endpoint for Ham API.
Uses Edge TTS (pure Python, Cloud Run compatible).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from models.edge_tts_wrapper import TextToSpeechEngine


router = APIRouter(prefix="/api/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US-JennyNeural"


@router.post("/generate")
async def generate_tts(request: TTSRequest):
    """
    Generate speech audio from text.
    
    Args:
        text: Text to convert to speech
        voice: Microsoft neural voice ID
    
    Returns:
        Audio file in MP3 format
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        tts = TextToSpeechEngine(voice=request.voice)
        audio_bytes = await tts.generate(request.text, request.voice)
        
        return {
            "audio": audio_bytes,
            "content_type": "audio/mpeg",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")
