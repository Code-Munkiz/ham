"""Unit tests for PATCH /api/social/autonomy/settings — M2 patch extensions.

Covers VAL-M15-M2-PATCH-* assertions:
  - VAL-M15-M2-PATCH-GOAL-ACCEPT-001: goal accepted (1..2000), idempotent
  - VAL-M15-M2-PATCH-GOAL-REJECT-002: goal > 2000 chars rejected
  - VAL-M15-M2-PATCH-CADENCE-ENUM-001: cadence ∈ {manual,hourly,daily} accepted
  - VAL-M15-M2-PATCH-CADENCE-REJECT-002: unknown cadence rejected
  - VAL-M15-M2-PATCH-ACTIONS-ALLOWED-ACCEPT-001: actions_allowed_per_channel accepted
  - VAL-M15-M2-PATCH-ACTIONS-ALLOWED-REJECT-002: unknown action rejected
  - VAL-M15-M2-PATCH-FORBIDDEN-TOPICS-001: forbidden_topics deduped+stripped
  - VAL-M15-M2-PATCH-FORBIDDEN-TOPICS-REJECT-002: forbidden_topics > 64 rejected
  - VAL-M15-M2-PATCH-SAFETY-RULES-CANONICAL-001: canonical safety_rules accepted
  - VAL-M15-M2-PATCH-SAFETY-RULES-REJECT-002: non-canonical safety_rule rejected
  - VAL-M15-M2-PATCH-LEARNING-ENABLED-001: learning_enabled round-trip
  - VAL-M15-M2-PATCH-AUDIT-ENVELOPE-001: audit envelope written with new fields
  - VAL-M15-M2-PATCH-IDEMPOTENT-MERGE-002: idempotent on repeated apply
  - VAL-M15-M2-PATCH-REJECTS-STATUS-001: status rejected
  - VAL-M15-M2-PATCH-REJECTS-EMERGENCY-STOP-002: emergency_stop rejected
  - VAL-M15-M2-PATCH-REJECTS-TELEGRAM-SECRETS-003: Telegram secrets rejected
  - VAL-M15-M2-PATCH-NEVER-ECHOES-SECRETS-004: response and audit never echo secrets
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import apply_social_autonomy_profile

client = TestClient(app)

_TOKEN = "m2-patch-write-token"  # noqa: S105

_CANONICAL_SIX = [
    "credential_request",
    "price_guarantee",
    "mass_tagging",
    "repeated_payload",
    "no_external_links",
    "payload_min_length",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    _disable_clerk(monkeypatch)
    return target


def _headers(token: str = _TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "m2-patch-test-profile",
        "status": "draft",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": False, "available": True},
            "telegram": {"enabled": False, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message"],
            "discord": [],
        },
        "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": _CANONICAL_SIX,
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: GoHamSocialProfile) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")


def _audit_dir(tmp_path: Path) -> Path:
    return tmp_path / "_audit" / "social_autonomy"


# ---------------------------------------------------------------------------
# Goal field tests — VAL-M15-M2-PATCH-GOAL-ACCEPT-001 / REJECT-002
# ---------------------------------------------------------------------------


def test_patch_accepts_goal_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-GOAL-ACCEPT-001: PATCH accepts goal, idempotent merge."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"goal": "Hello"},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["goal"] == "Hello"

    # Second identical PATCH → same after_digest (idempotent)
    audits_before = list(_audit_dir(tmp_path).glob("*.json"))
    response2 = client.patch(
        "/api/social/autonomy/settings",
        json={"goal": "Hello"},
        headers=_headers(),
    )
    assert response2.status_code == 200, response2.text
    assert response2.json()["goal"] == "Hello"

    audits_after = list(_audit_dir(tmp_path).glob("*.json"))
    assert len(audits_after) == len(audits_before) + 1

    # Both audit envelopes should have the same after_digest
    audit_docs = sorted(
        [json.loads(p.read_text()) for p in audits_after],
        key=lambda d: d["timestamp"],
    )
    # The last two audits should have the same after_digest
    last_two = audit_docs[-2:]
    assert last_two[-1]["after_digest"] == last_two[-2]["after_digest"]


def test_patch_rejects_goal_too_long(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-GOAL-REJECT-002: PATCH rejects goal > 2000 chars."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"goal": "a" * 2001},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text
    error_text = response.text
    assert "goal" in error_text


# ---------------------------------------------------------------------------
# Cadence field tests — VAL-M15-M2-PATCH-CADENCE-ENUM-001 / REJECT-002
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cadence_value", ["manual", "hourly", "daily"])
def test_patch_accepts_cadence_enum_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cadence_value: str
) -> None:
    """VAL-M15-M2-PATCH-CADENCE-ENUM-001: PATCH accepts cadence ∈ {manual,hourly,daily}."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"cadence": cadence_value},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["cadence"] == cadence_value


