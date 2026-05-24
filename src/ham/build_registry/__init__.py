"""Build Kit Registry v2 — unwired loader/composer (Game Pack pilot).

Not imported by chat, scaffold, or API paths. Explicit ``pack_root`` required.
"""

from src.ham.build_registry.compose import compose_build_recipe
from src.ham.build_registry.errors import BuildRegistryConfigError
from src.ham.build_registry.loader import load_registry_pack
from src.ham.build_registry.models import (
    DEFAULT_RENDER_CHAR_BUDGET,
    BuildRecipe,
    RegistryModule,
    RegistryPack,
)
from src.ham.build_registry.render import render_playbook_context
from src.ham.build_registry.scaffold_context import (
    ScaffoldContextResult,
    resolve_scaffold_context,
)
from src.ham.build_registry.validate import validate_registry_pack

__all__ = [
    "BuildRecipe",
    "BuildRegistryConfigError",
    "DEFAULT_RENDER_CHAR_BUDGET",
    "RegistryModule",
    "RegistryPack",
    "ScaffoldContextResult",
    "compose_build_recipe",
    "load_registry_pack",
    "render_playbook_context",
    "resolve_scaffold_context",
    "validate_registry_pack",
]
