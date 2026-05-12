from __future__ import annotations

from pathlib import Path

from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_chat_scaffold import (
    materialize_inline_files_as_zip_artifact,
    maybe_chat_scaffold_for_turn,
)
from src.ham.builder_cloud_runtime_gcp import (
    FakeGcpCloudRuntimeClient,
    set_gcp_cloud_runtime_client_for_tests,
)
from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore, set_builder_runtime_job_store_for_tests
from src.persistence.builder_runtime_store import BuilderRuntimeStore, set_builder_runtime_store_for_tests
from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests
from src.persistence.builder_usage_event_store import BuilderUsageEventStore, set_builder_usage_event_store_for_tests


def _cleanup() -> None:
    set_builder_source_store_for_tests(None)
    set_builder_runtime_job_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
    set_builder_usage_event_store_for_tests(None)
    set_gcp_cloud_runtime_client_for_tests(None)


def test_materialize_inline_files_writes_builder_artifact_uri(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    uri, zsize = materialize_inline_files_as_zip_artifact(
        workspace_id="ws1",
        project_id="p1",
        files={"a.txt": "hi"},
    )
    assert uri.startswith("builder-artifact://")
    assert zsize > 20


def test_maybe_chat_scaffold_sets_artifact_uri(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_1",
        last_user_plain="build me a landing page for a roofing company",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    assert snap.artifact_uri.startswith("builder-artifact://")
    _cleanup()


def test_chat_scaffold_enqueue_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-x")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    set_gcp_cloud_runtime_client_for_tests(FakeGcpCloudRuntimeClient())
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    set_builder_runtime_job_store_for_tests(BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json"))
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "runtime.json"))
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "usage.json"))

    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_dedupe",
        last_user_plain="build me a todo app with dark mode",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    sid = str(out["source_snapshot_id"])
    meta1 = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_dedupe",
        requested_by="user_1",
    )
    assert meta1.get("cloud_runtime_job_deduplicated") is False
    assert meta1.get("cloud_runtime_job_id")
    meta2 = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_dedupe",
        requested_by="user_1",
    )
    assert meta2.get("cloud_runtime_job_deduplicated") is True
    assert meta2.get("cloud_runtime_job_id") == meta1.get("cloud_runtime_job_id")
    _cleanup()
