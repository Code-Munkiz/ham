"""Stream/REST honest-failure surfacing for net-new builder scaffold turns."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.builder_error_codes import STEP_MODEL_UNAVAILABLE
from src.ham.builder_llm_scaffold import LLMScaffoldError
from src.ham.clerk_auth import HamActor
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)

client = TestClient(app)


def _byo_actor(uid: str = "user_byo") -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _net_new_fail_meta() -> dict[str, Any]:
    return {
        "builder_intent": "build_or_create",
        "llm_scaffold_failed": True,
        "llm_scaffold_error_code": STEP_MODEL_UNAVAILABLE,
        "builder_action_decision": {
            "kind": "mutate",
            "confidence": "high",
            "destructive": False,
            "reason": "explicit_mutation",
        },
    }


def test_gattica_stream_returns_honest_failure_not_502(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_prefix = (
        "I couldn't build this yet because the OpenRouter model call failed. "
        "Check Connected Tools (OpenRouter key) and your selected chat model, then try again.\n\n"
    )
    monkeypatch.setattr(
        "src.api.chat.run_builder_happy_path_hook",
        lambda **_kw: (fail_prefix, _net_new_fail_meta()),
    )

    with patch("src.ham.builder_planner.produce_plan") as mock_produce:
        res = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "ham build me a game like gattica"}],
                "workspace_id": "ws_gattica",
                "project_id": "proj_gattica",
            },
        )

    assert res.status_code == 200, res.text
    mock_produce.assert_not_called()
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    assistant = done["messages"][-1]["content"]
    assert "couldn't build" in assistant.lower()
    assert "apply that edit" not in assistant.lower()
    assert "interrupted before" not in assistant.lower()
    assert done.get("builder", {}).get("llm_scaffold_failed") is True


def test_spaceship_stream_model_access_required_rest(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = (
        "I cannot build this without model access. "
        "Connect OpenRouter in Settings (Connected Tools) and try again.\n\n"
    )
    meta = {
        "builder_intent": "build_or_create",
        "model_access_required": True,
        "builder_action_decision": {
            "kind": "mutate",
            "confidence": "high",
            "destructive": False,
            "reason": "explicit_mutation",
        },
    }
    monkeypatch.setattr(
        "src.api.chat.run_builder_happy_path_hook",
        lambda **_kw: (prefix, meta),
    )

    res = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "build a game where i can shoot things in a spaceship"}],
            "workspace_id": "ws_ship",
            "project_id": "proj_ship",
        },
    )

    assert res.status_code == 200, res.json()
    data = res.json()
    assistant = data["messages"][-1]["content"]
    assert "cannot build this without model access" in assistant.lower()
    assert data.get("builder", {}).get("model_access_required") is True


def test_llm_scaffold_failure_surfaces_model_slug_in_meta_and_message(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.builder_chat_hooks import run_builder_happy_path_hook

    resolved_model = "openrouter/anthropic/claude-3.5-haiku"
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_ENABLE_INTERNAL_SCAFFOLD_QUICK_PREVIEW", "1")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    actor = _byo_actor()
    try:
        with patch(
            "src.llm_client.resolve_openrouter_api_key_for_actor",
            return_value="sk-or-v1-connectedtoolskey000000000000",
        ), patch(
            "src.ham.builder_llm_scaffold._get_scaffold_model",
            return_value=resolved_model,
        ), patch(
            "src.ham.builder_llm_scaffold.generate_scaffold",
            side_effect=LLMScaffoldError("model call failed", error_code=STEP_MODEL_UNAVAILABLE),
        ):
            prefix, meta = run_builder_happy_path_hook(
                workspace_id="ws_model_fail",
                project_id="proj_model_fail",
                session_id="sess_model_fail",
                # The legacy scaffold path is now dev-flagged; this test opts in
                # to keep the old scaffold failure copy covered.
                last_user_plain="build me a game like asteroids as a quick preview",
                ham_actor=actor,
            )
        assert meta.get("llm_scaffold_failed") is True
        assert meta.get("llm_scaffold_failed_model") == resolved_model
        assert "anthropic/claude-3.5-haiku" in prefix
        assert "scaffold model" in prefix.lower()
        assert "connected tools" in prefix.lower()
    finally:
        set_builder_source_store_for_tests(None)
