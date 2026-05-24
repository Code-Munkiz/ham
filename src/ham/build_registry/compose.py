"""Compose BuildRecipe from a validated registry pack."""

from __future__ import annotations

from collections.abc import Sequence

from src.ham.build_registry._helpers import require_str, require_str_list
from src.ham.build_registry.errors import BuildRegistryConfigError
from src.ham.build_registry.models import BuildRecipe, RegistryPack
from src.ham.build_registry.validate import detect_dependency_cycle


def topological_sort(
    module_ids: Sequence[str],
    modules: dict[str, dict],
) -> tuple[str, ...]:
    id_set = set(module_ids)
    detect_dependency_cycle(module_ids, modules)

    incoming = {mid: 0 for mid in module_ids}
    edges: dict[str, list[str]] = {mid: [] for mid in module_ids}

    for mid in module_ids:
        for dep in require_str_list(modules[mid], "depends_on", source=mid):
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
        raise BuildRegistryConfigError(
            f"Could not topologically sort modules: {sorted(module_ids)}"
        )
    return tuple(ordered)


def compose_build_recipe(pack: RegistryPack, app_type_id: str) -> BuildRecipe:
    """Compose a recipe for ``app_type_id`` from a loaded pack."""
    if app_type_id not in pack.modules:
        raise BuildRegistryConfigError(f"Unknown app_type id {app_type_id!r}")

    app = pack.module_data(app_type_id)
    if app.get("kind") != "app_type":
        raise BuildRegistryConfigError(
            f"{app_type_id}: kind must be 'app_type', got {app.get('kind')!r}"
        )

    composed = app.get("composed_modules")
    if not isinstance(composed, dict):
        raise BuildRegistryConfigError(f"{app_type_id}: composed_modules missing")

    modules_data = {mid: pack.module_data(mid) for mid in pack.modules}

    stack_kit_id = require_str(app, "stack_kit_id", source=app_type_id)
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

    ordered_mechanics = topological_sort(mechanic_ids, modules_data)
    ordered_components = topological_sort(component_ids, modules_data)

    return BuildRecipe(
        pack=pack,
        app_type_id=app_type_id,
        stack_kit_id=stack_kit_id,
        mechanic_ids=ordered_mechanics,
        component_ids=ordered_components,
        validator_ids=tuple(validator_ids),
        recovery_ids=tuple(recovery_ids),
        progress_label_id=progress_label_id,
        learning_hook_id=learning_hook_id,
    )
