from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class TtlCache:
    """Thread-safe in-memory TTL cache for broker fragments."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            ent = self._data.get(key)
            if ent is None:
                return None
            exp, val = ent
            if now >= exp:
                del self._data[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl_s: float) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + max(0.1, ttl_s), value)

    def get_or_set(self, key: str, ttl_s: float, factory: Callable[[], T]) -> tuple[T, bool]:
        """Return ``(value, cache_hit)``."""
        hit = self.get(key)
        if hit is not None:
            return hit, True
        val = factory()
        self.set(key, val, ttl_s)
        return val, False
