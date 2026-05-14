from __future__ import annotations

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from typing import Protocol

from src.ham.builder_sandbox_provider import SandboxSourceFile


@dataclass(frozen=True)
class SourceBundlePackage:
    object_name: str
    payload: bytes
    sha256: str
    file_count: int


@dataclass(frozen=True)
class SourceBundleUploadOutcome:
    uri: str
    uploaded: bool
    sha256: str
    file_count: int
    byte_size: int


class SourceBundleUploader(Protocol):
    def upload_bundle(self, *, bucket: str, object_name: str, payload: bytes) -> SourceBundleUploadOutcome: ...


def _normalize_rel_path(raw_path: str) -> str:
    rel = raw_path.replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("source file path is empty")
    if ".." in rel.split("/"):
        raise ValueError(f"unsafe source file path: {raw_path}")
    return rel


def build_bundle_object_name(*, workspace_id: str, project_id: str, runtime_job_id: str) -> str:
    ws = workspace_id.replace("/", "-").replace("\\", "-").strip("-") or "ws"
    proj = project_id.replace("/", "-").replace("\\", "-").strip("-") or "proj"
    job = runtime_job_id.replace("/", "-").replace("\\", "-").strip("-") or "job"
    return f"builder-preview-runtime/{ws}/{proj}/{job}/preview-source.zip"


def package_source_files_to_zip(
    *,
    files: list[SandboxSourceFile],
    workspace_id: str,
    project_id: str,
    runtime_job_id: str,
) -> SourceBundlePackage:
    if not files:
        raise ValueError("source file list is empty")
    object_name = build_bundle_object_name(
        workspace_id=workspace_id,
        project_id=project_id,
        runtime_job_id=runtime_job_id,
    )
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(files, key=lambda row: row.path):
            rel = _normalize_rel_path(item.path)
            zf.writestr(rel, item.data)
    payload = mem.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    return SourceBundlePackage(
        object_name=object_name,
        payload=payload,
        sha256=digest,
        file_count=len(files),
    )


class PlanningSourceBundleUploader:
    """Safe default: generate bundle URI without mutating cloud state."""

    def upload_bundle(self, *, bucket: str, object_name: str, payload: bytes) -> SourceBundleUploadOutcome:
        digest = hashlib.sha256(payload).hexdigest()
        return SourceBundleUploadOutcome(
            uri=f"gs://{bucket.strip().strip('/')}/{object_name}",
            uploaded=False,
            sha256=digest,
            file_count=0,
            byte_size=len(payload),
        )


class GcsSourceBundleUploader:
    def __init__(self) -> None:
        from google.cloud import storage  # import lazily

        self._client = storage.Client()

    def upload_bundle(self, *, bucket: str, object_name: str, payload: bytes) -> SourceBundleUploadOutcome:
        bucket_name = bucket.strip().strip("/")
        blob = self._client.bucket(bucket_name).blob(object_name)
        blob.upload_from_string(payload, content_type="application/zip")
        digest = hashlib.sha256(payload).hexdigest()
        return SourceBundleUploadOutcome(
            uri=f"gs://{bucket_name}/{object_name}",
            uploaded=True,
            sha256=digest,
            file_count=0,
            byte_size=len(payload),
        )


_UPLOADER_FACTORY_OVERRIDE: list[object | None] = [None]


def build_source_bundle_uploader() -> SourceBundleUploader:
    override = _UPLOADER_FACTORY_OVERRIDE[0]
    if callable(override):
        return override()
    live_upload = str(os.environ.get("HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD") or "").strip().lower()
    if live_upload in {"1", "true", "yes", "on"}:
        return GcsSourceBundleUploader()
    return PlanningSourceBundleUploader()


def set_source_bundle_uploader_factory_for_tests(factory: object | None) -> None:
    _UPLOADER_FACTORY_OVERRIDE[0] = factory
