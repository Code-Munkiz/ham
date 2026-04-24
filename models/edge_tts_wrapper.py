"""
edge_tts_wrapper.py

Lightweight Edge TTS wrapper for text-to-speech.
Uses Microsoft Edge TTS (cloud-based, no local dependencies).

Safe for Cloud Run and Vercel deployment.

Usage:
    from models.edge_tts_wrapper import TextToSpeechEngine
    
    tts = TextToSpeechEngine()
    audio_bytes = tts.generate("Hello world", voice="en-US-JennyNeural")
"""

import base64
import httpx
from typing import Optional

class TextToSpeechEngine:
    """
    Edge TTS text-to-speech integration.
    
    Cloud-based TTS via Microsoft Edge TTS API.
    No local models, no heavy dependencies.
    Fits within Cloud Run image size limits.
    """
    
    VOICES = {
        "en-US": "en-US-JennyNeural",
        "en-GB": "en-GB-SoniaNeural",
        "es-ES": "es-ES-ElviraNeural",
        "fr-FR": "fr-FR-DeniseNeural",
        "de-DE": "de-DE-KatjaNeural",
    }
    
    def __init__(self, voice: str = "en-US-JennyNeural"):
        """
        Initialize TTS engine.
        
        Args:
            voice: Microsoft Edge neural voice ID
                   Default: en-US-JennyNeural (female, warm)
        """
        self.voice = voice
    
    async def generate(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        pitch: float = 0.0
    ) -> bytes:
        """
        Generate speech audio from text.
        
        Args:
            text: Text to convert to speech
            voice: Override default voice
            speed: Speech rate (0.5-2.0, default 1.0)
            pitch: Speech pitch (-20.0-20.0, default 0.0)
        
        Returns:
            Audio bytes in MP3 format
        """
        voice = voice or self.voice
        
        async with httpx.AsyncClient() as client:
            # Edge TTS API endpoint
            url = "https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {voice}",
                "Content-Type": "application/ssml+xml",
                "X-Timestamp": self._get_timestamp(),
                "user-agent": "Mozilla/5.0",
            }
            
            # SSML payload
            ssml = f"""
            <speak version="1.0" xml:lang="en-US">
                <voice xml:lang="en-US" name="{voice}">
                    <prosody rate="{speed}x" pitch="{pitch}Hz">
                        {text}
                    </prosody>
                </voice>
            </speak>
            """
            
            response = await client.post(
                url,
                headers=headers,
                content=ssml.encode('utf-8'),
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"TTS generation failed: {response.status_code} - {response.text}")
            
            return response.content
    
    def generate_base64(self, text: str, voice: Optional[str] = None) -> str:
        """
        Generate speech and return as Base64 string.
        
        Useful for embedding directly in HTML/audio elements.
        
        Args:
            text: Text to convert to speech
            voice: Override default voice
        
        Returns:
            Base64-encoded MP3 audio string
        """
        audio_bytes = self.generate(text, voice)
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    def _get_timestamp(self) -> str:
        """Generate TTS API timestamp."""
        import time
        return str(int(time.time() * 1000))
    
    def list_voices(self) -> list:
        """List available neural voices."""
        return list(self.VOICES.keys())