def test_patch_rejects_unknown_cadence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-CADENCE-REJECT-002: PATCH rejects unknown cadence value."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"cadence": "weekly"},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text
    assert "cadence" in response.text


# ---------------------------------------------------------------------------
# actions_allowed_per_channel — VAL-M15-M2-PATCH-ACTIONS-ALLOWED-ACCEPT-001 / REJECT-002
# ---------------------------------------------------------------------------


def test_patch_accepts_actions_allowed_per_channel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-ACTIONS-ALLOWED-ACCEPT-001: per-channel replace + dedup + other channels preserved."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={
            "actions_allowed_per_channel": {
                "telegram": ["message", "activity", "message"],  # dedup should collapse
            }
        },
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Telegram actions replaced + deduped
    telegram_actions = body["actions_allowed_per_channel"]["telegram"]
    assert "message" in telegram_actions
    assert "activity" in telegram_actions
    assert telegram_actions.count("message") == 1  # deduped
    # Other channels' settings preserved
    x_actions = body["actions_allowed_per_channel"]["x"]
    assert "reply" in x_actions
    assert "broadcast" in x_actions


def test_patch_rejects_unknown_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-ACTIONS-ALLOWED-REJECT-002: PATCH rejects unknown action."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={
            "actions_allowed_per_channel": {
                "telegram": ["broadcast", "hack"],
            }
        },
        headers=_headers(),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# forbidden_topics — VAL-M15-M2-PATCH-FORBIDDEN-TOPICS-001 / REJECT-002
# ---------------------------------------------------------------------------


def test_patch_accepts_forbidden_topics_dedup_strip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-FORBIDDEN-TOPICS-001: forbidden_topics deduped and stripped."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"forbidden_topics": ["nsfw", "  spam  ", "nsfw"]},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # stripped + deduped
    assert body["forbidden_topics"] == ["nsfw", "spam"]


def test_patch_rejects_forbidden_topics_too_many(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-FORBIDDEN-TOPICS-REJECT-002: forbidden_topics > 64 items rejected."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"forbidden_topics": [str(i) for i in range(65)]},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text
    assert "forbidden_topics" in response.text


# ---------------------------------------------------------------------------
# safety_rules — VAL-M15-M2-PATCH-SAFETY-RULES-CANONICAL-001 / REJECT-002
# ---------------------------------------------------------------------------


def test_patch_accepts_canonical_safety_rules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-SAFETY-RULES-CANONICAL-001: all six canonical safety_rules accepted."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"safety_rules": _CANONICAL_SIX},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["safety_rules"]) == sorted(_CANONICAL_SIX)


def test_patch_rejects_non_canonical_safety_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-SAFETY-RULES-REJECT-002: non-canonical safety_rule rejected."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"safety_rules": ["credential_request", "made_up_rule"]},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text
    assert "safety_rules" in response.text


# ---------------------------------------------------------------------------
# learning_enabled — VAL-M15-M2-PATCH-LEARNING-ENABLED-001
# ---------------------------------------------------------------------------


def test_patch_learning_enabled_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-LEARNING-ENABLED-001: learning_enabled accepted and round-trips."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile(learning_enabled=True))

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"learning_enabled": False},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["learning_enabled"] is False

    # Re-enable
    response2 = client.patch(
        "/api/social/autonomy/settings",
        json={"learning_enabled": True},
        headers=_headers(),
    )

    assert response2.status_code == 200, response2.text
    assert response2.json()["learning_enabled"] is True


# ---------------------------------------------------------------------------
# Audit envelope — VAL-M15-M2-PATCH-AUDIT-ENVELOPE-001
# ---------------------------------------------------------------------------


