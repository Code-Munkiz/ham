"""Template kind registry — Phase 2 Subsystem 9.

The legacy ``legacy_deterministic`` scaffold runtime path was **retired**.
Every template kind — including ``calculator`` and ``tetris`` — now routes
to the LLM scaffold path (``src/ham/builder_llm_scaffold.py``) with the
matching Builder Kit context.

The :data:`LEGACY_DETERMINISTIC` and :data:`LLM` constants remain as
historical markers so old callers that imported them keep importing
cleanly. They are no longer active routing values; :func:`select_scaffold_path`
always returns ``"llm"``.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
Retirement commit: refactor(builder): retire legacy deterministic scaffolds
"""

from __future__ import annotations

from typing import Literal

ScaffoldPath = Literal["legacy_deterministic", "llm"]

LEGACY_DETERMINISTIC: ScaffoldPath = "legacy_deterministic"
LLM: ScaffoldPath = "llm"


# ---------------------------------------------------------------------------
# Registry: template kind → scaffold path
# ---------------------------------------------------------------------------

# Empty: the legacy_deterministic runtime path was retired. Every kind
# (calculator, tetris, todo, dashboard, anything new) now routes through
# the LLM scaffold path with its matching Builder Kit.
_REGISTRY: dict[str, ScaffoldPath] = {}


# Empty frozenset: no kind routes to the legacy deterministic path at
# runtime. The constant is retained so older imports keep resolving.
_LEGACY_DETERMINISTIC_KINDS: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_template_kind(template_kind: str) -> str:
    """Lower-case + strip the template kind. Empty / non-str → ``""``."""
    if not isinstance(template_kind, str):
        return ""
    return template_kind.strip().lower()


def select_scaffold_path(template_kind: str) -> ScaffoldPath:
    """Return the scaffold path for a given template kind.

    Always returns ``"llm"`` — the legacy deterministic runtime path was
    retired. Calculator and Tetris now route through the LLM scaffold
    with their Builder Kits.
    """
    key = _normalize_template_kind(template_kind)
    return _REGISTRY.get(key, LLM)


def is_legacy_deterministic_kind(template_kind: str) -> bool:
    """Deprecated: legacy deterministic routing was retired; always ``False``."""
    return select_scaffold_path(template_kind) == LEGACY_DETERMINISTIC


def legacy_deterministic_kinds() -> frozenset[str]:
    """Deprecated: legacy deterministic routing was retired; returns an empty set."""
    return _LEGACY_DETERMINISTIC_KINDS


MIGRATION_POLICY: str = (
    "The legacy_deterministic scaffold runtime path was retired. The registry\n"
    "is empty (frozen at the empty set); calculator and tetris now route to\n"
    "the LLM scaffold path with their matching Builder Kits. The LEGACY_DETERMINISTIC\n"
    "constant is kept as a historical marker only; new kinds default to the\n"
    "LLM scaffold path, matching the verifier-graded parity contract.\n"
)
