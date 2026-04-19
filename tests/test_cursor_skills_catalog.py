"""Cursor skills catalog for chat control plane."""
from __future__ import annotations

from pathlib import Path

from src.ham.cursor_skills_catalog import (
    list_cursor_skills,
    render_skills_for_system_prompt,
)


def test_list_cursor_skills_finds_repo_skills(tmp_path: Path) -> None:
    skills = tmp_path / ".cursor" / "skills" / "demo-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: >-\n"
        "  First line.\n"
        "  Second line.\n"
        "---\n\n# Demo\n",
        encoding="utf-8",
    )
    out = list_cursor_skills(repo_root=tmp_path)
    assert len(out) == 1
    assert out[0]["id"] == "demo-skill"
    assert out[0]["name"] == "demo-skill"
    assert "First line." in out[0]["description"]
    assert "Second line." in out[0]["description"]


def test_render_skills_truncates() -> None:
    big = [{"id": "x", "name": "n", "description": "d" * 500}]
    text = render_skills_for_system_prompt(big, max_chars=80)
    assert len(text) <= 80
    assert text.endswith("…")
