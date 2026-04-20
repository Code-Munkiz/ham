"""Phase 2a: Hermes runtime skills shared install (preview/apply, capabilities)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham import hermes_skills_install as install
from src.ham.hermes_skills_catalog import catalog_upstream_meta

client = TestClient(app)

_UPSTREAM_COMMIT = (catalog_upstream_meta() or {}).get("commit")
assert isinstance(_UPSTREAM_COMMIT, str) and len(_UPSTREAM_COMMIT) == 40


def _dogfood_source_root(tmp_path) -> tuple[object, object]:
    """Minimal tree matching catalog `bundled.dogfood` → skills/dogfood."""
    root = tmp_path / "hermes-agent"
    skill = root / "skills" / "dogfood"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: dogfood\nversion: 1.0.0\ndescription: test\n---\nbody\n",
        encoding="utf-8",
    )
    (root / ".ham-hermes-agent-commit").write_text(_UPSTREAM_COMMIT, encoding="utf-8")
    return tmp_path, root


def _local_hermes_env(monkeypatch, tmp_path, source_root):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_SKILLS_MODE", raising=False)
    monkeypatch.setenv("HAM_HERMES_SKILLS_SOURCE_ROOT", str(source_root))
    (tmp_path / ".hermes").mkdir()


def test_capabilities_include_phase2a_fields(monkeypatch, tmp_path):
    _local_hermes_env(monkeypatch, tmp_path, _dogfood_source_root(tmp_path)[1])
    res = client.get("/api/hermes-skills/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "shared_runtime_install_supported" in data
    assert data["shared_runtime_install_supported"] is True
    assert "skills_apply_writes_enabled" in data


def test_preview_success_shared(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    res = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "hermes_skills_install_preview"
    assert body["catalog_id"] == "bundled.dogfood"
    assert body["target"] == {"kind": "shared"}
    assert len(body["proposal_digest"]) == 64
    assert len(body["base_revision"]) == 64
    assert "config_diff" in body
    assert "bundle_dest" in body
    assert "bundled.dogfood" in body["bundle_dest"]


def test_preview_remote_only_denied(monkeypatch, tmp_path):
    monkeypatch.setenv("HAM_HERMES_SKILLS_MODE", "remote_only")
    res = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    assert res.status_code == 400
    err = res.json()["detail"]["error"]
    assert err["code"] == "REMOTE_UNSUPPORTED"


def test_preview_target_not_supported():
    res = client.post(
        "/api/hermes-skills/install/preview",
        json={
            "catalog_id": "bundled.dogfood",
            "target": {"kind": "hermes_profile", "id": "dev"},
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "TARGET_NOT_SUPPORTED"


def test_preview_not_installable(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    fake = {
        "catalog_id": "bundled.dogfood",
        "display_name": "x",
        "summary": "",
        "trust_level": "builtin",
        "source_kind": "hermes_repo_pin",
        "source_ref": "",
        "version_pin": "",
        "content_hash_sha256": "abc",
        "platforms": [],
        "required_environment_variables": [],
        "config_keys": [],
        "has_scripts": False,
        "installable_by_default": False,
        "detail": {"provenance_note": "", "warnings": [], "manifest_files": []},
    }
    with patch("src.ham.hermes_skills_install.get_catalog_entry_detail", return_value=fake):
        res = client.post(
            "/api/hermes-skills/install/preview",
            json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
        )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "SKILL_NOT_INSTALLABLE"


def test_preview_unknown_catalog(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    res = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "not.a.real.catalog.id", "target": {"kind": "shared"}},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SKILL_NOT_IN_CATALOG"


def test_apply_success_with_token(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    monkeypatch.setenv("HAM_SKILLS_WRITE_TOKEN", "test-secret-token")
    pv = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    assert pv.status_code == 200
    p = pv.json()
    res = client.post(
        "/api/hermes-skills/install/apply",
        headers={"Authorization": "Bearer test-secret-token"},
        json={
            "catalog_id": "bundled.dogfood",
            "target": {"kind": "shared"},
            "proposal_digest": p["proposal_digest"],
            "base_revision": p["base_revision"],
        },
    )
    assert res.status_code == 200
    out = res.json()
    assert out["kind"] == "hermes_skills_install_apply"
    assert out["catalog_id"] == "bundled.dogfood"
    assert out["audit_id"].endswith("-audit")
    assert "backup_id" in out
    cfg = tmp_path / ".hermes" / "config.yaml"
    assert cfg.is_file()
    doc = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    dirs = doc["skills"]["external_dirs"]
    assert len(dirs) == 1
    assert "ham-runtime-bundles" in dirs[0]
    assert Path(dirs[0]).is_dir()
    assert (Path(dirs[0]) / "SKILL.md").is_file()


def test_apply_missing_token_rejected(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    monkeypatch.setenv("HAM_SKILLS_WRITE_TOKEN", "tok")
    pv = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    p = pv.json()
    res = client.post(
        "/api/hermes-skills/install/apply",
        json={
            "catalog_id": "bundled.dogfood",
            "target": {"kind": "shared"},
            "proposal_digest": p["proposal_digest"],
            "base_revision": p["base_revision"],
        },
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "TOKEN_REQUIRED"


def test_apply_invalid_token(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    monkeypatch.setenv("HAM_SKILLS_WRITE_TOKEN", "tok")
    pv = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    p = pv.json()
    res = client.post(
        "/api/hermes-skills/install/apply",
        headers={"Authorization": "Bearer wrong"},
        json={
            "catalog_id": "bundled.dogfood",
            "target": {"kind": "shared"},
            "proposal_digest": p["proposal_digest"],
            "base_revision": p["base_revision"],
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "INVALID_TOKEN"


def test_apply_conflict_on_base_revision(monkeypatch, tmp_path):
    _, src = _dogfood_source_root(tmp_path)
    _local_hermes_env(monkeypatch, tmp_path, src)
    monkeypatch.setenv("HAM_SKILLS_WRITE_TOKEN", "tok")
    pv = client.post(
        "/api/hermes-skills/install/preview",
        json={"catalog_id": "bundled.dogfood", "target": {"kind": "shared"}},
    )
    p = pv.json()
    cfg = tmp_path / ".hermes" / "config.yaml"
    cfg.write_text("skills: { other: true }\n", encoding="utf-8")
    res = client.post(
        "/api/hermes-skills/install/apply",
        headers={"Authorization": "Bearer tok"},
        json={
            "catalog_id": "bundled.dogfood",
            "target": {"kind": "shared"},
            "proposal_digest": p["proposal_digest"],
            "base_revision": p["base_revision"],
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "APPLY_CONFLICT"


def test_merge_external_dirs_no_duplicate():
    from pathlib import Path

    base = Path("/tmp/ham-x")
    d1 = base / "a"
    doc: dict = {"skills": {"external_dirs": [str(d1)]}}
    merged = install.merge_external_dirs(doc, d1)
    assert merged["skills"]["external_dirs"] == [str(d1.resolve())]


def test_merge_external_dirs_adds_once():
    from pathlib import Path

    a = Path("/tmp/ham-merge-a")
    b = Path("/tmp/ham-merge-b")
    doc: dict = {"skills": {"external_dirs": [str(a)]}}
    merged = install.merge_external_dirs(doc, b)
    dirs = merged["skills"]["external_dirs"]
    assert len(dirs) == 2
    assert str(a.resolve()) in dirs
    assert str(b.resolve()) in dirs


def test_allowlisted_bundle_dest_under_root(tmp_path):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    # slug strips weird chars; ensure resolved dest stays under bundle root
    dest = install._allowlisted_bundle_dest(hermes, "bundled.dogfood", "abc" * 20)
    root = install._bundle_root(hermes)
    assert dest == root or root in dest.parents
