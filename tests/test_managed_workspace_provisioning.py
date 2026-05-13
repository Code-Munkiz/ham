"""Tests for :mod:`src.ham.managed_workspace.provisioning`.

These tests lock the path-shape, idempotency, and typed-failure behavior
of :func:`ensure_managed_working_tree`. No real Anthropic / Claude SDK,
no GCS, no Firestore — every test runs against tmp_path with
``HAM_MANAGED_WORKSPACE_ROOT`` monkey-patched.
"""

from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ham.managed_workspace import provisioning
from src.ham.managed_workspace.provisioning import (
    ManagedWorkspaceSetupError,
    ensure_managed_working_tree,
)


def test_ensure_managed_working_tree_creates_path_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    out = ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert out.is_dir()
    expected_suffix = Path("managed") / "ws_abc" / "proj.xyz-1" / "working"
    assert out.resolve() == (tmp_path / expected_suffix).resolve()


def test_ensure_managed_working_tree_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    first = ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    second = ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert first == second
    assert second.is_dir()


def test_ensure_managed_working_tree_rejects_missing_workspace_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
        ensure_managed_working_tree(workspace_id=None, project_id="proj.xyz-1")
    assert exc_info.value.reason == "invalid_ids"
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info_b:
        ensure_managed_working_tree(workspace_id="", project_id="proj.xyz-1")
    assert exc_info_b.value.reason == "invalid_ids"


def test_ensure_managed_working_tree_rejects_invalid_id_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
        ensure_managed_working_tree(workspace_id="../etc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "invalid_ids"
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info_b:
        ensure_managed_working_tree(workspace_id="ws_abc", project_id="bad/slash")
    assert exc_info_b.value.reason == "invalid_ids"
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info_c:
        ensure_managed_working_tree(workspace_id="ws abc", project_id="proj.xyz-1")
    assert exc_info_c.value.reason == "invalid_ids"


def test_ensure_managed_working_tree_rejects_path_outside_managed_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    with patch.object(provisioning, "safe_path_in_root", return_value=False):
        with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
            ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "outside_managed_root"
    assert exc_info.value.detail == "path_escaped_managed_root"


def test_ensure_managed_working_tree_maps_permission_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))

    def _boom(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(errno.EACCES, "denied")

    with patch.object(Path, "mkdir", _boom):
        with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
            ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "permission_denied"
    assert exc_info.value.detail == "mkdir_permission_denied"


def test_ensure_managed_working_tree_maps_read_only_filesystem(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))

    def _boom(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError(errno.EROFS, "read-only file system")

    with patch.object(Path, "mkdir", _boom):
        with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
            ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "read_only_filesystem"
    assert exc_info.value.detail == "managed_root_read_only"


def test_ensure_managed_working_tree_maps_no_space_left(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))

    def _boom(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "no space left on device")

    with patch.object(Path, "mkdir", _boom):
        with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
            ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "filesystem_error"
    assert exc_info.value.detail == "no_space_left"


def test_ensure_managed_working_tree_maps_other_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))

    def _boom(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError(errno.EIO, "io error")

    with patch.object(Path, "mkdir", _boom):
        with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
            ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "filesystem_error"
    assert exc_info.value.detail == "mkdir_failed"


def test_ensure_managed_working_tree_rejects_when_path_is_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_MANAGED_WORKSPACE_ROOT", str(tmp_path))
    working = tmp_path / "managed" / "ws_abc" / "proj.xyz-1" / "working"
    working.parent.mkdir(parents=True, exist_ok=True)
    working.write_text("not a directory")
    with pytest.raises(ManagedWorkspaceSetupError) as exc_info:
        ensure_managed_working_tree(workspace_id="ws_abc", project_id="proj.xyz-1")
    assert exc_info.value.reason == "filesystem_error"
    assert exc_info.value.detail == "path_exists_not_directory"


def test_managed_workspace_setup_error_has_default_code() -> None:
    err = ManagedWorkspaceSetupError(reason="invalid_ids", detail="bad")
    assert err.code == "workspace_setup_failed"
    assert err.reason == "invalid_ids"
    assert err.detail == "bad"
    assert str(err) == "bad"


def test_managed_workspace_setup_error_detail_has_no_paths() -> None:
    err = ManagedWorkspaceSetupError(reason="filesystem_error", detail="mkdir_failed")
    assert "/" not in err.detail
    assert "HAM_" not in err.detail
