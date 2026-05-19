"""Composable Builder Kit registry (ADR-0011 strangler-pattern continuation).

Builder Kits are reusable, declarative bundles of app-archetype metadata
(stack recipe, expected files / routes, design recipe, capability tokens,
validation checklist, safety constraints) that the LLM scaffold path can
consume to produce more consistent, verifier-friendly output.

Boundary / migration rules:

- The calculator and tetris kits exist with ``legacy_parity_only=True`` as
  **migration evidence** for the deterministic templates that still live
  in ``builder_chat_scaffold.py``. They are **not** selected by the LLM
  scaffold path today — those template kinds still route to
  ``"legacy_deterministic"`` via ``builder_template_kinds._REGISTRY``.
- Adding a new kit here does **not** authorize adding a new legacy
  deterministic kind. The legacy set remains frozen at
  ``{calculator, tetris}`` until the LLM scaffold path has verifier-graded
  parity for those archetypes (see each legacy kit's
  ``validation_checklist``).
- This module has no live LLM / gateway / agent runtime dependencies.
  Loading is data-only over the bundled JSON files in
  ``src/ham/data/builder_kits/``.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
ADR: docs/adr/0011-llm-scaffold-staged-by-template-kind.md
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class BuilderKitConfigError(Exception):
    """Raised when a Builder Kit JSON file is malformed or duplicate."""


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuilderKit:
    """A composable Builder Kit definition.

    Loaded from ``src/ham/data/builder_kits/<kit_id>.json``. Tuple fields
    are immutable so a kit instance is safe to share across requests.
    """

    kit_id: str
    app_archetype: str
    supported_template_kinds: tuple[str, ...]
    stack_recipe: tuple[str, ...]
    expected_files: tuple[str, ...]
    expected_routes: tuple[str, ...]
    design_recipe: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    validation_checklist: tuple[str, ...]
    safety_constraints: tuple[str, ...]
    examples: tuple[str, ...] = field(default_factory=tuple)
    legacy_parity_only: bool = False
    migration_note: str | None = None


# ---------------------------------------------------------------------------
# Disk loading
# ---------------------------------------------------------------------------


_KIT_DATA_DIR: Path = Path(__file__).resolve().parent / "data" / "builder_kits"


_REQUIRED_STR_FIELDS: tuple[str, ...] = (
    "kit_id",
    "app_archetype",
)

_REQUIRED_LIST_FIELDS: tuple[str, ...] = (
    "supported_template_kinds",
    "stack_recipe",
    "expected_files",
    "expected_routes",
    "design_recipe",
    "allowed_capabilities",
    "validation_checklist",
    "safety_constraints",
)


def _normalize_kit_id(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _coerce_str_tuple(field_name: str, raw: Any, *, source: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise BuilderKitConfigError(
            f"{source}: field {field_name!r} must be a JSON array, got "
            f"{type(raw).__name__}"
        )
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise BuilderKitConfigError(
                f"{source}: field {field_name!r}[{i}] must be a string, got "
                f"{type(item).__name__}"
            )
        if item != item.strip():
            raise BuilderKitConfigError(
                f"{source}: field {field_name!r}[{i}] must not have leading or "
                "trailing whitespace"
            )
        out.append(item)
    return tuple(out)


def _build_kit_from_payload(payload: dict[str, Any], *, source: str) -> BuilderKit:
    if not isinstance(payload, dict):
        raise BuilderKitConfigError(
            f"{source}: top-level JSON must be an object, got "
            f"{type(payload).__name__}"
        )

    for name in _REQUIRED_STR_FIELDS:
        if name not in payload:
            raise BuilderKitConfigError(f"{source}: missing required field {name!r}")
        if not isinstance(payload[name], str) or not payload[name].strip():
            raise BuilderKitConfigError(
                f"{source}: field {name!r} must be a non-empty string"
            )

    for name in _REQUIRED_LIST_FIELDS:
        if name not in payload:
            raise BuilderKitConfigError(f"{source}: missing required field {name!r}")

    kit_id = _normalize_kit_id(payload["kit_id"])
    if not kit_id:
        raise BuilderKitConfigError(f"{source}: kit_id is empty after normalization")

    legacy_parity_only_raw = payload.get("legacy_parity_only", False)
    if not isinstance(legacy_parity_only_raw, bool):
        raise BuilderKitConfigError(
            f"{source}: field 'legacy_parity_only' must be a boolean"
        )

    migration_note_raw = payload.get("migration_note")
    if migration_note_raw is not None and not isinstance(migration_note_raw, str):
        raise BuilderKitConfigError(
            f"{source}: field 'migration_note' must be a string or null"
        )

    examples_raw = payload.get("examples", [])
    examples = _coerce_str_tuple("examples", examples_raw, source=source)

    return BuilderKit(
        kit_id=kit_id,
        app_archetype=payload["app_archetype"],
        supported_template_kinds=tuple(
            _normalize_kit_id(s)
            for s in _coerce_str_tuple(
                "supported_template_kinds",
                payload["supported_template_kinds"],
                source=source,
            )
        ),
        stack_recipe=_coerce_str_tuple(
            "stack_recipe", payload["stack_recipe"], source=source
        ),
        expected_files=_coerce_str_tuple(
            "expected_files", payload["expected_files"], source=source
        ),
        expected_routes=_coerce_str_tuple(
            "expected_routes", payload["expected_routes"], source=source
        ),
        design_recipe=_coerce_str_tuple(
            "design_recipe", payload["design_recipe"], source=source
        ),
        allowed_capabilities=_coerce_str_tuple(
            "allowed_capabilities", payload["allowed_capabilities"], source=source
        ),
        validation_checklist=_coerce_str_tuple(
            "validation_checklist", payload["validation_checklist"], source=source
        ),
        safety_constraints=_coerce_str_tuple(
            "safety_constraints", payload["safety_constraints"], source=source
        ),
        examples=examples,
        legacy_parity_only=legacy_parity_only_raw,
        migration_note=migration_note_raw,
    )


def _load_kits_from_disk(data_dir: Path | None = None) -> dict[str, BuilderKit]:
    """Read every ``*.json`` file in the kit data dir and build a dict.

    Args:
        data_dir: Optional override (defaults to ``_KIT_DATA_DIR``). Tests
            that need to validate duplicate-id behavior point this at a
            ``tmp_path``.

    Raises:
        BuilderKitConfigError: on duplicate kit_id, missing required
            fields, or invalid types.
    """
    target = data_dir if data_dir is not None else _KIT_DATA_DIR
    out: dict[str, BuilderKit] = {}
    if not target.is_dir():
        return out
    for path in sorted(target.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BuilderKitConfigError(
                f"{path.name}: invalid JSON ({exc})"
            ) from exc
        kit = _build_kit_from_payload(payload, source=path.name)
        if kit.kit_id in out:
            raise BuilderKitConfigError(
                f"duplicate kit_id {kit.kit_id!r} (already defined; second "
                f"definition in {path.name})"
            )
        out[kit.kit_id] = kit
    return out


_KITS: dict[str, BuilderKit] = _load_kits_from_disk()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_kit(kit_id: str) -> BuilderKit | None:
    """Look up a kit by its id (whitespace / case tolerant)."""
    key = _normalize_kit_id(kit_id)
    if not key:
        return None
    return _KITS.get(key)


def get_kit_for_template_kind(template_kind: str) -> BuilderKit | None:
    """Return the kit that supports ``template_kind``, or the ``generic`` fallback.

    Normalization mirrors :mod:`builder_template_kinds` (strip + lower).
    Falls back to the ``generic`` kit when no kit declares the kind in its
    ``supported_template_kinds``. Returns ``None`` only when both lookups
    fail (e.g. data dir missing).
    """
    key = _normalize_kit_id(template_kind)
    for kit in _KITS.values():
        if key and key in kit.supported_template_kinds:
            return kit
    return _KITS.get("generic")


def list_kit_ids() -> tuple[str, ...]:
    """Sorted tuple of registered kit ids."""
    return tuple(sorted(_KITS.keys()))


def iter_kits() -> Iterable[BuilderKit]:
    """Yield every kit in deterministic sorted order."""
    for kit_id in sorted(_KITS.keys()):
        yield _KITS[kit_id]


def render_kit_context(kit: BuilderKit) -> str:
    """Render a stable plain-text context block suitable for an LLM user message.

    Format is deterministic — assertions in tests substring-match these
    lines. Keep header order stable.
    """
    expected_files = (
        ", ".join(kit.expected_files) if kit.expected_files else "(none specified)"
    )
    expected_routes = (
        ", ".join(kit.expected_routes) if kit.expected_routes else "(none)"
    )
    lines: list[str] = [
        f"Builder Kit: {kit.kit_id}",
        f"Archetype: {kit.app_archetype}",
        f"Stack: {', '.join(kit.stack_recipe)}",
        f"Expected files: {expected_files}",
        f"Expected routes: {expected_routes}",
        f"Design recipe: {', '.join(kit.design_recipe)}",
        f"Allowed capabilities: {', '.join(kit.allowed_capabilities)}",
        f"Safety constraints: {', '.join(kit.safety_constraints)}",
        "Validation checklist:",
    ]
    for item in kit.validation_checklist:
        lines.append(f"  - {item}")
    return "\n".join(lines)


__all__ = [
    "BuilderKit",
    "BuilderKitConfigError",
    "get_kit",
    "get_kit_for_template_kind",
    "iter_kits",
    "list_kit_ids",
    "render_kit_context",
]
