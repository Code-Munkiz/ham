from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.builder_sources import router as builder_sources_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.builder_sandbox_provider import (
    E2BSandboxRuntimeProvider,
    SandboxRuntimeConfig,
    SandboxRuntimeState,
    SandboxSourceFile,
    set_sandbox_runtime_provider_factory_for_tests,
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
                    "package.json": '{"name":"sandbox-test","private":true}',
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


class _InjectedLiveProvider:
    def __init__(self, *, mode: str = "success") -> None:
        self.mode = mode

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        _ = config
        return state.__class__(
            **{**state.__dict__, "sandbox_id": "e2b_live_1234", "status": "creating", "updated_at": "2026-01-01T00:00:00Z"}
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
                    "error_code": "SANDBOX_SOURCE_FILES_MISSING",
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
                    "error_code": "SANDBOX_PREVIEW_HEALTHCHECK_FAILED",
                    "error_message": "Sandbox preview did not become reachable before timeout.",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            )
        return state.__class__(
            **{
                **state.__dict__,
                "status": "ready",
                "preview_upstream_url": "https://3000-e2bpreview.e2b.app/",
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
        return ("SANDBOX_PROVIDER_ERROR", "Sandbox provider operation failed safely.")


class _InjectedExplodingProvider:
    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        raise Exception("provider transport failure")

    def upload_source(
        self,
        *,
        state: SandboxRuntimeState,
        source_ref: str,
        artifact_uri: str,
        files: list[SandboxSourceFile],
    ) -> SandboxRuntimeState:
        _ = source_ref, artifact_uri, files
        return state

    def run_command(self, *, state: SandboxRuntimeState, command: list[str], stage: str) -> SandboxRuntimeState:
        _ = command, stage
        return state

    def start_preview_server(self, *, state: SandboxRuntimeState, port: int) -> SandboxRuntimeState:
        _ = port
        return state

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
        return ("SANDBOX_PROVIDER_ERROR", "Sandbox provider operation failed safely.")


class _InjectedCreateTransportFailureProvider(_InjectedExplodingProvider):
    def __init__(self) -> None:
        self.create_attempts = 0

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        self.create_attempts += 1
        raise httpx.RemoteProtocolError("server disconnected without sending a response")


class _InjectedCreateTransportRetryProvider(_InjectedLiveProvider):
    def __init__(self) -> None:
        super().__init__(mode="success")
        self.create_attempts = 0

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        self.create_attempts += 1
        if self.create_attempts == 1:
            raise httpx.RemoteProtocolError("transient protocol failure")
        return super().create_sandbox(state=state, config=config)


class _InjectedCreateAuthFailureProvider(_InjectedExplodingProvider):
    def __init__(self) -> None:
        self.create_attempts = 0

    def create_sandbox(self, *, state: SandboxRuntimeState, config: SandboxRuntimeConfig) -> SandboxRuntimeState:
        _ = state, config
        self.create_attempts += 1
        raise RuntimeError("api key rejected by provider")


class _FakeHttpResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _FakeSandboxCommands:
    def run(self, *args, **kwargs) -> None:
        _ = args, kwargs


class _FakeSandboxRef:
    def __init__(self) -> None:
        self.commands = _FakeSandboxCommands()


class _CapturingSandbox:
    captured_kwargs: dict[str, object] | None = None

    @classmethod
    def create(cls, **kwargs):  # type: ignore[no-untyped-def]
        cls.captured_kwargs = dict(kwargs)
        obj = cls()
        obj.sandbox_id = "sandbox_capture"
        return obj


def _sandbox_state() -> SandboxRuntimeState:
    return SandboxRuntimeState(
        provider="e2b",
        sandbox_id="sandbox_demo",
        workspace_id="ws_aaaaaaaaaaaaaaaa",
        project_id="proj_demo",
        snapshot_id="ssnp_demo",
        runtime_job_id="crj_demo",
        status="starting",
        preview_upstream_url=None,
        preview_proxy_url=None,
        logs_summary=None,
        error_code=None,
        error_message=None,
        started_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        expires_at=None,
    )


def test_sandbox_provider_disabled_returns_config_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "false")
    client, ws_id, project_id, _ = _seed_context(tmp_path)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "config_missing"
    _cleanup()


def test_sandbox_provider_dry_run_creates_runtime_without_ready_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "true")
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["provider"] == "sandbox_provider"
    assert body["job"]["status"] == "succeeded"
    assert body["runtime_session"]["status"] == "provisioning"
    assert body["runtime_session"]["preview_endpoint_id"] is None
    assert body["preview_status"]["status"] != "ready"
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_sandbox_provider_missing_api_key_reports_config_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_API_KEY", raising=False)
    client, ws_id, project_id, _ = _seed_context(tmp_path)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "config_missing"
    _cleanup()


def test_sandbox_provider_fake_success_creates_proxy_ready_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_FAKE_MODE", "success")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "succeeded"
    assert body["runtime_session"]["status"] == "running"
    assert body["runtime_session"]["preview_endpoint_id"]
    assert body["preview_status"]["status"] == "ready"
    assert body["preview_status"]["preview_url"] == (
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/"
    )
    raw = res.text.lower()
    assert "test-secret-api-key" not in raw
    assert "token=" not in raw
    assert "ham-sandbox-" not in raw
    _cleanup()


def test_sandbox_provider_fake_failure_reports_error_without_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_FAKE_MODE", "failure")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_PREVIEW_START_FAILED"
    assert body["preview_status"]["status"] != "ready"
    assert body["preview_status"]["preview_url"] is None
    activity = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/activity")
    assert activity.status_code == 200
    assert any(row["title"] == "Cloud runtime failed" for row in activity.json()["items"])
    _cleanup()


def test_cloud_runtime_request_executes_job_when_sandbox_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_FAKE_MODE", "success")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/request",
        json={"source_snapshot_id": snapshot_id, "metadata": {"request_source": "test"}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "succeeded"
    assert body["runtime"]["status"] == "running"
    assert body["preview_status"]["status"] == "ready"
    assert body["preview_status"]["preview_url"] == (
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/"
    )
    assert "provisioning is not implemented yet" not in (body["runtime"].get("message") or "").lower()
    _cleanup()


def test_sandbox_provider_live_adapter_success_returns_proxy_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="success"))
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "succeeded"
    assert body["runtime_session"]["status"] == "running"
    assert body["preview_status"]["status"] == "ready"
    assert body["preview_status"]["preview_url"] == (
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/"
    )
    raw = res.text.lower()
    assert "test-secret-api-key" not in raw
    assert "3000-e2bpreview.e2b.app" not in raw
    assert "token=" not in raw
    _cleanup()


