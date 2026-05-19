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


def _targets_specific_control_key_styling(lowered: str) -> bool:
    """True when the user targets a specific operator/control key, not digit styling broadly."""
    return bool(
        re.search(
            r"(?i)\b("
            r"ac|all[- ]clear|c\.?a\.?|clear\s+all|ce\b|clear\s+entry|equals?\b|equal\s+button|"
            r"pause|mute|start|stop|reset|backspace|sign|plus\s+button|minus\s+button|"
            r"times\s+button|divide\s+button|multiply\s+button|percent\s+button"
            r")\b",
            lowered,
        )
        or re.search(r"(?i)\+\s+and\s+-\s+|[-+*/]\s+button", lowered)
    )


def _user_requests_purple_digit_style(lowered: str) -> bool:
    if not re.search(r"\b(purple|violet|lavender)\b", lowered):
        return False
    if not _keypad_context(lowered) and not re.search(r"\b(calculator|calc)\b", lowered):
        return False
    if _targets_specific_control_key_styling(lowered):
        return False
    return True


def _user_requests_light_blue_digits(lowered: str) -> bool:
    """Digit/calculator palette shift toward blue (scaffold-verified when not purple/multicolor)."""
    explicit = bool(re.search(r"\b(light\s+blue|light-blue)\b", lowered))
    generic_blue = bool(re.search(r"\bblue\b", lowered)) and not re.search(
        r"\b(purple|violet|lavender|multicolor|rainbow)\b",
        lowered,
    )
    if not explicit and not generic_blue:
        return False
    if _targets_specific_control_key_styling(lowered):
        return False
    return bool(_keypad_context(lowered) or re.search(r"\b(calculator|calc)\b", lowered))


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


def list_calculator_scaffold_verification_checks(user_plain: str) -> list[str]:
    """Requested deterministic verifier checks for calculator scaffolds (same rules as verify_calculator_builder_artifact)."""
    lowered = _strip_dashboard_tail(user_plain).lower()
    requested: list[str] = []
    if _user_requests_purple_digit_style(lowered) and not _user_requests_multicolor(lowered):
        requested.append("purple_digit_keys")
    elif _user_requests_light_blue_digits(lowered) and not _user_requests_purple_digit_style(lowered):
        requested.append("light_blue_digit_keys")
    if _user_requests_yellow_border(lowered):
        requested.append("yellow_digit_border")
    if _user_requests_multicolor(lowered):
        requested.append("multicolor_digit_keys")
    if _user_requests_large_buttons(lowered):
        requested.append("large_buttons")
    if _user_requests_equation_flow(lowered):
        requested.append("equation_working_line")
    return requested


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
    requested = list_calculator_scaffold_verification_checks(user_plain)
    passed: list[str] = []
    failed: list[str] = []

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

    if "light_blue_digit_keys" in requested:
        ok = "calc-digit-light-blue" in app_l
        (passed if ok else failed).append("light_blue_digit_keys")

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
        elif "light_blue_digit_keys" in failed:
            reason = "missing light-blue digit styling"
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
    # Honest-failure gate: a placeholder fallback (set by
    # _build_react_scaffold_files when no calculator/tetris match AND the
    # LLM-scaffold attempt also did not replace the files) must not be
    # rubber-stamped as a successful scaffold. The chat-stream uses this
    # result to suppress the "I've generated the project files" message and
    # surface an honest "I can't generate that yet" response to the user.
    if bool(scaffold_meta.get("placeholder_fallback")) and operation == "build_or_create":
        return {
            "verified": False,
            "skipped": False,
            "status": "failed",
            "requested_checks": ["non_placeholder_initial_scaffold"],
            "passed_checks": [],
            "failed_checks": ["non_placeholder_initial_scaffold"],
            "reason": (
                "Initial scaffold for arbitrary apps requires an OpenRouter API key "
                "(BYO via Settings) so HAM can generate real source. Without one, the "
                "only built-in initial templates are 'calculator' and 'tetris'. Either "
                "configure a key, ask for one of those templates, or describe an edit "
                "to an existing project."
            ),
        }

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
