"""Subprocess lifecycle for ``opencode serve``.

Production callers spawn the binary via :func:`spawn_opencode_serve`;
tests inject a :class:`Spawner` so the OpenCode CLI is never invoked from
the test process. ``subprocess`` is imported lazily in the default
spawner so static import scans confirm no other module reaches into
``subprocess`` from the OpenCode runner package.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_LOG = logging.getLogger(__name__)


class ServeProcessHandle(Protocol):
    """Minimal subprocess-handle protocol the runner depends on."""

    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class Spawner(Protocol):
    """Factory function that spawns ``opencode serve``.

    Production passes :func:`default_spawner`. Tests inject a mock that
    returns a fake handle without touching the OpenCode binary.
    """

    def __call__(
        self,
        *,
        argv: list[str],
        env: Mapping[str, str],
        cwd: Path,
    ) -> ServeProcessHandle: ...


@dataclass(frozen=True)
class ServeProcess:
    """The HAM-side handle for one ``opencode serve`` invocation."""

    handle: ServeProcessHandle
    host: str
    port: int
    cwd: Path

    @property
    def pid(self) -> int:
        return int(self.handle.pid)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def default_spawner(
    *,
    argv: list[str],
    env: Mapping[str, str],
    cwd: Path,
) -> ServeProcessHandle:
    """Spawn ``opencode serve`` via :mod:`subprocess`.

    This is the **only** site in the OpenCode runner package that
    imports :mod:`subprocess`. Tests verify importing
    :mod:`src.ham.opencode_runner` does not require ``subprocess.Popen``
    to be available at module import time.
    """
    import subprocess  # noqa: S404 — subprocess is exactly the point of this helper.

    return subprocess.Popen(  # type: ignore[return-value]  # noqa: S603
        argv,
        env=dict(env),
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def spawn_opencode_serve(
    *,
    host: str,
    port: int,
    cwd: Path,
    env: Mapping[str, str],
    spawner: Spawner | None = None,
    binary: str = "opencode",
) -> ServeProcess:
    """Spawn ``opencode serve --hostname <host> --port <port>``.

    The default spawner shells out via :mod:`subprocess`. Tests inject
    their own spawner to satisfy the "never invoke the OpenCode binary"
    invariant.
    """
    chosen_spawner: Spawner = spawner or default_spawner
    argv = [
        binary,
        "serve",
        "--hostname",
        host,
        "--port",
        str(port),
    ]
    handle = chosen_spawner(argv=argv, env=env, cwd=cwd)
    _LOG.info(
        "opencode_runner.spawned pid=%s host=%s port=%s",
        getattr(handle, "pid", "?"),
        host,
        port,
    )
    return ServeProcess(handle=handle, host=host, port=port, cwd=cwd)


def shutdown_serve(
    process: ServeProcess,
    *,
    grace_period_s: float = 5.0,
    kill_fn: Callable[[int, int], None] | None = None,
) -> None:
    """Best-effort graceful shutdown + kill fallback.

    Sends SIGTERM, waits up to ``grace_period_s`` seconds, then sends
    SIGKILL. The optional ``kill_fn`` is injected by tests; in
    production it defaults to :func:`os.killpg` so child processes
    (bash, MCP servers) the OpenCode server may have spawned are reaped
    alongside the parent process group.
    """
    handle = process.handle
    if handle.poll() is not None:
        return
    try:
        handle.terminate()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("opencode_runner.terminate_raised %s", type(exc).__name__)

    deadline = time.monotonic() + max(grace_period_s, 0.0)
    while time.monotonic() < deadline:
        if handle.poll() is not None:
            return
        time.sleep(0.1)

    try:
        handle.kill()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("opencode_runner.kill_raised %s", type(exc).__name__)

    if kill_fn is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    else:
        try:
            kill_fn(process.pid, signal.SIGKILL)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("opencode_runner.killpg_raised %s", type(exc).__name__)


def reap_zombie_children(pid: int) -> int:
    """Best-effort child reaping for the leftover OpenCode subprocess tree.

    Returns the number of children successfully reaped. Never raises.
    """
    del pid
    reaped = 0
    try:
        while True:
            child_pid, _status = os.waitpid(-1, os.WNOHANG)
            if child_pid == 0:
                break
            reaped += 1
    except ChildProcessError:
        pass
    except OSError:
        pass
    return reaped


__all__ = [
    "ServeProcess",
    "ServeProcessHandle",
    "Spawner",
    "default_spawner",
    "reap_zombie_children",
    "shutdown_serve",
    "spawn_opencode_serve",
]


# Lazy reference so tests can confirm the public surface does not import
# subprocess until the runtime actually spawns the binary.
_ASSERT_NO_TOP_LEVEL_SUBPROCESS_IMPORT: Any = None
