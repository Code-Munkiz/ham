from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.builder_sources import router as builder_sources_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.builder_sandbox_provider import (
    GcpGkeRuntimeConfig,
    SandboxRuntimeState,
    SandboxSourceFile,
    set_sandbox_runtime_provider_factory_for_tests,
)
from src.ham.gcp_preview_source_bundle import set_source_bundle_uploader_factory_for_tests
from src.ham.gcp_preview_runtime_client import (
    PreviewPodRef,
    PreviewPodStatus,
    set_gke_runtime_client_factory_for_tests,
)
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore, set_builder_runtime_job_store_for_tests
from src.persistence.builder_runtime_store import BuilderRuntimeStore, set_builder_runtime_store_for_tests
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    SourceSnapshot,
    set_builder_source_store_for_tests,
)
from src.persistence.builder_usage_event_store import BuilderUsageEventStore, set_builder_usage_event_store_for_tests
from src.persistence.project_store import ProjectStore, set_project_store_for_tests
from src.persistence.workspace_store import InMemoryWorkspaceStore


def _actor(user_id: str, *, org_id: str | None, org_role: str | None = "org:admin") -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=org_id,
        session_id=f"sess_{user_id}",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role=org_role,
        raw_permission_claim=None,
    )


def _build_app(*, actor: HamActor | None, ws_store: InMemoryWorkspaceStore) -> FastAPI:
    app = FastAPI()
    app.include_router(builder_sources_router)

    async def _override_actor() -> HamActor | None:
        return actor

    def _override_workspace_store() -> InMemoryWorkspaceStore:
        return ws_store

    app.dependency_overrides[get_ham_clerk_actor] = _override_actor
    app.dependency_overrides[get_workspace_store] = _override_workspace_store
    return app


def _seed_workspace(
    store: InMemoryWorkspaceStore,
    *,
    workspace_id: str,
    org_id: str | None,
    owner_user_id: str,
    slug: str,
) -> None:
    now = datetime.now(UTC)
    store.create_workspace(
        WorkspaceRecord(
            workspace_id=workspace_id,
            org_id=org_id,
            owner_user_id=owner_user_id,
            name=slug,
            slug=slug,
            description="",
            status="active",
            created_by=owner_user_id,
            created_at=now,
            updated_at=now,
        )
    )
    store.upsert_member(
        WorkspaceMember(
            workspace_id=workspace_id,
            user_id=owner_user_id,
            role="owner",
            added_by=owner_user_id,
            added_at=now,
        )
    )


def _apply_gcp_gke_scaffold(
    monkeypatch,
    *,
    enabled: bool = True,
    dry_run: bool = True,
    fake_mode: str | None = None,
    omit_bucket: bool = False,
) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "gcp_gke_sandbox")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_DRY_RUN", "true" if dry_run else "false")
    if fake_mode:
        monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_FAKE_MODE", fake_mode)
    else:
        monkeypatch.delenv("HAM_BUILDER_GCP_RUNTIME_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_GCP_PROJECT_ID", "proj-test")
    monkeypatch.setenv("HAM_BUILDER_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_GKE_CLUSTER", "cluster-test")
    monkeypatch.setenv("HAM_BUILDER_GKE_NAMESPACE_PREFIX", "ham-builder-")
    if omit_bucket:
        monkeypatch.delenv("HAM_BUILDER_PREVIEW_SOURCE_BUCKET", raising=False)
    else:
        monkeypatch.setenv("HAM_BUILDER_PREVIEW_SOURCE_BUCKET", "ham-builder-sources-test")
    monkeypatch.setenv(
        "HAM_BUILDER_PREVIEW_RUNNER_IMAGE",
        "us-central1-docker.pkg.dev/proj/runner:test",
    )


