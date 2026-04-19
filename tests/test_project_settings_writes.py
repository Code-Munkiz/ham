"""Allowlisted project settings preview / apply / rollback (v1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.settings_write import (
    preview_project_settings,
    read_project_settings_document,
    revision_for_document,
)
from src.memory_heist import discover_config


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_discover_config_project_settings_replacement(tmp_path: Path, isolated_home: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".ham.json").write_text(
        json.dumps({"memory_heist": {"session_compaction_max_tokens": 111}}),
        encoding="utf-8",
    )
    (root / ".ham").mkdir(exist_ok=True)
    (root / ".ham" / "settings.json").write_text(
        json.dumps({"memory_heist": {"session_compaction_max_tokens": 222}}),
        encoding="utf-8",
    )
    merged_disk = discover_config(root).merged
    assert merged_disk.get("memory_heist", {}).get("session_compaction_max_tokens") == 222
    fake = {"memory_heist": {"session_compaction_max_tokens": 333}}
    merged_preview = discover_config(root, project_settings_replacement=fake).merged
    assert merged_preview.get("memory_heist", {}).get("session_compaction_max_tokens") == 333


@pytest.mark.usefixtures("isolated_home")
def test_preview_unit(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    from src.ham.settings_write import SettingsChanges, MemoryHeistPatch

    prev = preview_project_settings(
        root,
        SettingsChanges(memory_heist=MemoryHeistPatch(session_compaction_max_tokens=42_000)),
    )
    assert prev.base_revision == revision_for_document({})
    assert any(d["path"] == "memory_heist.session_compaction_max_tokens" for d in prev.diff)
    assert prev.effective_after["memory_heist"]["session_compaction_max_tokens"] == 42_000


def test_preview_rejects_unknown_field(isolated_home: Path) -> None:
    client = TestClient(app)
    root = isolated_home / "proj"
    root.mkdir()
    pid = _register_project(client, name="p", root=root)
    res = client.post(
        f"/api/projects/{pid}/settings/preview",
        json={"changes": {"evil": True}},
    )
    assert res.status_code == 422


def test_apply_disabled_without_token(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAM_SETTINGS_WRITE_TOKEN", raising=False)
    client = TestClient(app)
    root = tmp_path / "proj"
    root.mkdir()
    pid = _register_project(client, name="p2", root=root)
    res = client.post(
        f"/api/projects/{pid}/settings/apply",
        json={
            "changes": {"memory_heist": {"session_compaction_max_tokens": 8000}},
            "base_revision": revision_for_document({}),
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SETTINGS_WRITES_DISABLED"


def test_preview_apply_rollback_flow(tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SETTINGS_WRITE_TOKEN", "test-secret-token")
    client = TestClient(app)
    root = tmp_path / "proj"
    root.mkdir()
    pid = _register_project(client, name="p3", root=root)

    prev = client.post(
        f"/api/projects/{pid}/settings/preview",
        json={"changes": {"architect_instruction_chars": 12_000}},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    base_rev = body["base_revision"]

    bad = client.post(
        f"/api/projects/{pid}/settings/apply",
        headers={"Authorization": "Bearer wrong"},
        json={
            "changes": {"architect_instruction_chars": 12_000},
            "base_revision": base_rev,
        },
    )
    assert bad.status_code == 403

    apply_res = client.post(
        f"/api/projects/{pid}/settings/apply",
        headers={"Authorization": "Bearer test-secret-token"},
        json={
            "changes": {"architect_instruction_chars": 12_000},
            "base_revision": base_rev,
        },
    )
    assert apply_res.status_code == 200, apply_res.text
    doc = read_project_settings_document(root)
    assert doc.get("architect_instruction_chars") == 12_000
    backup_id = apply_res.json()["backup_id"]

    prev2 = client.post(
        f"/api/projects/{pid}/settings/preview",
        json={"changes": {"architect_instruction_chars": 16_000}},
    )
    assert prev2.status_code == 200
    wrong = client.post(
        f"/api/projects/{pid}/settings/apply",
        headers={"Authorization": "Bearer test-secret-token"},
        json={
            "changes": {"architect_instruction_chars": 16_000},
            "base_revision": base_rev,
        },
    )
    assert wrong.status_code == 409

    rb = client.post(
        f"/api/projects/{pid}/settings/rollback",
        headers={"Authorization": "Bearer test-secret-token"},
        json={"backup_id": backup_id},
    )
    assert rb.status_code == 200, rb.text
    doc_after = read_project_settings_document(root)
    assert "architect_instruction_chars" not in doc_after


def test_write_status_endpoint() -> None:
    client = TestClient(app)
    res = client.get("/api/settings/write-status")
    assert res.status_code == 200
    assert "writes_enabled" in res.json()
