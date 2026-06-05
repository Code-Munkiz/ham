"""Template pack source governance — approved/blocked catalogs and manifest validation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

SourceAuditStatus = Literal["ham_authored", "verified_external", "blocked", "unknown"]
_APPROVED_SOURCES_REL = Path("sources") / "approved-sources.yaml"
_REQUIRED_SOURCE_FIELDS = (
    "source_strategy",
    "source_audit_status",
    "third_party_code_included",
    "copy_paste_safe",
    "license_notes",
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PACKS_ROOT = _REPO_ROOT / "template-packs"


class TemplatePackSourceConfigError(ValueError):
    """Invalid template pack source metadata or approved-sources catalog."""


def default_template_packs_root() -> Path:
    return _DEFAULT_PACKS_ROOT

@dataclass(frozen=True)
class ApprovedSourceEntry:
    id: str
    name: str
    purpose: str = ""
    license: str = ""
    usage: str = ""
    copy_paste_safe: bool = False


@dataclass(frozen=True)
class BlockedSourceEntry:
    id: str
    name: str
    reason: str = ""


@dataclass(frozen=True)
class ApprovedSourcesCatalog:
    version: str
    approved: tuple[ApprovedSourceEntry, ...]
    blocked: tuple[BlockedSourceEntry, ...]

    @property
    def approved_ids(self) -> frozenset[str]:
        return frozenset(entry.id.lower() for entry in self.approved)

    @property
    def blocked_matchers(self) -> tuple[tuple[str, str], ...]:
        out: list[tuple[str, str]] = []
        for entry in self.blocked:
            out.append((entry.id.lower(), entry.id))
            if entry.name.lower() != entry.id.lower():
                out.append((entry.name.lower(), entry.name))
        return tuple(out)


def default_approved_sources_path(packs_root: Path | None = None) -> Path:
    root = (packs_root or default_template_packs_root()).resolve()
    return root / _APPROVED_SOURCES_REL


@lru_cache(maxsize=1)
def load_approved_sources_catalog() -> ApprovedSourcesCatalog:
    path = default_approved_sources_path()
    if not path.is_file():
        raise TemplatePackSourceConfigError(f"Missing approved sources catalog: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TemplatePackSourceConfigError(f"{path}: top-level YAML must be a mapping")

    approved: list[ApprovedSourceEntry] = []
    for item in raw.get("approved") or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "").strip()
        if not source_id:
            raise TemplatePackSourceConfigError(f"{path}: approved entry missing id")
        approved.append(
            ApprovedSourceEntry(
                id=source_id,
                name=str(item.get("name") or source_id).strip(),
                purpose=str(item.get("purpose") or "").strip(),
                license=str(item.get("license") or "").strip(),
                usage=str(item.get("usage") or "").strip(),
                copy_paste_safe=bool(item.get("copy_paste_safe", False)),
            )
        )

    blocked: list[BlockedSourceEntry] = []
    for item in raw.get("blocked") or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "").strip()
        if not source_id:
            raise TemplatePackSourceConfigError(f"{path}: blocked entry missing id")
        blocked.append(
            BlockedSourceEntry(
                id=source_id,
                name=str(item.get("name") or source_id).strip(),
                reason=str(item.get("reason") or "").strip(),
            )
        )

    version = str(raw.get("version") or "1").strip()
    return ApprovedSourcesCatalog(version=version, approved=tuple(approved), blocked=tuple(blocked))


def _as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise TemplatePackSourceConfigError(f"pack.yaml: {field_name} must be a boolean")


def _as_str_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TemplatePackSourceConfigError(f"pack.yaml: {field_name} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TemplatePackSourceConfigError(
                f"pack.yaml: {field_name} entries must be non-empty strings"
            )
        out.append(item.strip())
    return tuple(out)


def _contains_blocked_reference(text: str, catalog: ApprovedSourcesCatalog) -> str | None:
    haystack = (text or "").lower()
    if not haystack:
        return None
    for needle, label in catalog.blocked_matchers:
        if needle in haystack:
            return label
    return None


def _scan_manifest_for_blocked_references(
    data: dict[str, Any],
    *,
    pack_id: str,
    catalog: ApprovedSourcesCatalog,
) -> None:
    fields_to_scan = (
        data.get("source_strategy"),
        data.get("license_notes"),
        data.get("name"),
    )
    for value in fields_to_scan:
        if not isinstance(value, str):
            continue
        hit = _contains_blocked_reference(value, catalog)
        if hit:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: blocked source reference {hit!r} in manifest text"
            )

    for field_name in ("source_libraries", "approved_ui_sources"):
        for entry in _as_str_list(data.get(field_name), field_name=field_name):
            hit = _contains_blocked_reference(entry, catalog)
            if hit:
                raise TemplatePackSourceConfigError(
                    f"pack.yaml [{pack_id}]: blocked source {hit!r} listed in {field_name}"
                )


def validate_pack_source_metadata(
    data: dict[str, Any],
    *,
    pack_id: str,
    catalog: ApprovedSourcesCatalog | None = None,
) -> None:
    """Validate required source governance fields and approved/blocked rules."""
    catalog = catalog or load_approved_sources_catalog()

    for field_name in _REQUIRED_SOURCE_FIELDS:
        if field_name not in data:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: missing required field {field_name!r}"
            )

    status = data.get("source_audit_status")
    if status not in ("ham_authored", "verified_external", "blocked", "unknown"):
        raise TemplatePackSourceConfigError(f"pack.yaml [{pack_id}]: invalid source_audit_status")
    if status in ("unknown", "blocked"):
        raise TemplatePackSourceConfigError(
            f"pack.yaml [{pack_id}]: source_audit_status {status!r} is not allowed for shipped packs"
        )

    third_party = _as_bool(data.get("third_party_code_included"), field_name="third_party_code_included")
    copy_paste_safe = _as_bool(data.get("copy_paste_safe"), field_name="copy_paste_safe")
    license_notes = data.get("license_notes")
    if not isinstance(license_notes, str):
        raise TemplatePackSourceConfigError(f"pack.yaml [{pack_id}]: license_notes must be a string")

    approved_ui_sources = _as_str_list(
        data.get("approved_ui_sources"), field_name="approved_ui_sources"
    )

    _scan_manifest_for_blocked_references(data, pack_id=pack_id, catalog=catalog)

    if status == "ham_authored":
        if third_party:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: ham_authored packs must set third_party_code_included: false"
            )
        if approved_ui_sources:
            for source_id in approved_ui_sources:
                if source_id.lower() not in catalog.approved_ids:
                    raise TemplatePackSourceConfigError(
                        f"pack.yaml [{pack_id}]: unknown approved_ui_sources entry {source_id!r}"
                    )
        return

    if status == "verified_external":
        if not third_party:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: verified_external packs must set third_party_code_included: true"
            )
        if not copy_paste_safe:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: verified_external packs must set copy_paste_safe: true"
            )
        if not approved_ui_sources:
            raise TemplatePackSourceConfigError(
                f"pack.yaml [{pack_id}]: verified_external packs must list approved_ui_sources"
            )
        for source_id in approved_ui_sources:
            if source_id.lower() not in catalog.approved_ids:
                raise TemplatePackSourceConfigError(
                    f"pack.yaml [{pack_id}]: unapproved external source {source_id!r}"
                )


def parse_source_metadata_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Extract source governance fields for TemplatePackManifest."""
    return {
        "source_strategy": str(data.get("source_strategy") or "").strip(),
        "source_audit_status": data.get("source_audit_status", "unknown"),
        "third_party_code_included": _as_bool(
            data.get("third_party_code_included"), field_name="third_party_code_included"
        ),
        "copy_paste_safe": _as_bool(data.get("copy_paste_safe"), field_name="copy_paste_safe"),
        "license_notes": str(data.get("license_notes") or ""),
        "approved_ui_sources": _as_str_list(
            data.get("approved_ui_sources"), field_name="approved_ui_sources"
        ),
    }


__all__ = [
    "ApprovedSourcesCatalog",
    "ApprovedSourceEntry",
    "BlockedSourceEntry",
    "SourceAuditStatus",
    "TemplatePackSourceConfigError",
    "default_approved_sources_path",
    "default_template_packs_root",
    "load_approved_sources_catalog",
    "validate_pack_source_metadata",
]
