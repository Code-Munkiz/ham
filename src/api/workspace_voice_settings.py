"""HAM-native persisted voice settings (TTS/STT preferences), scoped by Clerk user when present."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham.voice_settings_models import (
    SavedVoiceSettings,
    VoiceSettingsPatchBody,
    capabilities_payload,
    default_voice_settings,
    merge_voice_settings,
)
from src.persistence.voice_settings_store import build_voice_settings_store

router = APIRouter(prefix="/api/workspace", tags=["workspace-voice"])

_STORE = build_voice_settings_store()


def _scope_key(actor: HamActor | None) -> str:
    uid = (actor.user_id if actor is not None else None) or ""
    if uid.strip():
        return f"user:{uid.strip()}"
    return "default"


def _load_saved(scope_key: str) -> dict[str, Any]:
    raw = _STORE.get_raw(scope_key)
    if not raw:
        return {}
    # Allow only our keys at top level
    out: dict[str, Any] = {}
    if isinstance(raw.get("tts"), dict):
        out["tts"] = dict(raw["tts"])
    if isinstance(raw.get("stt"), dict):
        out["stt"] = dict(raw["stt"])
    return out


@router.get("/voice-settings")
def get_voice_settings(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    scope = _scope_key(_actor)
    merged = merge_voice_settings(_load_saved(scope), VoiceSettingsPatchBody())
    caps = capabilities_payload(_actor)
    return {
        "kind": "ham_voice_settings",
        "settings": merged.model_dump(),
        "capabilities": caps,
    }


@router.patch("/voice-settings")
def patch_voice_settings(
    body: VoiceSettingsPatchBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    scope = _scope_key(_actor)
    try:
        merged = merge_voice_settings(_load_saved(scope), body)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=jsonable_encoder(e.errors())) from e

    blob = merged.model_dump()
    try:
        _STORE.put_raw(scope, blob)
    except Exception as e:
        raise HTTPException(status_code=503, detail="Voice settings could not be saved") from e

    caps = capabilities_payload(_actor)
    return {
        "kind": "ham_voice_settings",
        "settings": SavedVoiceSettings.model_validate(blob).model_dump(),
        "capabilities": caps,
    }

