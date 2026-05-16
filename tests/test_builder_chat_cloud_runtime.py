from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_chat_hooks import run_builder_happy_path_hook
from src.ham.builder_chat_scaffold import (
    materialize_inline_files_as_zip_artifact,
    maybe_chat_scaffold_for_turn,
)
from src.ham.builder_cloud_runtime_gcp import (
    FakeGcpCloudRuntimeClient,
    set_gcp_cloud_runtime_client_for_tests,
)
from src.ham.gcp_preview_runtime_client import (
    CleanupResult,
    PreviewPodRef,
    PreviewPodStatus,
    set_gke_runtime_client_factory_for_tests,
)
from src.ham.gcp_preview_source_bundle import SourceBundleUploadOutcome, set_source_bundle_uploader_factory_for_tests
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
    set_source_bundle_uploader_factory_for_tests(None)
    set_gke_runtime_client_factory_for_tests(None)


class _RecordingBundleUploader:
    def upload_bundle(self, *, bucket: str, object_name: str, payload: bytes) -> SourceBundleUploadOutcome:
        return SourceBundleUploadOutcome(
            uri=f"gs://{bucket}/{object_name}",
            uploaded=True,
            sha256="c" * 64,
            file_count=0,
            byte_size=len(payload),
        )


class _RecordingRuntimeClient:
    created_pods = 0

    def create_preview_pod(self, *, manifest: dict):
        _ = manifest
        self.__class__.created_pods += 1
        return PreviewPodRef(
            namespace="ham-builder-preview-spike",
            pod_name="ham-preview-pod-test",
            labels={"ham.workspace_id": "ws_a", "ham.project_id": "pr_a"},
        )

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus:
        _ = pod_ref
        return PreviewPodStatus(phase="Running", ready=True)

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus:
        _ = pod_ref, timeout_seconds
        return PreviewPodStatus(phase="Running", ready=True)

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None:
        _ = pod_ref, max_chars
        return "preview-runner ready"

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool:
        _ = pod_ref
        return True

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict | None = None) -> str | None:
        _ = pod_ref, manifest
        return "ham-preview-svc-test"

    def delete_preview_service(self, *, pod_ref: PreviewPodRef) -> bool:
        _ = pod_ref
        return True

    def cleanup_owned_expired_resources(
        self,
        *,
        resources: list[PreviewPodRef],
        workspace_id: str,
        project_id: str,
        now_iso: str,
    ) -> CleanupResult:
        _ = resources, workspace_id, project_id, now_iso
        return CleanupResult(deleted_pods=0, deleted_services=0, skipped=0, cleanup_status="success")

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_CLIENT_ERROR", "runtime client failed")


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


def test_chat_scaffold_app_tsx_includes_react_import_for_jsx_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_imports",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    assert "from \"react\";" in app_tsx
    _cleanup()


def test_chat_scaffold_tetris_prompt_generates_playable_game_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_tetris",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    styles_css = str(inline_files.get("src/styles.css") or "")
    readme = str(inline_files.get("README.md") or "")
    vite_config = str(inline_files.get("vite.config.ts") or "")
    package_json = str(inline_files.get("package.json") or "")
    assert "const BOARD_WIDTH = 10;" in app_tsx
    assert "const BOARD_HEIGHT = 20;" in app_tsx
    assert "function clearLines(board: Board)" in app_tsx
    assert "function collides(board: Board, piece: ActivePiece)" in app_tsx
    assert "Line clear scoring, levels, and game over + restart" in readme
    assert ".board {" in styles_css
    assert ".game-over {" in styles_css
    assert "height: 100dvh;" in styles_css
    assert "overflow: hidden;" in styles_css
    assert "aspect-ratio: 1 / 2;" in styles_css
    assert "grid-template-columns: minmax(150px, 190px) minmax(0, 1fr) minmax(150px, 190px);" in styles_css
    assert "grid-template-columns: 220px 1fr 220px;" not in styles_css
    assert "hmr: false" in vite_config
    assert '"dev": "vite build && vite preview"' in package_json
    assert "Scaffold created from your chat request." not in app_tsx
    _cleanup()


def test_chat_scaffold_calculator_prompt_generates_functional_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_calc",
        last_user_plain="start a new project and build me a clean calculator app",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    styles_css = str(inline_files.get("src/styles.css") or "")
    assert "function compute(left: number, right: number, op: Op): number" in app_tsx
    assert "<h1>Calculator</h1>" in app_tsx
    assert "Scaffold created from your chat request." not in app_tsx
    assert ".keypad {" in styles_css
    _cleanup()


