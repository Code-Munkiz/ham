"""HAM-native voice settings schema (TTS/STT) — providers are allowlisted only."""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.edge_tts_wrapper import TextToSpeechEngine
from src.ham.transcription_config import transcription_runtime_configured


def default_voice_settings() -> dict[str, Any]:
    return {
        "tts": {"enabled": True, "provider": "edge", "voice": "en-US-JennyNeural"},
        "stt": {"enabled": True, "provider": "openai"},
    }


ALLOWED_TTS_PROVIDERS: frozenset[str] = frozenset({"edge"})
ALLOWED_STT_PROVIDERS: frozenset[str] = frozenset({"openai"})
ALLOWED_EDGE_VOICES: frozenset[str] = frozenset(TextToSpeechEngine.VOICES.values())

# Short labels for GET capabilities (aligned with Edge neural display names).
VOICE_DISPLAY_LABELS: dict[str, str] = {
    "en-US-JennyNeural": "Jenny",
    "en-GB-SoniaNeural": "Sonia",
    "es-ES-ElviraNeural": "Elvira",
    "fr-FR-DeniseNeural": "Denise",
    "de-DE-KatjaNeural": "Katja",
}


def _tts_env_available() -> bool:
    raw = (os.environ.get("HAM_TTS_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


class TtsSettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: Literal["edge"] = "edge"
    voice: str = "en-US-JennyNeural"


class SttSettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: Literal["openai"] = "openai"


class SavedVoiceSettings(BaseModel):
    """Normalized persisted shape."""

    model_config = ConfigDict(extra="forbid")

    tts: TtsSettingsModel = Field(default_factory=lambda: TtsSettingsModel())
    stt: SttSettingsModel = Field(default_factory=lambda: SttSettingsModel())

    @model_validator(mode="after")
    def _validate_voices(self) -> SavedVoiceSettings:
        if self.tts.voice not in ALLOWED_EDGE_VOICES:
            raise ValueError(f"Unsupported TTS voice: {self.tts.voice!r}")
        return self


class TtsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    provider: Literal["edge"] | None = None
    voice: str | None = None


class SttPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    provider: Literal["openai"] | None = None


class VoiceSettingsPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tts: TtsPatch | None = None
    stt: SttPatch | None = None


def merge_voice_settings(current: dict[str, Any], patch: VoiceSettingsPatchBody) -> SavedVoiceSettings:
    """Deep-merge patch into current dict-of-dicts, then validate."""
    ddef = default_voice_settings()
    td = {**ddef["tts"], **(current.get("tts") if isinstance(current.get("tts"), dict) else {})}
    sd = {**ddef["stt"], **(current.get("stt") if isinstance(current.get("stt"), dict) else {})}
    if patch.tts is not None:
        pt = patch.tts.model_dump(exclude_unset=True)
        for k, v in pt.items():
            if v is not None:
                td[k] = v
    if patch.stt is not None:
        ps = patch.stt.model_dump(exclude_unset=True)
        for k, v in ps.items():
            if v is not None:
                sd[k] = v
    merged = {"tts": td, "stt": sd}
    return SavedVoiceSettings.model_validate(merged)


def capabilities_payload() -> dict[str, Any]:
    tts_ok = _tts_env_available()
    stt_ok, stt_reason = transcription_runtime_configured()
    voices = [
        {"id": vid, "label": VOICE_DISPLAY_LABELS.get(vid, vid)}
        for vid in sorted(ALLOWED_EDGE_VOICES)
    ]
    return {
        "tts": {
            "available": tts_ok,
            "providers": [
                {
                    "id": "edge",
                    "label": "Microsoft Edge (server)",
                    "available": tts_ok,
                },
            ],
            "voices": voices,
        },
        "stt": {
            "available": stt_ok,
            "reason": stt_reason,
            "providers": [
                {
                    "id": "openai",
                    "label": "OpenAI transcription",
                    "available": stt_ok,
                    "reason": stt_reason,
                },
            ],
        },
    }