def _seed_context(tmp_path: Path) -> tuple[TestClient, str, str, str]:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)

    source_store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    src = source_store.upsert_project_source(ProjectSource(workspace_id=ws_id, project_id=project.id, kind="chat_scaffold"))
    snap = source_store.upsert_source_snapshot(
        SourceSnapshot(
            workspace_id=ws_id,
            project_id=project.id,
            project_source_id=src.id,
            artifact_uri="builder-artifact://bzip_test",
            digest_sha256="a" * 64,
            manifest={
                "kind": "inline_text_bundle",
                "inline_files": {
                    "package.json": '{"name":"gcp-test","private":true}',
                    "src/main.tsx": "console.log('ok');",
                },
            },
        )
    )
    src.active_snapshot_id = snap.id
    source_store.upsert_project_source(src)
    set_builder_source_store_for_tests(source_store)
    set_builder_runtime_store_for_tests(BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json"))
    set_builder_runtime_job_store_for_tests(BuilderRuntimeJobStore(store_path=tmp_path / "builder_runtime_jobs.json"))
    set_builder_usage_event_store_for_tests(BuilderUsageEventStore(store_path=tmp_path / "builder_usage_events.json"))
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    return client, ws_id, project.id, snap.id


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)
    set_builder_runtime_job_store_for_tests(None)
    set_builder_usage_event_store_for_tests(None)
    set_sandbox_runtime_provider_factory_for_tests(None)
    set_source_bundle_uploader_factory_for_tests(None)
    set_gke_runtime_client_factory_for_tests(None)


