"""GET /api/hermes-skills/* — Hermes runtime skills catalog (Phase 1, read-only)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_hermes_catalog_lists_entries() -> None:
    res = client.get("/api/hermes-skills/catalog")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "hermes_runtime_skills_catalog"
    assert data["count"] >= 120
    assert isinstance(data["entries"], list)
    ids = {e["catalog_id"] for e in data["entries"]}
    assert "bundled.dogfood" in ids
    assert data.get("upstream", {}).get("repo") == "NousResearch/hermes-agent"
    assert len(data.get("upstream", {}).get("commit", "")) == 40
    assert "catalog_note" in data


def test_hermes_catalog_detail() -> None:
    res = client.get("/api/hermes-skills/catalog/bundled.dogfood")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "hermes_runtime_skill_detail"
    entry = data["entry"]
    assert entry["catalog_id"] == "bundled.dogfood"
    assert entry["trust_level"] == "builtin"
    assert "detail" in entry
    assert "manifest_files" in entry["detail"]


def test_hermes_catalog_detail_unknown() -> None:
    res = client.get("/api/hermes-skills/catalog/nonexistent-skill-id")
    assert res.status_code == 404
    body = res.json()
    assert body["detail"]["error"]["code"] == "HERMES_SKILL_CATALOG_UNKNOWN"


def test_hermes_capabilities_remote_only(monkeypatch) -> None:
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    res = client.get("/api/hermes-skills/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "hermes_skills_capabilities"
    assert data["mode"] == "remote_only"
    assert data["shared_target_supported"] is False
    assert data["profile_target_supported"] is False


def test_hermes_capabilities_unsupported_without_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    res = client.get("/api/hermes-skills/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "unsupported"
    assert data["hermes_home_detected"] is False


def test_hermes_capabilities_local_with_profiles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "profiles").mkdir()
    (hermes / "profiles" / "work").mkdir()
    res = client.get("/api/hermes-skills/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "local"
    assert data["hermes_home_detected"] is True
    assert data["profile_listing_supported"] is True
    assert data.get("profile_count") == 1


def test_hermes_targets_lists_shared_and_profiles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "profiles").mkdir()
    (hermes / "profiles" / "dev").mkdir()
    res = client.get("/api/hermes-skills/targets")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "hermes_skills_targets"
    kinds = {t["kind"] for t in data["targets"]}
    assert "shared" in kinds
    assert "hermes_profile" in kinds
    prof_ids = {t["id"] for t in data["targets"] if t["kind"] == "hermes_profile"}
    assert "dev" in prof_ids
