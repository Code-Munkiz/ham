"""Schema-extension tests for GoHAM Social autonomy tick state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.ham.social_autonomy.schema import GoHamSocialProfile, SocialAutonomyTickSummary
from src.ham.social_autonomy.store import (
    apply_social_autonomy_profile,
    read_social_autonomy_profile,
)

_TOKEN = "autonomy-write-token"  # noqa: S105
_TICK_FIELDS = {"last_run_at", "next_run_at", "last_tick_summary"}


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "status": "running",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 2, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": ["politics"],
        "safety_rules": ["no spam", "no financial promises"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _mission12_payload(**overrides: Any) -> dict[str, Any]:
    payload = GoHamSocialProfile.model_validate(_profile_payload(**overrides)).model_dump(
        mode="json"
    )
    for key in _TICK_FIELDS:
        payload.pop(key, None)
    return payload


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def _configure_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    return target


def _tick_summary(**overrides: Any) -> SocialAutonomyTickSummary:
    payload: dict[str, Any] = {
        "ran": True,
        "dry_run": True,
        "actions_considered": ["x:reply", "telegram:message"],
        "actions_taken": ["x:reply"],
        "blocked_reasons": [],
        "profile_status": "running",
        "recorded_at": datetime(2026, 5, 20, 12, 30, tzinfo=UTC),
        "next_run_summary": "Next daily tick after 2026-05-21T00:00:00Z",
    }
    payload.update(overrides)
    return SocialAutonomyTickSummary.model_validate(payload)


def test_defaults_none_for_new_tick_fields() -> None:
    profile = GoHamSocialProfile.model_validate(_mission12_payload())

    assert profile.last_run_at is None
    assert profile.next_run_at is None
    assert profile.last_tick_summary is None


@pytest.mark.parametrize("unknown_key", ["last_tick", "nextRun", "tick_summary"])
def test_extra_forbid_rejects_unknown_tick_aliases(unknown_key: str) -> None:
    payload = _profile_payload(**{unknown_key: True})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GoHamSocialProfile.model_validate(payload)


@pytest.mark.parametrize("field_name", ["last_run_at", "next_run_at"])
def test_tz_aware_required_for_profile_tick_datetimes(field_name: str) -> None:
    naive = datetime(2026, 5, 20, 12, 30)

    with pytest.raises(ValidationError, match=field_name):
        GoHamSocialProfile.model_validate(_profile_payload(**{field_name: naive}))

    aware = datetime(2026, 5, 20, 12, 30, tzinfo=UTC)
    success_payload = _profile_payload(**{field_name: aware})
    if field_name == "last_run_at":
        success_payload["updated_at"] = aware
    profile = GoHamSocialProfile.model_validate(success_payload)

    assert getattr(profile, field_name) == aware


def test_last_run_le_updated_constraint_allows_none() -> None:
    updated_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="last_run_at"):
        GoHamSocialProfile.model_validate(
            _profile_payload(
                updated_at=updated_at,
                last_run_at=updated_at + timedelta(seconds=1),
            )
        )

    profile = GoHamSocialProfile.model_validate(
        _profile_payload(updated_at=updated_at, last_run_at=None)
    )
    assert profile.last_run_at is None


def test_social_autonomy_tick_summary_shape_and_extra_forbid() -> None:
    summary = _tick_summary()

    assert set(SocialAutonomyTickSummary.model_fields) == {
        "ran",
        "dry_run",
        "actions_considered",
        "actions_taken",
        "blocked_reasons",
        "profile_status",
        "recorded_at",
        "next_run_summary",
    }
    assert SocialAutonomyTickSummary.model_validate(summary.model_dump(mode="json")) == summary
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SocialAutonomyTickSummary.model_validate(
            {**summary.model_dump(mode="json"), "extra_key": "not-allowed"}
        )


def test_social_autonomy_tick_summary_dedup_blocked_reasons() -> None:
    summary = _tick_summary(
        blocked_reasons=[
            "autonomy_cap_exceeded",
            "autonomy_cap_exceeded",
            "autonomy_quiet_hours_active",
        ]
    )

    assert summary.blocked_reasons == [
        "autonomy_cap_exceeded",
        "autonomy_quiet_hours_active",
    ]


def test_social_autonomy_store_tick_fields_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    last_run_at = datetime(2026, 5, 20, 12, 30, tzinfo=UTC)
    next_run_at = datetime(2026, 5, 21, 0, 0, tzinfo=UTC)
    summary = _tick_summary()
    profile = GoHamSocialProfile.model_validate(
        _profile_payload(
            updated_at=last_run_at,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            last_tick_summary=summary,
        )
    )

    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")
    loaded = read_social_autonomy_profile(tmp_path)
    on_disk = json.loads(target.read_text(encoding="utf-8"))

    assert loaded.last_run_at == last_run_at
    assert loaded.next_run_at == next_run_at
    assert loaded.last_tick_summary == summary
    assert on_disk["last_run_at"] == profile.model_dump(mode="json")["last_run_at"]
    assert on_disk["next_run_at"] == profile.model_dump(mode="json")["next_run_at"]
    assert on_disk["last_tick_summary"] == summary.model_dump(mode="json")


def test_social_autonomy_store_mission12_backward_compat_and_null_emit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    mission12 = _mission12_payload()
    mission12_text = _canonical_json(mission12)
    target.write_text(mission12_text, encoding="utf-8")

    loaded = read_social_autonomy_profile(tmp_path)

    assert loaded.last_run_at is None
    assert loaded.next_run_at is None
    assert loaded.last_tick_summary is None

    apply_social_autonomy_profile(tmp_path, loaded, token=_TOKEN, actor="pytest")
    on_disk = json.loads(target.read_text(encoding="utf-8"))

    assert on_disk["last_run_at"] is None
    assert on_disk["next_run_at"] is None
    assert on_disk["last_tick_summary"] is None
    without_tick_fields = {key: value for key, value in on_disk.items() if key not in _TICK_FIELDS}
    assert _canonical_json(without_tick_fields) == mission12_text


def test_social_autonomy_store_tick_fields_audit_envelope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_store(monkeypatch, tmp_path)
    base = GoHamSocialProfile.model_validate(_profile_payload())
    apply_social_autonomy_profile(tmp_path, base, token=_TOKEN, actor="pytest")
    audit_dir = tmp_path / "_audit" / "social_autonomy"
    assert len(list(audit_dir.glob("*.json"))) == 1

    tick_at = datetime(2026, 5, 20, 12, 30, tzinfo=UTC)
    updated = base.model_copy(
        update={
            "updated_at": tick_at,
            "last_run_at": tick_at,
            "next_run_at": datetime(2026, 5, 21, 0, 0, tzinfo=UTC),
            "last_tick_summary": _tick_summary(recorded_at=tick_at),
        }
    )

    apply_social_autonomy_profile(tmp_path, updated, token=_TOKEN, actor="pytest")

    audits = sorted(audit_dir.glob("*.json"))
    assert len(audits) == 2
    latest = next(
        audit
        for audit in (json.loads(path.read_text(encoding="utf-8")) for path in audits)
        if audit["after"]["last_run_at"] == updated.model_dump(mode="json")["last_run_at"]
    )
    assert latest["op"] == "apply"
    assert latest["before_digest"] != latest["after_digest"]
    assert latest["before"]["last_run_at"] is None
    assert latest["after"]["last_run_at"] == updated.model_dump(mode="json")["last_run_at"]


def test_social_autonomy_store_tick_summary_extra_forbid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    payload = _mission12_payload()
    payload["last_tick_summary"] = {**_tick_summary().model_dump(mode="json"), "extra_key": True}
    target.write_text(_canonical_json(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="extra_key"):
        read_social_autonomy_profile(tmp_path)
