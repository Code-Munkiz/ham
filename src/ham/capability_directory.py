"""Static first-party HAM Capability Directory (Phase 1) — load and validate registry JSON.

Registry rows are data only: no execution, no remote/community registries in v1.
See docs/capabilities/capability_bundle_directory_v1.md.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_KINDS = frozenset({"atomic_capability", "bundle", "profile_template"})
_TRUST = frozenset({"first_party", "verified_org", "community", "local_only", "unsigned"})
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def _data_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "capability_directory_v1.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    path = _data_path()
    if not path.is_file():
        return {
            "schema_version": "capability.directory.v1",
            "registry_id": "ham.first_party.v1",
            "capabilities": [],
            "bundles": [],
            "profile_templates": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _reject_path_leaks(obj: Any, *, path: str = "") -> None:
    """Ensure serialized public payloads do not include absolute filesystem paths."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_path_leaks(v, path=f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_path_leaks(v, path=f"{path}[{i}]")
    elif isinstance(obj, str):
        s = obj.strip()
        if len(s) > 2 and s.startswith("/") and not s.startswith("//"):
            if re.match(r"^/(usr|home|opt|var|tmp|etc|Users)/", s, re.I):
                raise ValueError(f"capability_directory: forbidden local path in payload at {path or 'root'}")


