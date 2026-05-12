from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ManifestFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="POSIX relative path inside the working tree")
    sha256: str = Field(min_length=64, max_length=64)


class SnapshotManifest(BaseModel):
    """Serialized as manifest.json beside snapshot blobs."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["ham_managed_snapshot_manifest_v1"] = "ham_managed_snapshot_manifest_v1"
    workspace_id: str
    project_id: str
    snapshot_id: str
    parent_snapshot_id: str | None = None
    created_at: str
    deleted_paths: list[str] = Field(default_factory=list)
    files: list[ManifestFileEntry] = Field(default_factory=list)


class ProjectSnapshot(BaseModel):
    """Indexed row for dashboard/API listing (Firestore or in-memory backend)."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    workspace_id: str
    snapshot_id: str
    parent_snapshot_id: str | None = None
    created_at: str
    bucket: str | None = None
    object_prefix: str = Field(description="Prefix under bucket: ws/proj/snapshots/sid/")
    preview_url: str
    manifest_object: str = Field(description="GCS object name for manifest.json")
    gcs_uri: str | None = Field(default=None, description="Optional gs:// bucket manifest URI")
    changed_paths_count: int = 0
    neutral_outcome: Literal["succeeded", "nothing_to_change"] | None = None


class SnapshotHead(BaseModel):
    """head.json pointing at tip snapshot id."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    updated_at: str


class ManagedHeadJson(BaseModel):
    """Thin wrapper for persisted head.json."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    updated_at: str
