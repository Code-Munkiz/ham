"""Load repo-local Template Pack Registry v1 manifests and starter files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.ham.template_packs.schema import (
    PACK_MANIFEST_NAME,
    TemplatePack,
    TemplatePackConfigError,
    parse_pack_manifest,
)

TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL = (
    "Template packs are not available in this runtime."
)


class TemplatePackRegistryEmptyError(RuntimeError):
    """Raised when ``template-packs/`` is missing or has no manifests in the image."""

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PACKS_ROOT = _REPO_ROOT / "template-packs"


def default_template_packs_root() -> Path:
    return _DEFAULT_PACKS_ROOT


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TemplatePackConfigError(f"{path}: top-level YAML must be a mapping")
    return data


def _collect_pack_files(files_dir: Path) -> dict[str, str]:
    if not files_dir.is_dir():
        raise TemplatePackConfigError(f"Missing files directory: {files_dir}")
    out: dict[str, str] = {}
    for file_path in sorted(files_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(files_dir).as_posix()
        if not rel or ".." in rel.split("/"):
            continue
        out[rel] = file_path.read_text(encoding="utf-8")
    if not out:
        raise TemplatePackConfigError(f"No starter files under {files_dir}")
    return out


def load_template_pack(pack_root: Path) -> TemplatePack:
    pack_root = pack_root.resolve()
    manifest_path = pack_root / PACK_MANIFEST_NAME
    if not manifest_path.is_file():
        raise TemplatePackConfigError(f"Missing manifest: {manifest_path}")
    manifest = parse_pack_manifest(_load_yaml(manifest_path), pack_root=pack_root)
    files_dir = pack_root / "files"
    files = _collect_pack_files(files_dir)
    for required in manifest.required_files:
        if required not in files:
            raise TemplatePackConfigError(
                f"Pack {manifest.id!r} missing required file {required!r}"
            )
    return TemplatePack(manifest=manifest, files=files)


def discover_pack_roots(packs_root: Path | None = None) -> list[Path]:
    root = (packs_root or default_template_packs_root()).resolve()
    if not root.is_dir():
        return []
    roots: list[Path] = []
    for manifest in sorted(root.rglob(PACK_MANIFEST_NAME)):
        roots.append(manifest.parent)
    return roots


def load_template_pack_registry(packs_root: Path | None = None) -> dict[str, TemplatePack]:
    """Load every pack under ``template-packs/**/pack.yaml`` keyed by manifest id."""
    packs: dict[str, TemplatePack] = {}
    for pack_root in discover_pack_roots(packs_root):
        pack = load_template_pack(pack_root)
        if pack.id in packs:
            raise TemplatePackConfigError(f"Duplicate template pack id: {pack.id!r}")
        packs[pack.id] = pack
    return packs


def require_non_empty_template_pack_registry(
    packs: dict[str, TemplatePack] | None = None,
) -> dict[str, TemplatePack]:
    """Return *packs* when non-empty; otherwise raise :class:`TemplatePackRegistryEmptyError`."""
    loaded = packs if packs is not None else load_template_pack_registry()
    if not loaded:
        raise TemplatePackRegistryEmptyError(TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL)
    return loaded


__all__ = [
    "TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL",
    "TemplatePackRegistryEmptyError",
    "default_template_packs_root",
    "discover_pack_roots",
    "load_template_pack",
    "load_template_pack_registry",
    "require_non_empty_template_pack_registry",
]
