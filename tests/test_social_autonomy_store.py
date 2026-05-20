"""Store-level tests for GoHAM Social autonomy profile persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    SocialAutonomyPathError,
    SocialAutonomyWriteAuthError,
    apply_social_autonomy_profile,
    preview_social_autonomy_profile,
    read_social_autonomy_profile,
    rollback_social_autonomy_profile,
    social_autonomy_path,
    social_autonomy_writes_enabled,
)

_TOKEN = "autonomy-write-token"  # noqa: S105
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "status": "draft",
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


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _configure_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    return target


def _audit_files(tmp_path: Path) -> list[Path]:
    audit_dir = tmp_path / "_audit" / "social_autonomy"
    return sorted(audit_dir.glob("*.json")) if audit_dir.exists() else []


def _backup_files(tmp_path: Path) -> list[Path]:
    backup_dir = tmp_path / "_backups" / "social_autonomy"
    return sorted(backup_dir.glob("*.json")) if backup_dir.exists() else []


def _assert_no_tmp_files(target: Path) -> None:
    assert not list(target.parent.glob("*.tmp"))
    assert not list(target.parent.glob(".*.tmp"))
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_default_draft_read_does_not_create_profile_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)

    profile = read_social_autonomy_profile(tmp_path)

    assert profile.status == "draft"
    assert profile.profile_id
    assert not target.exists()


def test_preview_no_persist_returns_normalized_dict_without_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    candidate = _profile(goal="  Grow awareness for HAM safely.  ")

    preview = preview_social_autonomy_profile(tmp_path, candidate.model_dump(mode="json"))

    assert preview == candidate.model_dump(mode="json")
    assert preview["goal"] == "Grow awareness for HAM safely."
    assert not target.exists()
    assert not (tmp_path / "_audit").exists()
    assert not (tmp_path / "_backups").exists()


def test_apply_persists_canonical_json_atomically_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    profile = _profile()

    result = apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")

    assert target.is_file()
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == profile.model_dump(mode="json")
    assert result.effective_after == on_disk
    assert result.backup_id is None
    _assert_no_tmp_files(target)

    audits = _audit_files(tmp_path)
    assert len(audits) == 1
    audit = json.loads(audits[0].read_text(encoding="utf-8"))
    assert audit["audit_id"] == result.audit_id
    assert audit["op"] == "apply"
    assert audit["actor"] == "pytest"
    assert audit["before_digest"] != audit["after_digest"]
    assert audit["before"]["status"] == "draft"
    assert audit["after"] == on_disk


def test_audit_envelope_increments_once_per_successful_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    apply_social_autonomy_profile(tmp_path, _profile(profile_id="p1"), token=_TOKEN)
    assert len(_audit_files(tmp_path)) == 1

    apply_social_autonomy_profile(
        tmp_path,
        _profile(profile_id="p2", goal="Announce product updates safely."),
        token=_TOKEN,
    )
    assert len(_audit_files(tmp_path)) == 2


def test_backup_written_verbatim_only_when_overwriting_existing_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    first = apply_social_autonomy_profile(tmp_path, _profile(profile_id="p1"), token=_TOKEN)
    first_bytes = target.read_bytes()
    assert first.backup_id is None
    assert _backup_files(tmp_path) == []

    second = apply_social_autonomy_profile(
        tmp_path,
        _profile(profile_id="p2", goal="Announce updates safely."),
        token=_TOKEN,
    )

    assert second.backup_id is not None
    backup_path = tmp_path / "_backups" / "social_autonomy" / f"{second.backup_id}.json"
    assert backup_path.read_bytes() == first_bytes


def test_rollback_round_trip_restores_backup_bytes_and_audits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    apply_social_autonomy_profile(tmp_path, _profile(profile_id="p1"), token=_TOKEN)
    p1_bytes = target.read_bytes()
    apply_result = apply_social_autonomy_profile(
        tmp_path,
        _profile(profile_id="p2", goal="Announce updates safely."),
        token=_TOKEN,
    )
    assert apply_result.backup_id is not None
    audit_count_before = len(_audit_files(tmp_path))

    rollback = rollback_social_autonomy_profile(
        tmp_path,
        apply_result.backup_id,
        token=_TOKEN,
        actor="pytest",
    )

    assert target.read_bytes() == p1_bytes
    assert rollback.backup_id == apply_result.backup_id
    assert rollback.effective_after["profile_id"] == "p1"
    assert len(_audit_files(tmp_path)) == audit_count_before + 1
    rollback_audit = json.loads(
        (tmp_path / "_audit" / "social_autonomy" / f"{rollback.audit_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert rollback_audit["op"] == "rollback"
    assert rollback_audit["restored_from_backup_id"] == apply_result.backup_id


def test_round_trip_byte_stable_preview_apply_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    original = _profile(profile_id="p0")
    changed = _profile(profile_id="p1", goal="Engage community safely.")

    preview_social_autonomy_profile(tmp_path, changed)
    apply_social_autonomy_profile(tmp_path, original, token=_TOKEN)
    original_bytes = target.read_bytes()
    changed_apply = apply_social_autonomy_profile(tmp_path, changed, token=_TOKEN)
    assert changed_apply.backup_id is not None

    rollback_social_autonomy_profile(tmp_path, changed_apply.backup_id, token=_TOKEN)

    assert target.read_bytes() == original_bytes


def test_path_override_honored_end_to_end_without_touching_repo_ham(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _configure_store(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    repo_profile = _REPO_ROOT / ".ham" / "social_autonomy.json"
    before = repo_profile.read_bytes() if repo_profile.exists() else None

    apply_social_autonomy_profile(_REPO_ROOT, _profile(), token=_TOKEN)

    assert social_autonomy_path(_REPO_ROOT) == target
    assert target.exists()
    assert _audit_files(tmp_path)
    assert (repo_profile.read_bytes() if repo_profile.exists() else None) == before


def test_write_token_gate_covers_missing_wrong_and_matching_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_store(monkeypatch, tmp_path)

    with pytest.raises(SocialAutonomyWriteAuthError):
        apply_social_autonomy_profile(tmp_path, _profile(), token=_TOKEN)

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    with pytest.raises(SocialAutonomyWriteAuthError):
        apply_social_autonomy_profile(tmp_path, _profile(), token="wrong")

    apply_result = apply_social_autonomy_profile(tmp_path, _profile(), token=_TOKEN)
    assert apply_result.audit_id

    second = apply_social_autonomy_profile(
        tmp_path,
        _profile(profile_id="p2", goal="Announce updates safely."),
        token=_TOKEN,
    )
    assert second.backup_id is not None

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", "other")
    with pytest.raises(SocialAutonomyWriteAuthError):
        rollback_social_autonomy_profile(tmp_path, second.backup_id, token=_TOKEN)

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    rollback = rollback_social_autonomy_profile(tmp_path, second.backup_id, token=_TOKEN)
    assert rollback.audit_id


def test_writes_enabled_only_when_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", raising=False)
    assert social_autonomy_writes_enabled() is False
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    assert social_autonomy_writes_enabled() is True


def test_symlink_safety_refuses_external_target_without_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external_target = external_dir / "external-profile.json"
    external_target.write_text("external-before\n", encoding="utf-8")

    root = tmp_path / "store"
    root.mkdir()
    symlink_path = root / "profile.json"
    symlink_path.symlink_to(external_target)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(symlink_path))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)

    with pytest.raises(SocialAutonomyPathError):
        apply_social_autonomy_profile(root, _profile(), token=_TOKEN)

    assert external_target.read_text(encoding="utf-8") == "external-before\n"
    assert not (root / "_audit").exists()
    assert not (root / "_backups").exists()
