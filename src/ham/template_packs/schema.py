"""Template Pack Registry v1 — manifest schema (backstage design starters)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.ham.template_packs.sources import (
    SourceAuditStatus,
    TemplatePackSourceConfigError,
    parse_source_metadata_fields,
    validate_pack_source_metadata,
)

AiDirective = Literal["preserve_structure", "remix_moderately", "remix_heavily"]
PACK_MANIFEST_NAME = "pack.yaml"


@dataclass(frozen=True)
class TemplatePackLicense:
    id: str
    name: str
    license_url: str | None = None
    commercial_use_allowed: bool = True
    redistribution_allowed: bool = True
    attribution_required: bool = False


@dataclass(frozen=True)
class TemplatePackQualityGate:
    required_sections: tuple[str, ...] = ()
    min_tailwind_class_tokens: int = 8
    require_responsive_classes: bool = True
    require_explicit_background: bool = True


@dataclass(frozen=True)
class TemplatePackManifest:
    id: str
    name: str
    app_types: tuple[str, ...]
    prompt_signals: tuple[str, ...]
    source_libraries: tuple[str, ...] = ()
    license: TemplatePackLicense | None = None
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)
    required_files: tuple[str, ...] = ()
    design_tokens: dict[str, str] = field(default_factory=dict)
    quality_gates: TemplatePackQualityGate | None = None
    ai_directive: AiDirective = "remix_moderately"
    source_strategy: str = ""
    source_audit_status: SourceAuditStatus = "unknown"
    third_party_code_included: bool = False
    copy_paste_safe: bool = False
    license_notes: str = ""
    approved_ui_sources: tuple[str, ...] = ()
    pack_root: Path | None = None
    files_dir: Path | None = None


@dataclass(frozen=True)
class TemplatePack:
    """Loaded template pack: manifest + repo-local starter files."""

    manifest: TemplatePackManifest
    files: dict[str, str]

    @property
    def id(self) -> str:
        return self.manifest.id


class TemplatePackConfigError(ValueError):
    """Invalid template pack manifest or on-disk layout."""


def _as_str_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TemplatePackConfigError(f"{field_name} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TemplatePackConfigError(f"{field_name} entries must be non-empty strings")
        out.append(item.strip())
    return tuple(out)


def _as_str_dict(value: Any, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TemplatePackConfigError(f"{field_name} must be a mapping")
    out: dict[str, str] = {}
    for key, val in value.items():
        if not isinstance(key, str) or not key.strip():
            raise TemplatePackConfigError(f"{field_name} keys must be non-empty strings")
        if not isinstance(val, str) or not val.strip():
            raise TemplatePackConfigError(f"{field_name} values must be non-empty strings")
        out[key.strip()] = val.strip()
    return out


def parse_pack_manifest(data: dict[str, Any], *, pack_root: Path) -> TemplatePackManifest:
    pack_id = data.get("id")
    if not isinstance(pack_id, str) or not pack_id.strip():
        raise TemplatePackConfigError("pack.yaml: missing or empty id")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise TemplatePackConfigError("pack.yaml: missing or empty name")

    license_block = data.get("license")
    license_obj: TemplatePackLicense | None = None
    if isinstance(license_block, dict):
        lic_id = license_block.get("id")
        lic_name = license_block.get("name")
        if not isinstance(lic_id, str) or not lic_id.strip():
            raise TemplatePackConfigError("pack.yaml: license.id required")
        if not isinstance(lic_name, str) or not lic_name.strip():
            raise TemplatePackConfigError("pack.yaml: license.name required")
        license_obj = TemplatePackLicense(
            id=lic_id.strip(),
            name=lic_name.strip(),
            license_url=(
                str(license_block["license_url"]).strip()
                if isinstance(license_block.get("license_url"), str)
                else None
            ),
            commercial_use_allowed=bool(license_block.get("commercial_use_allowed", True)),
            redistribution_allowed=bool(license_block.get("redistribution_allowed", True)),
            attribution_required=bool(license_block.get("attribution_required", False)),
        )

    qg_raw = data.get("quality_gates")
    quality_gates: TemplatePackQualityGate | None = None
    if isinstance(qg_raw, dict):
        min_tw = qg_raw.get("min_tailwind_class_tokens", 8)
        try:
            min_tw_int = int(min_tw)
        except (TypeError, ValueError) as exc:
            raise TemplatePackConfigError(
                "pack.yaml: quality_gates.min_tailwind_class_tokens must be int"
            ) from exc
        quality_gates = TemplatePackQualityGate(
            required_sections=_as_str_tuple(
                qg_raw.get("required_sections"), field_name="quality_gates.required_sections"
            ),
            min_tailwind_class_tokens=max(1, min_tw_int),
            require_responsive_classes=bool(qg_raw.get("require_responsive_classes", True)),
            require_explicit_background=bool(qg_raw.get("require_explicit_background", True)),
        )

    directive = data.get("ai_directive", "remix_moderately")
    if directive not in ("preserve_structure", "remix_moderately", "remix_heavily"):
        raise TemplatePackConfigError("pack.yaml: invalid ai_directive")

    try:
        validate_pack_source_metadata(data, pack_id=pack_id.strip())
    except TemplatePackSourceConfigError as exc:
        raise TemplatePackConfigError(str(exc)) from exc
    try:
        source_meta = parse_source_metadata_fields(data)
    except TemplatePackSourceConfigError as exc:
        raise TemplatePackConfigError(str(exc)) from exc

    files_dir = pack_root / "files"
    return TemplatePackManifest(
        id=pack_id.strip(),
        name=name.strip(),
        app_types=_as_str_tuple(data.get("app_types"), field_name="app_types"),
        prompt_signals=_as_str_tuple(data.get("prompt_signals"), field_name="prompt_signals"),
        source_libraries=_as_str_tuple(
            data.get("source_libraries"), field_name="source_libraries"
        ),
        license=license_obj,
        dependencies=_as_str_dict(data.get("dependencies"), field_name="dependencies"),
        dev_dependencies=_as_str_dict(data.get("dev_dependencies"), field_name="dev_dependencies"),
        required_files=_as_str_tuple(data.get("required_files"), field_name="required_files"),
        design_tokens=_as_str_dict(data.get("design_tokens"), field_name="design_tokens"),
        quality_gates=quality_gates,
        ai_directive=directive,
        source_strategy=source_meta["source_strategy"],
        source_audit_status=source_meta["source_audit_status"],
        third_party_code_included=source_meta["third_party_code_included"],
        copy_paste_safe=source_meta["copy_paste_safe"],
        license_notes=source_meta["license_notes"],
        approved_ui_sources=source_meta["approved_ui_sources"],
        pack_root=pack_root,
        files_dir=files_dir,
    )


__all__ = [
    "AiDirective",
    "PACK_MANIFEST_NAME",
    "TemplatePack",
    "TemplatePackConfigError",
    "TemplatePackLicense",
    "TemplatePackManifest",
    "TemplatePackQualityGate",
    "parse_pack_manifest",
]
