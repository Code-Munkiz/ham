"""Vendored Hermes-runtime skills catalog (read-only Phase 1)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "hermes_skills_catalog.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    path = _catalog_path()
    if not path.is_file():
        return {"schema_version": 1, "entries": []}
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _normalize_list_item(item: dict[str, Any]) -> dict[str, Any] | None:
    cid = item.get("catalog_id")
    if not cid:
        return None
    return {
        "catalog_id": cid,
        "display_name": item.get("display_name") or cid,
        "summary": item.get("summary") or "",
        "trust_level": item.get("trust_level") or "community",
        "source_kind": item.get("source_kind") or "unknown",
        "source_ref": item.get("source_ref") or "",
        "version_pin": item.get("version_pin") or "",
        "content_hash_sha256": item.get("content_hash_sha256") or "",
        "platforms": list(item.get("platforms") or []),
        "required_environment_variables": list(item.get("required_environment_variables") or []),
        "config_keys": list(item.get("config_keys") or []),
        "has_scripts": bool(item.get("has_scripts")),
        "installable_by_default": bool(item.get("installable_by_default", False)),
    }


def list_catalog_entries() -> list[dict[str, Any]]:
    """List entries for grid view (no heavy detail fields)."""
    raw = _load_raw()
    entries = raw.get("entries") if isinstance(raw.get("entries"), list) else []
    out: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        norm = _normalize_list_item(item)
        if norm is not None:
            out.append(norm)
    out.sort(key=lambda x: str(x["catalog_id"]))
    return out


def get_catalog_entry_detail(catalog_id: str) -> dict[str, Any] | None:
    """Full detail for one catalog id, including nested detail block."""
    cid = catalog_id.strip()
    raw_entries = _load_raw().get("entries") or []
    for raw in raw_entries:
        if not isinstance(raw, dict) or raw.get("catalog_id") != cid:
            continue
        item = _normalize_list_item(raw)
        if item is None:
            return None
        d = raw.get("detail") if isinstance(raw.get("detail"), dict) else {}
        merged = {**item}
        merged["detail"] = {
            "provenance_note": str(d.get("provenance_note") or ""),
            "warnings": list(d.get("warnings") or []),
            "manifest_files": list(d.get("manifest_files") or []),
        }
        return merged
    return None


def catalog_schema_version() -> int:
    raw = _load_raw()
    v = raw.get("schema_version")
    return int(v) if isinstance(v, int) else 1


def catalog_upstream_meta() -> dict[str, Any] | None:
    """Pinned upstream repo metadata from manifest (if present)."""
    raw = _load_raw()
    u = raw.get("upstream")
    return dict(u) if isinstance(u, dict) else None


def catalog_note() -> str | None:
    raw = _load_raw()
    n = raw.get("catalog_note")
    return str(n) if isinstance(n, str) else None
