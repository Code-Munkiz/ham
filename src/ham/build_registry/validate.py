"""Validation for Build Kit Registry v2 packs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.ham.build_registry._helpers import require_str, require_str_list
from src.ham.build_registry.errors import BuildRegistryConfigError
from src.ham.build_registry.models import (
    EXPECTED_SCHEMA_VERSION,
    MODULE_INDEX_KEYS,
    MODULE_REQUIRED_FIELDS,
    PACK_REQUIRED_FIELDS,
    REF_FIELDS,
    VALIDATOR_RUNNERS,
    VALIDATOR_SEVERITIES,
    RegistryPack,
)


def _flatten_module_index(module_index: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in MODULE_INDEX_KEYS:
        entries = module_index.get(key)
        if entries is None:
            raise BuildRegistryConfigError(
                f"registry-pack.yaml: module_index missing key {key!r}"
            )
        if not isinstance(entries, list):
            raise BuildRegistryConfigError(
                f"registry-pack.yaml: module_index.{key} must be a list"
            )
        for item in entries:
            if not isinstance(item, str) or not item.strip():
                raise BuildRegistryConfigError(
                    f"registry-pack.yaml: module_index.{key} entries must be "
                    "non-empty strings"
                )
            ids.append(item.strip())
    return ids


def _resolve_ref_ids(
    module_id: str,
    field: str,
    refs: list[str],
    known_ids: set[str],
    errors: list[str],
) -> None:
    for ref in refs:
        if ref.startswith("tag:"):
            continue
        if ref not in known_ids:
            errors.append(f"{module_id}: {field} references unknown id {ref!r}")


def detect_dependency_cycle(
    module_ids: Sequence[str],
    modules: dict[str, dict[str, Any]],
) -> None:
    id_set = set(module_ids)

    def deps(node: str) -> list[str]:
        raw = modules[node].get("depends_on") or []
        if not isinstance(raw, list):
            return []
        return [d for d in raw if isinstance(d, str) and d in id_set]

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise BuildRegistryConfigError(
                f"Dependency cycle detected involving {node!r} "
                f"among {sorted(id_set)}"
            )
        visiting.add(node)
        for dep in deps(node):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for mid in module_ids:
        visit(mid)


def _collect_validation_errors(pack: RegistryPack) -> list[str]:
    errors: list[str] = []
    manifest = dict(pack.manifest)
    modules = {mid: dict(mod.data) for mid, mod in pack.modules.items()}
    known_ids = set(modules)

    for field in PACK_REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"registry-pack.yaml: missing field {field!r}")

    if errors:
        return errors

    pack_id = require_str(manifest, "id", source="registry-pack.yaml")
    if manifest.get("kind") != "registry_pack":
        errors.append(
            f"registry-pack.yaml: expected kind 'registry_pack', "
            f"got {manifest.get('kind')!r}"
        )

    schema_version = require_str(manifest, "schema_version", source="registry-pack.yaml")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        errors.append(
            f"registry-pack.yaml: expected schema_version "
            f"{EXPECTED_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    _flatten_module_index(manifest["module_index"])

    for module_id, payload in sorted(modules.items()):
        source = module_id
        for field in MODULE_REQUIRED_FIELDS:
            if field not in payload:
                errors.append(f"{source}: missing field {field!r}")

        mod_schema = payload.get("schema_version")
        if isinstance(mod_schema, str) and mod_schema != schema_version:
            errors.append(
                f"{source}: schema_version {mod_schema!r} != pack "
                f"{schema_version!r}"
            )

        for field in REF_FIELDS:
            refs = require_str_list(payload, field, source=source)
            _resolve_ref_ids(source, field, refs, known_ids, errors)

    for app_id, app in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "app_type"
    ):
        stack_kit_id = app.get("stack_kit_id")
        if not isinstance(stack_kit_id, str) or not stack_kit_id.strip():
            errors.append(f"{app_id}: missing stack_kit_id")
        elif stack_kit_id.strip() not in known_ids:
            errors.append(f"{app_id}: stack_kit_id {stack_kit_id!r} does not resolve")

        if "legacy_v1_fallback" not in app:
            errors.append(f"{app_id}: missing legacy_v1_fallback")
        elif not isinstance(app.get("legacy_v1_fallback"), str):
            errors.append(f"{app_id}: legacy_v1_fallback must be a string")

        safety = app.get("safety_constraints")
        if not isinstance(safety, list) or not safety:
            errors.append(f"{app_id}: safety_constraints must be a non-empty list")

        composed = app.get("composed_modules")
        if not isinstance(composed, dict):
            errors.append(f"{app_id}: composed_modules must be a mapping")
            composed = {}

        for list_field in (
            "mechanics",
            "component_contracts",
            "validators",
            "recovery_playbooks",
        ):
            refs = composed.get(list_field)
            if not isinstance(refs, list) or not refs:
                errors.append(
                    f"{app_id}: composed_modules.{list_field} must be a non-empty list"
                )
                continue
            for ref in refs:
                if not isinstance(ref, str) or ref not in known_ids:
                    errors.append(
                        f"{app_id}: composed_modules.{list_field} "
                        f"references unknown id {ref!r}"
                    )

        composed_stack = composed.get("stack_kit_id")
        if isinstance(composed_stack, str) and composed_stack.strip() not in known_ids:
            errors.append(
                f"{app_id}: composed_modules.stack_kit_id "
                f"{composed_stack!r} does not resolve"
            )

        for scalar_field in ("progress_labels", "learning_hooks"):
            ref = composed.get(scalar_field)
            if isinstance(ref, str) and ref not in known_ids:
                errors.append(
                    f"{app_id}: composed_modules.{scalar_field} "
                    f"references unknown id {ref!r}"
                )

        phases = app.get("build_phases")
        if not isinstance(phases, list) or not phases:
            errors.append(f"{app_id}: build_phases must be a non-empty list")
        else:
            phase_ids: list[str] = []
            orders: list[int] = []
            for i, phase in enumerate(phases):
                if not isinstance(phase, dict):
                    errors.append(f"{app_id}: build_phases[{i}] must be a mapping")
                    continue
                pid = phase.get("id")
                if not isinstance(pid, str) or not pid.strip():
                    errors.append(f"{app_id}: build_phases[{i}] missing id")
                else:
                    phase_ids.append(pid.strip())
                order = phase.get("order")
                if not isinstance(order, int):
                    errors.append(f"{app_id}: build_phases[{i}] missing int order")
                else:
                    orders.append(order)
            if len(set(phase_ids)) != len(phase_ids):
                errors.append(f"{app_id}: build_phases ids must be unique")
            if orders != sorted(orders):
                errors.append(f"{app_id}: build_phases order values must be ascending")

    for vid, validator in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "validator"
    ):
        severity = validator.get("severity")
        if severity not in VALIDATOR_SEVERITIES:
            errors.append(
                f"{vid}: severity must be one of {sorted(VALIDATOR_SEVERITIES)}, "
                f"got {severity!r}"
            )
        runner = validator.get("runner")
        if runner not in VALIDATOR_RUNNERS:
            errors.append(
                f"{vid}: runner must be one of {sorted(VALIDATOR_RUNNERS)}, "
                f"got {runner!r}"
            )

    for rid, recovery in (
        (mid, mod)
        for mid, mod in modules.items()
        if mod.get("kind") == "recovery_playbook"
    ):
        max_attempts = recovery.get("max_attempts")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            errors.append(f"{rid}: max_attempts must be a positive integer")
        steps = recovery.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{rid}: steps must be a non-empty list")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"{rid}: steps[{i}] must be a mapping")
                    continue
                for key in ("id", "action", "detail"):
                    val = step.get(key)
                    if not isinstance(val, str) or not val.strip():
                        errors.append(f"{rid}: steps[{i}] missing non-empty {key!r}")

    for pl_id, progress in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "progress_label"
    ):
        owner = progress.get("source_phase_owner")
        if not isinstance(owner, str) or owner not in known_ids:
            errors.append(f"{pl_id}: source_phase_owner must resolve to an app_type id")
            continue
        owner_mod = modules.get(owner)
        if not owner_mod or owner_mod.get("kind") != "app_type":
            errors.append(f"{pl_id}: source_phase_owner {owner!r} is not an app_type")
            continue
        phase_map = progress.get("phase_message_map")
        if not isinstance(phase_map, dict):
            errors.append(f"{pl_id}: phase_message_map must be a mapping")
            continue
        owner_phase_ids = {
            p.get("id")
            for p in (owner_mod.get("build_phases") or [])
            if isinstance(p, dict) and isinstance(p.get("id"), str)
        }
        for key in phase_map:
            if key not in owner_phase_ids:
                errors.append(
                    f"{pl_id}: phase_message_map key {key!r} not in "
                    f"{owner} build_phases"
                )
        for pid in owner_phase_ids:
            if pid and pid not in phase_map:
                errors.append(f"{pl_id}: missing phase_message_map entry for {pid!r}")

    for app_id, app in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "app_type"
    ):
        composed = app.get("composed_modules") or {}
        mech_ids = [m for m in (composed.get("mechanics") or []) if isinstance(m, str)]
        comp_ids = [
            c for c in (composed.get("component_contracts") or []) if isinstance(c, str)
        ]
        try:
            if mech_ids:
                detect_dependency_cycle(mech_ids, modules)
            if comp_ids:
                detect_dependency_cycle(comp_ids, modules)
        except BuildRegistryConfigError as exc:
            errors.append(f"{app_id}: {exc}")

    if not errors and pack_id != "pack.game":
        errors.append(f"registry-pack.yaml: expected id 'pack.game', got {pack_id!r}")

    return errors


def validate_registry_pack(pack: RegistryPack) -> None:
    """Validate a loaded pack. Raises :class:`BuildRegistryConfigError` on failure."""
    errors = _collect_validation_errors(pack)
    if errors:
        message = "Registry pack validation failed:\n" + "\n".join(
            f"  - {err}" for err in errors
        )
        raise BuildRegistryConfigError(message)
