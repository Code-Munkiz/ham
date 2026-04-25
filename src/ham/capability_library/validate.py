"""Validate library refs against Hermes skills catalog and capability directory."""
from __future__ import annotations

from typing import Any, Literal

from src.ham.capability_directory import load_validated_registry
from src.ham.hermes_skills_catalog import get_catalog_entry_detail
from src.ham.capability_library.schema import parse_ref


def hermes_catalog_exists(catalog_id: str) -> bool:
    return get_catalog_entry_detail(catalog_id) is not None


def _find_capdir_record(entry_id: str) -> dict[str, Any] | None:
    rid = entry_id.strip()
    reg = load_validated_registry()
    for c in reg.get("capabilities", []):
        if isinstance(c, dict) and c.get("id") == rid:
            return c
    for b in reg.get("bundles", []):
        if isinstance(b, dict) and b.get("id") == rid:
            return b
    for p in reg.get("profile_templates", []):
        if isinstance(p, dict) and p.get("id") == rid:
            return p
    return None


def capdir_entry_exists(entry_id: str) -> bool:
    return _find_capdir_record(entry_id) is not None


def validate_ref_in_catalogs(ref: str) -> None:
    """Raise ValueError if the ref does not point to a known catalog entry."""
    kind, sid = parse_ref(ref)
    if kind == "hermes":
        if not hermes_catalog_exists(sid):
            raise ValueError(f"unknown Hermes catalog_id {sid!r}")
    else:
        if not capdir_entry_exists(sid):
            raise ValueError(f"unknown capability directory id {sid!r}")


def ref_source_kind(ref: str) -> Literal["hermes_catalog", "capability_directory"]:
    k, _ = parse_ref(ref)
    return "hermes_catalog" if k == "hermes" else "capability_directory"