def test_patch_writes_audit_envelope_with_new_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-AUDIT-ENVELOPE-001: audit envelope written with new fields visible."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())
    audit_dir = _audit_dir(tmp_path)

    audits_before = list(audit_dir.glob("*.json"))

    response = client.patch(
        "/api/social/autonomy/settings",
        json={
            "goal": "Updated goal for audit test",
            "cadence": "daily",
            "actions_allowed_per_channel": {"telegram": ["message", "activity"]},
            "forbidden_topics": ["violence", "spam"],
            "safety_rules": _CANONICAL_SIX[:3],
            "learning_enabled": True,
        },
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    audits_after = list(audit_dir.glob("*.json"))
    assert len(audits_after) == len(audits_before) + 1

    # Find the new audit
    new_audit_path = next(p for p in audits_after if p not in audits_before)
    audit = json.loads(new_audit_path.read_text())

    assert audit["op"] == "apply"
    assert audit["after"]["goal"] == "Updated goal for audit test"
    assert audit["after"]["cadence"] == "daily"
    assert audit["after"]["learning_enabled"] is True
    assert audit["after"]["forbidden_topics"] == ["violence", "spam"]
    assert sorted(audit["after"]["safety_rules"]) == sorted(_CANONICAL_SIX[:3])
    # before snapshot lacks the updated goal
    assert audit["before"]["goal"] != "Updated goal for audit test"


# ---------------------------------------------------------------------------
# Idempotency — VAL-M15-M2-PATCH-IDEMPOTENT-MERGE-002
# ---------------------------------------------------------------------------


def test_patch_is_idempotent_on_repeated_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-IDEMPOTENT-MERGE-002: identical PATCH yields identical post-state digest."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    patch_body = {
        "goal": "Idempotency test goal",
        "cadence": "hourly",
        "forbidden_topics": ["violence"],
        "safety_rules": _CANONICAL_SIX,
        "learning_enabled": True,
    }

    client.patch(
        "/api/social/autonomy/settings",
        json=patch_body,
        headers=_headers(),
    )
    client.patch(
        "/api/social/autonomy/settings",
        json=patch_body,
        headers=_headers(),
    )

    audit_dir = _audit_dir(tmp_path)
    audits = sorted(
        [json.loads(p.read_text()) for p in audit_dir.glob("*.json")],
        key=lambda d: d["timestamp"],
    )
    # The two last apply audits should have the same after_digest
    apply_audits = [a for a in audits if a["op"] == "apply"]
    assert len(apply_audits) >= 2
    last_two = apply_audits[-2:]
    assert last_two[-1]["after_digest"] == last_two[-2]["after_digest"]


# ---------------------------------------------------------------------------
# Rejected fields — VAL-M15-M2-PATCH-REJECTS-STATUS-001 / EMERGENCY-STOP-002
# ---------------------------------------------------------------------------


def test_patch_rejects_status_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-REJECTS-STATUS-001: PATCH with status field → 422."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"status": "running"},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text


def test_patch_rejects_emergency_stop_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-REJECTS-EMERGENCY-STOP-002: PATCH with emergency_stop → 422."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"emergency_stop": True},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Telegram secrets rejected — VAL-M15-M2-PATCH-REJECTS-TELEGRAM-SECRETS-003
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret_field",
    [
        "telegram_bot_token",
        "telegram_test_group_id",
        "telegram_allowed_users",
        "telegram_home_channel",
    ],
)
def test_patch_rejects_telegram_secret_and_target_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, secret_field: str
) -> None:
    """VAL-M15-M2-PATCH-REJECTS-TELEGRAM-SECRETS-003: Telegram secrets rejected → 422."""
    _isolate(monkeypatch, tmp_path)
    _persist(monkeypatch, tmp_path, _profile())

    response = client.patch(
        "/api/social/autonomy/settings",
        json={secret_field: "some-value"},
        headers=_headers(),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Never echo secrets — VAL-M15-M2-PATCH-NEVER-ECHOES-SECRETS-004
# ---------------------------------------------------------------------------


def test_patch_response_and_audit_never_echo_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M2-PATCH-NEVER-ECHOES-SECRETS-004: response and audit envelope never echo secrets."""
    _isolate(monkeypatch, tmp_path)
    # Set env vars with specific bait values
    bait_token = "synthetic-bot-token-BAIT123"  # noqa: S105
    bait_group_id = "synthetic-group-id-BAIT456"
    bait_allowed_users = "synthetic-allowed-users-BAIT789"
    bait_home_channel = "synthetic-home-channel-BAITABC"

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bait_token)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", bait_group_id)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", bait_allowed_users)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", bait_home_channel)

    _persist(monkeypatch, tmp_path, _profile())

    audit_dir = _audit_dir(tmp_path)

    response = client.patch(
        "/api/social/autonomy/settings",
        json={"goal": "Secret hygiene test", "learning_enabled": True},
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    response_text = response.text

    # Response body must never echo any of the bait secrets
    assert bait_token not in response_text
    assert bait_group_id not in response_text
    assert bait_allowed_users not in response_text
    assert bait_home_channel not in response_text

    # Audit envelopes must never echo any of the bait secrets
    for audit_path in audit_dir.glob("*.json"):
        audit_text = audit_path.read_text()
        assert bait_token not in audit_text
        assert bait_group_id not in audit_text
        assert bait_allowed_users not in audit_text
        assert bait_home_channel not in audit_text
