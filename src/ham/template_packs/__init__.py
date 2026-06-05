"""Template Pack Registry v1 — backstage design starters for native Hermes workspace builds."""

from src.ham.template_packs.quality import (
    TemplatePackQualityResult,
    evaluate_workspace_visual_quality,
    user_message_for_quality_failure,
    visual_quality_repair_instruction,
)
from src.ham.template_packs.registry import load_template_pack_registry
from src.ham.template_packs.renderer import (
    append_template_pack_context,
    seed_template_pack_workspace,
)
from src.ham.template_packs.schema import TemplatePack, TemplatePackManifest
from src.ham.template_packs.selector import select_template_pack

__all__ = [
    "TemplatePack",
    "TemplatePackManifest",
    "TemplatePackQualityResult",
    "append_template_pack_context",
    "evaluate_workspace_visual_quality",
    "load_template_pack_registry",
    "seed_template_pack_workspace",
    "select_template_pack",
    "user_message_for_quality_failure",
    "visual_quality_repair_instruction",
]
