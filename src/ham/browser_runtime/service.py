from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from src.ham.browser_runtime.sessions import BrowserSessionManager

T = TypeVar("T")

_manager = BrowserSessionManager()

# Playwright sync API is *not* thread-safe; FastAPI runs each sync route on a *different*
# thread-pool thread, which triggers greenlet "cannot switch to a different thread" on Cloud Run
# and under concurrent requests. All browser I/O must run on this single worker thread.
_BROWSER_POOL: ThreadPoolExecutor | None = None
_BROWSER_IO_TIMEOUT = 120.0


def get_browser_runtime_manager() -> BrowserSessionManager:
    return _manager


def _get_browser_pool() -> ThreadPoolExecutor:
    global _BROWSER_POOL
    if _BROWSER_POOL is None:
        _BROWSER_POOL = ThreadPoolExecutor(1, thread_name_prefix="ham_playwright_")
    return _BROWSER_POOL


def run_browser_io(func: Callable[[], T]) -> T:
    """Run Playwright- or session-touching work on a dedicated single thread."""
    return _get_browser_pool().submit(func).result(timeout=_BROWSER_IO_TIMEOUT)
