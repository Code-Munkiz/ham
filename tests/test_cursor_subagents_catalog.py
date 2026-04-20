"""Cursor subagent rules catalog (.cursor/rules/subagent-*.mdc)."""
from __future__ import annotations

from pathlib import Path

from src.ham.cursor_subagents_catalog import (
    list_cursor_subagents,
    render_subagents_for_system_prompt,
)


def test_list_cursor_subagents_parses_frontmatter_and_title(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "subagent-demo-auditor.mdc").write_text(
        '---\n'
        'description: "Demo charter for tests."\n'
        'globs: src/demo.py\n'
        'alwaysApply: false\n'
        '---\n\n'
        '# Subagent: Demo Auditor\n\n'
        'Body.\n',
        encoding="utf-8",
    )
    out = list_cursor_subagents(repo_root=tmp_path)
    assert len(out) == 1
    assert out[0]["id"] == "subagent-demo-auditor"
    assert out[0]["title"] == "Subagent: Demo Auditor"
    assert "Demo charter" in out[0]["description"]
    assert out[0]["globs"] == "src/demo.py"
    assert out[0]["always_apply"] is False
    assert out[0]["path"].replace("\\", "/") == ".cursor/rules/subagent-demo-auditor.mdc"


def test_list_ignores_non_subagent_mdc(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "minimal-diffs.mdc").write_text("---\ndescription: x\n---\n", encoding="utf-8")
    assert list_cursor_subagents(repo_root=tmp_path) == []


def test_render_subagents_truncates() -> None:
    big = [
        {
            "id": "subagent-x",
            "title": "T",
            "description": "d" * 400,
            "globs": None,
            "always_apply": False,
        },
    ]
    text = render_subagents_for_system_prompt(big, max_chars=120)
    assert len(text) <= 120
    assert text.endswith("…")
