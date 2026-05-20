"""AutonomyProfile route-gate tests for Social apply endpoints.

These tests pin the mission inversion: SocialPolicy remains advisory-only,
while a configured AutonomyProfile prepends ``autonomy_*`` blockers ahead of
the legacy apply/readiness reason arrays.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.api.social as social_api
from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_telegram_send import TelegramSendResult

client = TestClient(app)

_LIVE_TOKEN = "social-live-token-for-autonomy-gate"  # noqa: S105
_DIGEST = "a" * 64
_PERSONA_DIGEST = "b" * 64


@dataclass(frozen=True)
class ApplyRouteCase:
    name: str
    route: str
    body: dict[str, Any]
    channel: str
    action: str


_ROUTE_CASES: tuple[ApplyRouteCase, ...] = (
    ApplyRouteCase(
        name="reactive_reply",
        route="/api/social/providers/x/reactive/reply/apply",
        body={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND ONE LIVE REPLY"},
        channel="x",
        action="reply",
    ),
    ApplyRouteCase(
        name="reactive_batch",
        route="/api/social/providers/x/reactive/batch/apply",
        body={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND LIVE REACTIVE BATCH"},
        channel="x",
        action="reply",
    ),
    ApplyRouteCase(
        name="broadcast",
        route="/api/social/providers/x/broadcast/apply",
        body={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND ONE LIVE POST"},
        channel="x",
        action="broadcast",
    ),
    ApplyRouteCase(
        name="telegram_reactive",
        route="/api/social/providers/telegram/reactive/replies/apply",
        body={
            "proposal_digest": _DIGEST,
            "confirmation_phrase": "SEND ONE TELEGRAM REPLY",
            "inbound_id": "inbound-1",
        },
        channel="telegram",
        action="reply",
    ),
    ApplyRouteCase(
        name="telegram_activity",
        route="/api/social/providers/telegram/activity/apply",
        body={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND ONE TELEGRAM ACTIVITY"},
        channel="telegram",
        action="activity",
    ),
    ApplyRouteCase(
        name="telegram_message",
        route="/api/social/providers/telegram/messages/apply",
        body={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND ONE TELEGRAM MESSAGE"},
        channel="telegram",
        action="message",
    ),
)


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if (
            name.startswith("HAM_X_")
            or name.startswith("X_")
            or name.startswith("XAI_")
            or name.startswith("TELEGRAM_")
            or name.startswith("HERMES_")
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_POLICY_PATH", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "social_autonomy.json"))
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(tmp_path / "social_delivery.jsonl"))
    monkeypatch.setenv("HAM_HERMES_HOME", str(tmp_path / "hermes-home"))
    _disable_clerk(monkeypatch)
    return tmp_path / "social_autonomy.json"


def _set_live_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _LIVE_TOKEN)


def _headers() -> dict[str, str]:
    return {"X-Ham-Operator-Authorization": f"Bearer {_LIVE_TOKEN}"}


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    stamp = datetime(2026, 5, 20, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "profile_id": "autonomy-gate-profile",
        "status": "running",
        "goal": "Exercise route-level autonomy gates safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["reply", "message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 3, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["no spam", "no credential requests"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": stamp,
        "updated_at": stamp,
    }
    payload.update(overrides)
    return payload


def _write_autonomy_profile(path: Path, **overrides: Any) -> GoHamSocialProfile:
    profile = GoHamSocialProfile.model_validate(_profile_payload(**overrides))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n",
        encoding="utf-8",
    )
    return profile


def _write_social_policy(root: Path) -> None:
    target = root / ".ham" / "social_policy.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "persona": {"persona_id": "ham-canonical", "persona_version": 1},
                "autopilot_mode": "armed",
                "live_autonomy_armed": True,
                "providers": {
                    "x": {"provider_id": "x", "posting_mode": "off", "reply_mode": "off"},
                    "telegram": {
                        "provider_id": "telegram",
                        "posting_mode": "off",
                        "reply_mode": "off",
                    },
                    "discord": {
                        "provider_id": "discord",
                        "posting_mode": "off",
                        "reply_mode": "off",
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _set_x_write_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_API_KEY", "x-api-key-1234567890")
    monkeypatch.setenv("X_API_SECRET", "x-api-secret-1234567890")
    monkeypatch.setenv("X_ACCESS_TOKEN", "x-access-token-1234567890")
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "x-access-token-secret-1234567890")


def _enable_broadcast_apply_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_x_write_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_EXECUTION", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_CONTROLLER", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_LIVE_CONTROLLER", "true")
    monkeypatch.setenv("HAM_X_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_X_DRY_RUN", "false")
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_EXECUTION", "true")
    monkeypatch.setenv("HAM_X_GOHAM_LIVE_MAX_ACTIONS_PER_RUN", "1")
    monkeypatch.setenv("HAM_X_GOHAM_MAX_ACTIONS_PER_RUN", "1")
    monkeypatch.setenv("HAM_X_GOHAM_BLOCK_LINKS", "true")
    monkeypatch.setenv("HAM_X_GOHAM_ALLOWED_ACTIONS", "post")
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "false")


def _persona_fields() -> dict[str, Any]:
    return {
        "persona_id": "ham-canonical",
        "persona_version": 1,
        "persona_digest": _PERSONA_DIGEST,
    }


def _patch_telegram_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    target = social_api.TelegramPreviewTargetDto(kind="test_group", configured=False, masked_id="")
    monkeypatch.setattr(social_api, "_persona_ref_fields", _persona_fields)
    monkeypatch.setattr(
        social_api,
        "_telegram_reactive_replies_preview_response",
        lambda: social_api.TelegramReactiveRepliesPreviewResponse(
            **_persona_fields(),
            status="completed",
            inbound_count=1,
            processed_count=1,
            reply_candidate_count=1,
            items=[
                social_api.TelegramReactiveItemResultDto(
                    inbound_id="inbound-1",
                    inbound_text="hello",
                    author_ref="user:abc",
                    chat_ref="chat:def",
                    session_ref="session:ghi",
                    classification="safe",
                    policy=social_api.TelegramReactivePolicyDecisionDto(
                        allowed=True, classification="safe"
                    ),
                    governor=social_api.TelegramReactiveGovernorDecisionDto(
                        allowed=True,
                        max_reply_candidates=1,
                        reply_candidates_used=0,
                    ),
                    reply_candidate_text="safe reply",
                    proposal_digest=_DIGEST,
                    repliable=True,
                )
            ],
        ),
    )
    monkeypatch.setattr(
        social_api,
        "_telegram_activity_preview_response",
        lambda _request: social_api.TelegramActivityPreviewResponse(
            **_persona_fields(),
            status="completed",
            proposal_digest=_DIGEST,
            target=target,
            activity_preview=social_api.TelegramActivityPreviewDto(
                text="safe activity",
                char_count=13,
                activity_kind="test_activity",
            ),
            governor=social_api.TelegramActivityGovernorDto(allowed=True),
        ),
    )
    monkeypatch.setattr(
        social_api,
        "_telegram_preview_response",
        lambda _request: social_api.TelegramMessagePreviewResponse(
            **_persona_fields(),
            status="completed",
            proposal_digest=_DIGEST,
            target=target,
            message_preview=social_api.TelegramMessagePreviewDto(
                text="safe message", char_count=12
            ),
        ),
    )


@contextmanager
def _patched_telegram(case: ApplyRouteCase, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if case.channel != "telegram":
        yield
        return
    _patch_telegram_previews(monkeypatch)
    yield


def _call_apply(case: ApplyRouteCase) -> dict[str, Any]:
    response = client.post(case.route, headers=_headers(), json=case.body)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    return body


@pytest.mark.parametrize("case", _ROUTE_CASES, ids=[case.name for case in _ROUTE_CASES])
def test_autonomy_reasons_prepend_before_legacy_apply_reasons_per_route(
    case: ApplyRouteCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _set_live_token(monkeypatch)
    with _patched_telegram(case, monkeypatch):
        baseline = _call_apply(case)
        _write_autonomy_profile(profile_path, status="paused")
        blocked = _call_apply(case)

    assert baseline["reasons"]
    assert blocked["reasons"] == ["autonomy_profile_not_running", *baseline["reasons"]]


@pytest.mark.parametrize("case", _ROUTE_CASES, ids=[case.name for case in _ROUTE_CASES])
def test_permissive_autonomy_profile_preserves_legacy_reasons_byte_equal_per_route(
    case: ApplyRouteCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _set_live_token(monkeypatch)
    with _patched_telegram(case, monkeypatch):
        baseline = _call_apply(case)
        _write_autonomy_profile(profile_path, status="running")
        permissive = _call_apply(case)

    assert permissive["reasons"] == baseline["reasons"]


@pytest.mark.parametrize("case", _ROUTE_CASES, ids=[case.name for case in _ROUTE_CASES])
def test_confirmation_phrases_and_live_token_gate_remain_enforced(
    case: ApplyRouteCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    bad_phrase_body = {**case.body, "confirmation_phrase": "WRONG PHRASE"}
    _set_live_token(monkeypatch)
    response = client.post(case.route, headers=_headers(), json=bad_phrase_body)
    assert response.status_code == 200, response.text
    assert "confirmation_phrase_required" in response.json()["reasons"]

    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    response = client.post(case.route, headers=_headers(), json=case.body)
    assert response.status_code == 403
    assert response.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_DISABLED"


def test_confirmation_phrase_literals_remain_byte_equal() -> None:
    assert social_api.LIVE_REPLY_CONFIRMATION_PHRASE == "SEND ONE LIVE REPLY"
    assert social_api.LIVE_BATCH_CONFIRMATION_PHRASE == "SEND LIVE REACTIVE BATCH"
    assert social_api.LIVE_BROADCAST_CONFIRMATION_PHRASE == "SEND ONE LIVE POST"
    assert social_api.LIVE_TELEGRAM_CONFIRMATION_PHRASE == "SEND ONE TELEGRAM MESSAGE"
    assert social_api.LIVE_TELEGRAM_ACTIVITY_CONFIRMATION_PHRASE == "SEND ONE TELEGRAM ACTIVITY"
    assert social_api.LIVE_TELEGRAM_REACTIVE_REPLY_CONFIRMATION_PHRASE == "SEND ONE TELEGRAM REPLY"


def test_ham_x_config_codes_remain_after_autonomy_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _set_live_token(monkeypatch)
    _write_autonomy_profile(profile_path, status="paused")

    body = _call_apply(_ROUTE_CASES[2])

    assert body["reasons"][0] == "autonomy_profile_not_running"
    assert "goham_execution_disabled" in body["reasons"]
    assert "goham_controller_disabled" in body["reasons"]
    assert "autonomy_disabled" in body["reasons"]
    assert "dry_run_enabled" in body["reasons"]


def test_proposal_and_persona_digest_mismatch_codes_remain_with_permissive_autonomy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _set_live_token(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    _write_autonomy_profile(profile_path, status="running")

    body = _call_apply(_ROUTE_CASES[2])

    assert "proposal_digest_mismatch" in body["reasons"]
    assert "persona_digest_mismatch" in body["reasons"]
    assert all(not reason.startswith("autonomy_") for reason in body["reasons"])


def test_telegram_duplicate_idempotency_result_still_blocks_with_permissive_autonomy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profile_path = _isolate(monkeypatch, tmp_path)
    _set_live_token(monkeypatch)
    _patch_telegram_previews(monkeypatch)
    _write_autonomy_profile(profile_path, status="running")
    monkeypatch.setattr(social_api, "_telegram_readiness_apply_reasons", lambda: [])

    duplicate = TelegramSendResult(
        status="duplicate",
        execution_allowed=False,
        mutation_attempted=False,
        reasons=["duplicate_idempotency_key"],
    )
    with patch("src.api.social.send_confirmed_telegram_message", return_value=duplicate) as send:
        body = client.post(
            "/api/social/providers/telegram/messages/apply",
            headers=_headers(),
            json={"proposal_digest": _DIGEST, "confirmation_phrase": "SEND ONE TELEGRAM MESSAGE"},
        ).json()

    assert send.call_count == 1
    assert body["status"] == "duplicate"
    assert body["reasons"] == ["duplicate_idempotency_key"]


def test_social_policy_document_still_does_not_gate_apply_reasons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path
    _isolate(monkeypatch, root)
    _set_live_token(monkeypatch)

    baseline = _call_apply(_ROUTE_CASES[2])
    _write_social_policy(root)
    with_policy = _call_apply(_ROUTE_CASES[2])

    assert with_policy["reasons"] == baseline["reasons"]
    assert all(not reason.startswith("policy_") for reason in with_policy["reasons"])
