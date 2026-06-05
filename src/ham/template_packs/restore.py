"""Deterministic restore of missing template-pack sections (operator-only)."""

from __future__ import annotations

import re

from src.ham.template_packs.quality import TemplatePackQualityIssue
from src.ham.template_packs.schema import TemplatePack

_APP_PATH = "src/App.tsx"
_SECTION_BLOCK_RE = re.compile(
    r"<section\b[^>]*\bdata-ham-section=[\"']([^\"']+)[\"'][^>]*>.*?</section>",
    re.DOTALL | re.IGNORECASE,
)
_MISSING_SECTION_PREFIX = "Required section not found: "


def _section_id_from_issue(issue: TemplatePackQualityIssue) -> str | None:
    if issue.code != "missing_section":
        return None
    if not issue.detail.startswith(_MISSING_SECTION_PREFIX):
        return None
    return issue.detail[len(_MISSING_SECTION_PREFIX) :].strip()


def extract_pack_sections(app_tsx: str) -> dict[str, str]:
    """Map data-ham-section ids to full <section> blocks from pack App.tsx."""
    sections: dict[str, str] = {}
    for match in _SECTION_BLOCK_RE.finditer(app_tsx):
        section_id = match.group(1).strip().lower()
        if section_id and section_id not in sections:
            sections[section_id] = match.group(0)
    return sections


def _has_section_marker(app_tsx: str, section_id: str) -> bool:
    marker = section_id.lower().replace("_", "-")
    return (
        f'data-ham-section="{marker}"' in app_tsx
        or f"data-ham-section='{marker}'" in app_tsx
        or f"{{/* {marker}" in app_tsx.lower()
    )


def _insert_section_before_main_close(app_tsx: str, section_block: str) -> str:
    close_idx = app_tsx.rfind("</main>")
    if close_idx == -1:
        return f"{app_tsx.rstrip()}\n{section_block}\n"
    indent = ""
    line_start = app_tsx.rfind("\n", 0, close_idx)
    if line_start != -1:
        indent = re.match(r"[ \t]*", app_tsx[line_start + 1 : close_idx])
        indent = indent.group(0) if indent else ""
    insertion = f"\n{indent}{section_block}\n"
    return app_tsx[:close_idx] + insertion + app_tsx[close_idx:]


def restore_missing_pack_sections(
    files: dict[str, str],
    *,
    pack: TemplatePack,
    issues: tuple[TemplatePackQualityIssue, ...],
) -> tuple[dict[str, str], tuple[str, ...]] | None:
    """Splice missing required sections from the pack template into App.tsx."""
    missing_ids: list[str] = []
    for issue in issues:
        section_id = _section_id_from_issue(issue)
        if section_id and section_id not in missing_ids:
            missing_ids.append(section_id)
    if not missing_ids:
        return None

    pack_app = pack.files.get(_APP_PATH, "")
    if not pack_app.strip():
        return None

    pack_sections = extract_pack_sections(pack_app)
    current = files.get(_APP_PATH, "")
    if not current.strip():
        return None

    updated = current
    restored: list[str] = []
    for section_id in missing_ids:
        normalized = section_id.lower().replace("_", "-")
        if _has_section_marker(updated, normalized):
            continue
        block = pack_sections.get(normalized)
        if not block:
            continue
        updated = _insert_section_before_main_close(updated, block)
        restored.append(normalized)

    if not restored:
        return None

    out = dict(files)
    out[_APP_PATH] = updated
    return out, tuple(restored)


__all__ = [
    "extract_pack_sections",
    "restore_missing_pack_sections",
]
