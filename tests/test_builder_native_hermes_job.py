"""HAM Native Builder v2 — async job boundary + functional executor tests.

Covers the start function (creates a job and returns immediately without inline
Hermes artifact generation), the functional executor (materializes a source
snapshot on success, marks a safe error on failure), status persistence /
pollability, the non-blocking thread dispatch, that the old scaffold never runs,
and the no-internals guarantee.
"""

import json
import threading
import time

from src.ham.builder_native_hermes import (
    NATIVE_BUILD_JOB_ORIGIN,
    NATIVE_BUILD_PHASE_FAILED,
    NATIVE_BUILD_PHASE_QUEUED,
    NATIVE_BUILD_PHASE_SUCCEEDED,
    execute_native_build_job,
    ham_native_builder_user_message,
    start_native_build_job,
)
from src.ham.native_build_worker_enqueue import set_native_build_enqueue_for_tests
from src.integrations.nous_gateway_client import GatewayCallError
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)

_FORBIDDEN_TOKENS = (
    "registry_v2",
    "proposal_digest",
    "base_revision",
    "hermes_native_build",
    "inline_files",
    "hermes-builder",
    "hermes_gateway",
    "openrouter",
)

_VALID_BUNDLE = {
    "status": "success",
    "summary": "Built.",
    "files": {
        "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
        "src/main.tsx": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom/client';\n"
            "import App from './App';\n"
            "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
        ),
        "src/styles.css": "body { margin: 0; }\n",
    },
    "checks": ["renders"],
}


def _valid_turn(_messages) -> str:
    return json.dumps(_VALID_BUNDLE)


def _ready_env(tmp_path, monkeypatch) -> None:
    """Gateway + builder model configured; inline dispatch for deterministic tests."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-fast")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    monkeypatch.setenv("HAM_NATIVE_BUILD_DISPATCH", "inline")


def _durable_env(tmp_path, monkeypatch) -> None:
    """Gateway + builder model configured; default (durable) dispatch — not inline."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-fast")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    monkeypatch.delenv("HAM_NATIVE_BUILD_DISPATCH", raising=False)


class _RecordingEnqueue:
    def __init__(self) -> None:
        self.calls: list = []

    def enqueue(self, envelope) -> None:
        self.calls.append(envelope)


def test_durable_dispatch_persists_context_and_enqueues_without_inline_build(
    tmp_path, monkeypatch
) -> None:
    _durable_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    recorder = _RecordingEnqueue()
    set_native_build_enqueue_for_tests(recorder)
    try:
        result = start_native_build_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
        )
    finally:
        set_native_build_enqueue_for_tests(None)
        set_builder_source_store_for_tests(None)

    job_id = result["native_build_job_id"]
    assert result["ham_native_builder"]["status"] == "started"
    # Durable default: handed to the enqueue seam exactly once, build NOT run inline.
    assert len(recorder.calls) == 1
    assert recorder.calls[0].import_job_id == job_id
    jobs = store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert jobs[0].status == "queued"
    assert jobs[0].phase == NATIVE_BUILD_PHASE_QUEUED
    assert store.list_source_snapshots(workspace_id="ws_v2", project_id="proj_v2") == []
    # Durable execution context is persisted by job id for the out-of-process worker.
    ctx = store.get_native_build_context(import_job_id=job_id)
    assert ctx is not None
    assert ctx.workspace_id == "ws_v2"
    assert ctx.project_id == "proj_v2"
    assert ctx.session_id == "sess_v2"
    assert ctx.user_prompt == "build a small native app"
    assert ctx.created_by == "user_v2"


def test_start_creates_job_and_returns_started(tmp_path, monkeypatch) -> None:
    _ready_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        result = start_native_build_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
            complete_turn=_valid_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    # start always reports a non-blocking "started" with a pollable job id.
    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "started"
    assert result["native_build_job_id"]
    jobs = store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert len(jobs) == 1
    assert jobs[0].id == result["native_build_job_id"]
    assert jobs[0].metadata.get("origin") == NATIVE_BUILD_JOB_ORIGIN
    # inline dispatch ran the functional executor -> build materialized.
    assert jobs[0].status == "succeeded"
    assert jobs[0].phase == NATIVE_BUILD_PHASE_SUCCEEDED


