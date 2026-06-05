"""Template pack source governance validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ham.template_packs.registry import (
    default_template_packs_root,
    load_template_pack,
    load_template_pack_registry,
)
from src.ham.template_packs.schema import TemplatePackConfigError, parse_pack_manifest
from src.ham.template_packs.sources import (
    TemplatePackSourceConfigError,
    load_approved_sources_catalog,
    validate_pack_source_metadata,
)


def _minimal_ham_authored_manifest(*, pack_id: str = "landing/test") -> dict:
    return {
        "id": pack_id,
        "name": "Test Pack",
        "app_types": ["landing"],
        "prompt_signals": ["test"],
        "source_libraries": ["react", "tailwindcss"],
        "source_strategy": "HAM-authored starter inspired by approved copy-paste UI patterns",
        "source_audit_status": "ham_authored",
        "third_party_code_included": False,
        "copy_paste_safe": True,
        "license_notes": "HAM-authored test fixture.",
        "license": {
            "id": "ham-authored-internal",
            "name": "HAM Authored Internal Starter",
        },
        "required_files": ["src/App.tsx"],
    }


def test_approved_sources_catalog_loads() -> None:
    catalog = load_approved_sources_catalog()
    assert catalog.version == "1"
    assert "shadcn/ui" in catalog.approved_ids
    assert "tailwind-ui" in {entry.id for entry in catalog.blocked}


def test_shipped_ham_authored_packs_pass_source_validation() -> None:
    registry = load_template_pack_registry()
    assert len(registry) == 4
    for pack in registry.values():
        assert pack.manifest.source_audit_status == "ham_authored"
        assert pack.manifest.third_party_code_included is False
        assert pack.manifest.source_strategy
        assert isinstance(pack.manifest.license_notes, str)
        assert "tailwind ui" not in pack.manifest.license_notes.lower()


def test_agency_modern_manifest_has_no_blocked_sources() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    combined = " ".join(
        [
            pack.manifest.license_notes,
            pack.manifest.source_strategy,
            " ".join(pack.manifest.source_libraries),
        ]
    ).lower()
    assert "tailwind ui" not in combined
    assert "untitled ui" not in combined
    assert "cruip" not in combined


def test_missing_source_metadata_fails_validation() -> None:
    data = _minimal_ham_authored_manifest()
    data.pop("source_audit_status")
    with pytest.raises(TemplatePackSourceConfigError, match="missing required field"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_unknown_source_audit_status_fails_validation() -> None:
    data = _minimal_ham_authored_manifest()
    data["source_audit_status"] = "unknown"
    with pytest.raises(TemplatePackSourceConfigError, match="not allowed"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_blocked_source_in_license_notes_fails() -> None:
    data = _minimal_ham_authored_manifest()
    data["license_notes"] = "Inspired by Tailwind UI marketing blocks."
    with pytest.raises(TemplatePackSourceConfigError, match="blocked source"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_blocked_source_in_approved_ui_sources_fails() -> None:
    data = _minimal_ham_authored_manifest()
    data["approved_ui_sources"] = ["tailwind-plus"]
    with pytest.raises(TemplatePackSourceConfigError, match="blocked source"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_verified_external_requires_approved_ui_sources() -> None:
    data = _minimal_ham_authored_manifest()
    data["source_audit_status"] = "verified_external"
    data["third_party_code_included"] = True
    data["copy_paste_safe"] = True
    with pytest.raises(TemplatePackSourceConfigError, match="approved_ui_sources"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_verified_external_rejects_unapproved_source() -> None:
    data = _minimal_ham_authored_manifest()
    data["source_audit_status"] = "verified_external"
    data["third_party_code_included"] = True
    data["copy_paste_safe"] = True
    data["approved_ui_sources"] = ["not-a-real-ui-kit"]
    with pytest.raises(TemplatePackSourceConfigError, match="unapproved external source"):
        validate_pack_source_metadata(data, pack_id=data["id"])


def test_verified_external_accepts_catalog_source() -> None:
    data = _minimal_ham_authored_manifest()
    data["source_audit_status"] = "verified_external"
    data["third_party_code_included"] = True
    data["copy_paste_safe"] = True
    data["approved_ui_sources"] = ["hyperui"]
    validate_pack_source_metadata(data, pack_id=data["id"])


def test_parse_pack_manifest_requires_source_metadata(tmp_path: Path) -> None:
    pack_root = tmp_path / "landing" / "test"
    (pack_root / "files" / "src").mkdir(parents=True)
    (pack_root / "files" / "src" / "App.tsx").write_text("export default function App(){return null}\n")
    manifest = _minimal_ham_authored_manifest()
    manifest.pop("source_strategy")
    (pack_root / "pack.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(TemplatePackConfigError, match="source_strategy"):
        parse_pack_manifest(yaml.safe_load((pack_root / "pack.yaml").read_text()), pack_root=pack_root)


def test_ham_authored_pack_with_third_party_flag_fails(tmp_path: Path) -> None:
    pack_root = tmp_path / "landing" / "bad"
    (pack_root / "files" / "src").mkdir(parents=True)
    (pack_root / "files" / "src" / "App.tsx").write_text("export default function App(){return null}\n")
    manifest = _minimal_ham_authored_manifest(pack_id="landing/bad")
    manifest["third_party_code_included"] = True
    (pack_root / "pack.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(TemplatePackConfigError, match="third_party_code_included"):
        load_template_pack(pack_root)
