"""HAM-managed workspace snapshot pipeline (no GitHub; GCS + optional Firestore).

The MVP materializes snapshots from a constrained working tree layout under
`/srv/ham-workspaces/managed/<workspace_id>/<project_id>/working` (override via
HAM_MANAGED_WORKSPACE_ROOT in tests/dev).
"""

from __future__ import annotations

from src.ham.managed_workspace.models import ManifestFileEntry, SnapshotManifest

__all__ = ["ManifestFileEntry", "SnapshotManifest"]
