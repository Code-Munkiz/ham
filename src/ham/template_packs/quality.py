"""Private visual quality gates for template-pack native workspace builds."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ham.template_packs.schema import TemplatePack, TemplatePackQualityGate

_TAILWIND_CLASS_RE = re.compile(
    r"\b(?:bg|text|border|ring|shadow|rounded|p[xytblr]?-|m[xytblr]?-|gap-|grid|flex|"
    r"sm:|md:|lg:|xl:|2xl:|min-h-|max-w-|font-|leading-|tracking-|from-|to-|via-)"
)
_RESPONSIVE_RE = re.compile(r"\b(?:sm:|md:|lg:|xl:|2xl:)")
_SECTION_BLOCK_RE = re.compile(
    r'<section\b[^>]*\bdata-ham-section=["\']([^"\']+)["\'][^>]*>.*?</section>',
    re.DOTALL | re.IGNORECASE,
)
_SPARSE_APP_RE = re.compile(
    r"export\s+default\s+function\s+App\s*\([^)]*\)\s*\{\s*return\s*<main[^>]*>\s*[^<]{0,40}</main>",
    re.DOTALL | re.IGNORECASE,
)
_UNSTYLED_SEMANTIC_ONLY_RE = re.compile(
    r"<(main|div|section|header|footer|article)(\s|>)(?!.*className)",
    re.IGNORECASE,
)
_LOW_CONTRAST_RE = re.compile(
    r"text-(?:gray|slate|zinc)-(?:100|200)\b.*bg-(?:white|gray-50|slate-50)|"
    r"bg-(?:white|gray-50)\b.*text-(?:gray|100|200)\b",
    re.IGNORECASE,
)

_PREVIEW_FAILURE_USER_MESSAGE = "HAM couldn't finish this preview.\n\n"
_REPAIR_INSTRUCTION_BASE = (
    "The current workspace is valid but visually underdesigned. Improve layout, spacing, "
    "contrast, typography, section hierarchy, cards, and responsive styling while preserving "
    "the user request."
)
_SECTION_MARKER_RULE = (
    "Keep every data-ham-section=\"...\" marker on its section element. "
    "Do not remove, rename, or relocate those attributes."
)


@dataclass(frozen=True)
class TemplatePackQualityIssue:
    code: str
    detail: str


@dataclass(frozen=True)
class TemplatePackQualityResult:
    ok: bool
    issues: tuple[TemplatePackQualityIssue, ...] = ()
    pack_id: str | None = None

    def to_operator_metadata(self) -> dict[str, object]:
        return {
            "template_pack_quality_ok": self.ok,
            "template_pack_id": self.pack_id,
            "issues": [{"code": i.code, "detail": i.detail} for i in self.issues],
        }


def user_message_for_quality_failure() -> str:
    return _PREVIEW_FAILURE_USER_MESSAGE


def _section_id_from_missing_issue(detail: str) -> str | None:
    prefix = "Required section not found: "
    if detail.startswith(prefix):
        return detail[len(prefix) :].strip()
    return None


def visual_quality_repair_instruction(
    *,
    issues: tuple[TemplatePackQualityIssue, ...] = (),
) -> str:
    parts = [_REPAIR_INSTRUCTION_BASE, _SECTION_MARKER_RULE]
    missing_sections = [
        sid
        for issue in issues
        if issue.code == "missing_section"
        and (sid := _section_id_from_missing_issue(issue.detail)) is not None
    ]
    if missing_sections:
        names = ", ".join(missing_sections)
        parts.append(
            f"Restore these required sections with polished Tailwind layout: {names}."
        )
    other_codes = sorted({issue.code for issue in issues if issue.code != "missing_section"})
    if other_codes:
        parts.append(f"Also fix quality issues: {', '.join(other_codes)}.")
    return " ".join(parts)


def _file(files: dict[str, str], path: str) -> str:
    return files.get(path) or ""


def _count_tailwind_tokens(*parts: str) -> int:
    return sum(len(_TAILWIND_CLASS_RE.findall(part)) for part in parts if part)


def _section_block(app_tsx: str, section_id: str) -> str:
    pattern = (
        rf'<section\b[^>]*\bdata-ham-section=["\']{re.escape(section_id)}["\'][^>]*>.*?</section>'
    )
    match = re.search(pattern, app_tsx, re.DOTALL | re.IGNORECASE)
    return match.group(0) if match else ""


def _count_service_cards(app_tsx: str) -> int:
    services = _section_block(app_tsx, "services")
    article_count = len(re.findall(r"<article\b", services, re.I))
    if article_count >= 3:
        return article_count
    inline_titles = len(re.findall(r'\btitle:\s*"', services))
    if inline_titles >= 3:
        return inline_titles
    if article_count >= 1 and re.search(r"\bservices\.map\b", services):
        array_match = re.search(r"const\s+services\s*=\s*\[(.*?)\];", app_tsx, re.DOTALL)
        if array_match:
            array_titles = len(re.findall(r'\btitle:\s*"', array_match.group(1)))
            if array_titles:
                return array_titles
    return max(article_count, inline_titles)


def _evaluate_pack_specific_gates(
    app_tsx: str,
    gates: TemplatePackQualityGate,
    issues: list[TemplatePackQualityIssue],
) -> None:
    if gates.require_hero_richness:
        hero = _section_block(app_tsx, "hero")
        hero_rich = bool(
            hero
            and re.search(r"<h1\b", hero, re.I)
            and re.search(r"\b(?:from-|bg-gradient|blur-|rounded-full|shadow-)", hero, re.I)
        )
        if not hero_rich:
            issues.append(
                TemplatePackQualityIssue(
                    "weak_hero",
                    "Hero section lacks expected visual richness (headline + accent styling)",
                )
            )

    if gates.min_service_cards is not None:
        card_count = _count_service_cards(app_tsx)
        if card_count < gates.min_service_cards:
            issues.append(
                TemplatePackQualityIssue(
                    "insufficient_service_cards",
                    f"Services section has {card_count} cards; need >= {gates.min_service_cards}",
                )
            )

    if gates.require_cta_action:
        cta = _section_block(app_tsx, "cta")
        has_action = bool(
            cta
            and re.search(
                r"<(?:button|a)\b[^>]*className=",
                cta,
                re.I,
            )
        )
        if not has_action:
            issues.append(
                TemplatePackQualityIssue(
                    "missing_cta_action",
                    "CTA section missing visible button or link action",
                )
            )


def evaluate_workspace_visual_quality(
    files: dict[str, str],
    *,
    pack: TemplatePack | None = None,
) -> TemplatePackQualityResult:
    """Run lightweight heuristics on collected workspace files (operator diagnostics only)."""
    issues: list[TemplatePackQualityIssue] = []
    pack_id = pack.id if pack else None
    gates = pack.manifest.quality_gates if pack else None

    index_css = _file(files, "src/index.css")
    styles_css = _file(files, "src/styles.css")
    main_tsx = _file(files, "src/main.tsx")
    app_tsx = _file(files, "src/App.tsx")

    if not index_css and not styles_css:
        issues.append(TemplatePackQualityIssue("missing_global_css", "src/index.css missing"))

    css_imported = "./index.css" in main_tsx or "./styles.css" in main_tsx
    if not css_imported:
        issues.append(
            TemplatePackQualityIssue("css_not_imported", "Global CSS not imported from src/main.tsx")
        )

    if len(app_tsx.strip()) < 120 or _SPARSE_APP_RE.search(app_tsx):
        issues.append(TemplatePackQualityIssue("sparse_app", "App.tsx is extremely sparse"))

    tailwind_count = _count_tailwind_tokens(app_tsx, index_css, styles_css)
    min_tw = gates.min_tailwind_class_tokens if gates else 8
    if tailwind_count < min_tw:
        issues.append(
            TemplatePackQualityIssue(
                "insufficient_tailwind",
                f"Tailwind utility usage below threshold ({tailwind_count} < {min_tw})",
            )
        )

    semantic_hits = len(_UNSTYLED_SEMANTIC_ONLY_RE.findall(app_tsx))
    if semantic_hits >= 3 and tailwind_count < min_tw + 4:
        issues.append(
            TemplatePackQualityIssue(
                "unstyled_semantic_html",
                "App appears to use mostly unstyled semantic HTML",
            )
        )

    if gates and gates.require_responsive_classes and not _RESPONSIVE_RE.search(app_tsx):
        issues.append(
            TemplatePackQualityIssue("missing_responsive", "No responsive breakpoint classes in App.tsx")
        )

    if gates and gates.require_explicit_background:
        has_bg = bool(
            re.search(r"\b(?:bg-|background|min-h-screen|from-|to-)", app_tsx + index_css, re.I)
        )
        if not has_bg:
            issues.append(
                TemplatePackQualityIssue(
                    "missing_background", "No explicit page/section background styling"
                )
            )

    if not re.search(r"\b(?:rounded|shadow|border|card|btn|button)", app_tsx, re.I):
        issues.append(
            TemplatePackQualityIssue(
                "weak_visual_hierarchy", "Missing card/button/section visual hierarchy cues"
            )
        )

    if _LOW_CONTRAST_RE.search(app_tsx):
        issues.append(
            TemplatePackQualityIssue("low_contrast", "Possible low-contrast class combination")
        )

    if gates and gates.required_sections:
        combined = app_tsx
        for section in gates.required_sections:
            marker = section.lower().replace("_", "-")
            has_marker = (
                f'data-ham-section="{marker}"' in combined
                or f"data-ham-section='{marker}'" in combined
                or f"{{/* {marker}" in combined.lower()
            )
            if not has_marker:
                issues.append(
                    TemplatePackQualityIssue(
                        "missing_section",
                        f"Required section not found: {section}",
                    )
                )

    if gates:
        _evaluate_pack_specific_gates(app_tsx, gates, issues)

    return TemplatePackQualityResult(
        ok=not issues,
        issues=tuple(issues),
        pack_id=pack_id,
    )


def contains_template_pack_leak(text: str) -> bool:
    """Detect template-pack internals that must not appear in user-visible copy."""
    lower = (text or "").lower()
    forbidden = (
        "template pack",
        "template-pack",
        "pack.yaml",
        "landing/agency-modern",
        "landing/saas-clean",
        "dashboard/project-management",
        "dashboard/analytics",
        "ham-authored-internal",
        "ham template pack baseline",
    )
    return any(token in lower for token in forbidden)


__all__ = [
    "TemplatePackQualityIssue",
    "TemplatePackQualityResult",
    "contains_template_pack_leak",
    "evaluate_workspace_visual_quality",
    "user_message_for_quality_failure",
    "visual_quality_repair_instruction",
]
