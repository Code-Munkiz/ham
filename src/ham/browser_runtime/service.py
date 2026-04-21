from __future__ import annotations

from src.ham.browser_runtime.sessions import BrowserSessionManager

_manager = BrowserSessionManager()


def get_browser_runtime_manager() -> BrowserSessionManager:
    return _manager

