"""Pure helpers for GKE preview spike manifests — no Kubernetes API calls.

Used by ``scripts/builder/render_gke_preview_manifest.py`` and tests only until the
live ``gcp_gke_sandbox`` provider lands.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

_SAFE_ID_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,126}[a-zA-Z0-9]$")
_NS_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,251}[a-z0-9])?$")


class ManifestValidationError(ValueError):
    """Unsafe or invalid spike manifest inputs."""


def _utc_iso_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_dns_label(value: str, *, max_len: int = 63) -> str:
    """Lowercase RFC-ish DNS label fragment for Pod names."""
    base = "".join(ch if ch.isalnum() else "-" for ch in value.strip().lower())
    base = re.sub(r"-+", "-", base).strip("-")[:max_len]
    if not base:
        raise ManifestValidationError("sanitized label became empty")
    if base[0] == "-" or base[-1] == "-":
        base = base.strip("-") or "x"
    return base[:max_len]


def validate_manifest_inputs(
    *,
    workspace_id: str,
    project_id: str,
    runtime_session_id: str,
    namespace: str,
    bundle_gs_uri: str,
    runner_image: str,
    preview_port: int = 3000,
) -> None:
    """Reject pathological identifiers and obviously unsafe URIs."""
    for raw, label in (
        (workspace_id, "workspace_id"),
        (project_id, "project_id"),
        (runtime_session_id, "runtime_session_id"),
    ):
        text = raw.strip()
        if not text:
            raise ManifestValidationError(f"{label} must be non-empty")
        if "\n" in text or "\r" in text:
            raise ManifestValidationError(f"{label} must not contain newlines")
        if any(ch in text for ch in ("..", "`", "$", "|", ";", "&", "<", ">")):
            raise ManifestValidationError(f"{label} contains forbidden characters")
        if not _SAFE_ID_SEGMENT_RE.match(text):
            raise ManifestValidationError(f"{label} has invalid characters or length")

    ns = namespace.strip()
    if not ns or len(ns) > 253:
        raise ManifestValidationError("namespace looks invalid")
    if not _NS_RE.match(ns):
        raise ManifestValidationError("namespace must be DNS-compatible lowercase")

    bundle = bundle_gs_uri.strip()
    if not bundle.startswith("gs://"):
        raise ManifestValidationError("bundle_gs_uri must start with gs://")
    if any(tok in bundle.lower() for tok in ("bearer ", "authorization:", "secret")):
        raise ManifestValidationError("bundle_gs_uri must not embed credential hints")

    img = runner_image.strip()
    if not img:
        raise ManifestValidationError("runner_image must be non-empty")
    if img.startswith(("Bearer ", "bearer ", "gs://")):
        raise ManifestValidationError("runner_image must be an image reference")

    if preview_port < 1 or preview_port > 65535:
        raise ManifestValidationError("preview_port out of range")


def build_gke_preview_pod_manifest(
    *,
    workspace_id: str,
    project_id: str,
    runtime_session_id: str,
    namespace: str,
    bundle_gs_uri: str,
    runner_image: str,
    preview_port: int = 3000,
    ttl_seconds: int = 3600,
    cpu_limit: str = "2",
    memory_limit: str = "2Gi",
    ephemeral_storage_limit: str = "10Gi",
    cpu_request: str = "250m",
    memory_request: str = "512Mi",
    ephemeral_storage_request: str = "2Gi",
    pod_name_prefix: str = "ham-preview",
    service_account_name: str = "ham-preview-runner",
    preview_deploy_id: str | None = None,
) -> dict[str, Any]:
    """
    Build a Pod manifest suitable for GKE Sandbox / gVisor (runtimeClassName ``gvisor``).

    Does not mount secrets or hostPath; uses ``emptyDir`` for workspace scratch.
    """
    validate_manifest_inputs(
        workspace_id=workspace_id,
        project_id=project_id,
        runtime_session_id=runtime_session_id,
        namespace=namespace,
        bundle_gs_uri=bundle_gs_uri,
        runner_image=runner_image,
        preview_port=preview_port,
    )
    if ttl_seconds < 60 or ttl_seconds > 86400 * 7:
        raise ManifestValidationError("ttl_seconds must be between 60 and 604800")

    expires_iso = (
        (datetime.now(UTC) + timedelta(seconds=ttl_seconds))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    deploy_tag = ""
    raw_seed = runtime_session_id
    if preview_deploy_id and str(preview_deploy_id).strip():
        deploy_tag = sanitize_dns_label(str(preview_deploy_id).strip(), max_len=28)
        raw_seed = f"{runtime_session_id}-{deploy_tag}"
    name_seed = sanitize_dns_label(raw_seed, max_len=48)
    pod_name = sanitize_dns_label(f"{pod_name_prefix}-{name_seed}", max_len=63)

    labels = {
        "app.kubernetes.io/name": "ham-builder-preview",
        "app.kubernetes.io/component": "preview-worker-spike",
        "ham.workspace_id": sanitize_dns_label(workspace_id, max_len=63),
        "ham.project_id": sanitize_dns_label(project_id, max_len=63),
        "ham.runtime_session_id": sanitize_dns_label(runtime_session_id, max_len=63),
        "ham.expires_at": sanitize_dns_label(expires_iso.replace(":", "-"), max_len=63),
        "ham.preview_ttl_seconds": str(ttl_seconds),
    }
    if deploy_tag:
        labels["ham.preview_deploy_id"] = deploy_tag[:63]

    annotations = {
        "ham.dev/source-bundle-uri": bundle_gs_uri[:2048],
        "ham.dev/preview-port": str(preview_port),
    }

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace.strip(),
            "labels": labels,
            "annotations": annotations,
        },
        "spec": {
            "runtimeClassName": "gvisor",
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "serviceAccountName": service_account_name.strip()[:253],
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "runAsGroup": 1000,
                "fsGroup": 1000,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                {
                    "name": "preview-runner",
                    "image": runner_image.strip(),
                    "imagePullPolicy": "IfNotPresent",
                    "ports": [{"containerPort": preview_port, "protocol": "TCP"}],
                    "env": [
                        {"name": "PREVIEW_PORT", "value": str(preview_port)},
                        {"name": "PREVIEW_SOURCE_URI", "value": bundle_gs_uri.strip()},
                        {"name": "HAM_PREVIEW_SPIKE_RENDERED_AT", "value": _utc_iso_z()},
                    ],
                    "resources": {
                        "limits": {
                            "cpu": cpu_limit,
                            "memory": memory_limit,
                            "ephemeral-storage": ephemeral_storage_limit,
                        },
                        "requests": {
                            "cpu": cpu_request,
                            "memory": memory_request,
                            "ephemeral-storage": ephemeral_storage_request,
                        },
                    },
                    "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"}],
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": False,
                        "capabilities": {"drop": ["ALL"]},
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                    },
                },
            ],
            "volumes": [{"name": "workspace", "emptyDir": {}}],
        },
    }
