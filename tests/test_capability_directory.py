"""HAM Capability Directory Phase 1 — static registry and read-only API."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham import capability_directory as cd

client = TestClient(app)

_REQUIRED_RECORD_KEYS = frozenset(
    {
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
    }
)


def test_directory_index() -> None:
    res = client.get("/api/capability-directory")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "capability_directory_index"
    assert data["schema_version"] == "capability.directory.v1"
    assert data["registry_id"] == "ham.first_party.v1"
    assert data["mutation_policy"] == "read_only"
    assert data["apply_available_globally"] is False
    assert "no_execution_notice" in data
    c = data["counts"]
    assert c["capabilities"] >= 2
    assert c["bundles"] == 4
    assert c["profile_templates"] >= 1
    assert data["trust_tier_counts"]["first_party"] == c["capabilities"] + c["bundles"] + c["profile_templates"]
    assert "endpoints" in data


def test_list_capabilities() -> None:
    res = client.get("/api/capability-directory/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "capability_directory_capabilities"
    assert data["apply_available_globally"] is False
    assert data["count"] == len(data["capabilities"])
    for rec in data["capabilities"]:
        assert rec["kind"] == "atomic_capability"
        assert _REQUIRED_RECORD_KEYS.issubset(rec.keys())


def test_list_bundles() -> None:
    res = client.get("/api/capability-directory/bundles")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "capability_directory_bundles"
    assert data["apply_available_globally"] is False
    assert data["count"] == 4
    ids = {b["id"] for b in data["bundles"]}
    assert ids == {
        "hermes-runtime-inspector",
        "hermes-skills-live-overlay",
        "cursor-cloud-agent-handoff",
        "desktop-release-readiness",
    }


def test_get_bundle_by_id() -> None:
    res = client.get("/api/capability-directory/bundles/hermes-runtime-inspector")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "capability_directory_bundle"
    assert data["apply_available_globally"] is False
    assert data["mutation_policy"] == "read_only"
    b = data["bundle"]
    assert b["id"] == "hermes-runtime-inspector"
    assert b["display_name"] == "Hermes Runtime Inspector"
    assert b["apply_available"] is False
    assert "no_execution_notice" in data


def test_unknown_bundle_404() -> None:
    res = client.get("/api/capability-directory/bundles/does-not-exist")
    assert res.status_code == 404
    body = res.json()
    assert body["detail"]["error"]["code"] == "CAPABILITY_BUNDLE_UNKNOWN"


def test_all_records_non_mutating_apply() -> None:
    reg = cd.load_validated_registry()
    for section in ("capabilities", "bundles", "profile_templates"):
        for rec in reg[section]:
            assert rec["apply_available"] is False, rec["id"]


def test_registry_required_fields_and_provenance() -> None:
    reg = cd.load_validated_registry()
    for section in ("capabilities", "bundles", "profile_templates"):
        for rec in reg[section]:
            assert _REQUIRED_RECORD_KEYS == _REQUIRED_RECORD_KEYS.intersection(rec.keys())
            prov = rec["provenance"]
            assert isinstance(prov, dict)
            assert str(prov.get("source_kind") or "").strip()


def test_phase1_no_apply_available_true(tmp_path, monkeypatch) -> None:
    """Invalid registry with apply_available true must fail validation."""
    bad = {
        "schema_version": "capability.directory.v1",
        "registry_id": "ham.first_party.v1",
        "capabilities": [],
        "profile_templates": [],
        "bundles": [
            {
                "id": "bad-bundle",
                "schema_version": "capability.directory.v1",
                "kind": "bundle",
                "display_name": "Bad",
                "summary": "x",
                "description": "x",
                "trust_tier": "first_party",
                "provenance": {"source_kind": "ham_repo"},
                "version": "1.0.0",
                "required_backends": [],
                "capabilities": [],
                "skills": [],
                "tools_policy": {"mode": "x"},
                "mcp_policy": {"mode": "none"},
                "model_policy": {"mode": "x"},
                "memory_policy": {"mode": "x"},
                "surfaces": [{"route": "/x", "label": "X"}],
                "mutability": "read_only",
                "preview_available": False,
                "apply_available": True,
                "risks": [],
                "evidence_expectations": [],
                "tags": [],
            }
        ],
    }
    p = tmp_path / "capability_directory_v1.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(cd, "_data_path", lambda: p)
    cd.clear_capability_directory_cache()
    try:
        with pytest.raises(ValueError, match="apply_available"):
            cd.load_validated_registry()
    finally:
        cd.clear_capability_directory_cache()


def test_spec_section_reference_in_doc() -> None:
    """Sanity: bundled spec pointer remains §15 for inspection basis."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/capabilities/capability_bundle_directory_v1.md").read_text(encoding="utf-8")
    assert "§15" in text
