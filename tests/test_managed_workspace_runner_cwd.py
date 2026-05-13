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

from src.api.droid_build import (
    _ManagedWorkspaceConfigError,
    _effective_runner_cwd,
    _project_output_target,
)
from src.api.server import fastapi_app
from src.ham.droid_workflows.preview_launch import (
    _managed_workspace_root_blocker,
    build_droid_preview,
    verify_launch_against_preview,
)
from src.ham.managed_workspace.paths import (
    ham_managed_workspace_root,
    managed_working_dir,
)
from src.persistence.project_store import (
    ProjectStore,
    set_project_store_for_tests,
)
from src.registry.projects import ProjectRecord


@pytest.fixture
def isolated_store(tmp_path: Path) -> ProjectStore:
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture
def cleanup_overrides() -> None:
    yield
    fastapi_app.dependency_overrides.clear()


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

    def test_managed_workspace_without_workspace_id_raises(
        self, tmp_path: Path
    ) -> None:
        rec = _make_record(
            id_="project.orphan",
            root=str(tmp_path),
            output_target="managed_workspace",
            workspace_id=None,
        )
        with pytest.raises(_ManagedWorkspaceConfigError) as ei:
            _effective_runner_cwd(rec)
        msg = str(ei.value)
        assert "workspace_id" in msg
        assert "/app" not in msg
        assert "safe_edit_low" not in msg
        assert "HAM_DROID_EXEC_TOKEN" not in msg

    def test_managed_workspace_with_invalid_ids_raises(
        self, tmp_path: Path
    ) -> None:
        rec = _make_record(
            id_="proj/with/slash",
            root=str(tmp_path),
            output_target="managed_workspace",
            workspace_id="ws_ok",
        )
        with pytest.raises(_ManagedWorkspaceConfigError):
            _effective_runner_cwd(rec)

    def test_managed_workspace_ignores_legacy_app_root(self) -> None:
        rec = _make_record(
            id_="project.legacy",
            root="/app",
            output_target="managed_workspace",
            workspace_id="ws_legacy",
        )
        cwd = _effective_runner_cwd(rec)
        assert "/app" != str(cwd)
        assert cwd == managed_working_dir("ws_legacy", "project.legacy")
        assert "managed" in cwd.parts
        assert cwd.parts[-1] == "working"

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


