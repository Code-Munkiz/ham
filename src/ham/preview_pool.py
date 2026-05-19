"""Prewarmed preview pod pool — Phase 1 #7 (Tier 1 #18).

Maintains idle warm pods to reduce cold-start latency. The GKE client sits
behind a Protocol so tests substitute fakes without network I/O.

Spec: docs/MANUS_PARITY_ROADMAP.md § Tier 1 #18
"""

from __future__ import annotations

import copy
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.ham.gcp_preview_runtime_client import PreviewPodRef, PreviewPodStatus

logger = logging.getLogger(__name__)

_POOL_IDLE_LABEL = "ham.preview_pool"
_POOL_IDLE_VALUE = "idle"


@dataclass(frozen=True)
class PreviewAcquireSpec:
    manifest: dict[str, Any]


@runtime_checkable
class GkePoolClientProtocol(Protocol):
    def list_preview_pods(self, *, namespace: str) -> list[dict[str, Any]]: ...

    def create_preview_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef: ...

    def get_pod_status(self, *, pod_ref: PreviewPodRef) -> PreviewPodStatus: ...

    def delete_preview_pod(self, *, pod_ref: PreviewPodRef) -> bool: ...


@dataclass
class _IdlePod:
    ref: PreviewPodRef
    touched_at: float = field(default_factory=time.monotonic)


class PreviewPool:
    """In-memory warm pool with optional GKE inventory reconciliation."""

    def __init__(
        self,
        client: GkePoolClientProtocol,
        *,
        target_pool_size: int = 2,
        warm_manifest_template: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._target_pool_size = max(0, int(target_pool_size))
        self._warm_manifest_template = warm_manifest_template
        self._idle: dict[tuple[str, str], _IdlePod] = {}

    @property
    def target_pool_size(self) -> int:
        return self._target_pool_size

    @target_pool_size.setter
    def target_pool_size(self, value: int) -> None:
        self._target_pool_size = max(0, int(value))

    def current_pool_size(self) -> int:
        return len(self._idle)

    def acquire(self, spec: PreviewAcquireSpec) -> PreviewPodRef:
        metadata = spec.manifest.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "default")
        for key, entry in list(self._idle.items()):
            if key[0] != namespace:
                continue
            self._idle.pop(key)
            logger.info(
                "preview_pool_acquire_warm namespace=%s pod=%s",
                namespace,
                entry.ref.pod_name,
            )
            return entry.ref
        logger.info("preview_pool_acquire_fresh namespace=%s", namespace)
        return self._client.create_preview_pod(manifest=spec.manifest)

    def release(self, pod: PreviewPodRef) -> None:
        if self.current_pool_size() >= self.target_pool_size:
            logger.info(
                "preview_pool_release_retire namespace=%s pod=%s",
                pod.namespace,
                pod.pod_name,
            )
            self._client.delete_preview_pod(pod_ref=pod)
            return
        key = (pod.namespace, pod.pod_name)
        self._idle[key] = _IdlePod(ref=pod)
        logger.info(
            "preview_pool_release_idle namespace=%s pod=%s pool_size=%d",
            pod.namespace,
            pod.pod_name,
            self.current_pool_size(),
        )

    def reconstruct_from_inventory(self, *, namespace: str) -> None:
        """Rebuild idle entries from GKE pods labeled as pool idle."""
        self._idle.clear()
        for item in self._client.list_preview_pods(namespace=namespace):
            meta = item.get("metadata") or {}
            labels = {str(k): str(v) for k, v in (meta.get("labels") or {}).items()}
            if labels.get(_POOL_IDLE_LABEL) != _POOL_IDLE_VALUE:
                continue
            pod_name = str(meta.get("name") or "").strip()
            if not pod_name:
                continue
            ref = PreviewPodRef(namespace=namespace, pod_name=pod_name, labels=labels)
            self._idle[(namespace, pod_name)] = _IdlePod(ref=ref)
        logger.info(
            "preview_pool_reconstructed namespace=%s pool_size=%d",
            namespace,
            self.current_pool_size(),
        )

    def maintain(self, *, namespace: str) -> None:
        """Compare idle stock to target; fill shortfall or retire excess idle pods."""
        self.reconstruct_from_inventory(namespace=namespace)
        while self.current_pool_size() < self.target_pool_size:
            manifest = self._build_warm_manifest(namespace=namespace)
            if manifest is None:
                break
            ref = self._create_warm_pod(manifest=manifest)
            self._idle[(ref.namespace, ref.pod_name)] = _IdlePod(ref=ref)
            logger.info(
                "preview_pool_maintain_acquire namespace=%s pod=%s",
                namespace,
                ref.pod_name,
            )
        while self.current_pool_size() > self.target_pool_size:
            key, entry = next(iter(self._idle.items()))
            self._idle.pop(key)
            self._client.delete_preview_pod(pod_ref=entry.ref)
            logger.info(
                "preview_pool_maintain_expire namespace=%s pod=%s",
                entry.ref.namespace,
                entry.ref.pod_name,
            )

    def _create_warm_pod(self, *, manifest: dict[str, Any]) -> PreviewPodRef:
        """Create a warm pod without re-entering pool.acquire (avoids recursion)."""
        direct = getattr(self._client, "_create_preview_pod_direct", None)
        if callable(direct):
            return direct(manifest=manifest)
        return self._client.create_preview_pod(manifest=manifest)

    def _build_warm_manifest(self, *, namespace: str) -> dict[str, Any] | None:
        if self._warm_manifest_template is None:
            return None
        manifest = copy.deepcopy(self._warm_manifest_template)
        metadata = dict(manifest.get("metadata") or {})
        metadata["namespace"] = namespace
        metadata["name"] = f"pool-warm-{uuid.uuid4().hex[:10]}"
        labels = dict(metadata.get("labels") or {})
        labels[_POOL_IDLE_LABEL] = _POOL_IDLE_VALUE
        labels.setdefault("app.kubernetes.io/name", "ham-builder-preview")
        metadata["labels"] = labels
        manifest["metadata"] = metadata
        return manifest


_POOL_SINGLETON: list[PreviewPool | None] = [None]


def preview_pool_target_size() -> int:
    raw = os.environ.get("HAM_BUILDER_PREVIEW_POOL_TARGET_SIZE", "0")
    try:
        return max(0, int(str(raw).strip()))
    except ValueError:
        return 0


def get_preview_pool(client: GkePoolClientProtocol | None = None) -> PreviewPool | None:
    target = preview_pool_target_size()
    if target <= 0:
        return None
    if _POOL_SINGLETON[0] is None:
        if client is None:
            return None
        _POOL_SINGLETON[0] = PreviewPool(client, target_pool_size=target)
    return _POOL_SINGLETON[0]


def set_preview_pool_for_tests(pool: PreviewPool | None) -> None:
    _POOL_SINGLETON[0] = pool
