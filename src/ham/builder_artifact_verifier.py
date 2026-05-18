"""Calculator-focused artifact checks for chat-triggered builder scaffolds (v1).

Gates success copy: when the user asked for a checkable calculator visual/feature
and generated files do not contain the expected markers, consumers must not claim
the edit was applied successfully.
"""

from __future__ import annotations

import re
from typing import Any


def _strip_dashboard_tail(user_plain: str) -> str:
    text = str(user_plain or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"\s*\[user attached\s+\d+\s+(?:file|image)\(s\)\s+in\s+the\s+dashboard(?:\s*\([^]]*\))?\.\]\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _keypad_context(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(calculator|keypad|numpad|digit\s+buttons|number\s+buttons|digits|keys|buttons|them|those|these)\b",
            lowered,
        )
    )


def _user_requests_purple_digit_style(lowered: str) -> bool:
    if not re.search(r"\b(purple|violet|lavender)\b", lowered):
        return False
    if not _keypad_context(lowered) and not re.search(r"\b(calculator|calc)\b", lowered):
        return False
    return True


def _user_requests_yellow_border(lowered: str) -> bool:
    if re.search(r"\byellow\b.*\bborder\b|\bborder\b.*\byellow\b|\byellow\b.{0,32}\boutline\b", lowered):
        return True
    if re.search(
        r"\b(gold|amber)\b.{0,40}\bborder\b|\bborder\b.{0,40}\b(gold|amber)\b|\b#\s*facc15\b",
        lowered,
    ):
        return True
    if re.search(r"\b(yellow|gold|amber)\b.{0,72}\b(border|outline|ring)\b", lowered):
        return True
    if re.search(r"\b(border|outline|ring)\b.{0,72}\b(yellow|gold|amber)\b", lowered):
        return True
    if (
        re.search(r"\bborder\b|\boutline\b", lowered)
        and re.search(r"\byellow\b|\bgold\b|\bamber\b|#\s*facc15\b|\b#\s*[ef][a-f0-9]{5}\b", lowered)
        and re.search(
            r"\b(buttons?|digits?|numbers?|keys?|keypad|numpad|them|those|these|calc|calculator)\b",
            lowered,
        )
    ):
        return True
    return False


def _user_requests_multicolor(lowered: str) -> bool:
    if not re.search(
        r"\b(random\s+colors?|multicolor|multi[\s-]?color|rainbow|"
        r"different\s+colors?|each\s+(a\s+)?different\s+color|variety\s+of\s+colors?|"
        r"not\s+just\s+purple|not\s+only\s+purple|each\s+button\s+(a\s+)?different|"
        r"multi[\s-]?hue|assorted\s+colors?)\b",
        lowered,
    ):
        return False
    return bool(
        _keypad_context(lowered)
        or re.search(r"\b(buttons?|keys?|digits?|them|those|these)\b", lowered)
    )


def _user_requests_large_buttons(lowered: str) -> bool:
    return bool(
        re.search(r"\b(larger|bigger|large)\s+buttons?\b", lowered)
        or re.search(r"\bbuttons?\s+(larger|bigger|large)\b", lowered)
        or re.search(r"\b(make\s+|)(the\s+)?buttons?\s+(larger|bigger)\b", lowered)
        or re.search(r"\bbigger\s+buttons\b", lowered)
        or re.search(r"\bmuch\s+larger\b", lowered)
        or (
            re.search(r"\bsize\b", lowered)
            and re.search(r"\b(increase|big|large|bigger)\b", lowered)
            and re.search(r"\b(buttons?|keys?|digits?|keypad)\b", lowered)
        )
    )


def _user_requests_equation_flow(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(as i type|equation|expression|formula|numbers as|numbers still|typing|typed|typed out|see the flow|=+\s*\d+)\b",
            lowered,
        )
    )


def _file_blob(files: dict[str, str]) -> tuple[str, str, str]:
    app_raw = str(files.get("src/App.tsx") or "")
    styles_raw = str(files.get("src/styles.css") or "")
    app_l = app_raw.lower()
    styles_l = styles_raw.lower()
    all_l = (app_raw + "\n" + styles_raw).lower()
    return app_l, styles_l, all_l


def verify_calculator_builder_artifact(
    user_plain: str,
    *,
    files: dict[str, str],
) -> dict[str, Any]:
    """Return a JSON-serializable verification result for calculator scaffolds only."""
    lowered = _strip_dashboard_tail(user_plain).lower()

    requested: list[str] = []
    passed: list[str] = []
    failed: list[str] = []

    if _user_requests_purple_digit_style(lowered) and not _user_requests_multicolor(lowered):
        requested.append("purple_digit_keys")
    if _user_requests_yellow_border(lowered):
        requested.append("yellow_digit_border")
    if _user_requests_multicolor(lowered):
        requested.append("multicolor_digit_keys")
    if _user_requests_large_buttons(lowered):
        requested.append("large_buttons")
    if _user_requests_equation_flow(lowered):
        requested.append("equation_working_line")

    if not requested:
        return {
            "verified": True,
            "skipped": True,
            "status": "skipped",
            "requested_checks": [],
            "passed_checks": [],
            "failed_checks": [],
            "reason": "",
        }

    app_l, styles_l, _ = _file_blob(files)

    if "purple_digit_keys" in requested:
        ok = "calc-digit-purple-keys" in app_l and "calc-digit-light-blue" not in app_l
        (passed if ok else failed).append("purple_digit_keys")

    if "yellow_digit_border" in requested:
        ok = "calc-yellow-digit-border" in app_l and (
            ".calc-yellow-digit-border" in styles_l or "#facc15" in styles_l
        )
        (passed if ok else failed).append("yellow_digit_border")

    if "multicolor_digit_keys" in requested:
        ok = "calc-digit-multicolor-keys" in app_l and ".calc-digit-multicolor-keys" in styles_l
        (passed if ok else failed).append("multicolor_digit_keys")

    if "large_buttons" in requested:
        ok = "min-height: 3.55rem" in styles_l or "min-height:3.55rem" in styles_l.replace(" ", "")
        (passed if ok else failed).append("large_buttons")

    if "equation_working_line" in requested:
        ok = "equation-working" in app_l
        (passed if ok else failed).append("equation_working_line")

    verified = len(failed) == 0
    reason = ""
    if not verified:
        if "yellow_digit_border" in failed:
            reason = "missing yellow border styling on digit keys"
        elif "purple_digit_keys" in failed:
            reason = "missing purple digit styling or light-blue class still present"
        elif "multicolor_digit_keys" in failed:
            reason = "missing multicolor digit styling"
        elif "large_buttons" in failed:
            reason = "missing larger button spacing"
        elif "equation_working_line" in failed:
            reason = "missing live equation / working line"
        else:
            reason = "artifact did not satisfy requested checks"

    return {
        "verified": verified,
        "skipped": False,
        "status": "ok" if verified else "failed",
        "requested_checks": requested,
        "passed_checks": passed,
        "failed_checks": failed,
        "reason": reason,
    }


def verify_builder_scaffold_artifact(
    user_plain: str,
    scaffold_meta: dict[str, Any],
    files: dict[str, str],
    operation: str,
) -> dict[str, Any]:
    template = str(scaffold_meta.get("template") or "").strip().lower()
    if template != "calculator":
        return {
            "verified": True,
            "skipped": True,
            "status": "skipped",
            "requested_checks": [],
            "passed_checks": [],
            "failed_checks": [],
            "reason": "",
        }
    return verify_calculator_builder_artifact(user_plain, files=files)
