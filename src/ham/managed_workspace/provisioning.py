"""Idempotent provisioning of managed-workspace working trees.

This module is the only application point in HAM that creates the
``managed/<wid>/<pid>/working`` directory on the local filesystem. Path
shape validation is delegated to :func:`managed_working_dir`, and
symlink-aware path-scope safety is delegated to :func:`safe_path_in_root`
so this helper cannot weaken either invariant. Failures are translated
into a small, normie-safe taxonomy via :class:`ManagedWorkspaceSetupError`
so callers can persist a single terminal control-plane row without
inventing per-call-site copy.
"""

from __future__ import annotations

import errno
import logging
from pathlib import Path

from src.ham.claude_agent_runner.paths import safe_path_in_root
from src.ham.managed_workspace.paths import (
    ham_managed_workspace_root,
    managed_working_dir,
)

_LOG = logging.getLogger(__name__)


class ManagedWorkspaceSetupError(Exception):
    """Raised when a managed workspace working tree cannot be safely materialized."""

    def __init__(
        self,
        *,
        reason: str,
        detail: str,
        code: str = "workspace_setup_failed",
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.code = code


def ensure_managed_working_tree(
    *,
    workspace_id: str | None,
    project_id: str,
) -> Path:
    """Return the managed working dir, creating it (and parents) if missing.

    The returned Path is guaranteed to have the
    ``<root>/managed/<wid>/<pid>/working`` shape and to exist as a
    directory on the local filesystem on success. The call is idempotent:
    repeated invocations with the same valid ids return the same Path and
    do not raise as long as the existing entry is a directory.
    """
    wid = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not wid:
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=invalid_ids",
        )
        raise ManagedWorkspaceSetupError(
            reason="invalid_ids",
            detail="managed_workspace_id_required",
        )
    if not pid:
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=invalid_ids",
        )
        raise ManagedWorkspaceSetupError(
            reason="invalid_ids",
            detail="managed_project_id_required",
        )

    try:
        working_dir = managed_working_dir(wid, pid)
    except ValueError:
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=invalid_ids",
        )
        raise ManagedWorkspaceSetupError(
            reason="invalid_ids",
            detail="ids_failed_validation",
        ) from None

    managed_root = ham_managed_workspace_root() / "managed"
    if not safe_path_in_root(working_dir, managed_root):
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=outside_managed_root",
        )
        raise ManagedWorkspaceSetupError(
            reason="outside_managed_root",
            detail="path_escaped_managed_root",
        )

    try:
        working_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=permission_denied",
        )
        raise ManagedWorkspaceSetupError(
            reason="permission_denied",
            detail="mkdir_permission_denied",
        ) from None
    except FileExistsError:
        if working_dir.is_dir():
            _LOG.info("ensure_managed_working_tree ok (already_exists)")
            return working_dir
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=filesystem_error",
        )
        raise ManagedWorkspaceSetupError(
            reason="filesystem_error",
            detail="path_exists_not_directory",
        ) from None
    except OSError as exc:
        if exc.errno == errno.EROFS:
            _LOG.warning(
                "ensure_managed_working_tree refused: reason=read_only_filesystem",
            )
            raise ManagedWorkspaceSetupError(
                reason="read_only_filesystem",
                detail="managed_root_read_only",
            ) from None
        if exc.errno == errno.ENOSPC:
            _LOG.warning(
                "ensure_managed_working_tree refused: reason=filesystem_error",
            )
            raise ManagedWorkspaceSetupError(
                reason="filesystem_error",
                detail="no_space_left",
            ) from None
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=filesystem_error",
        )
        raise ManagedWorkspaceSetupError(
            reason="filesystem_error",
            detail="mkdir_failed",
        ) from None

    if not working_dir.is_dir():
        _LOG.warning(
            "ensure_managed_working_tree refused: reason=filesystem_error",
        )
        raise ManagedWorkspaceSetupError(
            reason="filesystem_error",
            detail="path_exists_not_directory",
        )

    _LOG.info("ensure_managed_working_tree ok")
    return working_dir


__all__ = [
    "ManagedWorkspaceSetupError",
    "ensure_managed_working_tree",
]