def test_sandbox_provider_live_adapter_timeout_normalizes_without_ready_preview(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="timeout"))
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_PREVIEW_HEALTHCHECK_FAILED"
    assert body["preview_status"]["status"] != "ready"
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_sandbox_provider_unexpected_exception_is_normalized(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedExplodingProvider())
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_PROVIDER_ERROR"
    assert body["runtime_session"]["status"] == "failed"
    assert "provisioning is not implemented yet" not in (body["runtime_session"]["message"] or "").lower()
    assert body["preview_status"]["status"] != "ready"
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_sandbox_provider_create_transport_failure_records_stage_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    injected = _InjectedCreateTransportFailureProvider()
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: injected)
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["job"]["metadata"]["sandbox_diagnostics"]
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_CREATE_TRANSPORT_ERROR"
    assert diag["lifecycle_stage"] == "create_sandbox"
    assert diag["exception_class"] == "RemoteProtocolError"
    assert diag["retry_count"] == 1
    assert diag["retryable"] is True
    assert body["preview_status"]["preview_url"] is None
    assert injected.create_attempts == 2
    _cleanup()


def test_sandbox_provider_create_transport_retry_then_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    injected = _InjectedCreateTransportRetryProvider()
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: injected)
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["job"]["metadata"]["sandbox_diagnostics"]
    assert body["job"]["status"] == "succeeded"
    assert body["preview_status"]["status"] == "ready"
    assert body["preview_status"]["preview_url"] == (
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/"
    )
    assert diag["lifecycle_stage"] == "persist"
    assert diag["retry_count"] == 1
    assert injected.create_attempts == 2
    _cleanup()


def test_sandbox_provider_create_auth_error_is_not_retried(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    injected = _InjectedCreateAuthFailureProvider()
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: injected)
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["job"]["metadata"]["sandbox_diagnostics"]
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_AUTH_FAILED"
    assert diag["retryable"] is False
    assert diag["retry_count"] == 0
    assert injected.create_attempts == 1
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_sandbox_provider_health_failure_has_non_create_stage_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    set_sandbox_runtime_provider_factory_for_tests(lambda _cfg: _InjectedLiveProvider(mode="timeout"))
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    diag = body["job"]["metadata"]["sandbox_diagnostics"]
    assert body["job"]["status"] == "failed"
    assert body["job"]["error_code"] == "SANDBOX_PREVIEW_HEALTHCHECK_FAILED"
    assert diag["lifecycle_stage"] == "health"
    assert diag["retry_count"] == 0
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_e2b_dependency_declared_in_requirements() -> None:
    req = Path("requirements.txt").read_text(encoding="utf-8").lower()
    assert "e2b>=2.21.0" in req


