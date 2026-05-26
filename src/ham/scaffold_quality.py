"""Lightweight static inspection and one-pass repair for LLM scaffold playability."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from src.ham.builder_plan import Plan

_LOG = logging.getLogger(__name__)

# Primary gameplay dispatch types that must not be no-ops when declared.
_PRIMARY_GAMEPLAY_ACTIONS = frozenset(
    {
        "PLAY_CARD",
        "DRAW_CARD",
        "END_TURN",
        "ALLOCATE",
        "SUBMIT_WORD",
        "START_TIMER",
        "TICK",
        "FLIP_CARD",
        "DRAW",
        "PLAY",
        "MATCH",
        "END_GAME",
        "NEXT_DAY",
        "END_TURN",
        "USE_HINT",
    }
)

_STUB_PLACEHOLDER = re.compile(
    r"//\s*(?:Logic to|TODO|FIXME|Implement(?:ation)?|placeholder|future[-\s]work|not implemented)",
    re.IGNORECASE,
)

_CASE_BLOCK = re.compile(
    r"case\s+['\"]([^'\"]+)['\"]\s*:\s*(.*?)(?=\bcase\s+['\"]|\bdefault\s*:)",
    re.DOTALL,
)

_NOOP_RETURN = re.compile(
    r"return\s+(?:state|\{\s*\.\.\.state\s*\})\s*;?\s*$",
    re.MULTILINE,
)

_DISPATCH_TYPE = re.compile(
    r"dispatch\s*\(\s*\{\s*type:\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_SWITCH_ON_ACTION = re.compile(r"switch\s*\(\s*action\.type\s*\)")

_LOG_ONLY_HANDLER = re.compile(
    r"(?:const|function)\s+(?:handle\w+|on\w+|play\w+|draw\w+|submit\w+|endTurn)\w*\s*=\s*"
    r"(?:\([^)]*\)\s*)?=>\s*\{\s*console\.log",
    re.IGNORECASE,
)

_EMPTY_HANDLER = re.compile(
    r"(?:onClick|onChange|onSubmit)=\{\s*(?:\(\)\s*)?=>\s*\{\s*\}\s*\}",
    re.IGNORECASE,
)

_STALE_HP_WIN_CHECK = re.compile(
    r"set(?:Enemy|Player)?Hp\s*\("
    r"(?:(?!;).){0,400}?"
    r"if\s*\(\s*(?:enemyHp|playerHp|health)\s*<=",
    re.IGNORECASE | re.DOTALL,
)

_STALE_NAMED_WIN_FN = re.compile(
    r"(?:function|const)\s+(?:checkWin\w*|check\w*Condition)\s*=\s*"
    r"(?:\([^)]*\)\s*)=>\s*\{[^}]*if\s*\(\s*(?:enemyHp|playerHp|health)\s*<=",
    re.IGNORECASE | re.DOTALL,
)

_NAMED_IMPORT = re.compile(
    r"import\s+\{\s*(\w+)\s*\}\s+from\s+['\"](\.[^'\"]+)['\"]"
)
_DEFAULT_EXPORT = re.compile(r"export\s+default\s+(\w+)")

_PROMPT_60_SECONDS = re.compile(
    r"60[\s-]?second|60s\b|after\s+60\b",
    re.IGNORECASE,
)

_EXPLICIT_60_DURATION = re.compile(
    r"useState\s*\(\s*60\s*\)"
    r"|\b(?:ROUND|GAME|TIMER|COUNTDOWN|DURATION|TIME_LIMIT|MAX_TIME|initial(?:Time|Seconds)|secondsLeft|timeLeft)\w*\s*=\s*60\b"
    r"|\b60000\b"
    r"|60\s*\*\s*1000"
    r"|(?:elapsedSeconds|elapsedTime|secondsLeft|timeLeft|timer|countdown)\w*\s*(?:<|<=|>|>=|===|==)\s*60\b",
    re.IGNORECASE,
)

_PROMPT_RESULT_REQUIRED = re.compile(
    r"\bwins?\b|\bvict(?:ory|orious)\b|\bsurvive\b|health to zero|reducing.*health|"
    r"final score|win state|game over|running out of",
    re.IGNORECASE,
)

_RESULT_STATE_MARKERS = re.compile(
    r"\b(?:gameWon|gameLost|isFinished|gameOver|hasWon|hasLost|showResult|resultScreen)\b"
    r"|set(?:Result|GameOver|Win|Victory|Status)\s*\("
    r"|['\"](?:win|won|lose|lost|victory)['\"]"
    r"|type:\s*['\"](?:WIN|LOSE|VICTORY|GAME_OVER)['\"]"
    r"|enemyHp\s*<=\s*0|enemyHp\s*===?\s*0"
    r"|VictoryScreen|ResultsPanel|GameOver|GoalStatus",
    re.IGNORECASE,
)

_JS_SOURCE_SUFFIXES = (".tsx", ".ts", ".jsx", ".js")


@dataclass(frozen=True)
class ScaffoldQualityIssue:
    """One playability problem detected in generated scaffold source."""

    code: str
    message: str
    path: str | None = None
    detail: str | None = None


def _file_map(file_changes: list[tuple[str, str]]) -> dict[str, str]:
    return {path: content for path, content in file_changes}


def _resolve_import_path(from_path: str, import_rel: str) -> str:
    """Resolve a relative import to a repo-style path (best effort)."""
    base = from_path.rsplit("/", 1)[0] if "/" in from_path else ""
    parts: list[str] = []
    if base:
        parts.extend(base.split("/"))
    for segment in import_rel.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if parts:
                parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts)


def _inspect_reducer_noops(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if "reducer" not in content.lower() and "usereducer" not in content.lower():
        return issues
    for match in _CASE_BLOCK.finditer(content):
        action = match.group(1).strip()
        body = match.group(2)
        if action == "default":
            continue
        action_upper = action.upper()
        is_primary = action_upper in _PRIMARY_GAMEPLAY_ACTIONS or (
            action_upper.replace("-", "_") in _PRIMARY_GAMEPLAY_ACTIONS
        )
        has_stub = bool(_STUB_PLACEHOLDER.search(body))
        has_noop = bool(_NOOP_RETURN.search(body.strip()))
        if has_stub or (has_noop and (is_primary or action_upper == action)):
            issues.append(
                ScaffoldQualityIssue(
                    code="noop_reducer_action",
                    message=f"Reducer action '{action}' is a stub or no-op",
                    path=path,
                    detail=body.strip()[:240],
                )
            )
    return issues


def _inspect_stub_comments(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if not _STUB_PLACEHOLDER.search(content):
        return issues
    if "reducer" in content.lower() or "dispatch" in content.lower():
        for match in _STUB_PLACEHOLDER.finditer(content):
            issues.append(
                ScaffoldQualityIssue(
                    code="stub_placeholder",
                    message="Core gameplay path contains TODO/stub placeholder comment",
                    path=path,
                    detail=match.group(0),
                )
            )
            break
    return issues


def _collect_reducer_actions(file_changes: list[tuple[str, str]]) -> dict[str, str]:
    """Map reducer action type -> case body across all files."""
    actions: dict[str, str] = {}
    for _path, content in file_changes:
        if not _SWITCH_ON_ACTION.search(content):
            continue
        for match in _CASE_BLOCK.finditer(content):
            action = match.group(1).strip()
            if action != "default":
                actions[action] = match.group(2)
    return actions


def _collect_dispatch_types(file_changes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return (action_type, path) for each dispatch call."""
    found: list[tuple[str, str]] = []
    for path, content in file_changes:
        for match in _DISPATCH_TYPE.finditer(content):
            found.append((match.group(1).strip(), path))
    return found


