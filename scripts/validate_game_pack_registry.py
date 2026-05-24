#!/usr/bin/env python3
"""Read-only validator and renderer for Build Kit Registry v2 Game Pack pilot.

Phase 0 spike — not imported by HAM runtime. Loads YAML from
``docs/build-kit-registry-v2/game-pack/``, validates cross-references,
composes a BuildRecipe for an app type, and optionally renders deterministic
playbook context for future LLM scaffolding.

Example::

    python scripts/validate_game_pack_registry.py \\
      --pack-root docs/build-kit-registry-v2/game-pack \\
      --app-type game.idle-incremental \\
      --check \\
      --render-sample /dev/stdout
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_MANIFEST_NAME = "registry-pack.yaml"
EXPECTED_SCHEMA_VERSION = "0.1"
RENDER_CHAR_BUDGET = 12_000

MODULE_REQUIRED_FIELDS = (
    "id",
    "kind",
    "schema_version",
    "status",
    "description",
    "non_template_statement",
)

PACK_REQUIRED_FIELDS = ("id", "kind", "schema_version", "module_index")

MODULE_INDEX_KEYS = (
    "app_types",
    "stack_kits",
    "mechanics",
    "component_contracts",
    "validators",
    "recovery_playbooks",
    "progress_labels",
    "learning_hooks",
)

VALIDATOR_SEVERITIES = frozenset({"blocking", "warning"})
VALIDATOR_RUNNERS = frozenset({"conceptual", "static", "harness", "playwright"})

REF_FIELDS = (
    "depends_on",
    "binds_components",
    "binds_mechanics",
    "validates_modules",
    "recovery_playbooks",
    "repairs_validators",
)


@dataclass(frozen=True)
class BuildRecipe:
    """Frozen composed recipe for one app type (in-memory only)."""

    pack_id: str
    schema_version: str
    app_type_id: str
    stack_kit_id: str
    mechanic_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    validator_ids: tuple[str, ...]
    recovery_ids: tuple[str, ...]
    progress_label_id: str | None
    learning_hook_id: str | None


class RegistryValidationError(Exception):
    """Raised when pack YAML fails validation."""


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise RegistryValidationError(f"{path}: top-level YAML must be a mapping")
    return data


def _flatten_module_index(module_index: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in MODULE_INDEX_KEYS:
        entries = module_index.get(key)
        if entries is None:
            raise RegistryValidationError(
                f"registry-pack.yaml: module_index missing key {key!r}"
            )
        if not isinstance(entries, list):
            raise RegistryValidationError(
                f"registry-pack.yaml: module_index.{key} must be a list"
            )
        for item in entries:
            if not isinstance(item, str) or not item.strip():
                raise RegistryValidationError(
                    f"registry-pack.yaml: module_index.{key} entries must be "
                    "non-empty strings"
                )
            ids.append(item.strip())
    return ids


def _collect_yaml_module_files(pack_root: Path) -> list[Path]:
    return sorted(
        path
        for path in pack_root.rglob("*.yaml")
        if path.name != PACK_MANIFEST_NAME
    )


def load_registry_pack(pack_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load manifest and every indexed module keyed by canonical id."""
    pack_root = pack_root.resolve()
    manifest_path = pack_root / PACK_MANIFEST_NAME
    if not manifest_path.is_file():
        raise RegistryValidationError(f"Missing manifest: {manifest_path}")

    pack = _load_yaml(manifest_path)
    indexed_ids = _flatten_module_index(pack["module_index"])
    indexed_set = set(indexed_ids)

    if len(indexed_ids) != len(indexed_set):
        raise RegistryValidationError(
            "registry-pack.yaml: duplicate ids in module_index"
        )

    modules_by_id: dict[str, dict[str, Any]] = {}
    paths_by_id: dict[str, Path] = {}

    for path in _collect_yaml_module_files(pack_root):
        payload = _load_yaml(path)
        module_id = payload.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise RegistryValidationError(f"{path}: missing or empty id")
        module_id = module_id.strip()
        if module_id in modules_by_id:
            raise RegistryValidationError(
                f"Duplicate module id {module_id!r} "
                f"({paths_by_id[module_id]} and {path})"
            )
        modules_by_id[module_id] = payload
        paths_by_id[module_id] = path

    missing = sorted(indexed_set - set(modules_by_id))
    if missing:
        raise RegistryValidationError(
            "Indexed module ids missing YAML files: " + ", ".join(missing)
        )

    orphans = sorted(set(modules_by_id) - indexed_set)
    if orphans:
        details = ", ".join(f"{oid} ({paths_by_id[oid]})" for oid in orphans)
        raise RegistryValidationError(f"Orphan YAML modules not in module_index: {details}")

    for module_id in indexed_ids:
        if paths_by_id[module_id] != paths_by_id.get(module_id):
            pass  # satisfied by single path map

    # Each indexed id must map to exactly one file (already enforced by dict).
    for module_id in indexed_ids:
        if module_id not in paths_by_id:
            raise RegistryValidationError(
                f"Indexed id {module_id!r} has no YAML file"
            )

    return pack, modules_by_id