def test_chat_scaffold_calculator_followup_adds_history_and_larger_buttons(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_calc_follow",
        last_user_plain="build me a clean calculator app",
        created_by="user_1",
    )
    assert first and first.get("scaffolded")
    first_snapshot = str(first["source_snapshot_id"])
    second = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_calc_follow",
        last_user_plain="make the buttons larger and add a history panel",
        created_by="user_1",
        operation="update_existing_project",
    )
    assert second and second.get("scaffolded")
    second_snapshot = str(second["source_snapshot_id"])
    assert second_snapshot != first_snapshot
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    latest = next(row for row in rows if row.id == second_snapshot)
    inline_files = latest.manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    styles_css = str(inline_files.get("src/styles.css") or "")
    assert "<h2>History</h2>" in app_tsx
    assert "min-height: 3.1rem;" in styles_css
    sources = store.list_project_sources(workspace_id="ws_a", project_id="pr_a")
    assert sources and sources[0].active_snapshot_id == second_snapshot
    _cleanup()


def test_chat_scaffold_tetris_reference_prompt_applies_style_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_style_ref",
        last_user_plain="ham make me a game like tetris like the one in the image",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    assert out.get("style_profile_id") == "neon_space_glass"
    assert out.get("reference_requested") is True
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    styles_css = str(inline_files.get("src/styles.css") or "")
    assert "Neon glass arena tuned from your style reference." in app_tsx
    assert "--ham-bg-start: #1c1140;" in styles_css
    assert "--ham-panel-border: #5340b8;" in styles_css
    assert "image was analyzed" not in app_tsx.lower()
    _cleanup()


def test_builder_hook_followup_edit_updates_existing_project_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_iter",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert first and first.get("scaffolded") is True
    first_snapshot = str(first.get("source_snapshot_id") or "")

    prefix, meta = run_builder_happy_path_hook(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_iter",
        last_user_plain="make the board smaller and change the colors",
        ham_actor=None,
    )
    assert prefix is not None
    assert "update the existing project" in prefix.lower()
    assert meta.get("scaffolded") is True
    assert meta.get("builder_operation") == "update_existing_project"
    second_snapshot = str(meta.get("source_snapshot_id") or "")
    assert second_snapshot and second_snapshot != first_snapshot
    source_rows = store.list_project_sources(workspace_id="ws_a", project_id="pr_a")
    assert source_rows and source_rows[0].active_snapshot_id == second_snapshot
    _cleanup()


def test_builder_hook_enhance_prompt_routes_to_update_existing_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_enhance",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert first and first.get("scaffolded") is True

    prefix, meta = run_builder_happy_path_hook(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_enhance",
        last_user_plain="the tetris game looks boring, enhance it",
        ham_actor=None,
    )
    assert prefix is not None
    assert "update the existing project" in prefix.lower()
    assert meta.get("builder_operation") == "update_existing_project"
    assert meta.get("scaffolded") is True
    _cleanup()


def test_chat_scaffold_update_carries_forward_reference_style_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_style_carry",
        last_user_plain="ham make me a game like tetris like the one in the image",
        created_by="user_1",
    )
    assert first and first.get("scaffolded") is True
    assert first.get("style_profile_id") == "neon_space_glass"
    second = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_style_carry",
        last_user_plain="enhance it and make it more polished",
        created_by="user_1",
        operation="update_existing_project",
    )
    assert second and second.get("scaffolded") is True
    # Follow-up enhancement should not regress back to generic style.
    assert second.get("style_profile_id") in {"neon_space_glass", "cyber_arcade", "compact_reference_game"}
    _cleanup()


def test_chat_scaffold_title_strips_dashboard_attachment_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    out = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_attached",
        last_user_plain="ham make me a tetris game that looks like this\n[User attached 1 image(s) in the dashboard (1 image(s)).]",
        created_by="user_1",
    )
    assert out and out.get("scaffolded")
    snap_id = str(out["source_snapshot_id"])
    rows = store.list_source_snapshots(workspace_id="ws_a", project_id="pr_a")
    snap = next(row for row in rows if row.id == snap_id)
    manifest = snap.manifest or {}
    inline_files = manifest.get("inline_files")
    assert isinstance(inline_files, dict)
    app_tsx = str(inline_files.get("src/App.tsx") or "")
    assert "User attached" not in app_tsx
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


def test_chat_scaffold_dedupe_includes_source_snapshot_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_dup",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    second = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_dup",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert first and first.get("scaffolded") is True
    assert second and second.get("deduplicated") is True
    assert second.get("source_snapshot_id") == first.get("source_snapshot_id")
    _cleanup()


def test_chat_scaffold_fingerprint_version_busts_old_dedupe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    first = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_ver",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert first and first.get("scaffolded") is True
    first_snapshot = str(first.get("source_snapshot_id") or "")
    monkeypatch.setattr("src.ham.builder_chat_scaffold._CHAT_SCAFFOLD_FINGERPRINT_VERSION", "v5")
    second = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_ver",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    assert second and second.get("scaffolded") is True
    second_snapshot = str(second.get("source_snapshot_id") or "")
    assert second_snapshot and second_snapshot != first_snapshot
    _cleanup()