def _is_noop_case_body(body: str, action: str) -> bool:
    action_upper = action.upper()
    is_primary = action_upper in _PRIMARY_GAMEPLAY_ACTIONS
    has_stub = bool(_STUB_PLACEHOLDER.search(body))
    has_noop = bool(_NOOP_RETURN.search(body.strip()))
    return has_stub or (has_noop and is_primary)


def _inspect_dispatch_reducer_mismatch(
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    reducer_actions = _collect_reducer_actions(file_changes)
    if not reducer_actions:
        return []
    issues: list[ScaffoldQualityIssue] = []
    for action, path in _collect_dispatch_types(file_changes):
        action_upper = action.upper()
        if action_upper not in _PRIMARY_GAMEPLAY_ACTIONS:
            continue
        body = reducer_actions.get(action)
        if body is None:
            issues.append(
                ScaffoldQualityIssue(
                    code="dispatch_reducer_mismatch",
                    message=f"dispatch type '{action}' has no matching reducer case",
                    path=path,
                )
            )
        elif _is_noop_case_body(body, action):
            issues.append(
                ScaffoldQualityIssue(
                    code="dispatch_reducer_mismatch",
                    message=f"dispatch type '{action}' maps to a no-op reducer case",
                    path=path,
                )
            )
    return issues


def _inspect_empty_or_log_handlers(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if _LOG_ONLY_HANDLER.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="empty_primary_handler",
                message="Primary handler only logs and does not mutate game state",
                path=path,
            )
        )
    if _EMPTY_HANDLER.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="empty_primary_handler",
                message="Primary UI handler is empty",
                path=path,
            )
        )
    return issues


