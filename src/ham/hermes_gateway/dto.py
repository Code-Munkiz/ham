"""Versioned snapshot shapes for ``GET /api/hermes-gateway/snapshot`` (JSON-serializable dicts)."""

from __future__ import annotations

# Bump when removing fields or changing semantics (clients may gate on this).
GATEWAY_SNAPSHOT_SCHEMA_VERSION = "1.0"

# Default TTL for expensive CLI / HTTP probes (override via HAM_HERMES_GATEWAY_CACHE_TTL_S).
DEFAULT_CACHE_TTL_S = 45.0
