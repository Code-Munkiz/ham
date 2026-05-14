from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


@dataclass(frozen=True)
class PreviewPodRef:
    namespace: str
    pod_name: str
    service_name: str | None = None
    labels: dict[str, str] | None = None


@dataclass(frozen=True)
class PreviewPodStatus:
    phase: str
    ready: bool
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CleanupResult:
    deleted_pods: int
    deleted_services: int
    skipped: int
    cleanup_status: str


class GkePreviewRuntimeClient(Protocol):
    def create_preview_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef: ...

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus: ...

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus: ...

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None: ...

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool: ...

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict[str, Any] | None = None) -> str | None: ...

    def delete_preview_service(self, *, pod_ref: PreviewPodRef) -> bool: ...

    def cleanup_owned_expired_resources(
        self,
        *,
        resources: list[PreviewPodRef],
        workspace_id: str,
        project_id: str,
        now_iso: str,
    ) -> CleanupResult: ...

    def normalize_error(self, *, error: Exception) -> tuple[str, str]: ...


class FakeGkePreviewRuntimeClient:
    def __init__(self, *, mode: str = "success") -> None:
        self._mode = "failure" if mode == "failure" else "success"
        self._pods: dict[tuple[str, str], dict[str, Any]] = {}

    def create_preview_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef:
        metadata = manifest.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "default")
        pod_name = str(metadata.get("name") or "").strip()
        if not pod_name:
            raise ValueError("manifest metadata.name is required")
        labels_raw = metadata.get("labels") or {}
        labels = {str(k): str(v) for k, v in labels_raw.items()}
        key = (namespace, pod_name)
        self._pods[key] = {
            "phase": "Running" if self._mode == "success" else "Failed",
            "ready": self._mode == "success",
            "logs_summary": (
                "fake gke runtime: pod created, bundle mounted, install/start simulated"
                if self._mode == "success"
                else "fake gke runtime: pod failed before healthy preview"
            ),
            "labels": labels,
        }
        return PreviewPodRef(namespace=namespace, pod_name=pod_name, labels=labels)

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus:
        pod = self._pods.get((pod_ref.namespace, pod_ref.pod_name))
        if pod is None:
            return PreviewPodStatus(
                phase="NotFound",
                ready=False,
                error_code="GCP_GKE_POD_NOT_FOUND",
                error_message="Preview pod was not found.",
            )
        if pod["ready"]:
            return PreviewPodStatus(phase="Running", ready=True)
        return PreviewPodStatus(
            phase="Failed",
            ready=False,
            error_code="GCP_GKE_POD_NOT_READY",
            error_message="Preview pod did not become ready.",
        )

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus:
        _ = timeout_seconds
        return self.get_pod_status(pod_ref=pod_ref)

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None:
        pod = self._pods.get((pod_ref.namespace, pod_ref.pod_name))
        if pod is None:
            return None
        return str(pod.get("logs_summary") or "")[:max_chars]

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool:
        return self._pods.pop((pod_ref.namespace, pod_ref.pod_name), None) is not None

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict[str, Any] | None = None) -> str | None:
        _ = manifest
        return f"{pod_ref.pod_name}-svc"

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
        now = _parse_iso_utc(now_iso) or datetime.now(UTC)
        deleted_pods = 0
        deleted_services = 0
        skipped = 0
        for ref in resources:
            labels = ref.labels or {}
            if labels.get("ham.workspace_id") != workspace_id or labels.get("ham.project_id") != project_id:
                skipped += 1
                continue
            expires = _parse_iso_utc(labels.get("ham.expires_at"))
            if expires is None or expires > now:
                skipped += 1
                continue
            if self.delete_preview_pod(pod_ref=ref):
                deleted_pods += 1
            if ref.service_name and self.delete_preview_service(pod_ref=ref):
                deleted_services += 1
        return CleanupResult(
            deleted_pods=deleted_pods,
            deleted_services=deleted_services,
            skipped=skipped,
            cleanup_status="partial_failure" if skipped else "success",
        )

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_CLIENT_ERROR", "GCP GKE runtime client operation failed safely.")


class LiveGkePreviewRuntimeClient:
    """Live client stub for future Wave C wiring."""

    def create_preview_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef:
        _ = manifest
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus:
        _ = pod_ref
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus:
        _ = pod_ref, timeout_seconds
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None:
        _ = pod_ref, max_chars
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool:
        _ = pod_ref
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict[str, Any] | None = None) -> str | None:
        _ = pod_ref, manifest
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def delete_preview_service(self, *, pod_ref: PreviewPodRef) -> bool:
        _ = pod_ref
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def cleanup_owned_expired_resources(
        self,
        *,
        resources: list[PreviewPodRef],
        workspace_id: str,
        project_id: str,
        now_iso: str,
    ) -> CleanupResult:
        _ = resources, workspace_id, project_id, now_iso
        raise NotImplementedError("Live GKE runtime client is not implemented yet.")

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        _ = error
        return ("GCP_GKE_RUNTIME_CLIENT_ERROR", "GCP GKE runtime client operation failed safely.")


_CLIENT_FACTORY_OVERRIDE: list[Any | None] = [None]


def build_gke_runtime_client() -> GkePreviewRuntimeClient:
    override = _CLIENT_FACTORY_OVERRIDE[0]
    if callable(override):
        return override()
    live_enabled = str(os.environ.get("HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED") or "").strip().lower()
    if live_enabled in {"1", "true", "yes", "on"}:
        return LiveGkePreviewRuntimeClient()
    fake_mode = str(os.environ.get("HAM_BUILDER_GCP_RUNTIME_FAKE_MODE") or "").strip().lower()
    return FakeGkePreviewRuntimeClient(mode="failure" if fake_mode == "failure" else "success")


def set_gke_runtime_client_factory_for_tests(factory: Any | None) -> None:
    _CLIENT_FACTORY_OVERRIDE[0] = factory
