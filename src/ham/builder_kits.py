"""Composable Builder Kit registry (ADR-0011 strangler-pattern continuation).

Builder Kits are reusable, declarative bundles of app-archetype metadata
(stack recipe, expected files / routes, design recipe, capability tokens,
validation checklist, safety constraints) that the LLM scaffold path can
consume to produce more consistent, verifier-friendly output.

Boundary / migration rules:

- The calculator and tetris kits exist with ``legacy_parity_only=True``
  as **historical migration evidence**. The legacy deterministic runtime
  path was retired; those template kinds now route through the LLM
  scaffold path with these kits as their Builder Kit context.
- Adding a new kit here is a normal extension of the LLM scaffold
  catalog — there is no longer a separate legacy registry to coordinate
  with (``builder_template_kinds._REGISTRY`` is empty).
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
    recommended_resources: tuple[str, ...] = field(default_factory=tuple)
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

    recommended_resources_raw = payload.get("recommended_resources", [])
    recommended_resources = tuple(
        _normalize_kit_id(s)
        for s in _coerce_str_tuple(
            "recommended_resources", recommended_resources_raw, source=source
        )
    )

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
        recommended_resources=recommended_resources,
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
    if kit.recommended_resources:
        lines.append("Recommended resources:")
        for resource_id in kit.recommended_resources:
            lines.append(f"  - {resource_id}")
    return "\n".join(lines)


__all__ = [
    "BuilderKit",
    "BuilderKitConfigError",
    "BuilderResource",
    "BuilderResourceConfigError",
    "get_kit",
    "get_kit_for_template_kind",
    "get_resource",
    "iter_kits",
    "iter_resources",
    "list_kit_ids",
    "list_resource_ids",
    "list_resources_for_kit",
    "render_kit_context",
    "resources_allowed_for_generation",
    "validate_kit_resource_ids",
]


# ---------------------------------------------------------------------------
# Resource catalog
# ---------------------------------------------------------------------------


class BuilderResourceConfigError(Exception):
    """Raised when a Builder Resource catalog entry is malformed or duplicate."""


@dataclass(frozen=True)
class BuilderResource:
    resource_id: str
    name: str
    type: str
    url: str
    license: str
    license_status: str
    free_status: str
    api_key_required: bool
    offline_friendly: bool
    agent_friendliness: int
    recommended_for: tuple[str, ...]
    usage_policy: str
    notes: str = ""
    risks: str = ""


_RESOURCE_DATA_FILE: Path = (
    Path(__file__).resolve().parent / "data" / "builder_resources" / "resources.json"
)


_RESOURCE_TYPES: frozenset[str] = frozenset(
    {
        "component-library",
        "ui-blocks",
        "ui-library",
        "charting",
        "table",
        "form",
        "validation",
        "accessibility-validation",
        "data-fetching",
        "mock-api",
        "icons",
        "animation",
        "reference-only",
    }
)
_RESOURCE_LICENSE_STATUSES: frozenset[str] = frozenset(
    {"safe-direct", "safe-reference", "restricted", "unknown"}
)
_RESOURCE_FREE_STATUSES: frozenset[str] = frozenset(
    {"free", "freemium", "paid", "mixed"}
)
_RESOURCE_USAGE_POLICIES: frozenset[str] = frozenset(
    {"use_directly", "reference_only", "avoid"}
)


_RESOURCE_REQUIRED_STR_FIELDS: tuple[str, ...] = (
    "resource_id",
    "name",
    "type",
    "url",
    "license",
    "license_status",
    "free_status",
    "usage_policy",
)


def _coerce_resource_str_tuple(
    field_name: str, raw: Any, *, source: str
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise BuilderResourceConfigError(
            f"{source}: field {field_name!r} must be a JSON array, got "
            f"{type(raw).__name__}"
        )
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise BuilderResourceConfigError(
                f"{source}: field {field_name!r}[{i}] must be a string, got "
                f"{type(item).__name__}"
            )
        if item != item.strip():
            raise BuilderResourceConfigError(
                f"{source}: field {field_name!r}[{i}] must not have leading or "
                "trailing whitespace"
            )
        out.append(item)
    return tuple(out)


def _build_resource_from_payload(
    payload: dict[str, Any], *, source: str
) -> BuilderResource:
    if not isinstance(payload, dict):
        raise BuilderResourceConfigError(
            f"{source}: resource entry must be a JSON object, got "
            f"{type(payload).__name__}"
        )

    for name in _RESOURCE_REQUIRED_STR_FIELDS:
        if name not in payload:
            raise BuilderResourceConfigError(
                f"{source}: missing required field {name!r}"
            )
        value = payload[name]
        if not isinstance(value, str) or not value.strip():
            raise BuilderResourceConfigError(
                f"{source}: field {name!r} must be a non-empty string"
            )
        if value != value.strip():
            raise BuilderResourceConfigError(
                f"{source}: field {name!r} must not have leading or trailing "
                "whitespace"
            )

    resource_type = payload["type"]
    if resource_type not in _RESOURCE_TYPES:
        raise BuilderResourceConfigError(
            f"{source}: field 'type' must be one of {sorted(_RESOURCE_TYPES)!r}, "
            f"got {resource_type!r}"
        )

    license_status = payload["license_status"]
    if license_status not in _RESOURCE_LICENSE_STATUSES:
        raise BuilderResourceConfigError(
            f"{source}: field 'license_status' must be one of "
            f"{sorted(_RESOURCE_LICENSE_STATUSES)!r}, got {license_status!r}"
        )

    free_status = payload["free_status"]
    if free_status not in _RESOURCE_FREE_STATUSES:
        raise BuilderResourceConfigError(
            f"{source}: field 'free_status' must be one of "
            f"{sorted(_RESOURCE_FREE_STATUSES)!r}, got {free_status!r}"
        )

    usage_policy = payload["usage_policy"]
    if usage_policy not in _RESOURCE_USAGE_POLICIES:
        raise BuilderResourceConfigError(
            f"{source}: field 'usage_policy' must be one of "
            f"{sorted(_RESOURCE_USAGE_POLICIES)!r}, got {usage_policy!r}"
        )

    for bool_field in ("api_key_required", "offline_friendly"):
        if bool_field not in payload:
            raise BuilderResourceConfigError(
                f"{source}: missing required field {bool_field!r}"
            )
        if not isinstance(payload[bool_field], bool):
            raise BuilderResourceConfigError(
                f"{source}: field {bool_field!r} must be a boolean"
            )

    if "agent_friendliness" not in payload:
        raise BuilderResourceConfigError(
            f"{source}: missing required field 'agent_friendliness'"
        )
    agent_friendliness = payload["agent_friendliness"]
    if isinstance(agent_friendliness, bool) or not isinstance(
        agent_friendliness, int
    ):
        raise BuilderResourceConfigError(
            f"{source}: field 'agent_friendliness' must be an integer"
        )
    if not 1 <= agent_friendliness <= 5:
        raise BuilderResourceConfigError(
            f"{source}: field 'agent_friendliness' must be in [1, 5], got "
            f"{agent_friendliness}"
        )

    if "recommended_for" not in payload:
        raise BuilderResourceConfigError(
            f"{source}: missing required field 'recommended_for'"
        )
    recommended_for = _coerce_resource_str_tuple(
        "recommended_for", payload["recommended_for"], source=source
    )

    for optional_str in ("notes", "risks"):
        raw_optional = payload.get(optional_str, "")
        if not isinstance(raw_optional, str):
            raise BuilderResourceConfigError(
                f"{source}: field {optional_str!r} must be a string"
            )

    return BuilderResource(
        resource_id=_normalize_kit_id(payload["resource_id"]),
        name=payload["name"],
        type=resource_type,
        url=payload["url"],
        license=payload["license"],
        license_status=license_status,
        free_status=free_status,
        api_key_required=payload["api_key_required"],
        offline_friendly=payload["offline_friendly"],
        agent_friendliness=agent_friendliness,
        recommended_for=recommended_for,
        usage_policy=usage_policy,
        notes=payload.get("notes", ""),
        risks=payload.get("risks", ""),
    )


def _load_resources_from_disk(
    data_file: Path | None = None,
) -> dict[str, BuilderResource]:
    """Load the resource catalog from ``resources.json``.

    Raises:
        BuilderResourceConfigError: on malformed JSON, missing required
            fields, invalid enum values, out-of-range numeric values, or
            duplicate ``resource_id``.
    """
    target = data_file if data_file is not None else _RESOURCE_DATA_FILE
    out: dict[str, BuilderResource] = {}
    if not target.is_file():
        return out
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuilderResourceConfigError(
            f"{target.name}: invalid JSON ({exc})"
        ) from exc
    if not isinstance(document, dict) or "resources" not in document:
        raise BuilderResourceConfigError(
            f"{target.name}: top-level JSON must be an object with a "
            "'resources' array"
        )
    entries = document["resources"]
    if not isinstance(entries, list):
        raise BuilderResourceConfigError(
            f"{target.name}: 'resources' must be a JSON array, got "
            f"{type(entries).__name__}"
        )
    for index, entry in enumerate(entries):
        source = f"{target.name}#resources[{index}]"
        resource = _build_resource_from_payload(entry, source=source)
        if not resource.resource_id:
            raise BuilderResourceConfigError(
                f"{source}: resource_id is empty after normalization"
            )
        if resource.resource_id in out:
            raise BuilderResourceConfigError(
                f"duplicate resource_id {resource.resource_id!r} "
                f"(second definition at {source})"
            )
        out[resource.resource_id] = resource
    return out


_RESOURCES: dict[str, BuilderResource] = _load_resources_from_disk()


def get_resource(resource_id: str) -> BuilderResource | None:
    """Look up a resource by id (whitespace / case tolerant)."""
    key = _normalize_kit_id(resource_id)
    if not key:
        return None
    return _RESOURCES.get(key)


def list_resource_ids() -> tuple[str, ...]:
    """Sorted tuple of registered resource ids."""
    return tuple(sorted(_RESOURCES.keys()))


def iter_resources() -> Iterable[BuilderResource]:
    """Yield every resource in deterministic sorted order."""
    for resource_id in sorted(_RESOURCES.keys()):
        yield _RESOURCES[resource_id]


def list_resources_for_kit(kit_id: str) -> tuple[BuilderResource, ...]:
    """Resources whose ``recommended_for`` includes ``kit_id``."""
    key = _normalize_kit_id(kit_id)
    if not key:
        return ()
    matched = [
        resource
        for resource in _RESOURCES.values()
        if key in resource.recommended_for
    ]
    return tuple(sorted(matched, key=lambda r: r.resource_id))


def resources_allowed_for_generation(kit_id: str) -> tuple[BuilderResource, ...]:
    """Resources a kit may freely mention in generated output.

    Filters :func:`list_resources_for_kit` to ``usage_policy == "use_directly"``
    AND ``license_status in {"safe-direct", "safe-reference"}``.
    """
    allowed_statuses = {"safe-direct", "safe-reference"}
    return tuple(
        resource
        for resource in list_resources_for_kit(kit_id)
        if resource.usage_policy == "use_directly"
        and resource.license_status in allowed_statuses
    )


def validate_kit_resource_ids() -> None:
    """Validate every kit's ``recommended_resources`` against the catalog.

    Raises:
        BuilderResourceConfigError: when an id does not resolve or when a
            resolved resource is not freely usable
            (``usage_policy != "use_directly"``).
    """
    for kit in _KITS.values():
        for resource_id in kit.recommended_resources:
            resource = _RESOURCES.get(resource_id)
            if resource is None:
                raise BuilderResourceConfigError(
                    f"kit {kit.kit_id!r} recommends unknown resource "
                    f"{resource_id!r}"
                )
            if resource.usage_policy != "use_directly":
                raise BuilderResourceConfigError(
                    f"kit {kit.kit_id!r} recommends resource "
                    f"{resource_id!r} with usage_policy "
                    f"{resource.usage_policy!r}; only 'use_directly' "
                    "resources may be recommended"
                )


validate_kit_resource_ids()