def _validate_policy_obj(val: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(val, dict):
        raise ValueError(f"{name} must be an object")
    return val


def _validate_record(rec: Any, *, section: str) -> dict[str, Any]:
    if not isinstance(rec, dict):
        raise ValueError(f"{section} entry must be an object")
    req = [
        "id",
        "schema_version",
        "kind",
        "display_name",
        "summary",
        "description",
        "trust_tier",
        "provenance",
        "version",
        "required_backends",
        "capabilities",
        "skills",
        "tools_policy",
        "mcp_policy",
        "model_policy",
        "memory_policy",
        "surfaces",
        "mutability",
        "preview_available",
        "apply_available",
        "risks",
        "evidence_expectations",
        "tags",
    ]
    for k in req:
        if k not in rec:
            raise ValueError(f"{section} record missing required field {k!r}: {rec.get('id')!r}")

    rid = str(rec["id"]).strip()
    if not _ID_RE.match(rid):
        raise ValueError(f"invalid id: {rid!r}")

    kind = str(rec["kind"]).strip()
    if kind not in _KINDS:
        raise ValueError(f"invalid kind {kind!r} for {rid}")

    trust = str(rec["trust_tier"]).strip()
    if trust not in _TRUST:
        raise ValueError(f"invalid trust_tier {trust!r} for {rid}")

    prov = rec["provenance"]
    if not isinstance(prov, dict) or not str(prov.get("source_kind") or "").strip():
        raise ValueError(f"provenance.source_kind required for {rid}")

    if rec["apply_available"] is not False:
        raise ValueError(f"apply_available must be false in Phase 1 for {rid}")

    for key in (
        "required_backends",
        "capabilities",
        "skills",
        "risks",
        "evidence_expectations",
        "tags",
    ):
        if not isinstance(rec[key], list):
            raise ValueError(f"{key} must be a list for {rid}")
        for item in rec[key]:
            if not isinstance(item, str):
                raise ValueError(f"{key} items must be strings for {rid}")

    if not isinstance(rec["surfaces"], list):
        raise ValueError(f"surfaces must be a list for {rid}")
    for surf in rec["surfaces"]:
        if not isinstance(surf, dict):
            raise ValueError(f"surfaces entries must be objects for {rid}")
        if not str(surf.get("route") or "").strip():
            raise ValueError(f"surfaces.route required for {rid}")
        if not str(surf.get("label") or "").strip():
            raise ValueError(f"surfaces.label required for {rid}")

    _validate_policy_obj(rec["tools_policy"], name=f"tools_policy[{rid}]")
    _validate_policy_obj(rec["mcp_policy"], name=f"mcp_policy[{rid}]")
    _validate_policy_obj(rec["model_policy"], name=f"model_policy[{rid}]")
    _validate_policy_obj(rec["memory_policy"], name=f"memory_policy[{rid}]")

    if not isinstance(rec["preview_available"], bool):
        raise ValueError(f"preview_available must be bool for {rid}")

    return dict(rec)


def _validate_registry(raw: dict[str, Any]) -> dict[str, Any]:
    sv = str(raw.get("schema_version") or "").strip()
    if sv != "capability.directory.v1":
        raise ValueError(f"unsupported schema_version: {sv!r}")

    reg_id = str(raw.get("registry_id") or "").strip()
    if not reg_id:
        raise ValueError("registry_id required")

    caps = raw.get("capabilities")
    bundles = raw.get("bundles")
    pts = raw.get("profile_templates")
    if not isinstance(caps, list):
        raise ValueError("capabilities must be a list")
    if not isinstance(bundles, list):
        raise ValueError("bundles must be a list")
    if not isinstance(pts, list):
        raise ValueError("profile_templates must be a list")

    seen: set[str] = set()
    out_caps: list[dict[str, Any]] = []
    for i, c in enumerate(caps):
        v = _validate_record(c, section="capabilities")
        if v["kind"] != "atomic_capability":
            raise ValueError(f"capabilities[{i}] must be atomic_capability")
        if v["id"] in seen:
            raise ValueError(f"duplicate id {v['id']}")
        seen.add(v["id"])
        out_caps.append(v)

    out_bundles: list[dict[str, Any]] = []
    for i, b in enumerate(bundles):
        v = _validate_record(b, section="bundles")
        if v["kind"] != "bundle":
            raise ValueError(f"bundles[{i}] must be bundle")
        if v["id"] in seen:
            raise ValueError(f"duplicate id {v['id']}")
        seen.add(v["id"])
        out_bundles.append(v)

    out_pt: list[dict[str, Any]] = []
    for i, p in enumerate(pts):
        v = _validate_record(p, section="profile_templates")
        if v["kind"] != "profile_template":
            raise ValueError(f"profile_templates[{i}] must be profile_template")
        if v["id"] in seen:
            raise ValueError(f"duplicate id {v['id']}")
        seen.add(v["id"])
        out_pt.append(v)

    return {
        "schema_version": sv,
        "registry_id": reg_id,
        "registry_note": str(raw.get("registry_note") or "").strip() or None,
        "capabilities": out_caps,
        "bundles": out_bundles,
        "profile_templates": out_pt,
    }


@lru_cache(maxsize=1)
def load_validated_registry() -> dict[str, Any]:
    """Parse, validate, and return the in-memory registry (immutable cache)."""
    raw = _load_raw()
    validated = _validate_registry(raw)
    # Defense in depth: ensure we never accidentally leak absolute paths.
    _reject_path_leaks(validated)
    return validated


def directory_index_payload() -> dict[str, Any]:
    """GET /api/capability-directory"""
    reg = load_validated_registry()
    trust_counts: dict[str, int] = {}
    for section in ("capabilities", "bundles", "profile_templates"):
        for rec in reg[section]:
            t = str(rec["trust_tier"])
            trust_counts[t] = trust_counts.get(t, 0) + 1
    note = reg.get("registry_note")
    payload: dict[str, Any] = {
        "kind": "capability_directory_index",
        "schema_version": reg["schema_version"],
        "registry_id": reg["registry_id"],
        "mutation_policy": "read_only",
        "apply_available_globally": False,
        "no_execution_notice": (
            "Directory records are metadata only. Phase 1 does not install skills, "
            "mutate settings, or invoke tools."
        ),
        "counts": {
            "capabilities": len(reg["capabilities"]),
            "bundles": len(reg["bundles"]),
            "profile_templates": len(reg["profile_templates"]),
        },
        "trust_tier_counts": trust_counts,
        "endpoints": {
            "capabilities": "/api/capability-directory/capabilities",
            "bundles": "/api/capability-directory/bundles",
            "bundle_by_id": "/api/capability-directory/bundles/{bundle_id}",
        },
    }
    if note:
        payload["registry_note"] = note
    return payload


def list_capabilities_payload() -> dict[str, Any]:
    reg = load_validated_registry()
    return {
        "kind": "capability_directory_capabilities",
        "schema_version": reg["schema_version"],
        "registry_id": reg["registry_id"],
        "mutation_policy": "read_only",
        "apply_available_globally": False,
        "count": len(reg["capabilities"]),
        "capabilities": reg["capabilities"],
    }


def list_bundles_payload() -> dict[str, Any]:
    reg = load_validated_registry()
    return {
        "kind": "capability_directory_bundles",
        "schema_version": reg["schema_version"],
        "registry_id": reg["registry_id"],
        "mutation_policy": "read_only",
        "apply_available_globally": False,
        "count": len(reg["bundles"]),
        "bundles": reg["bundles"],
    }


def get_bundle_payload(bundle_id: str) -> dict[str, Any] | None:
    bid = bundle_id.strip()
    reg = load_validated_registry()
    for b in reg["bundles"]:
        if b["id"] == bid:
            return {
                "kind": "capability_directory_bundle",
                "schema_version": reg["schema_version"],
                "registry_id": reg["registry_id"],
                "mutation_policy": "read_only",
                "apply_available_globally": False,
                "no_execution_notice": (
                    "This record does not trigger installs, settings writes, or tool execution."
                ),
                "bundle": b,
            }
    return None


def clear_capability_directory_cache() -> None:
    """Test hook: invalidate lru_cache for registry load."""
    _load_raw.cache_clear()
    load_validated_registry.cache_clear()