class _InjectedLiveProvider:
    def __init__(self, *, mode: str = "success") -> None:
        self.mode = mode

    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState:
        _ = config
        return state.__class__(
            **{
                **state.__dict__,
                "sandbox_id": "gke_live_1234",
                "status": "creating",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
        files: list[SandboxSourceFile],
    ) -> SandboxRuntimeState:
        _ = source_ref, artifact_uri
        if not files:
            return state.__class__(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "error_code": "GCP_GKE_SOURCE_FILES_MISSING",
                    "error_message": "no files",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            )
        return state.__class__(**{**state.__dict__, "status": "uploading", "updated_at": "2026-01-01T00:00:00Z"})

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState:
        _ = command, stage
        return state.__class__(**{**state.__dict__, "status": "starting", "updated_at": "2026-01-01T00:00:00Z"})

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState:
        _ = port
        if self.mode == "timeout":
            return state.__class__(
                **{
                    **state.__dict__,
                    "status": "failed",
                    "error_code": "GCP_GKE_PREVIEW_HEALTHCHECK_FAILED",
                    "error_message": "Preview did not become reachable before timeout.",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            )
        return state.__class__(
            **{
                **state.__dict__,
                "status": "ready",
                "preview_upstream_url": "https://3000-gkepreview.run.app/",
                "logs_summary": "preview ready",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    def get_preview_url(self, *, state: SandboxRuntimeState, port: int) -> str | None:
        _ = port
        return state.preview_upstream_url

    def get_status(self, *, state: SandboxRuntimeState) -> str:
        return state.status

    def get_logs_summary(self, *, state: SandboxRuntimeState) -> str | None:
        return state.logs_summary

    def stop_sandbox(self, *, state: SandboxRuntimeState) -> SandboxRuntimeState:
        return state

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_PROVIDER_ERROR", "GCP GKE runtime provider operation failed safely.")


class _InjectedExplodingProvider(_InjectedLiveProvider):
    def __init__(self) -> None:
        super().__init__(mode="success")

    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        raise Exception("provider transport failure")


class _InjectedCreateTransportFailureProvider(_InjectedExplodingProvider):
    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        raise httpx.RemoteProtocolError("server disconnected without sending a response")


class _InjectedCreateAuthFailureProvider(_InjectedExplodingProvider):
    def create_sandbox(self, *, state: SandboxRuntimeState, config: GcpGkeRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        raise RuntimeError("api key rejected by provider")


class _RecordingBundleUploader:
    calls: list[tuple[str, str, int]] = []

    def upload_bundle(self, *, bucket: str, object_name: str, payload: bytes):
        self.calls.append((bucket, object_name, len(payload)))
        from src.ham.gcp_preview_source_bundle import SourceBundleUploadOutcome

        return SourceBundleUploadOutcome(
            uri=f"gs://{bucket}/{object_name}",
            uploaded=True,
            sha256="b" * 64,
            file_count=0,
            byte_size=len(payload),
        )


class _RecordingRuntimeClient:
    manifests: list[dict] = []

    def create_preview_pod(self, *, manifest: dict):
        self.manifests.append(manifest)
        md = manifest.get("metadata") or {}
        return PreviewPodRef(
            namespace=str(md.get("namespace") or "ham-builder-preview-spike"),
            pod_name=str(md.get("name") or "pod"),
            labels={str(k): str(v) for k, v in (md.get("labels") or {}).items()},
        )

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus:
        _ = pod_ref
        return PreviewPodStatus(phase="Running", ready=True)

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus:
        _ = pod_ref, timeout_seconds
        return PreviewPodStatus(phase="Running", ready=True)

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None:
        _ = pod_ref, max_chars
        return "runtime client fake logs"

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool:
        _ = pod_ref
        return True

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict | None = None) -> str | None:
        _ = pod_ref, manifest
        return None

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
    ):
        _ = resources, workspace_id, project_id, now_iso
        from src.ham.gcp_preview_runtime_client import CleanupResult

        return CleanupResult(deleted_pods=0, deleted_services=0, skipped=0, cleanup_status="success")

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_CLIENT_ERROR", "runtime client failed")


def test_e2b_dependency_removed_from_requirements() -> None:
    req = Path("requirements.txt").read_text(encoding="utf-8").lower()
    assert "e2b" not in req


def test_gcp_gke_disabled_returns_config_missing(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, enabled=False)
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["error_code"] == "GCP_GKE_RUNTIME_CONFIG_MISSING"
        assert body["job"]["provider"] == "gcp_gke_sandbox"
    finally:
        _cleanup()


def test_gcp_gke_dry_run_creates_runtime_without_ready_preview(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=True)
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["provider"] == "gcp_gke_sandbox"
        assert body["job"]["status"] == "succeeded"
        sess = body["runtime_session"]
        assert sess["preview_endpoint_id"] in {None, ""}
        preview = client.get(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status",
            params={"source_snapshot_id": snap_id},
        ).json()
        assert preview["preview_url"] in {None, ""}
    finally:
        _cleanup()


def test_gcp_gke_incomplete_scaffold_reports_config_missing(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, omit_bucket=True)
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["error_code"] == "GCP_GKE_RUNTIME_CONFIG_MISSING"
    finally:
        _cleanup()


def test_gcp_gke_live_without_fake_reports_not_implemented(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False)
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["error_code"] == "GCP_GKE_RUNTIME_LIVE_NOT_IMPLEMENTED"
    finally:
        _cleanup()


def test_gcp_gke_fake_success_creates_proxy_ready_preview(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["provider"] == "gcp_gke_sandbox"
        assert body["job"]["status"] == "succeeded"
        handoff = body["job"]["metadata"]["source_handoff"]
        assert str(handoff["artifact_uri"]).startswith("gs://ham-builder-sources-test/")
        assert str(handoff["source_ref"]).startswith("bundle:")
        source_bundle = body["job"]["metadata"]["source_bundle"]
        assert source_bundle["uploaded"] is False
        assert source_bundle["file_count"] >= 1
        sess = body["runtime_session"]
        assert sess["preview_endpoint_id"]
        preview = client.get(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status",
            params={"source_snapshot_id": snap_id},
        ).json()
        url = preview["preview_url"]
        assert url
        assert url.endswith("/builder/preview-proxy/")
        assert "ham-gke-preview" not in url.lower()
    finally:
        _cleanup()


def test_gcp_gke_uses_injected_source_bundle_uploader(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    _RecordingBundleUploader.calls = []
    set_source_bundle_uploader_factory_for_tests(lambda: _RecordingBundleUploader())
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        source_bundle = body["job"]["metadata"]["source_bundle"]
        assert source_bundle["uploaded"] is True
        assert _RecordingBundleUploader.calls
        bucket, object_name, payload_size = _RecordingBundleUploader.calls[0]
        assert bucket == "ham-builder-sources-test"
        assert object_name.endswith("/preview-source.zip")
        assert payload_size > 0
    finally:
        _cleanup()


def test_gcp_gke_passes_source_bundle_uri_into_runtime_client_manifest(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    _RecordingRuntimeClient.manifests = []
    set_gke_runtime_client_factory_for_tests(lambda: _RecordingRuntimeClient())
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "succeeded"
        assert _RecordingRuntimeClient.manifests
        manifest = _RecordingRuntimeClient.manifests[0]
        envs = manifest["spec"]["containers"][0]["env"]
        source_uri = next((e["value"] for e in envs if e["name"] == "PREVIEW_SOURCE_URI"), "")
        assert source_uri.startswith("gs://ham-builder-sources-test/")
        runtime_resource = body["job"]["metadata"]["runtime_resource"]
        assert runtime_resource["pod_phase"] == "Running"
    finally:
        _cleanup()


def test_gcp_gke_fake_failure_reports_error_without_preview(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="failure")
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        preview = client.get(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status",
            params={"source_snapshot_id": snap_id},
        ).json()
        assert preview["preview_url"] in {None, ""}
    finally:
        _cleanup()


def test_gcp_gke_live_client_gate_without_impl_fails_safely(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED", "true")
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        assert body["job"]["error_code"] == "GCP_GKE_RUNTIME_CLIENT_ERROR"
    finally:
        _cleanup()


def test_gcp_gke_injected_live_success_returns_proxy_only(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="success"))
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "succeeded"
        preview = client.get(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status",
            params={"source_snapshot_id": snap_id},
        ).json()
        url = preview["preview_url"]
        assert url
        raw = str(preview)
        assert "3000-gkepreview.run.app" not in raw
        assert "?token=" not in raw.lower()
    finally:
        _cleanup()


def test_gcp_gke_injected_adapter_timeout_normalizes_without_ready_preview(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="timeout"))
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        preview = client.get(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-status",
            params={"source_snapshot_id": snap_id},
        ).json()
        assert preview["preview_url"] in {None, ""}
    finally:
        _cleanup()


def test_gcp_gke_unexpected_exception_is_normalized(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedExplodingProvider())
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        assert body["job"]["error_code"] == "GCP_GKE_RUNTIME_PROVIDER_ERROR"
    finally:
        _cleanup()


def test_gcp_gke_create_transport_failure_records_runtime_metadata(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    injected = _InjectedCreateTransportFailureProvider()
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: injected)
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        diag = body["job"]["metadata"]["runtime_diagnostics"]
        assert diag["lifecycle_stage"] == "create_sandbox"
        assert diag["normalized_error_code"] == "GCP_GKE_RUNTIME_PROVIDER_ERROR"
        assert diag["exception_class"] == "RemoteProtocolError"
    finally:
        _cleanup()


def test_gcp_gke_create_auth_style_failure_records_metadata(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedCreateAuthFailureProvider())
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        assert body["job"]["status"] == "failed"
        diag = body["job"]["metadata"]["runtime_diagnostics"]
        assert diag["lifecycle_stage"] == "create_sandbox"
        assert diag["normalized_error_code"] == "GCP_GKE_RUNTIME_PROVIDER_ERROR"
    finally:
        _cleanup()


def test_gcp_gke_health_failure_has_non_create_stage_metadata(tmp_path: Path, monkeypatch) -> None:
    _apply_gcp_gke_scaffold(monkeypatch, dry_run=False, fake_mode="success")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="timeout"))
    client, ws_id, project_id, snap_id = _seed_context(tmp_path)
    try:
        body = client.post(
            f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
            json={"source_snapshot_id": snap_id},
        ).json()
        diag = body["job"]["metadata"]["runtime_diagnostics"]
        assert diag["lifecycle_stage"] == "health"
    finally:
        _cleanup()