def _require_str(data: dict[str, Any], field: str, *, source: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(f"{source}: missing or empty field {field!r}")
    return value.strip()


def _require_str_list(
    data: dict[str, Any], field: str, *, source: str
) -> list[str]:
    raw = data.get(field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RegistryValidationError(
            f"{source}: field {field!r} must be a list when present"
        )
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise RegistryValidationError(
                f"{source}: field {field!r}[{i}] must be a non-empty string"
            )
        out.append(item.strip())
    return out


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
            errors.append(
                f"{module_id}: {field} references unknown id {ref!r}"
            )


def _detect_cycle(module_ids: Sequence[str], modules: dict[str, dict[str, Any]]) -> None:
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
            raise RegistryValidationError(
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


def topological_sort(
    module_ids: Sequence[str], modules: dict[str, dict[str, Any]]
) -> tuple[str, ...]:
    id_set = set(module_ids)
    _detect_cycle(module_ids, modules)

    incoming = {mid: 0 for mid in module_ids}
    edges: dict[str, list[str]] = {mid: [] for mid in module_ids}

    for mid in module_ids:
        for dep in _require_str_list(modules[mid], "depends_on", source=mid):
            if dep in id_set:
                edges[dep].append(mid)
                incoming[mid] += 1

    queue = sorted(mid for mid in module_ids if incoming[mid] == 0)
    ordered: list[str] = []
    while queue:
        node = queue.pop(0)
        ordered.append(node)
        for nxt in sorted(edges[node]):
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
                queue.sort()

    if len(ordered) != len(module_ids):
        raise RegistryValidationError(
            f"Could not topologically sort modules: {sorted(module_ids)}"
        )
    return tuple(ordered)


def validate_registry_pack(
    pack: dict[str, Any],
    modules: dict[str, dict[str, Any]],
) -> list[str]:
    """Validate pack and modules. Returns human-readable error strings."""
    errors: list[str] = []
    known_ids = set(modules)

    for field in PACK_REQUIRED_FIELDS:
        if field not in pack:
            errors.append(f"registry-pack.yaml: missing field {field!r}")

    if errors:
        return errors

    pack_id = _require_str(pack, "id", source="registry-pack.yaml")
    if pack.get("kind") != "registry_pack":
        errors.append(
            f"registry-pack.yaml: expected kind 'registry_pack', "
            f"got {pack.get('kind')!r}"
        )

    schema_version = _require_str(pack, "schema_version", source="registry-pack.yaml")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        errors.append(
            f"registry-pack.yaml: expected schema_version "
            f"{EXPECTED_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    indexed_ids = _flatten_module_index(pack["module_index"])

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
            refs = _require_str_list(payload, field, source=source)
            _resolve_ref_ids(source, field, refs, known_ids, errors)

    # App-type-specific checks for every app_type module.
    for app_id, app in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "app_type"
    ):
        stack_kit_id = app.get("stack_kit_id")
        if not isinstance(stack_kit_id, str) or not stack_kit_id.strip():
            errors.append(f"{app_id}: missing stack_kit_id")
        elif stack_kit_id.strip() not in known_ids:
            errors.append(
                f"{app_id}: stack_kit_id {stack_kit_id!r} does not resolve"
            )

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
                errors.append(
                    f"{app_id}: build_phases order values must be ascending"
                )

    # Validators
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

    # Recovery playbooks
    for rid, recovery in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "recovery_playbook"
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
                        errors.append(
                            f"{rid}: steps[{i}] missing non-empty {key!r}"
                        )

    # Progress labels
    for pl_id, progress in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "progress_label"
    ):
        owner = progress.get("source_phase_owner")
        if not isinstance(owner, str) or owner not in known_ids:
            errors.append(
                f"{pl_id}: source_phase_owner must resolve to an app_type id"
            )
            continue
        owner_mod = modules.get(owner)
        if not owner_mod or owner_mod.get("kind") != "app_type":
            errors.append(
                f"{pl_id}: source_phase_owner {owner!r} is not an app_type"
            )
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
                errors.append(
                    f"{pl_id}: missing phase_message_map entry for {pid!r}"
                )

    # Cycle checks on composed app types (pilot: validate all app types).
    for app_id, app in (
        (mid, mod) for mid, mod in modules.items() if mod.get("kind") == "app_type"
    ):
        composed = app.get("composed_modules") or {}
        mech_ids = [
            m for m in (composed.get("mechanics") or []) if isinstance(m, str)
        ]
        comp_ids = [
            c
            for c in (composed.get("component_contracts") or [])
            if isinstance(c, str)
        ]
        try:
            if mech_ids:
                _detect_cycle(mech_ids, modules)
            if comp_ids:
                _detect_cycle(comp_ids, modules)
        except RegistryValidationError as exc:
            errors.append(f"{app_id}: {exc}")

    if not errors and pack_id != "pack.game":
        errors.append(
            f"registry-pack.yaml: expected id 'pack.game', got {pack_id!r}"
        )

    return errors


def compose_build_recipe(
    pack: dict[str, Any],
    modules: dict[str, dict[str, Any]],
    app_type_id: str,
) -> BuildRecipe:
    if app_type_id not in modules:
        raise RegistryValidationError(f"Unknown app_type id {app_type_id!r}")

    app = modules[app_type_id]
    if app.get("kind") != "app_type":
        raise RegistryValidationError(
            f"{app_type_id}: kind must be 'app_type', got {app.get('kind')!r}"
        )

    composed = app.get("composed_modules")
    if not isinstance(composed, dict):
        raise RegistryValidationError(f"{app_type_id}: composed_modules missing")

    stack_kit_id = _require_str(app, "stack_kit_id", source=app_type_id)
    mechanic_ids = list(composed.get("mechanics") or [])
    component_ids = list(composed.get("component_contracts") or [])
    validator_ids = list(composed.get("validators") or [])
    recovery_ids = list(composed.get("recovery_playbooks") or [])

    progress_raw = composed.get("progress_labels")
    progress_label_id = (
        progress_raw.strip()
        if isinstance(progress_raw, str) and progress_raw.strip()
        else None
    )
    learning_raw = composed.get("learning_hooks")
    learning_hook_id = (
        learning_raw.strip()
        if isinstance(learning_raw, str) and learning_raw.strip()
        else None
    )

    ordered_mechanics = topological_sort(mechanic_ids, modules)
    ordered_components = topological_sort(component_ids, modules)

    return BuildRecipe(
        pack_id=_require_str(pack, "id", source="registry-pack.yaml"),
        schema_version=_require_str(
            pack, "schema_version", source="registry-pack.yaml"
        ),
        app_type_id=app_type_id,
        stack_kit_id=stack_kit_id,
        mechanic_ids=ordered_mechanics,
        component_ids=ordered_components,
        validator_ids=tuple(validator_ids),
        recovery_ids=tuple(recovery_ids),
        progress_label_id=progress_label_id,
        learning_hook_id=learning_hook_id,
    )


def _bullet_lines(items: Iterable[str], prefix: str = "  - ") -> list[str]:
    return [f"{prefix}{item}" for item in items]


def _string_list_field(module: dict[str, Any], field: str) -> list[str]:
    raw = module.get(field)
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str)]


