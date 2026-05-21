"""Builder chat grounding: deterministic status replies and anti-hallucination short-circuit."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.builder_chat_hooks import run_builder_happy_path_hook
from src.ham.clerk_auth import HamActor
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStore,
    CloudRuntimeJob,
    set_builder_runtime_job_store_for_tests,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    SourceSnapshot,
    set_builder_source_store_for_tests,
)

client = TestClient(app)

_FORBIDDEN_SUBSTRINGS = (
    "on this machine",
    "already a",
    "open it in your browser",
    "space shooter",
    "game files",
    "your computer",
)


def _byo_actor(uid: str = "user_ground") -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _assert_no_forbidden(text: str) -> None:
    low = text.lower()
    for bad in _FORBIDDEN_SUBSTRINGS:
        assert bad not in low, f"forbidden substring {bad!r} in reply: {text!r}"


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


@pytest.fixture
def builder_stores(tmp_path):
    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    job_store = BuilderRuntimeJobStore(store_path=tmp_path / "builder_runtime_jobs.json")
    set_builder_source_store_for_tests(source_store)
    set_builder_runtime_job_store_for_tests(job_store)
    try:
        yield source_store, job_store
    finally:
        set_builder_source_store_for_tests(None)
        set_builder_runtime_job_store_for_tests(None)


def test_hook_empty_workspace_grounded_preview_complaint(builder_stores) -> None:
    prefix, meta = run_builder_happy_path_hook(
        workspace_id="ws_ground",
        project_id="proj_ground",
        session_id="sess_ground",
        last_user_plain="i don't see anything in the preview screen",
        ham_actor=_byo_actor(),
    )
    assert meta.get("builder_grounded_status") is True
    assert prefix is not None
    text = str(prefix)
    assert "no committed project source" in text.lower() or "isn't any committed" in text.lower()
    assert "build" in text.lower()
    _assert_no_forbidden(text)


def test_hook_source_exists_preview_failed(builder_stores) -> None:
    source_store, job_store = builder_stores
    ws, pid = "ws_ground", "proj_ground"
    snap = SourceSnapshot(
        workspace_id=ws,
        project_id=pid,
        project_source_id="psrc_1",
        status="materialized",
    )
    source_store.upsert_source_snapshot(snap)
    source_store.upsert_project_source(
        ProjectSource(
            id="psrc_1",
            workspace_id=ws,
            project_id=pid,
            active_snapshot_id=snap.id,
            display_name="demo",
        )
    )
    job_store.upsert_cloud_runtime_job(
        CloudRuntimeJob(
            workspace_id=ws,
            project_id=pid,
            source_snapshot_id=snap.id,
            status="failed",
            phase="failed",
        )
    )

    prefix, meta = run_builder_happy_path_hook(
        workspace_id=ws,
        project_id=pid,
        session_id="sess_ground",
        last_user_plain="preview is blank",
        ham_actor=_byo_actor(),
    )
    assert meta.get("builder_grounded_status") is True
    text = str(prefix or "")
    assert "source exists" in text.lower()
    assert "preview" in text.lower() and ("fail" in text.lower() or "did not succeed" in text.lower())
    assert "retry" in text.lower() or "rebuild" in text.lower()
    _assert_no_forbidden(text)


def test_post_chat_short_circuits_llm_for_grounded_status(
    mock_mode: None,
    builder_stores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_llm(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("complete_chat_turn must not run for grounded status replies")

    monkeypatch.setattr("src.api.chat.complete_chat_turn", _no_llm)

    res = client.post(
        "/api/chat",
        json={
            "workspace_id": "ws_ground",
            "project_id": "proj_ground",
            "messages": [{"role": "user", "content": "i don't see anything in the preview screen"}],
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    visible = data["messages"][-1]["content"]
    assert data.get("builder", {}).get("builder_grounded_status") is True
    assert "build" in visible.lower()
    _assert_no_forbidden(visible)


def test_stream_short_circuits_llm_for_grounded_status(
    mock_mode: None,
    builder_stores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_stream(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("stream_chat_turn must not run for grounded status replies")

    monkeypatch.setattr("src.api.chat.stream_chat_turn", _no_stream)

    res = client.post(
        "/api/chat/stream",
        json={
            "workspace_id": "ws_ground",
            "project_id": "proj_ground",
            "messages": [{"role": "user", "content": "nothing shows in the preview"}],
        },
    )
    assert res.status_code == 200, res.text
    events = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    done = [e for e in events if e.get("type") == "done"][0]
    visible = done["messages"][-1]["content"]
    assert done.get("builder", {}).get("builder_grounded_status") is True
    _assert_no_forbidden(visible)


def test_scaffold_not_called_for_grounded_status(builder_stores) -> None:
    def _raise_scaffold(**_kw: object) -> object:
        raise AssertionError("scaffold must not run for grounded status")

    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_scaffold,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_ground",
            project_id="proj_ground",
            session_id="sess_ground",
            last_user_plain="preview broken",
            ham_actor=_byo_actor(),
        )
    assert meta.get("builder_grounded_status") is True
    assert prefix
