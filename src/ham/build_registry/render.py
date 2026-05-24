"""Render deterministic playbook context from a composed BuildRecipe."""

from __future__ import annotations

from collections.abc import Iterable

from src.ham.build_registry._helpers import require_str, string_list_field
from src.ham.build_registry.models import DEFAULT_RENDER_CHAR_BUDGET, BuildRecipe


def _bullet_lines(items: Iterable[str], prefix: str = "  - ") -> list[str]:
    return [f"{prefix}{item}" for item in items]


def _render_module_summary(module_id: str, module: dict) -> list[str]:
    name = module.get("name") or module_id
    lines = [f"[{module_id}] {name}"]
    for field in ("depends_on", "provides", "binds_components", "binds_mechanics"):
        vals = string_list_field(module, field)
        if vals:
            lines.append(f"  {field}: {', '.join(vals)}")
    guidance = string_list_field(module, "guidance")
    if guidance:
        lines.append("  guidance:")
        lines.extend(_bullet_lines(guidance[:6], prefix="    - "))
        if len(guidance) > 6:
            lines.append(f"    - ... ({len(guidance) - 6} more)")
    return lines


def _apply_render_budget(
    rendered: str,
    *,
    safety: list[str],
    recipe: BuildRecipe,
    max_chars: int,
) -> str:
    if len(rendered) <= max_chars:
        return rendered

    validator_summary_lines = ["--- Validators (conceptual — not executed) ---"]
    for vid in recipe.validator_ids:
        validator = recipe.pack.module_data(vid)
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
            f"[truncated to {max_chars} characters]",
        ]
    )
    keep = max_chars - len(tail)
    if keep < 500:
        return rendered[: max_chars - 1] + "…\n"
    return rendered[:keep].rstrip() + "\n" + tail


def render_playbook_context(
    recipe: BuildRecipe,
    *,
    max_chars: int = DEFAULT_RENDER_CHAR_BUDGET,
) -> str:
    """Render a deterministic plain-text playbook context block."""
    pack = recipe.pack
    app = pack.module_data(recipe.app_type_id)
    stack = pack.module_data(recipe.stack_kit_id)

    lines: list[str] = [
        "Build Kit Registry v2 — BuildRecipe",
        f"Registry pack: {recipe.pack_id} (schema {recipe.schema_version})",
        f"App type: {recipe.app_type_id} — {app.get('name', '')}",
        f"Legacy v1 fallback: {app.get('legacy_v1_fallback', '')}",
        f"Non-template: {require_str(app, 'non_template_statement', source=recipe.app_type_id)}",
        "",
        "--- Intent ---",
        f"Description: {str(app.get('description', '')).strip()}",
    ]
    guidance = string_list_field(app, "guidance")
    if guidance:
        lines.append("Guidance:")
        lines.extend(_bullet_lines(guidance))
    out_of_scope = string_list_field(app, "out_of_scope")
    if out_of_scope:
        lines.append("Out of scope:")
        lines.extend(_bullet_lines(out_of_scope))

    lines.extend(["", "--- Assumptions ---"])
    assumptions = string_list_field(app, "default_assumptions")
    if assumptions:
        lines.append("Default assumptions:")
        lines.extend(_bullet_lines(assumptions))
    safety = string_list_field(app, "safety_constraints")
    lines.append("Safety constraints:")
    lines.extend(_bullet_lines(safety))

    lines.extend(["", "--- Stack ---"])
    lines.append(f"Stack kit: {recipe.stack_kit_id} — {stack.get('name', '')}")
    capabilities = string_list_field(stack, "capabilities")
    if capabilities:
        lines.append(f"Capabilities: {', '.join(capabilities)}")
    stack_guidance = string_list_field(stack, "guidance")
    if stack_guidance:
        lines.append("Guidance:")
        lines.extend(_bullet_lines(stack_guidance[:8]))
        if len(stack_guidance) > 8:
            lines.append(f"  - ... ({len(stack_guidance) - 8} more)")

    lines.extend(["", "--- Mechanics ---"])
    for mid in recipe.mechanic_ids:
        lines.extend(_render_module_summary(mid, pack.module_data(mid)))

    lines.extend(["", "--- Components ---"])
    for cid in recipe.component_ids:
        lines.extend(_render_module_summary(cid, pack.module_data(cid)))

    lines.extend(["", "--- Phases ---"])
    phases = app.get("build_phases") or []
    progress = (
        pack.module_data(recipe.progress_label_id)
        if recipe.progress_label_id
        else None
    )
    phase_map = (
        progress.get("phase_message_map") if isinstance(progress, dict) else {}
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
        validator = pack.module_data(vid)
        lines.append(
            f"[{vid}] severity={validator.get('severity')} "
            f"runner={validator.get('runner')} "
            f"check_type={validator.get('check_type')}"
        )
        pass_conditions = string_list_field(validator, "pass_conditions")
        if pass_conditions:
            lines.append("  pass:")
            lines.extend(_bullet_lines(pass_conditions[:4], prefix="    - "))
        recovery = string_list_field(validator, "recovery_playbooks")
        if recovery:
            lines.append(f"  recovery_playbooks: {', '.join(recovery)}")

    lines.extend(["", "--- Recovery (conceptual — not executed) ---"])
    for rid in recipe.recovery_ids:
        recovery = pack.module_data(rid)
        lines.append(f"[{rid}] max_attempts={recovery.get('max_attempts')}")
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
        lines.append(f"Source phase owner: {progress.get('source_phase_owner', '')}")

    if recipe.learning_hook_id:
        hook = pack.module_data(recipe.learning_hook_id)
        lines.extend(["", "--- Learning hooks (telemetry shapes only) ---"])
        lines.append(
            f"Learning hook: {recipe.learning_hook_id} — {hook.get('name', '')}"
        )

    rendered = "\n".join(lines).strip() + "\n"
    return _apply_render_budget(rendered, safety=safety, recipe=recipe, max_chars=max_chars)