def test_e2b_create_sandbox_passes_explicit_api_key_without_env_mutation(monkeypatch) -> None:
    provider = E2BSandboxRuntimeProvider(api_key="test-key", template_id="tmpl_123")
    monkeypatch.setenv("E2B_API_KEY", "keep-existing")
    monkeypatch.setattr(provider, "_require_sdk", lambda: _CapturingSandbox)
    state = _sandbox_state()
    state.sandbox_id = None
    cfg = SandboxRuntimeConfig(
        enabled=True,
        provider="e2b",
        dry_run=False,
        default_port=3000,
        ttl_seconds=120,
        install_timeout_seconds=120,
        start_timeout_seconds=120,
        fake_mode="failure",
        fake_mode_explicit=False,
        api_key_present=True,
    )

    next_state = provider.create_sandbox(state=state, config=cfg)

    assert next_state.sandbox_id == "sandbox_capture"
    assert _CapturingSandbox.captured_kwargs is not None
    assert _CapturingSandbox.captured_kwargs["api_key"] == "test-key"
    assert _CapturingSandbox.captured_kwargs["template"] == "tmpl_123"
    assert os.environ.get("E2B_API_KEY") == "keep-existing"


def test_sandbox_provider_missing_sdk_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "sandbox_provider")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_PROVIDER", "e2b")
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_DRY_RUN", "false")
    monkeypatch.delenv("HAM_BUILDER_SANDBOX_FAKE_MODE", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_API_KEY", "test-secret-api-key")
    monkeypatch.setattr("src.ham.builder_sandbox_provider.util.find_spec", lambda _name: None)
    client, ws_id, project_id, snapshot_id = _seed_context(tmp_path)
    res = client.post(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/cloud-runtime/jobs",
        json={"source_snapshot_id": snapshot_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"]["status"] == "failed"
    assert body["preview_status"]["status"] != "ready"
    assert body["preview_status"]["preview_url"] is None
    _cleanup()


def test_e2b_healthcheck_direct_success_marks_ready(monkeypatch) -> None:
    provider = E2BSandboxRuntimeProvider(api_key="test-key")
    provider._sandbox_ref = _FakeSandboxRef()
    provider._sandbox_id = "sboxsafe"
    state = _sandbox_state()
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS", "5")
    seen: dict[str, bool] = {"follow_redirects": True}

    def _fake_get(url, timeout, follow_redirects):
        _ = url, timeout
        seen["follow_redirects"] = follow_redirects
        return _FakeHttpResponse(200)

    monkeypatch.setattr("src.ham.builder_sandbox_provider.httpx.get", _fake_get)
    next_state = provider.start_preview_server(state=state, port=3000)
    assert next_state.status == "ready"
    assert next_state.preview_upstream_url == "https://3000-sboxsafe.e2b.app/"
    assert seen["follow_redirects"] is False


def test_e2b_healthcheck_unsafe_redirect_fails(monkeypatch) -> None:
    provider = E2BSandboxRuntimeProvider(api_key="test-key")
    provider._sandbox_ref = _FakeSandboxRef()
    provider._sandbox_id = "sboxsafe"
    state = _sandbox_state()
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(
        "src.ham.builder_sandbox_provider.httpx.get",
        lambda url, timeout, follow_redirects: _FakeHttpResponse(
            302, {"location": "https://evil.example.com/redirect"}
        ),
    )
    next_state = provider.start_preview_server(state=state, port=3000)
    assert next_state.status == "failed"
    assert next_state.error_code == "SANDBOX_PREVIEW_UNSAFE_REDIRECT"
    assert next_state.preview_upstream_url is None


def test_e2b_healthcheck_redirect_with_query_fails(monkeypatch) -> None:
    provider = E2BSandboxRuntimeProvider(api_key="test-key")
    provider._sandbox_ref = _FakeSandboxRef()
    provider._sandbox_id = "sboxsafe"
    state = _sandbox_state()
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(
        "src.ham.builder_sandbox_provider.httpx.get",
        lambda url, timeout, follow_redirects: _FakeHttpResponse(
            302, {"location": "https://3000-sboxsafe.e2b.app/?token=leak"}
        ),
    )
    next_state = provider.start_preview_server(state=state, port=3000)
    assert next_state.status == "failed"
    assert next_state.error_code == "SANDBOX_PREVIEW_UNSAFE_REDIRECT"
    assert next_state.preview_upstream_url is None


def test_e2b_healthcheck_non_https_redirect_fails(monkeypatch) -> None:
    provider = E2BSandboxRuntimeProvider(api_key="test-key")
    provider._sandbox_ref = _FakeSandboxRef()
    provider._sandbox_id = "sboxsafe"
    state = _sandbox_state()
    monkeypatch.setenv("HAM_BUILDER_SANDBOX_START_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(
        "src.ham.builder_sandbox_provider.httpx.get",
        lambda url, timeout, follow_redirects: _FakeHttpResponse(
            302, {"location": "http://3000-sboxsafe.e2b.app/"}
        ),
    )
    next_state = provider.start_preview_server(state=state, port=3000)
    assert next_state.status == "failed"
    assert next_state.error_code == "SANDBOX_PREVIEW_UNSAFE_REDIRECT"
    assert next_state.preview_upstream_url is None
