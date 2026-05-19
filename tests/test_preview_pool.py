"""Tests for src/ham/preview_pool.py — Phase 1 #7."""

from __future__ import annotations

from src.ham.gcp_preview_runtime_client import FakeGkePreviewRuntimeClient
from src.ham.gcp_preview_worker_manifest import build_gke_preview_pod_manifest
from src.ham.preview_pool import PreviewAcquireSpec, PreviewPool, set_preview_pool_for_tests


def _sample_manifest(*, pod_name: str = "pod-live", namespace: str = "ns-a") -> dict:
    return {
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/name": "ham-builder-preview",
                "ham.workspace_id": "ws1",
                "ham.project_id": "proj1",
            },
        }
    }


def _warm_template() -> dict:
    return build_gke_preview_pod_manifest(
        workspace_id="ws1",
        project_id="proj1",
        runtime_session_id="rt1",
        namespace="ns-a",
        bundle_gs_uri="gs://bucket/obj.zip",
        runner_image="us-central1-docker.pkg.dev/proj/runner:tag",
        preview_port=5173,
        ttl_seconds=900,
    )


class TestPreviewPool:
    def setup_method(self) -> None:
        set_preview_pool_for_tests(None)

    def teardown_method(self) -> None:
        set_preview_pool_for_tests(None)

    def test_empty_pool_acquires_fresh(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        pool = PreviewPool(client, target_pool_size=2)
        spec = PreviewAcquireSpec(manifest=_sample_manifest())
        ref = pool.acquire(spec)
        assert ref.pod_name == "pod-live"
        assert pool.current_pool_size() == 0

    def test_populated_pool_acquires_warm(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        pool = PreviewPool(client, target_pool_size=2)
        ref = client.create_preview_pod(manifest=_sample_manifest(pod_name="warm-1"))
        pool.release(ref)
        assert pool.current_pool_size() == 1
        acquired = pool.acquire(PreviewAcquireSpec(manifest=_sample_manifest(pod_name="other")))
        assert acquired.pod_name == "warm-1"

    def test_release_returns_pod_to_pool(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        pool = PreviewPool(client, target_pool_size=2)
        ref = client.create_preview_pod(manifest=_sample_manifest())
        pool.release(ref)
        assert pool.current_pool_size() == 1

    def test_maintain_acquires_up_to_target(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        template = _warm_template()
        pool = PreviewPool(client, target_pool_size=2, warm_manifest_template=template)
        pool.maintain(namespace="ns-a")
        assert pool.current_pool_size() == 2

    def test_maintain_expires_idle_above_target(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        pool = PreviewPool(client, target_pool_size=1, warm_manifest_template=_warm_template())
        pool.maintain(namespace="ns-a")
        assert pool.current_pool_size() == 1
        pool.target_pool_size = 0
        pool.maintain(namespace="ns-a")
        assert pool.current_pool_size() == 0

    def test_reconstruct_from_gke_inventory(self) -> None:
        client = FakeGkePreviewRuntimeClient(mode="success")
        manifest = _sample_manifest(pod_name="idle-1")
        manifest["metadata"]["labels"]["ham.preview_pool"] = "idle"
        client.create_preview_pod(manifest=manifest)
        pool = PreviewPool(client, target_pool_size=2)
        pool.reconstruct_from_inventory(namespace="ns-a")
        assert pool.current_pool_size() == 1

    def test_warm_manifest_retains_security_spec(self) -> None:
        template = _warm_template()
        assert template["spec"]["runtimeClassName"] == "gvisor"
        pod_sc = template["spec"]["securityContext"]
        assert pod_sc["runAsNonRoot"] is True
        container_sc = template["spec"]["containers"][0]["securityContext"]
        assert container_sc["runAsNonRoot"] is True
        assert container_sc["capabilities"]["drop"] == ["ALL"]
        assert container_sc["allowPrivilegeEscalation"] is False