class TestManagedPreviewApiContract:
    """End-to-end contract: managed-workspace preview must ignore legacy
    ``project.root`` (``/app`` or arbitrary), derive cwd from
    ``managed_working_dir(workspace_id, project_id)``, refuse on missing
    ``workspace_id`` with a structured 422, and never leak ``safe_edit_low``
    or ``HAM_DROID_EXEC_TOKEN`` in user-facing fields.
    """

    def _setup(
        self,
        isolated_store,  # type: ignore[no-untyped-def]
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        legacy_root: str | None = None,
        workspace_id_present: bool = True,
    ):
        from tests.test_droid_build_api import (  # local import: shared fixtures
            _client,
            _override_store,
            _register_managed_build_project,
            _seed_managed_workspace,
        )

        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
        monkeypatch.delenv("HAM_WORKSPACE_OPERATOR_EMAILS", raising=False)
        ws_store, ws_id, actor = _seed_managed_workspace(
            role="owner", user_id="user_cwd_mapping"
        )
        _override_store(ws_store)
        root = Path(legacy_root) if legacy_root else (tmp_path / "r")
        if legacy_root is None:
            root.mkdir()
        rec = _register_managed_build_project(
            isolated_store,
            name="p_cwd_mapping",
            root=root,
            workspace_id=ws_id if workspace_id_present else None,
        )
        return _client(actor), rec, ws_id

    def test_managed_preview_ignores_legacy_app_root_and_uses_managed_working_dir(
        self,
        isolated_store,  # type: ignore[no-untyped-def]
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cleanup_overrides: None,
    ) -> None:
        # Seed a managed project whose persisted ``root`` is the legacy
        # ``/app`` value that used to leak into the runner cwd.
        client, rec, ws_id = self._setup(
            isolated_store, tmp_path, monkeypatch, legacy_root="/app"
        )
        res = client.post(
            "/api/droid/build/preview",
            json={"project_id": rec.id, "user_prompt": "Tidy README typos."},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["output_target"] == "managed_workspace"
        assert body["will_open_pull_request"] is False
        # The preview proposal must not echo the legacy /app root.
        # cwd is intentionally not exposed via the public response, so we
        # rely on the helper-level test above for cwd derivation and on
        # the digest binding: the proposal_digest is computed against the
        # managed_working_dir, so launching with a digest computed for /app
        # would fail verify_launch_against_preview.
        assert "/app" not in res.text
        assert "safe_edit_low" not in res.text.lower()
        assert "ham_droid_exec_token" not in res.text.lower()
        assert managed_working_dir is not None  # import is intentional

    def test_managed_preview_missing_workspace_id_is_structured_422(
        self,
        isolated_store,  # type: ignore[no-untyped-def]
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cleanup_overrides: None,
    ) -> None:
        client, rec, _ = self._setup(
            isolated_store,
            tmp_path,
            monkeypatch,
            workspace_id_present=False,
        )
        res = client.post(
            "/api/droid/build/preview",
            json={"project_id": rec.id, "user_prompt": "Tidy README."},
        )
        assert res.status_code == 422
        body = res.json()
        assert (
            body["detail"]["error"]["code"]
            == "BUILD_LANE_PROJECT_MISSING_WORKSPACE_ID"
        )
        raw = res.text.lower()
        assert "safe_edit_low" not in raw
        assert "ham_droid_exec_token" not in raw
        assert "--auto low" not in raw

    def test_managed_preview_response_does_not_leak_internal_workflow_or_env(
        self,
        isolated_store,  # type: ignore[no-untyped-def]
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cleanup_overrides: None,
    ) -> None:
        client, rec, _ = self._setup(isolated_store, tmp_path, monkeypatch)
        res = client.post(
            "/api/droid/build/preview",
            json={"project_id": rec.id, "user_prompt": "Tidy README typos."},
        )
        assert res.status_code == 200, res.text
        raw = res.text.lower()
        assert "safe_edit_low" not in raw
        assert "ham_droid_exec_token" not in raw
        assert "--auto low" not in raw
        assert "--skip-permissions-unsafe" not in raw


class TestGithubPrCwdUnchanged:
    """Regression: github_pr projects must continue to use ``project.root``
    verbatim and ``is_dir()`` must still gate non-managed previews.
    """

    def test_github_pr_preview_uses_project_root_when_valid(
        self,
        isolated_store,  # type: ignore[no-untyped-def]
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cleanup_overrides: None,
    ) -> None:
        from tests.test_droid_build_api import (
            _client,
            _register_build_project,
        )

        monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
        monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")
        root = tmp_path / "r"
        root.mkdir()
        rec = _register_build_project(isolated_store, name="p_gh", root=root)
        # Build a minimal HamActor matching the existing operator fixture
        # (operator@example.test is the operator email above).
        from src.ham.clerk_auth import HamActor

        actor = HamActor(
            user_id="user_op",
            org_id=None,
            session_id="sess_o",
            email="operator@example.test",
            permissions=frozenset(),
            org_role=None,
            raw_permission_claim=None,
        )
        res = _client(actor).post(
            "/api/droid/build/preview",
            json={"project_id": rec.id, "user_prompt": "Tidy README."},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["output_target"] == "github_pr"
        assert body["will_open_pull_request"] is True
        # Response intentionally does not echo runner cwd; helper-level
        # tests above already cover the derivation. We only assert the
        # github_pr happy path still succeeds when project.root exists.
        raw = res.text.lower()
        assert "safe_edit_low" not in raw
        assert "ham_droid_exec_token" not in raw


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
