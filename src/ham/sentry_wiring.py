"""Sentry SDK initialisation wrapper — Phase 1 #9 (ADR-0008).

Wraps ``sentry_sdk.init()`` with HAM defaults. The SDK is dormant when
``SENTRY_DSN`` is unset (native SDK no-op). Idempotent: safe to call
from multiple test fixtures.

Spec: docs/adr/0008-sentry-scaffolding-deferred-dsn.md
"""

from __future__ import annotations

import os

import sentry_sdk

# Module-level flag so is_active() is testable without calling init() twice.
_initialized: bool = False


def init(*, dsn: str | None = None, release: str | None = None) -> None:
    """Initialise Sentry SDK with HAM defaults.

    Safe to call multiple times — only the first call with a non-empty DSN
    initialises the SDK; subsequent calls are no-ops.

    Args:
        dsn: Override DSN. Defaults to ``SENTRY_DSN`` env var. SDK is
             dormant when both are unset or empty.
        release: Optional release string (e.g. git SHA). Defaults to
                 ``HAM_RELEASE`` env var when set.
    """
    global _initialized  # noqa: PLW0603

    resolved_dsn = (dsn if dsn is not None else os.environ.get("SENTRY_DSN", "")).strip()
    if not resolved_dsn:
        return
    if _initialized:
        return

    resolved_release = release or os.environ.get("HAM_RELEASE") or None

    sentry_sdk.init(
        dsn=resolved_dsn,
        traces_sample_rate=0.0,  # no perf overhead until owner opts in (ADR-0008)
        send_default_pii=False,
        release=resolved_release,
    )
    _initialized = True


def is_active() -> bool:
    """Return True if the SDK was successfully initialised with a DSN."""
    return _initialized


def reset_for_tests() -> None:
    """Reset module-level state between tests. Call from teardown only."""
    global _initialized  # noqa: PLW0603
    _initialized = False
