"""Local / GCS-optional cleanup adjuncts on workspace archival."""

from __future__ import annotations

from pathlib import Path

from src.ham.workspace_purge import (
    purge_gcs_builder_preview_bundle_prefix,
    purge_local_workspace_builder_artifact_tree,
)


def test_purge_local_workspace_builder_artifact_tree_removes_workspace_subtree(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path))
    ws = Path(tmp_path / "ws_a")
    proj = ws / "pr_b"
    proj.mkdir(parents=True)
    (proj / "sample.zip").write_bytes(b"z")
    assert ws.is_dir()
    assert purge_local_workspace_builder_artifact_tree(workspace_id="ws_a") == 1
    assert not ws.exists()


def test_purge_gcs_builder_preview_bundle_prefix_no_bucket_is_zero(monkeypatch: object) -> None:
    monkeypatch.delenv("HAM_BUILDER_PREVIEW_SOURCE_BUCKET", raising=False)
    assert purge_gcs_builder_preview_bundle_prefix(workspace_id="ws_a") == 0
