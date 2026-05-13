"""Lock the managed-workspace runner cwd derivation.

For ``output_target="managed_workspace"`` projects the runner cwd is the
canonical ``managed/<workspace_id>/<project_id>/working`` path derived from
``managed_working_dir()``. Legacy ``project.root`` values (``/app``, an
arbitrary local path) must not leak into managed builds, and the ham-api
``is_dir()`` check must not gate managed projects on a runner-only path.

The strict cwd validation on the runner (allow-list +
``MANAGED_WORKSPACE_CWD_MISMATCH``) is unchanged by this PR; these tests
only cover the ham-api derivation + the relaxed-but-still-strict shape
validation that replaces ``is_dir()`` for managed projects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.droid_build import _effective_runner_cwd, _project_output_target
from src.ham.droid_workflows.preview_launch import (
    _managed_workspace_root_blocker,
    build_droid_preview,
    verify_launch_against_preview,
)
from src.ham.managed_workspace.paths import (
    ham_managed_workspace_root,
    managed_working_dir,
)
from src.registry.projects import ProjectRecord


def _make_record(
    *,
    id_: str,
    root: str,
    output_target: str,
    workspace_id: str | None,
) -> ProjectRecord:
    return ProjectRecord(
        id=id_,
        name=id_,
        root=root,
        output_target=output_target,  # type: ignore[arg-type]
        workspace_id=workspace_id,
        build_lane_enabled=True,
    )


class TestEffectiveRunnerCwd:
    def test_managed_workspace_returns_managed_working_dir(self) -> None:
        rec = _make_record(
            id_="project.app-f53b52",
            root="/app",
            output_target="managed_workspace",
            workspace_id="ws_test001",
        )
        cwd = _effective_runner_cwd(rec)
        expected = managed_working_dir("ws_test001", "project.app-f53b52")
        assert cwd == expected
        assert cwd.parts[-1] == "working"
        assert "managed" in cwd.parts

    def test_github_pr_uses_project_root_verbatim(self, tmp_path: Path) -> None:
        rec = _make_record(
            id_="project.gh",
            root=str(tmp_path),
            output_target="github_pr",
            workspace_id=None,
        )
        cwd = _effective_runner_cwd(rec)
        assert cwd == Path(str(tmp_path))

    def test_managed_workspace_without_workspace_id_falls_back_to_root(
        self, tmp_path: Path
    ) -> None:
        rec = _make_record(
            id_="project.orphan",
            root=str(tmp_path),
            output_target="managed_workspace",
            workspace_id=None,
        )
        cwd = _effective_runner_cwd(rec)
        assert cwd == Path(str(tmp_path))

    def test_managed_workspace_with_invalid_ids_falls_back_to_root(
        self, tmp_path: Path
    ) -> None:
        rec = _make_record(
            id_="proj/with/slash",
            root=str(tmp_path),
            output_target="managed_workspace",
            workspace_id="ws_ok",
        )
        cwd = _effective_runner_cwd(rec)
        assert cwd == Path(str(tmp_path))

    def test_project_output_target_defaults_to_managed_workspace(
        self, tmp_path: Path
    ) -> None:
        rec = _make_record(
            id_="p",
            root=str(tmp_path),
            output_target="managed_workspace",
            workspace_id=None,
        )
        assert _project_output_target(rec) == "managed_workspace"


class TestManagedWorkspaceRootBlocker:
    def test_canonical_managed_path_is_accepted(self) -> None:
        path = managed_working_dir("ws_abc", "project.zzz")
        assert _managed_workspace_root_blocker(path) is None

    def test_path_outside_managed_root_is_rejected(self, tmp_path: Path) -> None:
        msg = _managed_workspace_root_blocker(tmp_path)
        assert msg is not None
        assert "not under" in msg

    def test_app_legacy_path_is_rejected(self) -> None:
        msg = _managed_workspace_root_blocker(Path("/app"))
        assert msg is not None

    def test_managed_root_without_working_leaf_is_rejected(self) -> None:
        path = ham_managed_workspace_root() / "managed" / "ws_a" / "project.b"
        msg = _managed_workspace_root_blocker(path)
        assert msg is not None
        assert "working" in msg

    def test_extra_segments_beyond_working_is_rejected(self) -> None:
        path = (
            ham_managed_workspace_root()
            / "managed"
            / "ws_a"
            / "project.b"
            / "working"
            / "extra"
        )
        msg = _managed_workspace_root_blocker(path)
        assert msg is not None


class TestBuildDroidPreviewManagedTarget:
    def test_preview_does_not_require_is_dir_for_managed_workspace(self) -> None:
        non_existent = managed_working_dir("ws_smoke", "project.smoke")
        assert not non_existent.exists()
        result = build_droid_preview(
            workflow_id="safe_edit_low",
            project_id="project.smoke",
            project_root=non_existent,
            user_prompt="Tidy a README typo.",
            output_target="managed_workspace",
        )
        assert result.ok, result.blocking_reason
        assert result.workflow_id == "safe_edit_low"
        assert result.cwd == str(non_existent.resolve())
        assert result.proposal_digest is not None

    def test_preview_rejects_managed_target_with_path_outside_managed_root(
        self, tmp_path: Path
    ) -> None:
        result = build_droid_preview(
            workflow_id="safe_edit_low",
            project_id="project.x",
            project_root=tmp_path,
            user_prompt="x",
            output_target="managed_workspace",
        )
        assert not result.ok
        assert result.blocking_reason is not None
        assert "not under" in result.blocking_reason

    def test_github_pr_still_requires_is_dir(self) -> None:
        non_existent = Path("/this/path/does/not/exist/anywhere/abc123xyz")
        result = build_droid_preview(
            workflow_id="safe_edit_low",
            project_id="project.gh",
            project_root=non_existent,
            user_prompt="x",
            output_target="github_pr",
        )
        assert not result.ok
        assert result.blocking_reason is not None
        assert "Project root is not a directory" in result.blocking_reason

    def test_github_pr_succeeds_for_real_tmp_path(self, tmp_path: Path) -> None:
        result = build_droid_preview(
            workflow_id="safe_edit_low",
            project_id="project.gh.ok",
            project_root=tmp_path,
            user_prompt="Tidy a README typo.",
            output_target="github_pr",
        )
        assert result.ok, result.blocking_reason


class TestVerifyLaunchManagedTarget:
    def test_verify_launch_skips_is_dir_for_managed_target(self) -> None:
        cwd = managed_working_dir("ws_ver", "project.ver")
        from src.ham.droid_workflows.preview_launch import compute_proposal_digest
        from src.ham.droid_workflows.registry import REGISTRY_REVISION

        focus = "Tidy a README typo."
        digest = compute_proposal_digest(
            workflow_id="safe_edit_low",
            project_id="project.ver",
            cwd=str(cwd.resolve()),
            user_prompt=focus,
        )
        err = verify_launch_against_preview(
            workflow_id="safe_edit_low",
            project_id="project.ver",
            project_root=cwd,
            user_prompt=focus,
            proposal_digest=digest,
            base_revision=REGISTRY_REVISION,
            output_target="managed_workspace",
        )
        assert err is None

    def test_verify_launch_rejects_managed_with_bad_root(self, tmp_path: Path) -> None:
        err = verify_launch_against_preview(
            workflow_id="safe_edit_low",
            project_id="project.bad",
            project_root=tmp_path,
            user_prompt="x",
            proposal_digest="0" * 64,
            base_revision="anything",
            output_target="managed_workspace",
        )
        assert err is not None
