from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from src.bridge.contracts import BrowserIntent, BrowserStepSpec, PolicyDecision

POLICY_VERSION = "browser-v0"
MAX_STEPS_CEILING = 100
MAX_STEP_TIMEOUT_MS_CEILING = 120_000
MAX_DOM_CHARS_CEILING = 100_000
MAX_CONSOLE_CHARS_CEILING = 100_000
MAX_NETWORK_EVENTS_CEILING = 10_000
FORBIDDEN_URL_SCHEMES = {"file", "javascript", "data"}


def validate_browser_intent(intent: BrowserIntent, *, repo_root: Path | None = None) -> PolicyDecision:
    reasons: list[str] = []
    _ = (repo_root or Path.cwd()).resolve()

    if not intent.intent_id or not intent.request_id or not intent.run_id:
        reasons.append("Missing required correlation IDs.")

    if intent.policy.max_steps > MAX_STEPS_CEILING:
        reasons.append("policy.max_steps exceeds browser-v0 ceiling.")
    if intent.policy.step_timeout_ms > MAX_STEP_TIMEOUT_MS_CEILING:
        reasons.append("policy.step_timeout_ms exceeds browser-v0 ceiling.")
    if intent.policy.max_dom_chars > MAX_DOM_CHARS_CEILING:
        reasons.append("policy.max_dom_chars exceeds browser-v0 ceiling.")
    if intent.policy.max_console_chars > MAX_CONSOLE_CHARS_CEILING:
        reasons.append("policy.max_console_chars exceeds browser-v0 ceiling.")
    if intent.policy.max_network_events > MAX_NETWORK_EVENTS_CEILING:
        reasons.append("policy.max_network_events exceeds browser-v0 ceiling.")
    if len(intent.steps) > intent.policy.max_steps:
        reasons.append("Intent has more browser steps than allowed by policy.max_steps.")

    if intent.start_url:
        reasons.extend(_url_policy_reasons(intent.start_url, intent.policy.allowed_domains))

    for step in intent.steps:
        reasons.extend(
            _step_policy_reasons(
                step,
                intent.policy.allow_form_submit,
                intent.policy.allowed_domains,
            )
        )
        reasons.extend(_download_policy_reasons(step, intent.policy.allow_file_download))

    accepted = not reasons
    return PolicyDecision(
        accepted=accepted,
        reasons=reasons,
        policy_version=POLICY_VERSION,
    )


def _step_policy_reasons(
    step: BrowserStepSpec,
    allow_form_submit: bool,
    allowed_domains: list[str],
) -> list[str]:
    reasons: list[str] = []
    args = step.args
    if step.timeout_ms is not None and step.timeout_ms > MAX_STEP_TIMEOUT_MS_CEILING:
        reasons.append(f"Step {step.step_id} timeout exceeds browser-v0 ceiling.")

    if step.action == "navigate":
        url = args.get("url")
        if not isinstance(url, str) or not url.strip():
            reasons.append(f"Step {step.step_id} navigate requires a non-empty url.")
        else:
            reasons.extend(_url_policy_reasons(url, allowed_domains))

    submit_flag = args.get("submit")
    if submit_flag is True and not allow_form_submit:
        reasons.append(f"Step {step.step_id} requests form submission but policy forbids it.")

    return reasons


def _download_policy_reasons(step: BrowserStepSpec, allow_file_download: bool) -> list[str]:
    wants_download = step.args.get("download") is True
    if wants_download and not allow_file_download:
        return [f"Step {step.step_id} requests file download but policy forbids it."]
    return []


def _url_policy_reasons(url: str, allowed_domains: list[str]) -> list[str]:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme in FORBIDDEN_URL_SCHEMES:
        return [f"URL scheme '{scheme}' is forbidden in browser-v0."]
    if scheme not in {"http", "https"}:
        return [f"URL scheme '{scheme or '(missing)'}' is not allowed in browser-v0."]
    if allowed_domains and not _domain_allowed(parsed.hostname or "", allowed_domains):
        return [f"URL domain '{parsed.hostname or ''}' is outside allowed_domains."]
    return []


def _domain_allowed(hostname: str, allowed_domains: list[str]) -> bool:
    host = hostname.strip().lower()
    for allowed in allowed_domains:
        allowed_clean = allowed.strip().lower()
        if not allowed_clean:
            continue
        if host == allowed_clean or host.endswith(f".{allowed_clean}"):
            return True
    return False