def _render_module_summary(module_id: str, module: dict[str, Any]) -> list[str]:
    name = module.get("name") or module_id
    lines = [f"[{module_id}] {name}"]
    for field in ("depends_on", "provides", "binds_components", "binds_mechanics"):
        vals = _string_list_field(module, field)
        if vals:
            lines.append(f"  {field}: {', '.join(vals)}")
    guidance = _string_list_field(module, "guidance")
    if guidance:
        lines.append("  guidance:")
        lines.extend(_bullet_lines(guidance[:6], prefix="    - "))
        if len(guidance) > 6:
            lines.append(f"    - ... ({len(guidance) - 6} more)")
    return lines


def render_playbook_context(
    pack: dict[str, Any],
    modules: dict[str, dict[str, Any]],
    recipe: BuildRecipe,
) -> str:
    app = modules[recipe.app_type_id]
    stack = modules[recipe.stack_kit_id]

    lines: list[str] = [
        "Build Kit Registry v2 — BuildRecipe",
        f"Registry pack: {recipe.pack_id} (schema {recipe.schema_version})",
        f"App type: {recipe.app_type_id} — {app.get('name', '')}",
        f"Legacy v1 fallback: {app.get('legacy_v1_fallback', '')}",
        f"Non-template: {_require_str(app, 'non_template_statement', source=recipe.app_type_id)}",
        "",
        "--- Intent ---",
        f"Description: {app.get('description', '').strip()}",
    ]
    guidance = _string_list_field(app, "guidance")
    if guidance:
        lines.append("Guidance:")
        lines.extend(_bullet_lines(guidance))
    out_of_scope = _string_list_field(app, "out_of_scope")
    if out_of_scope:
        lines.append("Out of scope:")
        lines.extend(_bullet_lines(out_of_scope))

    lines.extend(["", "--- Assumptions ---"])
    assumptions = _string_list_field(app, "default_assumptions")
    if assumptions:
        lines.append("Default assumptions:")
        lines.extend(_bullet_lines(assumptions))
    safety = _string_list_field(app, "safety_constraints")
    lines.append("Safety constraints:")
    lines.extend(_bullet_lines(safety))

    lines.extend(["", "--- Stack ---"])
    lines.append(
        f"Stack kit: {recipe.stack_kit_id} — {stack.get('name', '')}"
    )
    capabilities = _string_list_field(stack, "capabilities")
    if capabilities:
        lines.append(f"Capabilities: {', '.join(capabilities)}")
    stack_guidance = _string_list_field(stack, "guidance")
    if stack_guidance:
        lines.append("Guidance:")
        lines.extend(_bullet_lines(stack_guidance[:8]))
        if len(stack_guidance) > 8:
            lines.append(f"  - ... ({len(stack_guidance) - 8} more)")

    lines.extend(["", "--- Mechanics ---"])
    for mid in recipe.mechanic_ids:
        lines.extend(_render_module_summary(mid, modules[mid]))

    lines.extend(["", "--- Components ---"])
    for cid in recipe.component_ids:
        lines.extend(_render_module_summary(cid, modules[cid]))

    lines.extend(["", "--- Phases ---"])
    phases = app.get("build_phases") or []
    progress = (
        modules.get(recipe.progress_label_id)
        if recipe.progress_label_id
        else None
    )
    phase_map = (
        progress.get("phase_message_map")
        if isinstance(progress, dict)
        else {}
    ) or {}
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        pid = phase.get("id", "")
        order = phase.get("order", "")
        title = phase.get("title", "")
        lines.append(f"{pid} ({order}): {title}")
        mapped = phase_map.get(pid) if isinstance(phase_map, dict) else None
        if isinstance(mapped, dict):
            msg_title = mapped.get("title", "")
            msg = mapped.get("message", "")
            if msg_title or msg:
                lines.append(f"  Progress copy: {msg_title} — {msg}")

    lines.extend(["", "--- Validators (conceptual — not executed) ---"])
    for vid in recipe.validator_ids:
        validator = modules[vid]
        lines.append(
            f"[{vid}] severity={validator.get('severity')} "
            f"runner={validator.get('runner')} "
            f"check_type={validator.get('check_type')}"
        )
        pass_conditions = _string_list_field(validator, "pass_conditions")
        if pass_conditions:
            lines.append("  pass:")
            lines.extend(_bullet_lines(pass_conditions[:4], prefix="    - "))
        recovery = _string_list_field(validator, "recovery_playbooks")
        if recovery:
            lines.append(f"  recovery_playbooks: {', '.join(recovery)}")

    lines.extend(["", "--- Recovery (conceptual — not executed) ---"])
    for rid in recipe.recovery_ids:
        recovery = modules[rid]
        lines.append(
            f"[{rid}] max_attempts={recovery.get('max_attempts')}"
        )
        steps = recovery.get("steps") or []
        if isinstance(steps, list):
            step_ids = [
                s.get("id", "")
                for s in steps
                if isinstance(s, dict) and isinstance(s.get("id"), str)
            ]
            if step_ids:
                lines.append(f"  steps: {' → '.join(step_ids)}")

    lines.extend(["", "--- Progress ---"])
    if recipe.progress_label_id and progress:
        lines.append(f"Progress label: {recipe.progress_label_id}")
        lines.append(
            f"Source phase owner: {progress.get('source_phase_owner', '')}"
        )

    if recipe.learning_hook_id:
        hook = modules.get(recipe.learning_hook_id)
        if hook:
            lines.extend(["", "--- Learning hooks (telemetry shapes only) ---"])
            lines.append(
                f"Learning hook: {recipe.learning_hook_id} — {hook.get('name', '')}"
            )

    rendered = "\n".join(lines).strip() + "\n"
    return _apply_render_budget(rendered, safety, recipe, modules)


