"""Tests for the ``claude_agent`` coding-router provider.

These tests lock that:

- The provider is disabled by default (Mission 2 unchanged from Mission 1).
- When enabled, readiness presence + auth detection is delegated to the
  existing worker-adapter (mocked here so tests do not require the
  ``claude-agent-sdk`` package or any real Anthropic credentials).
- Blocker / reason / operator-signal strings are normie-safe (no env names,
  secret values, URLs, or internal workflow ids).
- The provider is registered in the harness-capability registry as an
  implemented launchable provider AND is part of the ``ControlPlaneProvider``
  enum (Mission 2 promotion).
- The conductor recommender includes ``claude_agent`` as a candidate for
  ``single_file_edit`` task kinds when readiness reports it available.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any
from unittest.mock import patch

import pytest

from src.ham.coding_router.classify import classify_task
from src.ham.coding_router.claude_agent_provider import (
    _BLOCKER_DISABLED,
    _BLOCKER_NOT_CONFIGURED,
    _BLOCKER_SDK_MISSING,
    build_claude_agent_readiness,
    launch_claude_agent_coding,
)
from src.ham.coding_router.readiness import collate_readiness
from src.ham.coding_router.recommend import recommend
from src.ham.harness_capabilities import (
    HARNESS_CAPABILITIES,
    is_provider_launchable,
)
from src.persistence.control_plane_run import ControlPlaneProvider

_FAKE_READINESS_PATH = "src.ham.coding_router.claude_agent_provider.check_claude_agent_readiness"
_FAKE_COARSE_PATH = "src.ham.coding_router.claude_agent_provider.claude_agent_coarse_provider"


class _FakeWorkerReadiness:
    def __init__(self, *, sdk_available: bool, authenticated: bool) -> None:
        self.sdk_available = sdk_available
        self.authenticated = authenticated


@pytest.fixture(autouse=True)
def _isolate_claude_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the env that affects this provider so each test starts clean."""
    for name in (
        "CLAUDE_AGENT_ENABLED",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "GCLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_readiness_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_AGENT_ENABLED", raising=False)
    pr = build_claude_agent_readiness(actor=None, include_operator_details=False)
    assert pr.provider == "claude_agent"
    assert pr.available is False
    assert pr.blockers == (_BLOCKER_DISABLED,)
    assert pr.operator_signals == ()


def test_readiness_not_configured_when_enabled_but_no_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    with patch(
        _FAKE_READINESS_PATH,
        return_value=_FakeWorkerReadiness(sdk_available=False, authenticated=False),
    ):
        pr = build_claude_agent_readiness(actor=None, include_operator_details=False)
    assert pr.available is False
    assert pr.blockers == (_BLOCKER_SDK_MISSING,)


def test_readiness_not_configured_when_enabled_and_sdk_but_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    with patch(
        _FAKE_READINESS_PATH,
        return_value=_FakeWorkerReadiness(sdk_available=True, authenticated=False),
    ):
        pr = build_claude_agent_readiness(actor=None, include_operator_details=False)
    assert pr.available is False
    assert pr.blockers == (_BLOCKER_NOT_CONFIGURED,)


def test_readiness_configured_when_enabled_sdk_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    with (
        patch(
            _FAKE_READINESS_PATH,
            return_value=_FakeWorkerReadiness(sdk_available=True, authenticated=True),
        ),
        patch(_FAKE_COARSE_PATH, return_value="anthropic_direct"),
        patch(
            "src.ham.coding_router.claude_agent_provider.claude_agent_mission_auth_configured",
            return_value=True,
        ),
    ):
        pr = build_claude_agent_readiness(actor=None, include_operator_details=False)
    assert pr.available is True
    assert pr.blockers == ()


def test_readiness_does_not_leak_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-agent-test-canary-not-a-real-key")
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    with (
        patch(
            _FAKE_READINESS_PATH,
            return_value=_FakeWorkerReadiness(sdk_available=True, authenticated=True),
        ),
        patch(_FAKE_COARSE_PATH, return_value="anthropic_direct"),
    ):
        pr = build_claude_agent_readiness(actor=None, include_operator_details=True)
    rendered = json.dumps(dataclasses.asdict(pr))
    assert "claude-agent-test-canary-not-a-real-key" not in rendered
    assert "ANTHROPIC_API_KEY" not in rendered
    assert "CLAUDE_AGENT_ENABLED" not in rendered


def test_disabled_provider_returns_disabled_status() -> None:
    result = launch_claude_agent_coding(project_id="proj-1", user_prompt="do anything")
    assert result.status == "disabled"
    assert isinstance(result.reason, str) and result.reason
    # claude_agent is now an implemented provider; launchability is gated by
    # env, not by the registry shape.
    assert is_provider_launchable("claude_agent") is True


def test_claude_agent_in_harness_capabilities_registry() -> None:
    assert "claude_agent" in HARNESS_CAPABILITIES
    row = HARNESS_CAPABILITIES["claude_agent"]
    assert row.implemented is True
    assert row.registry_status == "implemented"
    assert row.audit_sink is not None
    assert "claude_agent" in {p.value for p in ControlPlaneProvider}


def test_claude_agent_status_appears_in_coding_readiness_collator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_AGENT_ENABLED", raising=False)
    snap = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    entries = [p for p in snap.providers if p.provider == "claude_agent"]
    assert len(entries) == 1
    assert entries[0].available is False


def test_claude_agent_recommended_for_single_file_edit_when_launchable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When readiness reports claude_agent as available, the recommender
    must include it as a viable candidate for ``single_file_edit`` task
    kinds. We mock readiness so the test never touches the real Anthropic
    SDK or environment.
    """
    monkeypatch.setenv("CLAUDE_AGENT_ENABLED", "1")
    with (
        patch(
            _FAKE_READINESS_PATH,
            return_value=_FakeWorkerReadiness(sdk_available=True, authenticated=True),
        ),
        patch(_FAKE_COARSE_PATH, return_value="anthropic_direct"),
        patch(
            "src.ham.coding_router.claude_agent_provider.claude_agent_mission_auth_configured",
            return_value=True,
        ),
    ):
        snap = collate_readiness(actor=None, project_id=None, include_operator_details=False)
    task = classify_task("Tweak this file's import order.")
    assert task.kind == "single_file_edit"
    candidates = recommend(task, snap)
    claude_agent_candidates = [c for c in candidates if c.provider == "claude_agent"]
    assert len(claude_agent_candidates) == 1
    ca = claude_agent_candidates[0]
    # When readiness mocks claude_agent as ready and the project flags do
    # not block it, the candidate must be approve-able.
    assert ca.blockers == ()
    # Confidence for single_file_edit must be high enough to land in the
    # candidate list (recommender table sets >= 0.5 for this cell).
    assert ca.confidence >= 0.5


def test_claude_agent_blocker_strings_are_normie_safe() -> None:
    forbidden: tuple[str, ...] = (
        "CLAUDE_AGENT_ENABLED",
        "ANTHROPIC_API_KEY",
        "HAM_",
        "https://",
        "http://",
        "safe_edit_low",
    )
    for blocker in (_BLOCKER_DISABLED, _BLOCKER_SDK_MISSING, _BLOCKER_NOT_CONFIGURED):
        for token in forbidden:
            assert token not in blocker, f"blocker leaks {token!r}: {blocker!r}"


def _asdict_for_blob(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return value
