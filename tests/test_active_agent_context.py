"""HAM active agent guidance for chat (Agent Builder + Hermes catalog descriptors)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham.active_agent_context import (
    build_active_agent_guidance,
    try_active_agent_guidance_for_project_root,
)
from src.ham.agent_profiles import HamAgentProfile


def test_build_guidance_default_profile() -> None:
    p = HamAgentProfile(
        id="ham.default",
        name="HAM",
        description="Primary assistant",
        skills=[],
        enabled=True,
    )
    r = build_active_agent_guidance(p)
    assert "HAM active agent guidance" in r.guidance_text
    assert "HAM" in r.guidance_text
    assert "Attached Hermes runtime catalog skills:** none" in r.guidance_text
    assert r.meta["skills_requested"] == 0
    assert r.meta["skills_resolved"] == 0


def test_build_guidance_resolves_catalog_skill() -> None:
    p = HamAgentProfile(
        id="ham.default",
        name="X",
        description="",
        skills=["bundled.apple.apple-notes"],
        enabled=True,
    )
    r = build_active_agent_guidance(p)
    assert "apple-notes" in r.guidance_text or "Apple" in r.guidance_text
    assert r.meta["skills_resolved"] == 1
    assert r.meta["skills_skipped_catalog_miss"] == 0


def test_build_guidance_skips_unknown_catalog_id() -> None:
    p = HamAgentProfile(
        id="ham.default",
        name="X",
        description="",
        skills=["bundled.apple.apple-notes", "not.a.real.catalog.id.zzzzz"],
        enabled=True,
    )
    r = build_active_agent_guidance(p)
    assert r.meta["skills_resolved"] == 1
    assert r.meta["skills_skipped_catalog_miss"] == 1
    assert "missing from the vendored catalog" in r.guidance_text


def test_try_guidance_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "FromDisk",
                            "description": "",
                            "skills": [],
                            "enabled": True,
                        },
                    ],
                    "primary_agent_id": "ham.default",
                },
            },
        ),
        encoding="utf-8",
    )
    r = try_active_agent_guidance_for_project_root(root)
    assert r is not None
    assert "FromDisk" in r.guidance_text
    assert r.meta["profile_id"] == "ham.default"


def test_try_guidance_bad_root_returns_none(tmp_path: Path) -> None:
    assert try_active_agent_guidance_for_project_root(tmp_path / "nope") is None
