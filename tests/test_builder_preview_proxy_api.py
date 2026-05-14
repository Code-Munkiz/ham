from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.builder_sources import router as builder_sources_router
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.workspace_models import WorkspaceMember, WorkspaceRecord
from src.persistence.builder_runtime_store import (
    BuilderRuntimeStore,
    PreviewEndpoint,
    RuntimeSession,
    set_builder_runtime_store_for_tests,
)
from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests
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


def _seed_context(tmp_path: Path) -> tuple[TestClient, str, str, BuilderRuntimeStore]:
    ws_store = InMemoryWorkspaceStore()
    ws_id = "ws_aaaaaaaaaaaaaaaa"
    _seed_workspace(ws_store, workspace_id=ws_id, org_id="org_a", owner_user_id="user_a", slug="alpha")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    project = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_id})
    project_store.register(project)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    return client, ws_id, project.id, runtime_store


def _seed_cloud_runtime(runtime_store: BuilderRuntimeStore, *, ws_id: str, project_id: str) -> RuntimeSession:
    runtime = runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_id,
            project_id=project_id,
            mode="cloud",
            status="running",
            health="unknown",
        )
    )
    return runtime


def _cleanup() -> None:
    set_project_store_for_tests(None)
    set_builder_source_store_for_tests(None)
    set_builder_runtime_store_for_tests(None)


def test_proxy_no_endpoint_returns_not_configured(tmp_path: Path) -> None:
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/index.html")
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PREVIEW_PROXY_NOT_CONFIGURED"
    _cleanup()


def test_proxy_local_url_endpoint_is_not_proxied(tmp_path: Path) -> None:
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="local_url",
            status="ready",
            url="http://localhost:3000/",
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PREVIEW_PROXY_NOT_CONFIGURED"
    _cleanup()


@pytest.mark.parametrize(
    "upstream",
    [
        "https://evil.example.com/app",
        "https://user:pass@safe.run.app/",
        "https://127.0.0.1/",
        "https://10.0.0.8/app",
    ],
)
def test_proxy_rejects_unsafe_or_credentialed_upstream(tmp_path: Path, upstream: str) -> None:
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url=upstream,
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "PREVIEW_PROXY_UNSAFE_UPSTREAM"
    _cleanup()


def test_proxy_safe_run_app_host_accepted_and_headers_stripped(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_fetch(*, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        return httpx.Response(200, content=b"<html>ok</html>", headers={"content-type": "text/html"})

    monkeypatch.setattr("src.api.builder_sources._proxy_upstream_fetch", _fake_fetch)
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="https://ham-preview-123.run.app/base",
            metadata={"trusted_proxy_host": "ham-preview-123.run.app"},
        )
    )
    res = client.get(
        f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/assets/app.js?x=1",
        headers={
            "Authorization": "Bearer secret",
            "Cookie": "sid=abc",
            "X-HAM-Token": "hidden",
            "Accept": "text/html",
            "User-Agent": "pytest-client",
        },
    )
    assert res.status_code == 200, res.text
    assert res.text == "<html>ok</html>"
    assert captured["method"] == "GET"
    forwarded = captured["headers"]
    assert isinstance(forwarded, dict)
    assert "authorization" not in {key.lower() for key in forwarded.keys()}
    assert "cookie" not in {key.lower() for key in forwarded.keys()}
    assert "accept" in {key.lower() for key in forwarded.keys()}
    _cleanup()


def test_proxy_accepts_provider_owned_internal_upstream_only_server_side(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_fetch(*, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    monkeypatch.setattr("src.api.builder_sources._proxy_upstream_fetch", _fake_fetch)
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="http://10.10.20.20:3000/",
            metadata={"provider": "gcp_gke_sandbox", "internal_upstream": True},
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 200, res.text
    assert captured["method"] == "GET"
    assert str(captured["url"]).startswith("http://10.10.20.20:3000/")
    _cleanup()


def test_proxy_timeout_maps_to_safe_error(tmp_path: Path, monkeypatch) -> None:
    async def _timeout_fetch(*, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        _ = (method, url, headers)
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("src.api.builder_sources._proxy_upstream_fetch", _timeout_fetch)
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="https://ham-preview-123.run.app/",
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 504
    assert res.json()["detail"]["error"]["code"] == "PREVIEW_PROXY_TIMEOUT"
    _cleanup()


def test_proxy_scope_enforced_no_cross_project_leak(tmp_path: Path) -> None:
    ws_store = InMemoryWorkspaceStore()
    ws_a = "ws_aaaaaaaaaaaaaaaa"
    ws_b = "ws_bbbbbbbbbbbbbbbb"
    _seed_workspace(ws_store, workspace_id=ws_a, org_id="org_a", owner_user_id="user_a", slug="alpha")
    _seed_workspace(ws_store, workspace_id=ws_b, org_id="org_b", owner_user_id="user_b", slug="beta")
    project_store = ProjectStore(store_path=tmp_path / "projects.json")
    p_a = project_store.make_record(name="proj-a", root=str(tmp_path), metadata={"workspace_id": ws_a})
    p_b = project_store.make_record(name="proj-b", root=str(tmp_path), metadata={"workspace_id": ws_b})
    project_store.register(p_a)
    project_store.register(p_b)
    set_project_store_for_tests(project_store)
    set_builder_source_store_for_tests(BuilderSourceStore(store_path=tmp_path / "builder_sources.json"))
    runtime_store = BuilderRuntimeStore(store_path=tmp_path / "builder_runtime.json")
    runtime = runtime_store.upsert_runtime_session(
        RuntimeSession(
            workspace_id=ws_b,
            project_id=p_b.id,
            mode="cloud",
            status="running",
            health="unknown",
        )
    )
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_b,
            project_id=p_b.id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="https://ham-preview-123.run.app/",
        )
    )
    set_builder_runtime_store_for_tests(runtime_store)
    client = TestClient(_build_app(actor=_actor("user_a", org_id="org_a"), ws_store=ws_store))
    forbidden = client.get(f"/api/workspaces/{ws_b}/projects/{p_b.id}/builder/preview-proxy/")
    wrong_workspace = client.get(f"/api/workspaces/{ws_a}/projects/{p_b.id}/builder/preview-proxy/")
    assert forbidden.status_code == 403
    assert wrong_workspace.status_code == 404
    _cleanup()


def test_proxy_does_not_execute_processes(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    async def _fake_fetch(*, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
        _ = (method, url, headers)
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("preview proxy must not execute shell/processes")

    monkeypatch.setattr("src.api.builder_sources._proxy_upstream_fetch", _fake_fetch)
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="https://ham-preview-123.run.app/",
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 200
    _cleanup()


def test_proxy_rejects_internal_upstream_with_query_tokens_even_when_provider_owned(
    tmp_path: Path,
) -> None:
    client, ws_id, project_id, runtime_store = _seed_context(tmp_path)
    runtime = _seed_cloud_runtime(runtime_store, ws_id=ws_id, project_id=project_id)
    runtime_store.upsert_preview_endpoint(
        PreviewEndpoint(
            workspace_id=ws_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
            access_mode="proxy",
            status="ready",
            url="http://10.10.20.20:3000/?token=secret",
            metadata={"provider": "gcp_gke_sandbox", "internal_upstream": True},
        )
    )
    res = client.get(f"/api/workspaces/{ws_id}/projects/{project_id}/builder/preview-proxy/")
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "PREVIEW_PROXY_UNSAFE_UPSTREAM"
    _cleanup()
