"""Unwired scaffold context resolver (ADR-0017 Phase 2B).

Resolves v2 playbook context vs v1 Builder Kit fallback. Not called by
chat, scaffold, or API paths until Phase 2C.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.ham.build_registry.compose import compose_build_recipe
from src.ham.build_registry.errors import BuildRegistryConfigError
from src.ham.build_registry.loader import load_registry_pack
from src.ham.build_registry.models import DEFAULT_RENDER_CHAR_BUDGET, RegistryPack
from src.ham.build_registry.render import render_playbook_context
from src.ham.build_registry.validate import validate_registry_pack

V2_HEADER = "Build Registry v2 playbook context:"
V1_HEADER = "Builder Kit context:"
DEFAULT_GAME_PACK_REL = Path("docs/build-kit-registry-v2/game-pack")

_TRUTHY_ENV = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class ScaffoldContextResult:
    source: Literal["v1", "v2", "none"]
    header: str
    context: str
    registry_v2_app_type: str | None = None
    registry_v2_pack_id: str | None = None
    fallback_template_kind: str | None = None
    fallback_reason: str | None = None


def build_registry_v2_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when ``HAM_BUILD_REGISTRY_V2_ENABLED`` is a truthy string."""
    source = env if env is not None else __import__("os").environ
    raw = source.get("HAM_BUILD_REGISTRY_V2_ENABLED", "")
    return raw.strip().lower() in _TRUTHY_ENV


def default_repo_root() -> Path:
    """Repository root inferred from this module location."""
    return Path(__file__).resolve().parents[3]


def resolve_pack_root(
    metadata: Mapping[str, Any] | None,
    *,
    repo_root: Path,
) -> Path:
    """Resolve registry pack directory from metadata override or default."""
    if metadata:
        override = metadata.get("registry_v2_pack_root")
        if isinstance(override, str) and override.strip():
            path = Path(override.strip())
            if not path.is_absolute():
                path = (repo_root / path).resolve()
            return path.resolve()
    return (repo_root / DEFAULT_GAME_PACK_REL).resolve()


def _metadata_app_type_id(metadata: Mapping[str, Any] | None) -> str | None:
    if not metadata:
        return None
    raw = metadata.get("registry_v2_app_type")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _resolve_fallback_template_kind(
    *,
    pack: RegistryPack | None,
    app_type_id: str | None,
    template_kind: str | None,
) -> str:
    if pack is not None and app_type_id and app_type_id in pack.modules:
        app = pack.module_data(app_type_id)
        legacy = app.get("legacy_v1_fallback")
        if isinstance(legacy, str) and legacy.strip():
            return legacy.strip()
    if template_kind and str(template_kind).strip():
        return str(template_kind).strip()
    return "generic"


def _render_v1_context_for_template_kind(template_kind: str | None) -> tuple[str, str] | None:
    """Return (kit_id, rendered context) or None when no kit resolves."""
    from src.ham.builder_kits import (  # noqa: PLC0415 — lazy v1 coupling
        get_kit,
        get_kit_for_template_kind,
        render_kit_context,
    )

    kind = (template_kind or "").strip() or "generic"
    kit = get_kit(kind) or get_kit_for_template_kind(kind)
    if kit is None:
        return None
    return kit.kit_id, render_kit_context(kit)


def _v1_result(
    template_kind: str | None,
    *,
    fallback_reason: str,
    pack: RegistryPack | None = None,
    app_type_id: str | None = None,
) -> ScaffoldContextResult:
    resolved_kind = _resolve_fallback_template_kind(
        pack=pack,
        app_type_id=app_type_id,
        template_kind=template_kind,
    )
    rendered = _render_v1_context_for_template_kind(resolved_kind)
    if rendered is None:
        return ScaffoldContextResult(
            source="none",
            header="",
            context="",
            registry_v2_app_type=app_type_id,
            fallback_template_kind=resolved_kind,
            fallback_reason="no_fallback_kit_resolved",
        )
    kit_id, context = rendered
    return ScaffoldContextResult(
        source="v1",
        header=V1_HEADER,
        context=context,
        registry_v2_app_type=app_type_id,
        fallback_template_kind=kit_id,
        fallback_reason=fallback_reason,
    )


def _try_v2_context(
    *,
    metadata: Mapping[str, Any],
    app_type_id: str,
    repo_root: Path,
    max_chars: int,
) -> ScaffoldContextResult:
    pack_root = resolve_pack_root(metadata, repo_root=repo_root)
    pack = load_registry_pack(pack_root)
    validate_registry_pack(pack)
    recipe = compose_build_recipe(pack, app_type_id)
    context = render_playbook_context(recipe, max_chars=max_chars)
    if not context.strip():
        raise BuildRegistryConfigError("render_playbook_context returned empty output")
    return ScaffoldContextResult(
        source="v2",
        header=V2_HEADER,
        context=context,
        registry_v2_app_type=app_type_id,
        registry_v2_pack_id=pack.pack_id,
    )


def resolve_scaffold_context(
    *,
    metadata: Mapping[str, Any] | None,
    template_kind: str | None,
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
    max_chars: int = DEFAULT_RENDER_CHAR_BUDGET,
) -> ScaffoldContextResult:
    """Resolve scaffold prompt context: v2 playbook (opt-in) or v1 kit fallback."""
    root = repo_root.resolve() if repo_root is not None else default_repo_root()

    if not build_registry_v2_enabled(env):
        return _v1_result(
            template_kind,
            fallback_reason="registry_v2_disabled",
        )

    app_type_id = _metadata_app_type_id(metadata)
    if not app_type_id:
        return _v1_result(
            template_kind,
            fallback_reason="registry_v2_metadata_missing",
        )

    pack: RegistryPack | None = None
    try:
        return _try_v2_context(
            metadata=metadata or {},
            app_type_id=app_type_id,
            repo_root=root,
            max_chars=max_chars,
        )
    except BuildRegistryConfigError as exc:
        pack_root = resolve_pack_root(metadata, repo_root=root)
        try:
            pack = load_registry_pack(pack_root)
        except BuildRegistryConfigError:
            pack = None
        return _v1_result(
            template_kind,
            fallback_reason=f"registry_v2_error:{exc}",
            pack=pack,
            app_type_id=app_type_id,
        )
