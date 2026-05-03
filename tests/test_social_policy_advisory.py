"""Pure-function tests for :mod:`src.ham.social_policy.advisory`.

These tests have **no I/O**: they instantiate :class:`SocialPolicy`
in-memory and check the advisory-reason output. The advisory module is
the only part of D.2 that other surfaces consume, so coverage here is
the contract the API layer relies on.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_policy.advisory import (
    ADVISORY_REASON_CODES,
    POLICY_ACTION_NOT_ALLOWED,
    POLICY_DOCUMENT_MISSING,
    POLICY_LIVE_AUTONOMY_NOT_ARMED,
    POLICY_POSTING_MODE_OFF,
    POLICY_PROVIDER_UNMAPPED,
    POLICY_REPLY_MODE_OFF,
    POLICY_TARGET_LABEL_DISABLED,
    policy_advisory_reasons_for_apply,
    policy_advisory_reasons_for_lane,
    policy_for_provider,
    policy_revision_summary,
)
from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    ChannelTarget,
    ProviderPolicy,
    SocialPolicy,
)


def _policy_with_provider(provider: ProviderPolicy, **policy_overrides: Any) -> SocialPolicy:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["providers"][provider.provider_id] = provider.model_dump(mode="json")
    raw.update(policy_overrides)
    return SocialPolicy.model_validate(raw)


# ---------------------------------------------------------------------------
# Lane reasons
# ---------------------------------------------------------------------------


def test_default_policy_lane_reasons_are_empty() -> None:
    # Default has posting_mode='off' and reply_mode='off' for every provider,
    # so the lane reads correctly surface the lane-mode flags.
    pol = DEFAULT_SOCIAL_POLICY
    assert policy_advisory_reasons_for_lane(pol, provider_id="x", lane="broadcast") == [
        POLICY_POSTING_MODE_OFF,
    ]
    assert policy_advisory_reasons_for_lane(pol, provider_id="x", lane="reactive") == [
        POLICY_REPLY_MODE_OFF,
    ]


def test_permissive_policy_emits_no_lane_reasons() -> None:
    provider = ProviderPolicy(
        provider_id="x",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["post", "reply"],
        targets=[ChannelTarget(label="home_channel", enabled=True)],
    )
    pol = _policy_with_provider(provider)
    assert policy_advisory_reasons_for_lane(pol, provider_id="x", lane="broadcast") == []
    assert policy_advisory_reasons_for_lane(pol, provider_id="x", lane="reactive") == []


def test_lane_reads_never_emit_live_autonomy_not_armed() -> None:
    provider = ProviderPolicy(
        provider_id="x",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["post"],
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_lane(pol, provider_id="x", lane="broadcast")
    assert POLICY_LIVE_AUTONOMY_NOT_ARMED not in out


def test_target_label_disabled_emitted_when_target_missing() -> None:
    provider = ProviderPolicy(
        provider_id="telegram",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["post"],
        targets=[],  # nothing enabled
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_lane(
        pol, provider_id="telegram", lane="broadcast", target_label="home_channel"
    )
    assert out == [POLICY_TARGET_LABEL_DISABLED]


def test_target_label_disabled_emitted_when_target_explicitly_disabled() -> None:
    provider = ProviderPolicy(
        provider_id="telegram",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["post"],
        targets=[ChannelTarget(label="home_channel", enabled=False)],
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_lane(
        pol, provider_id="telegram", lane="broadcast", target_label="home_channel"
    )
    assert out == [POLICY_TARGET_LABEL_DISABLED]


def test_target_label_disabled_not_emitted_when_target_label_is_none() -> None:
    provider = ProviderPolicy(
        provider_id="telegram",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["post"],
        targets=[],
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_lane(pol, provider_id="telegram", lane="broadcast")
    assert POLICY_TARGET_LABEL_DISABLED not in out


# ---------------------------------------------------------------------------
# Apply reasons
# ---------------------------------------------------------------------------


def test_apply_reasons_default_policy_emits_action_not_allowed_and_not_armed() -> None:
    pol = DEFAULT_SOCIAL_POLICY  # autopilot_mode="off", live_autonomy_armed=False
    out = policy_advisory_reasons_for_apply(pol, provider_id="x", action="post")
    # Default has posting_mode='off' and empty posting_actions_allowed, and
    # autopilot is not armed.
    assert POLICY_POSTING_MODE_OFF in out
    assert POLICY_ACTION_NOT_ALLOWED in out
    assert POLICY_LIVE_AUTONOMY_NOT_ARMED in out


def test_apply_reasons_armed_permissive_policy_is_empty() -> None:
    provider = ProviderPolicy(
        provider_id="x",
        posting_mode="autopilot",
        reply_mode="autopilot",
        posting_actions_allowed=["post", "reply", "quote"],
        targets=[ChannelTarget(label="home_channel", enabled=True)],
    )
    pol = _policy_with_provider(
        provider,
        autopilot_mode="armed",
        live_autonomy_armed=True,
    )
    assert policy_advisory_reasons_for_apply(
        pol, provider_id="x", action="post", target_label="home_channel"
    ) == []


def test_apply_reasons_action_not_in_allowed_list() -> None:
    provider = ProviderPolicy(
        provider_id="x",
        posting_mode="approval_required",
        reply_mode="approval_required",
        posting_actions_allowed=["reply"],  # only reply allowed
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_apply(pol, provider_id="x", action="post")
    assert POLICY_ACTION_NOT_ALLOWED in out


def test_apply_reasons_for_reply_only_consults_reply_mode() -> None:
    provider = ProviderPolicy(
        provider_id="telegram",
        posting_mode="off",
        reply_mode="approval_required",
        posting_actions_allowed=["reply"],
    )
    pol = _policy_with_provider(provider, autopilot_mode="armed", live_autonomy_armed=True)
    out = policy_advisory_reasons_for_apply(pol, provider_id="telegram", action="reply")
    # posting_mode is off but action is reply -> posting_mode_off must NOT
    # appear; reply_mode is permissive so reply_mode_off must NOT appear.
    assert POLICY_POSTING_MODE_OFF not in out
    assert POLICY_REPLY_MODE_OFF not in out
    assert POLICY_LIVE_AUTONOMY_NOT_ARMED not in out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_none_policy_emits_document_missing_for_lane_and_apply() -> None:
    assert policy_advisory_reasons_for_lane(None, provider_id="x", lane="broadcast") == [
        POLICY_DOCUMENT_MISSING,
    ]
    assert policy_advisory_reasons_for_apply(None, provider_id="x", action="post") == [
        POLICY_DOCUMENT_MISSING,
    ]


def test_provider_unmapped_emitted_when_provider_absent() -> None:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    # Drop the discord provider entry to simulate an unmapped provider.
    raw["providers"].pop("discord", None)
    pol = SocialPolicy.model_validate(raw)
    assert policy_advisory_reasons_for_lane(pol, provider_id="discord", lane="reactive") == [
        POLICY_PROVIDER_UNMAPPED,
    ]
    assert policy_advisory_reasons_for_apply(pol, provider_id="discord", action="reply") == [
        POLICY_PROVIDER_UNMAPPED,
    ]


def test_policy_for_provider_returns_none_when_missing() -> None:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["providers"].pop("discord", None)
    pol = SocialPolicy.model_validate(raw)
    assert policy_for_provider(pol, "discord") is None
    assert policy_for_provider(None, "x") is None


def test_returned_lists_are_sorted_unique_and_contain_only_policy_codes() -> None:
    # Build a worst-case provider that triggers multiple flags; verify the
    # output is a sorted set of the allowed reason codes.
    provider = ProviderPolicy(
        provider_id="x",
        posting_mode="off",
        reply_mode="off",
        posting_actions_allowed=[],
        targets=[ChannelTarget(label="home_channel", enabled=False)],
    )
    pol = _policy_with_provider(provider)
    out = policy_advisory_reasons_for_apply(
        pol, provider_id="x", action="post", target_label="home_channel"
    )
    # Sorted + unique.
    assert out == sorted(set(out))
    # Every emitted code must be a known advisory code.
    for code in out:
        assert code in ADVISORY_REASON_CODES
        assert code.startswith("policy_")


def test_revision_summary_shapes_are_stable() -> None:
    assert policy_revision_summary(None) == {
        "autopilot_mode": "off",
        "live_autonomy_armed": False,
        "policy_present": False,
    }
    armed_provider = ProviderPolicy(provider_id="x", posting_actions_allowed=["post"])
    pol = _policy_with_provider(
        armed_provider, autopilot_mode="armed", live_autonomy_armed=True
    )
    summary = policy_revision_summary(pol)
    assert summary == {
        "autopilot_mode": "armed",
        "live_autonomy_armed": True,
        "policy_present": True,
    }


# ---------------------------------------------------------------------------
# Static safety: advisory module imports are bounded
# ---------------------------------------------------------------------------


_ADVISORY_PATH = (
    Path(__file__).resolve().parent.parent / "src" / "ham" / "social_policy" / "advisory.py"
)


def test_advisory_module_does_not_import_runners_transports_or_schedulers() -> None:
    forbidden = (
        "src.ham.social_telegram_send",
        "src.ham.social_telegram_autopilot",
        "src.ham.social_telegram_reactive_runner",
        "src.ham.social_telegram_activity_runner",
        "src.ham.ham_x.goham_live_controller",
        "src.ham.ham_x.goham_reactive_live",
        "src.ham.ham_x.goham_reactive_batch",
        "asyncio",
        "threading",
        "multiprocessing",
        "subprocess",
        "signal",
        "sched",
        "schedule",
        "socket",
        "urllib",
    )
    tree = ast.parse(_ADVISORY_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for needle in forbidden:
                    assert not (
                        alias.name == needle or alias.name.startswith(needle + ".")
                    ), f"advisory.py imports forbidden module {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for needle in forbidden:
                assert not (
                    module == needle or module.startswith(needle + ".")
                ), f"advisory.py imports from forbidden module {module}"


def test_advisory_module_has_no_io_bound_calls() -> None:
    """Walk the AST and assert no open()/Path(...).read*() / requests / etc."""
    forbidden_attr_calls = {
        "open",
        "exec",
        "eval",
        "compile",
    }
    # Pure-function helpers; the module legitimately uses .get on the
    # providers dict, so we check call _shape_ not just method names. Rule:
    # no Call node where the callee resolves to a Name in
    # forbidden_attr_calls.
    tree = ast.parse(_ADVISORY_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_attr_calls:
                pytest.fail(f"advisory.py uses forbidden builtin {func.id}")
            # Allow .get on providers dict; flag heavier IO methods.
            if isinstance(func, ast.Attribute) and func.attr in (
                "read_text",
                "read_bytes",
                "write_text",
                "write_bytes",
                "urlopen",
            ):
                pytest.fail(f"advisory.py uses forbidden IO method {func.attr}")
