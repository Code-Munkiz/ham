"""Local in-process HAM-on-X Phase 1A rate guardrails."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from src.ham.ham_x.config import HamXConfig, load_ham_x_config

RateAction = Literal["search", "post", "quote", "like", "draft"]


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    reason: str = ""
    limit: int | None = None
    used: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "limit": self.limit,
            "used": self.used,
        }


@dataclass
class InProcessRateLimiter:
    """Simple per-process sliding-window limiter for scaffold tests and dry runs."""

    window_seconds: int = 3600
    _events: dict[str, list[float]] = field(default_factory=dict)

    def check(self, action_type: RateAction, *, config: HamXConfig | None = None) -> RateLimitResult:
        cfg = config or load_ham_x_config()
        limit = _limit_for(action_type, cfg)
        if limit is None:
            return RateLimitResult(allowed=True, limit=None)
        events = self._recent(action_type)
        if limit <= 0:
            return RateLimitResult(
                allowed=False,
                reason=f"{action_type}_limit_is_zero",
                limit=limit,
                used=len(events),
            )
        if len(events) >= limit:
            return RateLimitResult(
                allowed=False,
                reason=f"{action_type}_rate_limit_exceeded",
                limit=limit,
                used=len(events),
            )
        return RateLimitResult(allowed=True, limit=limit, used=len(events))

    def record(self, action_type: RateAction) -> None:
        self._events.setdefault(action_type, []).append(time.time())

    def _recent(self, action_type: str) -> list[float]:
        cutoff = time.time() - self.window_seconds
        events = [ts for ts in self._events.get(action_type, []) if ts >= cutoff]
        self._events[action_type] = events
        return events


def _limit_for(action_type: str, cfg: HamXConfig) -> int | None:
    if action_type == "search":
        return cfg.max_searches_per_hour
    if action_type == "post":
        return cfg.max_posts_per_hour
    if action_type == "quote":
        return cfg.max_quotes_per_hour
    if action_type == "like":
        return 0
    return None
