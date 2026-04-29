"""
audio_upload.py

Audio upload endpoint for voice messages.
Safely accepts audio blobs and optionally triggers external transcription.

Safe for Cloud Run:
- Uses native FastAPI upload handling
- Optional external Whisper API integration
- No local Whisper model required
"""

import os
import uuid
import tempfile
from pathlib import Path
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from models.edge_tts_wrapper import TextToSpeechEngine


AUDIO_UPLOAD_DIR = Path(os.getenv("AUDIO_UPLOAD_DIR", "/tmp/audio_uploads"))
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB max upload


def ensure_upload_dir():
    """Ensure audio upload directory exists."""
    AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def upload_audio(file: UploadFile = File(...)) -> dict:
    """
    Upload audio file and return metadata.
    
    Args:
        file: Audio file uploaded via FormData
    
    Returns:
        dict with:
            - id: Unique audio ID
            - filename: Original filename
            - size: File size in bytes
            - url: Temporary download URL
            - transcription_url: Optional (if external provider configured)
            
    Raises:
        HTTPException if file too large or invalid type
    """
    ensure_upload_dir()
    
    # Validate file
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only audio files are accepted."
        )
    
    # Validate size
    file_size = 0
    chunks = []
    async for chunk in file.iterate_chunked(1024 * 1024):
        file_size += len(chunk)
        if file_size > MAX_AUDIO_SIZE:
            chunks.append(chunk)
            continue
        chunks.append(chunk)
    
    if file_size > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size: {MAX_AUDIO_SIZE // (1024 * 1024)}MB"
        )
    
    # Save file with unique ID
    audio_id = str(uuid.uuid4())[:8]
    filename = f"{audio_id}_{file.filename}"
    file_path = AUDIO_UPLOAD_DIR / filename
    
    # Write file
    with open(file_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
    
    # Generate URL (relative path for API)
    file_url = f"/api/audio/{audio_id}"
    
    return {
        "id": audio_id,
        "filename": filename,
        "size": file_size,
        "url": file_url,
        "mime_type": file.content_type,
    }


async def get_audio_file(audio_id: str) -> tuple:
    """
    Retrieve audio file by ID.
    
    Args:
        audio_id: Unique audio identifier
    
    Returns:
        (file_path, mime_type) tuple
    """
    ensure_upload_dir()
    
    file_path = AUDIO_UPLOAD_DIR / f"{audio_id}_"
    if not file_path.exists():
        raise ValueError(f"Audio file not found: {audio_id}")
    
    # Return first matching file
    return (file_path, "audio/webm")


async def delete_audio(audio_id: str) -> bool:
    """
    Delete audio file by ID.
    
    Args:
        audio_id: Unique audio identifier
    
    Returns:
        True if deleted successfully
    """
    ensure_upload_dir()
    
    file_path = AUDIO_UPLOAD_DIR / f"{audio_id}_"
    if file_path.exists():
        file_path.unlink()
        return True
    return False


# Integration helper for external transcription providers
def transcribe_audio_async(
    audio_path: Path,
    provider: str = "assemblyai",
    api_key: str = None
) -> str:
    """
    Transcribe audio using external provider.
    
    Args:
        audio_path: Path to audio file
        provider: Transcription provider
            Options: assemblyai, azure_ai_voices, deepgram, rev_ai
        api_key: Provider API key (from environment)
    
    Returns:
        Transcribed text string
    """
    # This is an integration stub - plug in your provider:
    # - AssemblyAI: https://www.assemblyai.com/
    # - Azure AI Speech: https://learn.microsoft.com/azure/ai-services/speech-service/
    # - Deepgram: https://deepgram.com/
    # - RevAI: https://www.rev.ai/
    
    # Example integration for AssemblyAI:
    if provider == "assemblyai":
        import requests
        
        # Upload audio to AssemblyAI
        upload_url = "https://api.assemblyai.com/v2/upload"
        with open(audio_path, "rb") as f:
            response = requests.post(upload_url, 
                                   headers={"authorization": api_key},
                                   data=f.read())
        
        upload_id = response.json()["upload_id"]
        
        # Transcribe
        transcript_url = "https://api.assemblyai.com/v2/transcript"
        response = requests.post(
            transcript_url,
            headers={
                "authorization": api_key,
                "content-type": "application/json"
            },
            json={"audio_url": upload_url}
        )
        
        transcript_id = response.json()["id"]
        
        # Get result (polling in real implementation)
        result = requests.get(
            f"{transcript_url}/{transcript_id}",
            headers={"authorization": api_key}
        )
        
        return result.json()["text"]
    
    # Add more providers here as needed
    raise NotImplementedError(f"Provider '{provider}' not implemented yet")
