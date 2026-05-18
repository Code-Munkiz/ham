"""VAL-SAFETY-011 — GET /api/models response never leaks the conversational env name or value."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


_CONV_SENTINEL_VALUE = "conv-sentinel-slug:free"
_CONV_ENV_NAME = "HAM_CHAT_CONVERSATIONAL_MODEL"


def _row_ids(payload: dict) -> list[str]:
    items = payload.get("items") or []
    return [str(it.get("id")) for it in items if it.get("id") is not None]


def test_models_catalog_does_not_leak_conversational_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/models with the env set must not surface the env name or the env value."""
    monkeypatch.delenv(_CONV_ENV_NAME, raising=False)
    baseline = client.get("/api/models")
    assert baseline.status_code == 200, baseline.text
    baseline_payload = baseline.json()
    baseline_ids = _row_ids(baseline_payload)

    monkeypatch.setenv(_CONV_ENV_NAME, _CONV_SENTINEL_VALUE)
    env_set = client.get("/api/models")
    assert env_set.status_code == 200, env_set.text
    env_payload = env_set.json()

    body_text = env_set.text
    assert _CONV_ENV_NAME not in body_text, (
        f"GET /api/models leaked the env var name in the body: {_CONV_ENV_NAME}"
    )
    assert _CONV_SENTINEL_VALUE not in body_text, (
        f"GET /api/models leaked the env value: {_CONV_SENTINEL_VALUE}"
    )
    serialized = json.dumps(env_payload)
    assert _CONV_ENV_NAME not in serialized
    assert _CONV_SENTINEL_VALUE not in serialized

    env_set_ids = _row_ids(env_payload)
    assert env_set_ids == baseline_ids, (
        "row id set must be identical between env-unset and env-set baselines"
    )
