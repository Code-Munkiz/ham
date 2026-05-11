from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectRecord(BaseModel):
    id: str
    version: str = "1.0.0"
    name: str
    root: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Build Lane (Factory Droid mutating workflow) — disabled by default.
    # Stored persistently but not yet exposed through any router or UI.
    build_lane_enabled: bool = False
    # Output target for the Build Lane post-exec step.
    #
    # - "managed_workspace" (default): the live-beta target. The droid edits a
    #   HAM-managed project workspace and the post-exec step snapshots the
    #   change into HAM-owned storage. No git, no gh, no GitHub install
    #   required. The :class:`ManagedWorkspaceStubAdapter` returns a structured
    #   ``MANAGED_WORKSPACE_NOT_IMPLEMENTED`` failure until PR-B lands the
    #   real snapshot adapter; nothing user-visible is wired today.
    # - "github_pr": the connected-repo target. The droid edits a local git
    #   clone and the post-exec step opens a real pull request via
    #   ``gh pr create``. Requires ``github_repo``, a runner-side GitHub App /
    #   installation token (no personal PATs), and an explicit per-project
    #   opt-in. This is the optional, advanced mode.
    #
    # The field defaults to ``"managed_workspace"`` so new projects do not
    # require any GitHub setup. Existing project records without this field
    # also default to ``"managed_workspace"`` on read (Pydantic default).
    output_target: Literal["managed_workspace", "github_pr"] = "managed_workspace"
    # ``github_repo`` is meaningful only when ``output_target == "github_pr"``.
    github_repo: str | None = None
    # ``workspace_id`` and ``managed_storage_uri`` are populated only when
    # ``output_target == "managed_workspace"``; both remain ``None`` in PR-A
    # because the managed snapshot path is a stub. PR-B will require
    # ``workspace_id`` and lazy-allocate ``managed_storage_uri`` on first build.
    workspace_id: str | None = None
    managed_storage_uri: str | None = None