def _apply_render_budget(
    rendered: str,
    safety: list[str],
    recipe: BuildRecipe,
    modules: dict[str, dict[str, Any]],
) -> str:
    if len(rendered) <= RENDER_CHAR_BUDGET:
        return rendered

    validator_summary_lines = ["--- Validators (conceptual — not executed) ---"]
    for vid in recipe.validator_ids:
        validator = modules[vid]
        validator_summary_lines.append(
            f"[{vid}] severity={validator.get('severity')} "
            f"runner={validator.get('runner')}"
        )

    tail = "\n".join(
        [
            "",
            "--- Safety constraints (required summary) ---",
            *_bullet_lines(safety),
            "",
            *validator_summary_lines,
            "",
            f"[truncated to {RENDER_CHAR_BUDGET} characters]",
        ]
    )
    keep = RENDER_CHAR_BUDGET - len(tail)
    if keep < 500:
        return (rendered[:RENDER_CHAR_BUDGET - 1] + "…\n")
    return rendered[:keep].rstrip() + "\n" + tail


def _write_render_sample(path: str, content: str) -> None:
    if path == "/dev/stdout":
        sys.stdout.write(content)
        return
    out = Path(path)
    out.write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and render Build Kit Registry v2 Game Pack pilot YAML."
    )
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=REPO_ROOT / "docs/build-kit-registry-v2/game-pack",
        help="Path to game-pack directory containing registry-pack.yaml",
    )
    parser.add_argument(
        "--app-type",
        default="game.idle-incremental",
        help="App type id to compose (default: game.idle-incremental)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate pack; exit 1 on failure",
    )
    parser.add_argument(
        "--render-sample",
        metavar="PATH",
        help="Write rendered playbook context to PATH (/dev/stdout supported)",
    )
    args = parser.parse_args(argv)

    try:
        pack, modules = load_registry_pack(args.pack_root)
    except RegistryValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1 if args.check else 0

    errors = validate_registry_pack(pack, modules)
    if errors:
        print("Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1 if args.check else 0

    if args.check:
        print(
            f"OK: pack {pack.get('id')} schema {pack.get('schema_version')} "
            f"— {len(modules)} modules validated"
        )

    try:
        recipe = compose_build_recipe(pack, modules, args.app_type)
    except RegistryValidationError as exc:
        print(f"ERROR: compose failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print(f"Compose OK: app_type={recipe.app_type_id}")
        print(f"  mechanics: {' → '.join(recipe.mechanic_ids)}")
        print(f"  components: {' → '.join(recipe.component_ids)}")

    if args.render_sample:
        rendered = render_playbook_context(pack, modules, recipe)
        _write_render_sample(args.render_sample, rendered)
        if args.render_sample != "/dev/stdout":
            print(f"Rendered {len(rendered)} characters to {args.render_sample}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
