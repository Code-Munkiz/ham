"""Frozen dataclasses for Build Kit Registry v2 (unwired pilot)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

PACK_MANIFEST_NAME = "registry-pack.yaml"
EXPECTED_SCHEMA_VERSION = "0.1"
DEFAULT_RENDER_CHAR_BUDGET = 12_000

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


def freeze_mapping(data: dict[str, Any]) -> MappingProxyType:
    return MappingProxyType(dict(data))


@dataclass(frozen=True)
class RegistryModule:
    """One loaded YAML module from a registry pack."""

    id: str
    kind: str
    path: Path
    data: MappingProxyType


@dataclass(frozen=True)
class RegistryPack:
    """Loaded registry pack manifest plus indexed modules."""

    pack_root: Path
    pack_id: str
    schema_version: str
    manifest: MappingProxyType
    modules: MappingProxyType  # id -> RegistryModule

    def module_ids(self) -> frozenset[str]:
        return frozenset(self.modules.keys())

    def get_module(self, module_id: str) -> RegistryModule:
        try:
            return self.modules[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown module id {module_id!r}") from exc

    def module_data(self, module_id: str) -> dict[str, Any]:
        return dict(self.get_module(module_id).data)


@dataclass(frozen=True)
class BuildRecipe:
    """Composed in-memory recipe for one app type."""

    pack: RegistryPack
    app_type_id: str
    stack_kit_id: str
    mechanic_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    validator_ids: tuple[str, ...]
    recovery_ids: tuple[str, ...]
    progress_label_id: str | None
    learning_hook_id: str | None

    @property
    def pack_id(self) -> str:
        return self.pack.pack_id

    @property
    def schema_version(self) -> str:
        return self.pack.schema_version
