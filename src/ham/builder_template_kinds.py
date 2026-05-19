"""Template kind registry — Phase 2 Subsystem 9 (ADR-0011).

Routes each template kind to either the **legacy deterministic** scaffold
path (existing ``builder_chat_scaffold.py``) or the new LLM-scaffold path
(``builder_llm_scaffold.py``).

Strangler-pattern intent:

- ``legacy_deterministic`` is **temporary compatibility only**. The set is
  frozen at ``{calculator, tetris}`` (see :data:`_LEGACY_DETERMINISTIC_KINDS`
  and the lock test in ``tests/test_builder_template_kinds.py``). New
  template kinds **must not** be added here — they default to ``"llm"``
  and route to ``src/ham/builder_llm_scaffold.py``.
- The detection helpers backing the legacy path live in
  ``src/ham/builder_legacy_templates.py`` (a thin facade over the
  pre-existing detection in ``builder_chat_scaffold``); future contributors
  signalling "this is legacy" should import from that module.
- Once the verifier (Phase 1 #19) demonstrates parity for the LLM path on
  ``calculator`` / ``tetris``, the corresponding entry can be removed from
  :data:`_REGISTRY` (one kind at a time) and the registry will route to
  ``"llm"`` for everything.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
ADR: docs/adr/0011-llm-scaffold-staged-by-template-kind.md
"""

from __future__ import annotations

from typing import Literal

ScaffoldPath = Literal["legacy_deterministic", "llm"]

LEGACY_DETERMINISTIC: ScaffoldPath = "legacy_deterministic"
LLM: ScaffoldPath = "llm"


# ---------------------------------------------------------------------------
# Registry: template kind → scaffold path
# ---------------------------------------------------------------------------

# Legacy-deterministic entries: existing ~1400 LoC templates in
# builder_chat_scaffold.py (calculator, tetris). DO NOT add new kinds here —
# they are legacy compatibility shims only. All other kinds (todo, dashboard,
# landing-page, anything new) default to "llm" via select_scaffold_path().
_REGISTRY: dict[str, ScaffoldPath] = {
    "calculator": LEGACY_DETERMINISTIC,
    "tetris": LEGACY_DETERMINISTIC,
}


# Canonical, frozen set of legacy kinds. Tests assert this set is exactly
# {calculator, tetris}; any future-proofing of legacy must add an explicit
# row here AND update the lock test deliberately.
_LEGACY_DETERMINISTIC_KINDS: frozenset[str] = frozenset(
    {kind for kind, path in _REGISTRY.items() if path == LEGACY_DETERMINISTIC}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_template_kind(template_kind: str) -> str:
    """Lower-case + strip the template kind. Empty / non-str → ``""``.

    Both the Planner and the chat-side scaffold derive kind strings from
    user prompts, so accepting case / whitespace variants ("Calculator",
    "  tetris  ") and routing them to the legacy path until the LLM path
    achieves parity is the safer migration default.
    """
    if not isinstance(template_kind, str):
        return ""
    return template_kind.strip().lower()


def select_scaffold_path(template_kind: str) -> ScaffoldPath:
    """Return the scaffold path for a given template kind.

    Args:
        template_kind: The kind string set by the Planner (e.g. ``"calculator"``,
            ``"todo"``, ``"dashboard"``). Normalized via
            :func:`_normalize_template_kind` (strip + lower) before lookup.

    Returns:
        ``"legacy_deterministic"`` — route to ``builder_chat_scaffold.py``
            (existing calculator / tetris templates, unchanged per ADR-0011).
            Legacy compatibility only; the set is frozen.
        ``"llm"`` — route to ``builder_llm_scaffold.py`` (new kinds or any
            kind not explicitly listed in the registry). This is the
            **default** for anything not in the legacy set.
    """
    key = _normalize_template_kind(template_kind)
    return _REGISTRY.get(key, LLM)


def is_legacy_deterministic_kind(template_kind: str) -> bool:
    """True iff ``template_kind`` resolves to the legacy deterministic path."""
    return select_scaffold_path(template_kind) == LEGACY_DETERMINISTIC


def legacy_deterministic_kinds() -> frozenset[str]:
    """Return the frozen set of kinds currently routed to the legacy path."""
    return _LEGACY_DETERMINISTIC_KINDS
