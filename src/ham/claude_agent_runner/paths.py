"""Filesystem-scope helpers shared by permissions and hooks."""

from __future__ import annotations

from pathlib import Path

PATH_ARG_KEYS: tuple[str, ...] = (
    "file_path",
    "path",
    "notebook_path",
    "target_file",
    "destination",
)


def safe_path_in_root(raw: str | Path, project_root: Path) -> bool:
    """True only when ``raw`` resolves inside ``project_root``.

    Symlinks are followed (``resolve(strict=False)``) so an attacker cannot
    side-step the boundary by writing through a link. Any resolution error
    (broken root, recursive symlink, type error) collapses to ``False``.
    """
    try:
        resolved = Path(raw).expanduser().resolve(strict=False)
        root_resolved = project_root.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError, TypeError):
        return False
    if resolved == root_resolved:
        return True
    try:
        return resolved.is_relative_to(root_resolved)
    except (AttributeError, ValueError):
        try:
            resolved.relative_to(root_resolved)
            return True
        except ValueError:
            return False


__all__ = ["PATH_ARG_KEYS", "safe_path_in_root"]
