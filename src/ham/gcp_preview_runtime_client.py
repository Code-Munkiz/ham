from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
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


def _parse_label_expires(value: str | None) -> datetime | None:
    parsed = _parse_iso_utc(value)
    if parsed is not None:
        return parsed
    text = str(value or "").strip()
    if not text:
        return None
    text_upper = text.upper()
    if "T" not in text_upper or not text_upper.endswith("Z"):
        return None
    # Support manifest-safe label values like 2026-05-14T04-39-04Z.
    date_part, time_part = text_upper[:-1].split("T", maxsplit=1)
    bits = time_part.split("-")
    if len(bits) != 3:
        return None
    return _parse_iso_utc(f"{date_part}T{bits[0]}:{bits[1]}:{bits[2]}Z")


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


_SENSITIVE_LOG_RE = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+[^\s]+|x-ham-[a-z0-9_-]+\s*:\s*[^\s]+|token=[^\s&]+|cookie:\s*[^\s]+)"
)


def _redact_logs(text: str) -> str:
    return _SENSITIVE_LOG_RE.sub("[redacted]", text)


class _KubeRestError(RuntimeError):
    def __init__(self, *, status: int, reason: str, body: str = "") -> None:
        self.status = status
        self.reason = reason
        self.body = body
        super().__init__(f"kube api request failed: status={status} reason={reason}")


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
    pod_ip: str | None = None


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
            return PreviewPodStatus(phase="Running", ready=True, pod_ip="10.0.0.10")
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
    """Live Kubernetes REST client for GKE preview pods/services."""

    def __init__(self) -> None:
        self._project_id = str(os.environ.get("HAM_BUILDER_GCP_PROJECT_ID") or "").strip()
        self._region = str(os.environ.get("HAM_BUILDER_GCP_REGION") or "").strip()
        self._cluster = str(os.environ.get("HAM_BUILDER_GKE_CLUSTER") or "").strip()
        self._cluster_endpoint: str | None = None
        self._cluster_ca_file: str | None = None
        self._credentials: Any | None = None
        self._auth_request: Any | None = None

    def _require_gke_target(self) -> tuple[str, str, str]:
        if self._project_id and self._region and self._cluster:
            return (self._project_id, self._region, self._cluster)
        raise RuntimeError("GCP GKE runtime target is not configured.")

    def _ensure_google_auth(self) -> tuple[Any, Any]:
        if self._credentials is not None and self._auth_request is not None:
            return self._credentials, self._auth_request
        try:
            import google.auth  # type: ignore[import-not-found]
            from google.auth.transport.requests import Request  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - dependency/runtime guard
            raise RuntimeError("google-auth is required for live GKE runtime calls.") from exc
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self._credentials = creds
        self._auth_request = Request()
        return creds, self._auth_request

    def _refresh_token(self) -> str:
        creds, auth_req = self._ensure_google_auth()
        creds.refresh(auth_req)
        token = str(getattr(creds, "token", "") or "").strip()
        if not token:
            raise RuntimeError("Unable to acquire GCP access token for GKE runtime calls.")
        return token

    def _gke_api_get(self, *, path: str) -> dict[str, Any]:
        token = self._refresh_token()
        url = f"https://container.googleapis.com/v1/{path.lstrip('/')}"
        req = urlrequest.Request(
            url=url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlrequest.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise _KubeRestError(status=exc.code, reason=f"GKE cluster API {exc.reason}", body=body) from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"GKE cluster API unavailable: {exc.reason}") from exc

    def _ensure_cluster_connection(self) -> tuple[str, str]:
        if self._cluster_endpoint and self._cluster_ca_file:
            return self._cluster_endpoint, self._cluster_ca_file
        project, region, cluster = self._require_gke_target()
        payload = self._gke_api_get(path=f"projects/{project}/locations/{region}/clusters/{cluster}")
        endpoint = str(payload.get("endpoint") or "").strip()
        ca_b64 = str(((payload.get("masterAuth") or {}).get("clusterCaCertificate")) or "").strip()
        if not endpoint or not ca_b64:
            raise RuntimeError("GKE cluster endpoint metadata is incomplete.")
        ca_bytes = base64.b64decode(ca_b64.encode("utf-8"))
        with tempfile.NamedTemporaryFile(prefix="ham-gke-ca-", suffix=".crt", delete=False) as tmp:
            tmp.write(ca_bytes)
            ca_path = tmp.name
        self._cluster_endpoint = endpoint
        self._cluster_ca_file = ca_path
        return endpoint, ca_path

    def _kube_request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        endpoint, ca_file = self._ensure_cluster_connection()
        token = self._refresh_token()
        url = f"https://{endpoint}{path}"
        body = None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urlrequest.Request(url=url, headers=headers, data=body, method=method)
        try:
            import ssl

            ctx = ssl.create_default_context(cafile=ca_file)
            with urlrequest.urlopen(req, timeout=timeout_seconds, context=ctx) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urlerror.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise _KubeRestError(status=exc.code, reason=str(exc.reason), body=err_body) from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"Kubernetes API unavailable: {exc.reason}") from exc

    def create_preview_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef:
        metadata = manifest.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "default")
        pod_name = str(metadata.get("name") or "").strip()
        if not pod_name:
            raise ValueError("manifest metadata.name is required")
        try:
            self._kube_request(
                method="POST",
                path=f"/api/v1/namespaces/{urlparse.quote(namespace, safe='')}/pods",
                payload=manifest,
            )
        except _KubeRestError as exc:
            if exc.status != 409:
                raise
        labels_raw = metadata.get("labels") or {}
        labels = {str(k): str(v) for k, v in labels_raw.items()}
        return PreviewPodRef(namespace=namespace, pod_name=pod_name, labels=labels)

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus:
        try:
            payload = self._kube_request(
                method="GET",
                path=(
                    f"/api/v1/namespaces/{urlparse.quote(pod_ref.namespace, safe='')}"
                    f"/pods/{urlparse.quote(pod_ref.pod_name, safe='')}"
                ),
            )
        except _KubeRestError as exc:
            if exc.status == 404:
                return PreviewPodStatus(
                    phase="NotFound",
                    ready=False,
                    error_code="GCP_GKE_POD_NOT_FOUND",
                    error_message="Preview pod was not found.",
                )
            raise
        status = payload.get("status") or {}
        phase = str(status.get("phase") or "Unknown")
        pod_ip = str(status.get("podIP") or "").strip() or None
        conditions = status.get("conditions") or []
        ready = False
        for item in conditions:
            if str((item or {}).get("type") or "") == "Ready" and str((item or {}).get("status") or "") == "True":
                ready = True
                break
        if ready:
            return PreviewPodStatus(phase=phase or "Running", ready=True, pod_ip=pod_ip)
        if phase in {"Failed", "Unknown"}:
            return PreviewPodStatus(
                phase=phase,
                ready=False,
                error_code="GCP_GKE_POD_FAILED",
                error_message="Preview pod entered a failed phase.",
            )
        return PreviewPodStatus(phase=phase, ready=False, pod_ip=pod_ip)

    def poll_pod_ready(self, *, pod_ref: PreviewPodRef, timeout_seconds: int) -> PreviewPodStatus:
        start = time.monotonic()
        timeout = max(5, int(timeout_seconds))
        while True:
            status = self.get_pod_status(pod_ref=pod_ref)
            if status.ready:
                return status
            if status.phase in {"Failed", "Unknown", "Succeeded"}:
                return PreviewPodStatus(
                    phase=status.phase,
                    ready=False,
                    error_code=status.error_code or "GCP_GKE_POD_NOT_READY",
                    error_message=status.error_message or "Preview pod did not become ready.",
                )
            if time.monotonic() - start >= timeout:
                return PreviewPodStatus(
                    phase=status.phase,
                    ready=False,
                    error_code="GCP_GKE_POD_READY_TIMEOUT",
                    error_message="Preview pod did not become ready before timeout.",
                )
            time.sleep(2.0)

    def get_pod_logs_summary(self, *, pod_ref: PreviewPodRef, max_chars: int = 240) -> str | None:
        path = (
            f"/api/v1/namespaces/{urlparse.quote(pod_ref.namespace, safe='')}"
            f"/pods/{urlparse.quote(pod_ref.pod_name, safe='')}/log?tailLines=120"
        )
        try:
            endpoint, ca_file = self._ensure_cluster_connection()
            token = self._refresh_token()
            import ssl

            req = urlrequest.Request(
                url=f"https://{endpoint}{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": "text/plain"},
                method="GET",
            )
            ctx = ssl.create_default_context(cafile=ca_file)
            with urlrequest.urlopen(req, timeout=20, context=ctx) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except _KubeRestError:
            return None
        except urlerror.HTTPError as exc:
            if exc.code == 404:
                return None
            return None
        except Exception:
            return None
        return _redact_logs(text)[: max(0, max_chars)]

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool:
        try:
            self._kube_request(
                method="DELETE",
                path=(
                    f"/api/v1/namespaces/{urlparse.quote(pod_ref.namespace, safe='')}"
                    f"/pods/{urlparse.quote(pod_ref.pod_name, safe='')}"
                ),
            )
            return True
        except _KubeRestError as exc:
            if exc.status == 404:
                return False
            raise

    def create_preview_service(self, *, pod_ref: PreviewPodRef, manifest: dict[str, Any] | None = None) -> str | None:
        _ = manifest
        labels = dict(pod_ref.labels or {})
        runtime_label = str(labels.get("ham.runtime_session_id") or "").strip()
        if not runtime_label:
            return None
        service_name = f"{pod_ref.pod_name[:52]}-svc"
        svc_manifest: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "namespace": pod_ref.namespace,
                "labels": {
                    "app.kubernetes.io/name": "ham-builder-preview",
                    "ham.runtime_session_id": runtime_label,
                    "ham.workspace_id": str(labels.get("ham.workspace_id") or ""),
                    "ham.project_id": str(labels.get("ham.project_id") or ""),
                },
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {"ham.runtime_session_id": runtime_label},
                "ports": [{"name": "http", "port": 80, "targetPort": 3000, "protocol": "TCP"}],
            },
        }
        try:
            self._kube_request(
                method="POST",
                path=f"/api/v1/namespaces/{urlparse.quote(pod_ref.namespace, safe='')}/services",
                payload=svc_manifest,
            )
        except _KubeRestError as exc:
            if exc.status != 409:
                raise
        return service_name

    def delete_preview_service(self, *, pod_ref: PreviewPodRef) -> bool:
        service_name = str(pod_ref.service_name or "").strip()
        if not service_name:
            return False
        try:
            self._kube_request(
                method="DELETE",
                path=(
                    f"/api/v1/namespaces/{urlparse.quote(pod_ref.namespace, safe='')}"
                    f"/services/{urlparse.quote(service_name, safe='')}"
                ),
            )
            return True
        except _KubeRestError as exc:
            if exc.status == 404:
                return False
            raise

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
            labels = dict(ref.labels or {})
            if labels.get("ham.workspace_id") != workspace_id or labels.get("ham.project_id") != project_id:
                skipped += 1
                continue
            expires_at = _parse_label_expires(labels.get("ham.expires_at"))
            if expires_at is None or expires_at > now:
                skipped += 1
                continue
            pod_deleted = False
            with suppress(Exception):
                pod_deleted = self.delete_preview_pod(pod_ref=ref)
            if pod_deleted:
                deleted_pods += 1
            svc_deleted = False
            if ref.service_name:
                with suppress(Exception):
                    svc_deleted = self.delete_preview_service(pod_ref=ref)
            if svc_deleted:
                deleted_services += 1
        return CleanupResult(
            deleted_pods=deleted_pods,
            deleted_services=deleted_services,
            skipped=skipped,
            cleanup_status="success",
        )

    def normalize_error(self, *, error: Exception) -> tuple[str, str]:
        if isinstance(error, _KubeRestError):
            if error.status in {401, 403}:
                return (
                    "GCP_GKE_RBAC_DENIED",
                    "GCP GKE runtime access was denied by Kubernetes API authorization.",
                )
            if error.status == 404:
                return (
                    "GCP_GKE_RESOURCE_NOT_FOUND",
                    "GCP GKE runtime resource was not found.",
                )
            if error.status == 409:
                return (
                    "GCP_GKE_RESOURCE_CONFLICT",
                    "GCP GKE runtime resource already exists or conflicts with current state.",
                )
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
