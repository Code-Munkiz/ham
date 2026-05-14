from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MethodType

from src.ham.gcp_preview_runtime_client import (
    FakeGkePreviewRuntimeClient,
    LiveGkePreviewRuntimeClient,
    PreviewPodRef,
    build_gke_runtime_client,
    set_gke_runtime_client_factory_for_tests,
)


def test_fake_client_success_create_and_ready() -> None:
    client = FakeGkePreviewRuntimeClient(mode="success")
    ref = client.create_preview_pod(
        manifest={
            "metadata": {
                "name": "pod-a",
                "namespace": "ns-a",
                "labels": {
                    "ham.workspace_id": "ws1",
                    "ham.project_id": "proj1",
                    "ham.expires_at": "2000-01-01T00:00:00Z",
                },
            }
        }
    )
    status = client.poll_pod_ready(pod_ref=ref, timeout_seconds=30)
    assert status.ready is True
    assert status.phase == "Running"
    assert client.get_pod_logs_summary(pod_ref=ref)


def test_fake_client_failure_status() -> None:
    client = FakeGkePreviewRuntimeClient(mode="failure")
    ref = client.create_preview_pod(
        manifest={"metadata": {"name": "pod-f", "namespace": "ns-f", "labels": {}}}
    )
    status = client.poll_pod_ready(pod_ref=ref, timeout_seconds=30)
    assert status.ready is False
    assert status.error_code == "GCP_GKE_POD_NOT_READY"


def test_cleanup_deletes_only_owned_and_expired() -> None:
    client = FakeGkePreviewRuntimeClient(mode="success")
    now = datetime.now(UTC).replace(microsecond=0)
    expired = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    future = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    owned_expired = PreviewPodRef(
        namespace="ns",
        pod_name="pod-1",
        service_name="svc-1",
        labels={
            "ham.workspace_id": "ws",
            "ham.project_id": "proj",
            "ham.expires_at": expired,
        },
    )
    owned_future = PreviewPodRef(
        namespace="ns",
        pod_name="pod-2",
        service_name="svc-2",
        labels={
            "ham.workspace_id": "ws",
            "ham.project_id": "proj",
            "ham.expires_at": future,
        },
    )
    other = PreviewPodRef(
        namespace="ns",
        pod_name="pod-3",
        service_name="svc-3",
        labels={
            "ham.workspace_id": "ws-other",
            "ham.project_id": "proj",
            "ham.expires_at": expired,
        },
    )
    client.create_preview_pod(
        manifest={"metadata": {"name": "pod-1", "namespace": "ns", "labels": dict(owned_expired.labels or {})}}
    )
    client.create_preview_pod(
        manifest={"metadata": {"name": "pod-2", "namespace": "ns", "labels": dict(owned_future.labels or {})}}
    )
    client.create_preview_pod(
        manifest={"metadata": {"name": "pod-3", "namespace": "ns", "labels": dict(other.labels or {})}}
    )
    result = client.cleanup_owned_expired_resources(
        resources=[owned_expired, owned_future, other],
        workspace_id="ws",
        project_id="proj",
        now_iso=now.isoformat().replace("+00:00", "Z"),
    )
    assert result.deleted_pods == 1
    assert result.deleted_services == 1
    assert result.skipped == 2


def test_build_runtime_client_override() -> None:
    set_gke_runtime_client_factory_for_tests(lambda: FakeGkePreviewRuntimeClient(mode="failure"))
    try:
        client = build_gke_runtime_client()
        assert isinstance(client, FakeGkePreviewRuntimeClient)
    finally:
        set_gke_runtime_client_factory_for_tests(None)


def test_build_runtime_client_uses_live_gate(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED", "false")
    client = build_gke_runtime_client()
    assert isinstance(client, FakeGkePreviewRuntimeClient)
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED", "true")
    client_live = build_gke_runtime_client()
    assert isinstance(client_live, LiveGkePreviewRuntimeClient)


def test_live_client_constructs_without_cluster_access(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_GCP_PROJECT_ID", "proj")
    monkeypatch.setenv("HAM_BUILDER_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_GKE_CLUSTER", "cluster")
    client = LiveGkePreviewRuntimeClient()
    assert isinstance(client, LiveGkePreviewRuntimeClient)


def test_live_client_poll_timeout_without_ready() -> None:
    client = LiveGkePreviewRuntimeClient()

    def _always_pending(self, *, pod_ref: PreviewPodRef):  # type: ignore[no-untyped-def]
        _ = pod_ref
        return type("Status", (), {"phase": "Pending", "ready": False, "error_code": None, "error_message": None})()

    client.get_pod_status = MethodType(_always_pending, client)  # type: ignore[method-assign]
    status = client.poll_pod_ready(
        pod_ref=PreviewPodRef(namespace="ns", pod_name="pod"),
        timeout_seconds=1,
    )
    assert status.ready is False
    assert status.error_code == "GCP_GKE_POD_READY_TIMEOUT"


def test_live_client_service_requires_runtime_label() -> None:
    client = LiveGkePreviewRuntimeClient()
    ref = PreviewPodRef(namespace="ns", pod_name="pod-no-label", labels={"ham.workspace_id": "ws"})
    assert client.create_preview_service(pod_ref=ref) is None


def test_live_client_cleanup_parses_manifest_safe_expiry_label(monkeypatch) -> None:
    client = LiveGkePreviewRuntimeClient()
    deleted: list[str] = []

    def _del_pod(self, *, pod_ref: PreviewPodRef):  # type: ignore[no-untyped-def]
        deleted.append(f"pod:{pod_ref.pod_name}")
        return True

    def _del_svc(self, *, pod_ref: PreviewPodRef):  # type: ignore[no-untyped-def]
        deleted.append(f"svc:{pod_ref.service_name}")
        return True

    client.delete_preview_pod = MethodType(_del_pod, client)  # type: ignore[method-assign]
    client.delete_preview_service = MethodType(_del_svc, client)  # type: ignore[method-assign]

    now = datetime.now(UTC).replace(microsecond=0)
    expired_label = (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z").replace(":", "-")
    result = client.cleanup_owned_expired_resources(
        resources=[
            PreviewPodRef(
                namespace="ns",
                pod_name="pod1",
                service_name="svc1",
                labels={
                    "ham.workspace_id": "ws",
                    "ham.project_id": "proj",
                    "ham.expires_at": expired_label,
                },
            )
        ],
        workspace_id="ws",
        project_id="proj",
        now_iso=now.isoformat().replace("+00:00", "Z"),
    )
    assert result.deleted_pods == 1
    assert result.deleted_services == 1
    assert "pod:pod1" in deleted