def _inspect_stale_state_win_checks(path: str, content: str) -> list[ScaffoldQualityIssue]:
    issues: list[ScaffoldQualityIssue] = []
    if _STALE_HP_WIN_CHECK.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="stale_state_win_check",
                message=(
                    "Win/loss may read stale HP state immediately after setState; "
                    "compute next state before checking result"
                ),
                path=path,
            )
        )
    elif _STALE_NAMED_WIN_FN.search(content):
        issues.append(
            ScaffoldQualityIssue(
                code="stale_state_win_check",
                message=(
                    "checkWin/checkCondition reads HP from closure; "
                    "use computed next HP or functional update result"
                ),
                path=path,
            )
        )
    return issues


def _js_sources(file_changes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(path, content) for path, content in file_changes if path.endswith(_JS_SOURCE_SUFFIXES)]


def _combined_js_source(file_changes: list[tuple[str, str]]) -> str:
    return "\n".join(content for _path, content in _js_sources(file_changes))


def _first_path_matching(content_iter: list[tuple[str, str]], pattern: str) -> str | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for path, content in content_iter:
        if rx.search(content):
            return path
    return None


def _has_explicit_timer_duration(content: str) -> bool:
    return bool(_EXPLICIT_60_DURATION.search(content))


def _prompt_requests_60_seconds(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_60_SECONDS.search(prompt))


def _prompt_requires_result_state(prompt: str | None) -> bool:
    if not prompt:
        return False
    return bool(_PROMPT_RESULT_REQUIRED.search(prompt))


