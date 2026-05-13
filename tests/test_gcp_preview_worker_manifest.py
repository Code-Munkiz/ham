"""Tests for GKE preview spike manifest helpers (no cluster calls)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.ham.gcp_preview_worker_manifest import (
    ManifestValidationError,
    build_gke_preview_pod_manifest,
    validate_manifest_inputs,
)


def test_manifest_sets_gvisor_runtime_class() -> None:
    doc = build_gke_preview_pod_manifest(
        workspace_id="ws_demo_alpha",
        project_id="proj_demo_alpha",
        runtime_session_id="rs_demo_alpha",
        namespace="ham-builder-preview-spike",
        bundle_gs_uri="gs://bucket/prefix/preview-source.zip",
        runner_image="us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:spike",
    )
    assert doc["spec"]["runtimeClassName"] == "gvisor"


def test_manifest_resource_limits_present() -> None:
    doc = build_gke_preview_pod_manifest(
        workspace_id="ws_demo_alpha",
        project_id="proj_demo_alpha",
        runtime_session_id="rs_demo_alpha",
        namespace="ham-builder-preview-spike",
        bundle_gs_uri="gs://bucket/prefix/preview-source.zip",
        runner_image="us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:spike",
    )
    limits = doc["spec"]["containers"][0]["resources"]["limits"]
    assert "cpu" in limits and "memory" in limits and "ephemeral-storage" in limits


def test_manifest_ttl_labels_and_no_privileged_hostpath() -> None:
    doc = build_gke_preview_pod_manifest(
        workspace_id="ws_demo_alpha",
        project_id="proj_demo_alpha",
        runtime_session_id="rs_demo_alpha",
        namespace="ham-builder-preview-spike",
        bundle_gs_uri="gs://bucket/prefix/preview-source.zip",
        runner_image="us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:spike",
        ttl_seconds=120,
    )
    labels = doc["metadata"]["labels"]
    assert labels["ham.workspace_id"]
    assert labels["ham.project_id"]
    assert labels["ham.runtime_session_id"]
    assert labels["ham.preview_ttl_seconds"] == "120"
    assert doc["spec"]["automountServiceAccountToken"] is False
    vols = doc["spec"]["volumes"]
    assert any(v.get("emptyDir") == {} for v in vols)
    assert not any("hostPath" in v for v in vols)
    container_sec = doc["spec"]["containers"][0]["securityContext"]
    assert container_sec["allowPrivilegeEscalation"] is False


def test_manifest_rejects_traversal_workspace_id() -> None:
    with pytest.raises(ManifestValidationError):
        validate_manifest_inputs(
            workspace_id="ws/../../../etc",
            project_id="proj_demo_alpha",
            runtime_session_id="rs_demo_alpha",
            namespace="ham-builder-preview-spike",
            bundle_gs_uri="gs://bucket/preview-source.zip",
            runner_image="us-central1-docker.pkg.dev/proj/ham/runner:spike",
        )


def test_manifest_yaml_roundtrip_has_no_bearer_tokens() -> None:
    doc = build_gke_preview_pod_manifest(
        workspace_id="ws_demo_alpha",
        project_id="proj_demo_alpha",
        runtime_session_id="rs_demo_alpha",
        namespace="ham-builder-preview-spike",
        bundle_gs_uri="gs://bucket/prefix/preview-source.zip",
        runner_image="us-central1-docker.pkg.dev/proj/ham/ham-preview-runner:spike",
    )
    dumped = yaml.safe_dump(doc)
    lowered = dumped.lower()
    assert "bearer " not in lowered
    assert "authorization:" not in lowered


def test_manifest_rejects_bundle_with_auth_hints() -> None:
    with pytest.raises(ManifestValidationError):
        validate_manifest_inputs(
            workspace_id="ws_demo_alpha",
            project_id="proj_demo_alpha",
            runtime_session_id="rs_demo_alpha",
            namespace="ham-builder-preview-spike",
            bundle_gs_uri="gs://bucket/obj?token=secret",
            runner_image="us-central1-docker.pkg.dev/proj/ham/runner:spike",
        )


def test_no_e2b_import_modules_under_src_ham_builder_surface() -> None:
    """Guardrail: ``import e2b`` / ``from e2b`` must not return under curated paths."""
    roots = (
        Path("src/ham/builder_runtime_worker.py"),
        Path("src/ham/builder_cloud_runtime_gcp.py"),
        Path("src/ham/builder_chat_cloud_runtime.py"),
        Path("src/ham/builder_sandbox_provider.py"),
        Path("src/ham/gcp_preview_worker_manifest.py"),
    )
    pattern = re.compile(r"^\s*(from\s+e2b\b|import\s+e2b\b)")
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if pattern.match(line):
                raise AssertionError(f"Forbidden e2b import in {path}: {line.strip()}")