def test_chat_scaffold_enqueue_retries_after_failed_terminal_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "gcp_gke_sandbox")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_PROJECT_ID", "proj-x")
    monkeypatch.setenv("HAM_BUILDER_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_GKE_CLUSTER", "cluster-test")
    monkeypatch.setenv("HAM_BUILDER_GKE_NAMESPACE_PREFIX", "ham-builder-preview")
    monkeypatch.setenv("HAM_BUILDER_PREVIEW_SOURCE_BUCKET", "bucket-test")
    monkeypatch.setenv(
        "HAM_BUILDER_PREVIEW_RUNNER_IMAGE",
        "us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:test",
    )
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    set_source_bundle_uploader_factory_for_tests(lambda: _RecordingBundleUploader())
    _RecordingRuntimeClient.created_pods = 0
    set_gke_runtime_client_factory_for_tests(lambda: _RecordingRuntimeClient())
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "sources.json"))
    job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
    set_builder_runtime_job_store_for_tests(job_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "runtime.json"))
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "usage.json"))

    summary = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_retry",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    sid = str((summary or {}).get("source_snapshot_id") or "")
    first = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_retry",
        requested_by="user_1",
    )
    assert first.get("cloud_runtime_job_deduplicated") is False
    first_job_id = str(first.get("cloud_runtime_job_id") or "")
    first_job = job_store.get_cloud_runtime_job(workspace_id="ws_a", project_id="pr_a", job_id=first_job_id)
    assert first_job is not None
    first_job.status = "failed"
    first_job.phase = "failed"
    job_store.upsert_cloud_runtime_job(first_job)

    second = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_retry",
        requested_by="user_1",
    )
    assert second.get("cloud_runtime_job_deduplicated") is False
    assert str(second.get("cloud_runtime_job_id") or "") != first_job_id
    assert _RecordingRuntimeClient.created_pods >= 2
    _cleanup()


def test_chat_scaffold_enqueue_supersedes_stale_active_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "cloud_run_poc")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-x")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_STALE_JOB_SECONDS", "60")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    set_gcp_cloud_runtime_client_for_tests(FakeGcpCloudRuntimeClient())
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "sources.json"))
    job_store = BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json")
    set_builder_runtime_job_store_for_tests(job_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "runtime.json"))
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "usage.json"))

    summary = maybe_chat_scaffold_for_turn(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_stale",
        last_user_plain="build me a game like Tetris",
        created_by="user_1",
    )
    sid = str((summary or {}).get("source_snapshot_id") or "")
    first = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_stale",
        requested_by="user_1",
    )
    first_job_id = str(first.get("cloud_runtime_job_id") or "")
    first_job = job_store.get_cloud_runtime_job(workspace_id="ws_a", project_id="pr_a", job_id=first_job_id)
    assert first_job is not None
    first_job.status = "running"
    first_job.phase = "preview_pending"
    first_job.updated_at = (datetime.now(UTC) - timedelta(minutes=30)).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    job_store.upsert_cloud_runtime_job(first_job)

    second = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id="ws_a",
        project_id="pr_a",
        source_snapshot_id=sid,
        session_id="sess_stale",
        requested_by="user_1",
    )
    second_job_id = str(second.get("cloud_runtime_job_id") or "")
    assert second.get("cloud_runtime_job_deduplicated") is False
    assert second_job_id != first_job_id
    stale_row = job_store.get_cloud_runtime_job(workspace_id="ws_a", project_id="pr_a", job_id=first_job_id)
    assert stale_row is not None
    assert stale_row.status == "cancelled"
    assert stale_row.error_code == "CLOUD_RUNTIME_JOB_SUPERSEDED"
    _cleanup()


def test_builder_chat_hook_auto_enqueue_invokes_live_runtime_when_gates_true(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "gcp_gke_sandbox")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_PROJECT_ID", "proj-x")
    monkeypatch.setenv("HAM_BUILDER_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_GKE_CLUSTER", "cluster-test")
    monkeypatch.setenv("HAM_BUILDER_GKE_NAMESPACE_PREFIX", "ham-builder-preview")
    monkeypatch.setenv("HAM_BUILDER_PREVIEW_SOURCE_BUCKET", "bucket-test")
    monkeypatch.setenv(
        "HAM_BUILDER_PREVIEW_RUNNER_IMAGE",
        "us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:test",
    )
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    set_source_bundle_uploader_factory_for_tests(lambda: _RecordingBundleUploader())
    _RecordingRuntimeClient.created_pods = 0
    set_gke_runtime_client_factory_for_tests(lambda: _RecordingRuntimeClient())
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "sources.json"))
    set_builder_runtime_job_store_for_tests(BuilderRuntimeJobStore(store_path=tmp_path / "jobs.json"))
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "runtime.json"))
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "usage.json"))

    _, meta = run_builder_happy_path_hook(
        workspace_id="ws_a",
        project_id="pr_a",
        session_id="sess_hook_live",
        last_user_plain="build me a game like Tetris",
        ham_actor=None,
    )
    assert meta.get("scaffolded") is True
    assert meta.get("cloud_runtime_job_id")
    assert _RecordingRuntimeClient.created_pods >= 1
    _cleanup()
