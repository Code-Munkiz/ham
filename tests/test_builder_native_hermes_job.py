"""HAM Native Builder v2 — async job boundary tests.

Covers the start function (creates a job and returns immediately without inline
Hermes artifact generation), the placeholder executor, status persistence /
pollability, the non-blocking thread dispatch, and the no-internals guarantee.
"""

import json
import threading
import time

from src.ham.builder_native_hermes import (
    NATIVE_BUILD_JOB_ORIGIN,
    NATIVE_BUILD_PHASE_PENDING_EXECUTOR,
    NATIVE_BUILD_PHASE_QUEUED,
    execute_native_build_job,
    ham_native_builder_user_message,
    start_native_build_job,
)
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


def _ready_env(tmp_path, monkeypatch) -> None:
    """Gateway + builder model configured so preflight passes with no injected turn."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-fast")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    monkeypatch.delenv("HAM_NATIVE_BUILD_DISPATCH", raising=False)


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
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "started"
    assert result["native_build_job_id"]
    jobs = store.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert len(jobs) == 1
    assert jobs[0].id == result["native_build_job_id"]
    assert jobs[0].metadata.get("origin") == NATIVE_BUILD_JOB_ORIGIN
    # inline placeholder executor ran off the start contract -> terminal pending state
    assert jobs[0].status == "failed"
    assert jobs[0].phase == NATIVE_BUILD_PHASE_PENDING_EXECUTOR


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
        )
    finally:
        set_builder_source_store_for_tests(None)
    job_id = result["native_build_job_id"]

    # A fresh store reading the same file sees the persisted job (pollable).
    reopened = BuilderSourceStore(store_path=tmp_path / "sources.json")
    jobs = reopened.list_import_jobs(workspace_id="ws_v2", project_id="proj_v2")
    assert [j.id for j in jobs] == [job_id]
    serialized = json.dumps(jobs[0].model_dump(mode="json")).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in serialized


def test_placeholder_executor_marks_pending(tmp_path, monkeypatch) -> None:
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
        updated = execute_native_build_job(
            import_job_id=job.id,
            workspace_id="ws_v2",
            project_id="proj_v2",
            session_id="sess_v2",
            user_prompt="x",
            created_by="user_v2",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert updated.status == "failed"
    assert updated.phase == NATIVE_BUILD_PHASE_PENDING_EXECUTOR
    assert updated.error_code == "HAM_NATIVE_BUILDER_V2_PENDING_EXECUTOR"
    assert "not implemented" in (updated.error_message or "").lower()


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
