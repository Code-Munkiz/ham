from __future__ import annotations

from src.bridge.browser_policy import validate_browser_intent
from src.bridge.contracts import BrowserIntent, BrowserPolicySpec, BrowserStepSpec


def _intent() -> BrowserIntent:
    return BrowserIntent(
        intent_id="intent-browser-1",
        request_id="request-browser-1",
        run_id="run-browser-1",
        steps=[
            BrowserStepSpec(
                step_id="s1",
                action="navigate",
                args={"url": "https://docs.example.com"},
            ),
            BrowserStepSpec(
                step_id="s2",
                action="extract_text",
                args={"selector": "main"},
            ),
        ],
        policy=BrowserPolicySpec(
            max_steps=5,
            step_timeout_ms=5_000,
            max_dom_chars=4_000,
            max_console_chars=2_000,
            max_network_events=100,
            allowed_domains=["example.com"],
            allow_file_download=False,
            allow_form_submit=False,
        ),
        reason="browser policy test",
    )


def test_accept_valid_browser_intent():
    decision = validate_browser_intent(_intent())
    assert decision.accepted is True
    assert decision.reasons == []


def test_reject_domain_outside_allowlist():
    intent = _intent()
    intent.steps[0].args["url"] = "https://other.com/page"
    decision = validate_browser_intent(intent)
    assert decision.accepted is False
    assert any("outside allowed_domains" in r for r in decision.reasons)


def test_reject_too_many_steps():
    intent = _intent()
    intent.policy.max_steps = 1
    decision = validate_browser_intent(intent)
    assert decision.accepted is False
    assert any("more browser steps" in r for r in decision.reasons)


def test_reject_download_when_forbidden():
    intent = _intent()
    intent.steps = list(intent.steps) + [
        BrowserStepSpec(
            step_id="s3",
            action="screenshot",
            args={"download": True},
        )
    ]
    decision = validate_browser_intent(intent)
    assert decision.accepted is False
    assert any("file download" in r.lower() for r in decision.reasons)


def test_reject_form_submit_when_forbidden():
    intent = _intent()
    intent.steps = list(intent.steps) + [
        BrowserStepSpec(
            step_id="s3",
            action="fill",
            args={"selector": "#email", "value": "a@b.com", "submit": True},
        )
    ]
    decision = validate_browser_intent(intent)
    assert decision.accepted is False
    assert any("form submission" in r.lower() for r in decision.reasons)
