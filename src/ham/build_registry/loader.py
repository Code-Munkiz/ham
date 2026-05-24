"""Lazy loader for Build Kit Registry v2 YAML packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.ham.build_registry.errors import BuildRegistryConfigError
from src.ham.build_registry.models import (
    MODULE_INDEX_KEYS,
    PACK_MANIFEST_NAME,
    RegistryModule,
    RegistryPack,
    freeze_mapping,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise BuildRegistryConfigError(f"{path}: top-level YAML must be a mapping")
    return data


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


def _collect_yaml_module_files(pack_root: Path) -> list[Path]:
    return sorted(
        path
        for path in pack_root.rglob("*.yaml")
        if path.name != PACK_MANIFEST_NAME
    )


def load_registry_pack(pack_root: Path) -> RegistryPack:
    """Load manifest and every indexed module from ``pack_root``.

    Requires an explicit ``pack_root`` — no module-level registry cache.
    """
    pack_root = pack_root.resolve()
    manifest_path = pack_root / PACK_MANIFEST_NAME
    if not manifest_path.is_file():
        raise BuildRegistryConfigError(f"Missing manifest: {manifest_path}")

    manifest = _load_yaml(manifest_path)
    if "module_index" not in manifest:
        raise BuildRegistryConfigError("registry-pack.yaml: missing field 'module_index'")

    indexed_ids = _flatten_module_index(manifest["module_index"])
    indexed_set = set(indexed_ids)
    if len(indexed_ids) != len(indexed_set):
        raise BuildRegistryConfigError(
            "registry-pack.yaml: duplicate ids in module_index"
        )

    modules_by_id: dict[str, RegistryModule] = {}
    paths_by_id: dict[str, Path] = {}

    for path in _collect_yaml_module_files(pack_root):
        payload = _load_yaml(path)
        module_id = payload.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise BuildRegistryConfigError(f"{path}: missing or empty id")
        module_id = module_id.strip()
        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise BuildRegistryConfigError(f"{path}: missing or empty kind")
        if module_id in modules_by_id:
            raise BuildRegistryConfigError(
                f"Duplicate module id {module_id!r} "
                f"({paths_by_id[module_id]} and {path})"
            )
        modules_by_id[module_id] = RegistryModule(
            id=module_id,
            kind=kind.strip(),
            path=path,
            data=freeze_mapping(payload),
        )
        paths_by_id[module_id] = path

    missing = sorted(indexed_set - set(modules_by_id))
    if missing:
        raise BuildRegistryConfigError(
            "Indexed module ids missing YAML files: " + ", ".join(missing)
        )

    orphans = sorted(set(modules_by_id) - indexed_set)
    if orphans:
        details = ", ".join(f"{oid} ({paths_by_id[oid]})" for oid in orphans)
        raise BuildRegistryConfigError(
            f"Orphan YAML modules not in module_index: {details}"
        )

    pack_id = manifest.get("id")
    schema_version = manifest.get("schema_version")
    if not isinstance(pack_id, str) or not pack_id.strip():
        raise BuildRegistryConfigError("registry-pack.yaml: missing or empty id")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise BuildRegistryConfigError(
            "registry-pack.yaml: missing or empty schema_version"
        )

    return RegistryPack(
        pack_root=pack_root,
        pack_id=pack_id.strip(),
        schema_version=schema_version.strip(),
        manifest=freeze_mapping(manifest),
        modules=freeze_mapping(modules_by_id),
    )
