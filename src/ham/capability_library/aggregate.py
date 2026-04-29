"""Build aggregate views: saved library row + optional catalog detail for display."""
from __future__ import annotations

from typing import Any

from src.ham.capability_directory import get_bundle_payload, load_validated_registry
from src.ham.capability_library.schema import parse_ref
from src.ham.capability_library.store import read_capability_library
from src.ham.capability_library.validate import ref_source_kind
from src.ham.hermes_skills_catalog import get_catalog_entry_detail
from src.ham.hermes_skills_live import build_skills_installed_overlay


def _hermes_item(ref: str, catalog_id: str) -> dict[str, Any]:
    detail = get_catalog_entry_detail(catalog_id)
    if detail is None:
        return {
            "ref": ref,
            "in_catalog": False,
        }
    return {
        "ref": ref,
        "in_catalog": True,
        "hermes": {
            "catalog_id": catalog_id,
            "display_name": detail.get("display_name"),
            "summary": (detail.get("summary") or "")[:500],
            "trust_level": detail.get("trust_level"),
        },
    }


def _capdir_item(ref: str, entry_id: str) -> dict[str, Any]:
    reg = load_validated_registry()
    for c in reg.get("capabilities", []):
        if isinstance(c, dict) and c.get("id") == entry_id:
            return {
                "ref": ref,
                "in_directory": True,
                "capability_directory": {
                    "kind": "atomic_capability",
                    "id": c.get("id"),
                    "display_name": c.get("display_name"),
                    "trust_tier": c.get("trust_tier"),
                },
            }
    bwrap = get_bundle_payload(entry_id)
    if bwrap:
        b = bwrap.get("bundle") or {}
        return {
            "ref": ref,
            "in_directory": True,
            "capability_directory": {
                "kind": "bundle",
                "id": b.get("id"),
                "display_name": b.get("display_name"),
                "trust_tier": b.get("trust_tier"),
            },
        }
    for p in reg.get("profile_templates", []):
        if isinstance(p, dict) and p.get("id") == entry_id:
            return {
                "ref": ref,
                "in_directory": True,
                "capability_directory": {
                    "kind": "profile_template",
                    "id": p.get("id"),
                    "display_name": p.get("display_name"),
                    "trust_tier": p.get("trust_tier"),
                },
            }
    return {"ref": ref, "in_directory": False}


def build_aggregate(
    project_root: str,
) -> dict[str, Any]:
    from pathlib import Path

    root = Path(project_root).resolve()
    idx, rev = read_capability_library(root)
    try:
        installed = build_skills_installed_overlay()
    except Exception:  # noqa: BLE001 – aggregate stays useful without live overlay
        installed = None
    items: list[dict[str, Any]] = []
    for entry in idx.ordered_entries():
        _kind, eid = parse_ref(entry.ref)
        base: dict[str, Any] = {
            "ref": entry.ref,
            "source": ref_source_kind(entry.ref),
            "in_library": True,
            "library": {
                "notes": entry.notes,
                "user_order": entry.user_order,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            },
        }
        if _kind == "hermes":
            cat = _hermes_item(entry.ref, eid)
            base.update(cat)
            if installed and isinstance(installed, dict) and "hermes" in base:
                st = installed.get("status")
                inst = installed.get("installations") if isinstance(installed.get("installations"), list) else []
                linked = any(
                    isinstance(i, dict)
                    and i.get("catalog_id") == eid
                    and i.get("resolution") == "linked"
                    for i in inst
                )
                base["hermes"]["installed_summary"] = {"status": st, "linked": linked}
        else:
            base.update(_capdir_item(entry.ref, eid))
        items.append(base)

    return {
        "kind": "ham_capability_library_aggregate",
        "schema_version": idx.schema_version,
        "project_root": str(root),
        "revision": rev,
        "entry_count": len(items),
        "items": items,
    }


def library_payload(project_root: str) -> dict[str, Any]:
    from pathlib import Path

    root = Path(project_root).resolve()
    idx, rev = read_capability_library(root)
    return {
        "kind": "ham_capability_library",
        "schema_version": idx.schema_version,
        "project_root": str(root),
        "revision": rev,
        "entries": [e.model_dump(mode="json") for e in idx.ordered_entries()],
    }
