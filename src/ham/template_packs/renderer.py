"""Materialize template pack starter files into an isolated Hermes workspace."""

from __future__ import annotations

from pathlib import Path

from src.ham.builder_preview_bootstrap import safe_npm_package_name
from src.ham.template_packs.schema import TemplatePack

_TEMPLATE_PACK_INTERNAL_HEADER = "HAM template pack baseline (internal — do not mention pack ids to the user):"


def template_pack_hermes_instruction(pack: TemplatePack) -> str:
    """Short internal instruction appended to the Hermes workspace prompt."""
    directive = pack.manifest.ai_directive.replace("_", " ")
    return (
        "Use this starter pack as the design baseline. Customize it to the user request. "
        "Preserve the polished layout quality, spacing, typography, cards, and responsive styling. "
        f"Customization mode: {directive}. "
        "Do not reduce the UI to unstyled/default HTML."
    )


def append_template_pack_context(user_prompt: str, pack: TemplatePack) -> str:
    """Append internal template-pack guidance (never shown to end users)."""
    prompt = str(user_prompt or "").strip()
    block = template_pack_hermes_instruction(pack)
    return f"{prompt}\n\n{_TEMPLATE_PACK_INTERNAL_HEADER}\n{block}"


def materialize_pack_files(pack: TemplatePack, *, project_title: str) -> dict[str, str]:
    """Return a copy of pack files with optional package name substitution."""
    files = dict(pack.files)
    pkg_name = safe_npm_package_name(project_title)
    pkg_json = files.get("package.json")
    if pkg_json and '"name"' in pkg_json:
        import json

        try:
            data = json.loads(pkg_json)
            if isinstance(data, dict):
                data["name"] = pkg_name
                files["package.json"] = json.dumps(data, indent=2) + "\n"
        except json.JSONDecodeError:
            pass
    return files


def write_pack_to_workspace(workspace_dir: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = workspace_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def seed_template_pack_workspace(
    workspace_dir: Path,
    *,
    pack: TemplatePack,
    user_prompt: str,
) -> None:
    """Write template pack starter files into the isolated workspace directory."""
    title = (user_prompt or pack.manifest.name)[:80]
    files = materialize_pack_files(pack, project_title=title)
    write_pack_to_workspace(workspace_dir, files)


__all__ = [
    "append_template_pack_context",
    "materialize_pack_files",
    "seed_template_pack_workspace",
    "template_pack_hermes_instruction",
    "write_pack_to_workspace",
]
