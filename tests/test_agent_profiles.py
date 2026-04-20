"""HAM agent profiles — schema, merged config parsing, settings preview/apply."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.server import app
from src.ham.agent_profiles import (
    PRIMARY_AGENT_DEFAULT_ID,
    HamAgentProfile,
    HamAgentsConfig,
    agents_config_from_merged,
    default_agents_config,
    validate_agents_config,
)
from src.ham.settings_write import SettingsChanges, read_project_settings_document


def test_default_agents_config() -> None:
    d = default_agents_config()
    assert d.primary_agent_id == PRIMARY_AGENT_DEFAULT_ID
    assert len(d.profiles) == 1
    assert d.profiles[0].id == PRIMARY_AGENT_DEFAULT_ID
    assert d.profiles[0].skills == []


def test_agents_from_merged_missing() -> None:
    cfg = agents_config_from_merged({})
    assert cfg.primary_agent_id == PRIMARY_AGENT_DEFAULT_ID


def test_agents_from_merged_round_trip() -> None:
    blob = {
        "agents": {
            "profiles": [
                {
                    "id": "ham.default",
                    "name": "HAM",
                    "description": "Primary assistant",
                    "skills": [],
                    "enabled": True,
                },
                {
                    "id": "custom.sec",
                    "name": "Security",
                    "description": "",
                    "skills": ["bundled.apple.apple-notes"],
                    "enabled": False,
                },
            ],
            "primary_agent_id": "ham.default",
        }
    }
    cfg = agents_config_from_merged(blob)
    assert cfg.primary_agent_id == "ham.default"
    assert len(cfg.profiles) == 2
    assert cfg.profiles[1].skills == ["bundled.apple.apple-notes"]


def test_validate_rejects_duplicate_profile_ids() -> None:
    cfg = HamAgentsConfig(
        profiles=[
            HamAgentProfile(id="a.x", name="A", skills=[]),
            HamAgentProfile(id="a.x", name="B", skills=[]),
        ],
        primary_agent_id="a.x",
    )
    with pytest.raises(ValueError, match="duplicate profile id"):
        validate_agents_config(cfg)


def test_validate_rejects_primary_missing() -> None:
    cfg = HamAgentsConfig(
        profiles=[HamAgentProfile(id="a.x", name="A", skills=[])],
        primary_agent_id="nope",
    )
    with pytest.raises(ValueError, match="primary_agent_id"):
        validate_agents_config(cfg)


def test_validate_rejects_unknown_skill() -> None:
    cfg = HamAgentsConfig(
        profiles=[
            HamAgentProfile(
                id="ham.default",
                name="HAM",
                skills=["not.a.real.catalog.entry.zzzzz"],
            ),
        ],
        primary_agent_id="ham.default",
    )
    with pytest.raises(ValueError, match="unknown Hermes runtime skill"):
        validate_agents_config(cfg)


def test_validate_rejects_duplicate_skill_in_profile() -> None:
    with pytest.raises(ValidationError, match="duplicate skill"):
        HamAgentProfile(
            id="ham.default",
            name="HAM",
            skills=["bundled.apple.apple-notes", "bundled.apple.apple-notes"],
        )


@pytest.mark.usefixtures("isolated_home")
def test_settings_preview_apply_agents(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_SETTINGS_WRITE_TOKEN", "tok-agents")
    client = TestClient(app)
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".ham").mkdir(exist_ok=True)
    (root / ".ham" / "settings.json").write_text("{}", encoding="utf-8")
    res_reg = client.post(
        "/api/projects",
        json={"name": "agproj", "root": str(root), "description": ""},
    )
    assert res_reg.status_code == 201, res_reg.text
    pid = res_reg.json()["id"]

    new_agents = HamAgentsConfig(
        profiles=[
            HamAgentProfile(
                id="ham.default",
                name="HAM",
                description="Primary assistant",
                skills=["bundled.apple.apple-notes"],
                enabled=True,
            ),
            HamAgentProfile(
                id="work.sec",
                name="Security",
                description="",
                skills=[],
                enabled=True,
            ),
        ],
        primary_agent_id="work.sec",
    )
    changes = SettingsChanges(agents=new_agents)
    prev = client.post(
        f"/api/projects/{pid}/settings/preview",
        json={"changes": changes.model_dump(mode="json", exclude_none=True)},
    )
    assert prev.status_code == 200, prev.text
    base_rev = prev.json()["base_revision"]
    assert any(d.get("path") == "agents" for d in prev.json()["diff"])

    get_before = client.get(f"/api/projects/{pid}/agents")
    assert get_before.status_code == 200
    assert get_before.json()["agents"]["primary_agent_id"] == PRIMARY_AGENT_DEFAULT_ID

    apply_res = client.post(
        f"/api/projects/{pid}/settings/apply",
        headers={"Authorization": "Bearer tok-agents"},
        json={
            "changes": changes.model_dump(mode="json", exclude_none=True),
            "base_revision": base_rev,
        },
    )
    assert apply_res.status_code == 200, apply_res.text
    doc = read_project_settings_document(root)
    assert doc["agents"]["primary_agent_id"] == "work.sec"
    assert len(doc["agents"]["profiles"]) == 2
    assert doc["agents"]["profiles"][0]["skills"] == ["bundled.apple.apple-notes"]

    get_after = client.get(f"/api/projects/{pid}/agents")
    assert get_after.json()["agents"]["primary_agent_id"] == "work.sec"


@pytest.mark.usefixtures("isolated_home")
def test_settings_preview_agents_invalid_skill(
    tmp_path: Path, isolated_home: Path,
) -> None:
    client = TestClient(app)
    root = tmp_path / "proj2"
    root.mkdir()
    (root / ".ham").mkdir(exist_ok=True)
    (root / ".ham" / "settings.json").write_text("{}", encoding="utf-8")
    res_reg = client.post(
        "/api/projects",
        json={"name": "bad", "root": str(root), "description": ""},
    )
    assert res_reg.status_code == 201
    pid = res_reg.json()["id"]
    bad = HamAgentsConfig(
        profiles=[
            HamAgentProfile(id="ham.default", name="HAM", skills=["invalid.skill.zz"]),
        ],
        primary_agent_id="ham.default",
    )
    prev = client.post(
        f"/api/projects/{pid}/settings/preview",
        json={"changes": {"agents": bad.model_dump(mode="json")}},
    )
    assert prev.status_code == 422


# Re-use isolated_home fixture from test_project_settings_writes
@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home