def test_executor_success_materializes_source_snapshot(tmp_path, monkeypatch) -> None:
    _ready_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        job = store.create_import_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            created_by="user_v2",
            phase=NATIVE_BUILD_PHASE_QUEUED,
            status="queued",
            metadata={"origin": NATIVE_BUILD_JOB_ORIGIN},
        )
        result = execute_native_build_job(
            import_job_id=job.id,
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
            complete_turn=_valid_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is True
    assert result["ham_native_builder"] == {"status": "succeeded"}
    assert result["source_snapshot_id"]

    jobs = store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert jobs[0].status == "succeeded"
    assert jobs[0].phase == NATIVE_BUILD_PHASE_SUCCEEDED
    sources = store.list_project_sources(workspace_id="ws_v2", project_id="proj_v2")
    assert sources[0].kind == "ham_native_builder"
    snapshots = store.list_source_snapshots(workspace_id="ws_v2", project_id="proj_v2")
    assert snapshots[0].manifest["kind"] == "inline_text_bundle"
    assert "src/App.tsx" in snapshots[0].manifest["inline_files"]
    assert "package.json" in snapshots[0].manifest["inline_files"]


def test_executor_failure_marks_safe_error(tmp_path, monkeypatch) -> None:
    _ready_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _boom(_messages) -> str:
        raise GatewayCallError("UPSTREAM_TIMEOUT", "Gateway request timed out")

    try:
        job = store.create_import_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            created_by="user_v2",
            phase=NATIVE_BUILD_PHASE_QUEUED,
            status="queued",
            metadata={"origin": NATIVE_BUILD_JOB_ORIGIN},
        )
        result = execute_native_build_job(
            import_job_id=job.id,
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
            complete_turn=_boom,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"] == {"status": "failed", "failure_reason": "gateway"}
    jobs = store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert jobs[0].status == "failed"
    assert jobs[0].phase == NATIVE_BUILD_PHASE_FAILED
    assert jobs[0].error_code == "HAM_NATIVE_BUILDER_GATEWAY_ERROR"
    # No raw gateway code / internals leak into the user-pollable record.
    serialized = json.dumps(jobs[0].model_dump(mode="json")).lower()
    for token in (*_FORBIDDEN_TOKENS, "upstream_timeout"):
        assert token not in serialized


def test_status_persists_across_store_reload_without_internals(tmp_path, monkeypatch) -> None:
    _ready_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        result = start_native_build_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
            complete_turn=_valid_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)
    job_id = result["native_build_job_id"]

    # A fresh store reading the same file sees the persisted job (pollable).
    reopened = BuilderSourceStore(store_path=tmp_path / "sources.json")
    jobs = reopened.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert [j.id for j in jobs] == [job_id]
    assert jobs[0].status == "succeeded"
    serialized = json.dumps(jobs[0].model_dump(mode="json")).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in serialized


def test_executor_does_not_run_old_scaffold(tmp_path, monkeypatch) -> None:
    _ready_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    import src.ham.builder_chat_scaffold as scaffold_mod

    def _raise_if_called(*_a, **_k):
        raise AssertionError("old internal scaffold must not run in the native executor")

    monkeypatch.setattr(scaffold_mod, "maybe_chat_scaffold_for_turn", _raise_if_called)
    try:
        job = store.create_import_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            created_by="user_v2",
            phase=NATIVE_BUILD_PHASE_QUEUED,
            status="queued",
            metadata={"origin": NATIVE_BUILD_JOB_ORIGIN},
        )
        result = execute_native_build_job(
            import_job_id=job.id,
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
            complete_turn=_valid_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["ham_native_builder"] == {"status": "succeeded"}


def test_unconfigured_returns_unavailable_and_creates_no_job(tmp_path, monkeypatch) -> None:
    # Gateway reachable but no builder model and no injected turn -> fail fast, no job.
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.delenv("HERMES_BUILDER_MODEL", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        result = start_native_build_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["ham_native_builder"] == {"status": "unavailable", "failure_reason": "unconfigured"}
    assert "native_build_job_id" not in result
    assert store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2") == []


def test_thread_dispatch_returns_before_executor_completes(tmp_path, monkeypatch) -> None:
    """Real async boundary: with thread dispatch, start returns while a slow executor is still running."""
    _ready_env(tmp_path, monkeypatch)
    monkeypatch.setenv("HAM_NATIVE_BUILD_DISPATCH", "thread")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    entered = threading.Event()
    release = threading.Event()
    finished = {"v": False}

    def _slow_executor(**_kwargs) -> None:
        entered.set()
        release.wait(5)
        finished["v"] = True

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.execute_native_build_job", _slow_executor
    )
    try:
        result = start_native_build_job(
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="build a small native app",
            created_by="user_v2",
        )
        assert result["ham_native_builder"]["status"] == "started"
        assert entered.wait(5) is True
        # start did NOT block on the executor (still parked on release).
        assert finished["v"] is False
        release.set()
        for _ in range(200):
            if finished["v"]:
                break
            time.sleep(0.01)
        assert finished["v"] is True
    finally:
        release.set()
        set_builder_source_store_for_tests(None)


def test_started_copy_is_safe_and_non_internal() -> None:
    msg = ham_native_builder_user_message({"status": "started"})
    assert msg.startswith("HAM started the native build.")
    for token in _FORBIDDEN_TOKENS:
        assert token not in msg.lower()
