"""
PTY / subprocess helpers for the HAM workspace terminal bridge.

- **Windows (nt):** ConPTY via ``pywinpty`` when ``HAM_TERMINAL_PTY`` is not ``0``.
- **Elsewhere:** return ``None`` so ``workspace_terminal`` can fall back to pipe ``Popen``.
"""

from __future__ import annotations

import os
from typing import Any

_WINPTY_MODULE: Any = None


def pty_wanted() -> bool:
    if os.name != "nt":
        return False
    v = (os.environ.get("HAM_TERMINAL_PTY") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def winpty_popen(cwd: str, rows: int, cols: int) -> Any:
    """Start ``cmd.exe`` in a ConPTY. Returns a ``winpty.ptyprocess.PtyProcess`` instance."""
    if not pty_wanted():
        raise RuntimeError("WinPTY not enabled")
    try:
        global _WINPTY_MODULE
        if _WINPTY_MODULE is None:
            from winpty import PtyProcess as _P  # type: ignore[import-not-found]

            _WINPTY_MODULE = _P
        PtyProcess = _WINPTY_MODULE
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("pywinpty (winpty) is not available") from e
    r = max(1, int(rows))
    c = max(1, int(cols))
    return PtyProcess.spawn("cmd.exe", cwd=cwd, dimensions=(r, c))


def try_winpty(cwd: str, rows: int, cols: int) -> Any | None:
    """Return a ``PtyProcess`` or ``None`` if this platform or env disables PTY or import failed."""
    if not pty_wanted():
        return None
    try:
        return winpty_popen(cwd, rows, cols)
    except (RuntimeError, OSError):
        return None
