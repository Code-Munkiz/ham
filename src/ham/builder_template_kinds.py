"""Template kind registry — Phase 2 Subsystem 9 (ADR-0011).

Routes each template kind to either the deterministic scaffold path
(existing ``builder_chat_scaffold.py``) or the new LLM-scaffold path
(``builder_llm_scaffold.py``).

Adding a new template kind = appending one entry to ``_REGISTRY``.
Omitting a kind = it defaults to ``"llm"``.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
ADR: docs/adr/0011-llm-scaffold-staged-by-template-kind.md
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Registry: template kind → scaffold path
# ---------------------------------------------------------------------------

# Deterministic entries: existing ~1400 LoC templates in builder_chat_scaffold.py.
# All OTHER kinds (todo, dashboard, landing-page, ...) default to "llm".
_REGISTRY: dict[str, Literal["deterministic", "llm"]] = {
    "calculator": "deterministic",
    "tetris": "deterministic",
    # New Phase 2 kinds route to the LLM scaffold path automatically via the
    # default in select_scaffold_path(); no explicit entry needed.
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_scaffold_path(template_kind: str) -> Literal["deterministic", "llm"]:
    """Return the scaffold path for a given template kind.

    Args:
        template_kind: The kind string set by the Planner (e.g. ``"calculator"``,
            ``"todo"``, ``"dashboard"``).

    Returns:
        ``"deterministic"`` — route to ``builder_chat_scaffold.py`` (existing
            calculator / tetris templates, unchanged per ADR-0011).
        ``"llm"`` — route to ``builder_llm_scaffold.py`` (new kinds or any
            kind not explicitly listed in the registry).
    """
    return _REGISTRY.get(template_kind, "llm")