def _inspect_timer_duration(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requests_60_seconds(plan.user_message):
        return []
    sources = _js_sources(file_changes)
    combined = _combined_js_source(file_changes)
    if not re.search(r"timer|countdown|seconds|elapsed|timeLeft|secondsLeft", combined, re.I):
        return []
    if _has_explicit_timer_duration(combined):
        return []
    path = _first_path_matching(sources, r"timer|countdown|seconds|elapsed|timeLeft|secondsLeft")
    return [
        ScaffoldQualityIssue(
            code="timer_duration_mismatch",
            message=(
                "Prompt requests a 60-second round but code lacks explicit "
                "60/60000 duration constant or countdown init"
            ),
            path=path,
        )
    ]


def _inspect_missing_result_state(
    plan: Plan | None,
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    if plan is None or not _prompt_requires_result_state(plan.user_message):
        return []
    combined = _combined_js_source(file_changes)
    if _RESULT_STATE_MARKERS.search(combined):
        return []
    path = _first_path_matching(
        _js_sources(file_changes),
        r"App\.|Game\.|enemyHp|playerHp|health",
    )
    if path is None:
        js_sources = _js_sources(file_changes)
        path = js_sources[0][0] if js_sources else None
    return [
        ScaffoldQualityIssue(
            code="missing_result_state",
            message=(
                "Prompt requires win/loss/final result but code lacks visible "
                "result or completion state handling"
            ),
            path=path,
        )
    ]


def _inspect_import_export(
    file_changes: list[tuple[str, str]],
) -> list[ScaffoldQualityIssue]:
    files = _file_map(file_changes)
    default_exports: dict[str, str] = {}
    for path, content in files.items():
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        m = _DEFAULT_EXPORT.search(content)
        if m:
            default_exports[path] = m.group(1)

    issues: list[ScaffoldQualityIssue] = []
    for path, content in files.items():
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        for m in _NAMED_IMPORT.finditer(content):
            name, rel = m.group(1), m.group(2)
            target = _resolve_import_path(path, rel)
            target_base = target.rsplit("/", 1)[-1]
            for candidate, exported in default_exports.items():
                cand_base = candidate.rsplit("/", 1)[-1].replace(".tsx", "").replace(".ts", "")
                if exported == name and (
                    candidate == target
                    or candidate.endswith(f"/{target_base}.tsx")
                    or candidate.endswith(f"/{target_base}.ts")
                    or cand_base == target_base
                ):
                    issues.append(
                        ScaffoldQualityIssue(
                            code="import_export_mismatch",
                            message=(
                                f"Named import {{{name}}} from '{rel}' but "
                                f"{candidate} default-exports {exported}"
                            ),
                            path=path,
                        )
                    )
                    break
    return issues


def inspect_generated_scaffold_quality(
    file_changes: list[tuple[str, str]],
    *,
    plan: Plan | None = None,
) -> list[ScaffoldQualityIssue]:
    """Return playability issues found in generated scaffold files."""
    issues: list[ScaffoldQualityIssue] = []
    for path, content in file_changes:
        if not path.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        issues.extend(_inspect_reducer_noops(path, content))
        issues.extend(_inspect_stub_comments(path, content))
        issues.extend(_inspect_empty_or_log_handlers(path, content))
        issues.extend(_inspect_stale_state_win_checks(path, content))
    if plan is not None:
        issues.extend(_inspect_timer_duration(plan, file_changes))
        issues.extend(_inspect_missing_result_state(plan, file_changes))
    issues.extend(_inspect_import_export(file_changes))
    issues.extend(_inspect_dispatch_reducer_mismatch(file_changes))
    # De-dupe by (code, path, message)
    seen: set[tuple[str, str | None, str]] = set()
    unique: list[ScaffoldQualityIssue] = []
    for issue in issues:
        key = (issue.code, issue.path, issue.message)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def scaffold_quality_repair_enabled(env: dict[str, str] | None = None) -> bool:
    mapping = env if env is not None else os.environ
    raw = (mapping.get("HAM_SCAFFOLD_QUALITY_REPAIR") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_scaffold_repair_prompt(
    plan: Plan,
    file_changes: list[tuple[str, str]],
    issues: list[ScaffoldQualityIssue],
    *,
    base_system_prompt: str,
) -> list[dict[str, str]]:
    """Build LLM messages for a single focused scaffold repair pass."""
    issue_lines = "\n".join(
        f"- [{i.code}] {i.message}"
        + (f" ({i.path})" if i.path else "")
        + (f": {i.detail}" if i.detail else "")
        for i in issues[:12]
    )
    file_summary = "\n\n".join(
        f"--- {path} ---\n{content[:4000]}"
        for path, content in file_changes[:16]
    )
    repair_system = (
        base_system_prompt
        + "\n\nScaffold repair mode:\n"
        "- Keep the same file paths and architecture when possible.\n"
        "- Do not create a larger empty component shell.\n"
        "- Implement the missing core loop and wire controls to state transitions.\n"
        "- Remove no-op reducer cases; every declared primary action must mutate state meaningfully.\n"
        "- Verify every primary control changes canonical game state (not just logs or local UI text).\n"
        "- Compute next state values first; derive win/loss from those next values, not stale closure reads.\n"
        "- Do not check old HP/resources immediately after setState — use functional updates or local next values.\n"
        "- Avoid stale-state win/loss checks: compute next HP/resources before checking result conditions.\n"
        "- When the prompt specifies a duration (e.g. 60 seconds), use an explicit round constant "
        "(useState(60), ROUND_SECONDS = 60, or 60000 ms) and show a final score when time expires.\n"
        "- When the prompt requires winning/surviving/final score, add visible win/loss/result UI and restart/reset.\n"
        "- Make resource/turn loops strategically meaningful — allocations and day ticks must change resources.\n"
        "- Ensure visible feedback and result/win state where the plan requires them.\n"
        "- Fix import/export consistency (default export ↔ default import).\n"
        "- Output ONLY the same JSON object schema.\n"
    )
    issue_codes = {issue.code for issue in issues}
    if "timer_duration_mismatch" in issue_codes:
        repair_system += (
            "\nTimer repair focus:\n"
            "- Replace elapsed-only counters (e.g. elapsedTime from 0 to >= 59) with a 60-second countdown.\n"
            "- Initialize round duration to 60 seconds (or 60000 ms) and lock input when it reaches zero.\n"
            "- Display final score/WPM/accuracy on expiry.\n"
        )
    if "missing_result_state" in issue_codes:
        repair_system += (
            "\nResult-state repair focus:\n"
            "- Wire victory when enemy HP reaches zero (or survival goal met) into visible result UI.\n"
            "- Include win/loss/completion state and a restart or play-again control.\n"
        )
    user_content = (
        f"User request: {plan.user_message}\n\n"
        f"The previous scaffold failed automated playability checks:\n{issue_lines}\n\n"
        f"Repair the scaffold below. Implement state mutations for primary actions.\n\n"
        f"Previous files:\n{file_summary}"
    )
    return [
        {"role": "system", "content": repair_system},
        {"role": "user", "content": user_content},
    ]


def maybe_repair_generated_scaffold(
    result: Any,
    *,
    plan: Plan,
    api_key: str,
    model: str,
    scaffold_timeout: float,
    base_system_prompt: str,
    parse_result: Any,
    complete_chat: Any,
    env: dict[str, str] | None = None,
) -> Any:
    """Run one repair LLM pass when quality issues are detected; else return as-is."""
    if not scaffold_quality_repair_enabled(env):
        return result
    issues = inspect_generated_scaffold_quality(result.file_changes, plan=plan)
    if not issues:
        return result
    _LOG.info(
        "Scaffold quality: %d issue(s) detected for plan=%s — running one repair pass",
        len(issues),
        plan.plan_id,
    )
    messages = build_scaffold_repair_prompt(
        plan,
        result.file_changes,
        issues,
        base_system_prompt=base_system_prompt,
    )
    try:
        raw = complete_chat(
            messages,
            model_override=model,
            api_key_override=api_key,
            timeout_sec=scaffold_timeout,
        )
        repaired = parse_result(raw)
        remaining = inspect_generated_scaffold_quality(repaired.file_changes, plan=plan)
        if remaining:
            summary = ", ".join(
                f"{issue.code}@{issue.path or '?'}" for issue in remaining[:8]
            )
            _LOG.warning(
                "Scaffold quality: %d issue(s) remain after repair for plan=%s: %s",
                len(remaining),
                plan.plan_id,
                summary,
            )
        else:
            _LOG.info(
                "Scaffold quality repair cleared all detected issues for plan=%s",
                plan.plan_id,
            )
        _LOG.info(
            "Scaffold quality repair produced %d file(s) for plan=%s",
            len(repaired.file_changes),
            plan.plan_id,
        )
        return repaired
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "Scaffold quality repair failed for plan=%s (%s) — keeping original output",
            plan.plan_id,
            exc,
        )
        return result
