"""Legacy deterministic template facade (ADR-0011 strangler-pattern).

This module is the **explicit legacy surface** for the deterministic
calculator / tetris scaffold templates that still live inside
``src/ham/builder_chat_scaffold.py``. Future contributors who need to
reference legacy template detection should import from here — the
presence of an import from this module is a build-time signal that the
caller is on the strangler-pattern path, not the LLM scaffold path.

Boundary:

- This module re-exports detection helpers from ``builder_chat_scaffold``
  without copying logic. ADR-0011 forbids refactoring
  ``builder_chat_scaffold.py`` until the LLM scaffold path has verifier
  evidence of parity, so the actual template-building code stays there
  for now.
- The registry in ``src/ham/builder_template_kinds.py`` is the single
  source of truth for which template kinds route to this legacy path.
  Do **not** add new template kinds here; new kinds must default to the
  LLM scaffold path (``src/ham/builder_llm_scaffold.py``).
- This module never invokes a live model / gateway / agent. It is pure
  detection over user-supplied text.

Removal plan: once ``builder_llm_scaffold`` has verifier-graded parity
for a legacy kind, drop the kind from
``builder_template_kinds._REGISTRY`` and update
:data:`LEGACY_TEMPLATE_KINDS` here in lockstep; the chat-side detection
in ``builder_chat_scaffold`` can then be deleted as a follow-up.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
ADR: docs/adr/0011-llm-scaffold-staged-by-template-kind.md
"""

from __future__ import annotations

from src.ham.builder_chat_scaffold import (
    _is_calculator_prompt as _legacy_is_calculator_prompt,
)
from src.ham.builder_chat_scaffold import (
    _is_tetris_prompt as _legacy_is_tetris_prompt,
)
from src.ham.builder_template_kinds import (
    legacy_deterministic_kinds,
)

# Canonical legacy template kinds, mirrored from the registry. Asserted in
# tests to stay aligned with builder_template_kinds._REGISTRY.
LEGACY_TEMPLATE_KINDS: frozenset[str] = legacy_deterministic_kinds()


def is_legacy_calculator_prompt(user_plain: str) -> bool:
    """True iff ``user_plain`` is recognized by the legacy calculator template."""
    return _legacy_is_calculator_prompt(user_plain)


def is_legacy_tetris_prompt(user_plain: str) -> bool:
    """True iff ``user_plain`` is recognized by the legacy tetris template."""
    return _legacy_is_tetris_prompt(user_plain)


def legacy_template_kind_for_prompt(user_plain: str) -> str | None:
    """Return the legacy template kind matching ``user_plain``, or ``None``.

    Order matches the precedence inside ``builder_chat_scaffold``: tetris
    is checked before calculator. Returns ``None`` when no legacy
    template applies — new kinds must route through the LLM scaffold.
    """
    if is_legacy_tetris_prompt(user_plain):
        return "tetris"
    if is_legacy_calculator_prompt(user_plain):
        return "calculator"
    return None


__all__ = [
    "LEGACY_TEMPLATE_KINDS",
    "is_legacy_calculator_prompt",
    "is_legacy_tetris_prompt",
    "legacy_template_kind_for_prompt",
]
