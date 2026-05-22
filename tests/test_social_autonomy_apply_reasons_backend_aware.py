"""Backend-aware apply-reasons gate tests.

Verifies that ``_autonomy_apply_reasons()`` in ``src/api/social.py`` derives
'profile configured' from ``store.read().status`` rather than from
``store.path().exists()``, so the gate works identically for both the file
backend and the Firestore backend.

Key assertions:
- A ``status == "draft"`` profile — whether it comes from the file store
  (no file persisted) or from the Firestore store (no document persisted yet)
  — is treated as "not yet configured" and returns no blockers.
- A ``status == "paused"`` profile from either backend returns
  ``["autonomy_profile_not_running"]``.
- A ``status == "running"`` profile with permissive settings returns no
  autonomy-specific blockers from either backend.
- File-backend and Firestore-backend results are byte-equal for equivalent
  profile states (cross-backend parity).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.api.social import _autonomy_apply_reasons
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    ApplyResult,
    RollbackResult,
    set_social_autonomy_store_for_tests,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STAMP = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "goham-social-default",
        "status": "draft",
        "goal": "Test apply-reasons gate.",
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
        "daily_caps": {"x": 5, "telegram": 5, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": ["credential_request"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": _STAMP,
        "updated_at": _STAMP,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _write_profile(path: Path, **overrides: Any) -> None:
    """Write a profile JSON file to *path* for file-backend tests."""
    profile = _profile(**overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n",
        encoding="utf-8",
    )


class _FakeStore:
    """Minimal Protocol-conforming store that returns a controlled profile.

    Simulates the Firestore backend's characteristic: ``path().exists()``
    ALWAYS returns False (there is no local file), while ``read()`` returns
    the profile the caller injects.  This lets us verify that
    ``_autonomy_apply_reasons`` no longer relies on ``path().exists()`` and
    instead uses ``read().status``.
    """

    def __init__(self, profile: GoHamSocialProfile) -> None:
        self._profile = profile

    def read(self, root: Path | None = None) -> GoHamSocialProfile:
        return self._profile

    def path(self, root: Path | None = None) -> Path:
        # Simulate Firestore: path never exists on the local filesystem.
        return Path("/nonexistent/__firestore_sim__/social_autonomy.json")

    def preview(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError  # not exercised by these tests

    def apply(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
        *,
        token: str | None,
        actor: str = "system",
    ) -> ApplyResult:
        raise NotImplementedError

    def save(
        self,
        root: Path | None,
        profile: GoHamSocialProfile,
        *,
        actor: str = "system",
    ) -> ApplyResult:
        raise NotImplementedError

    def rollback(
        self,
        root: Path | None,
        backup_id: str,
        *,
        token: str | None,
        actor: str = "system",
    ) -> RollbackResult:
        raise NotImplementedError

    def writes_enabled(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# File-backend gate tests
# ---------------------------------------------------------------------------


class TestFileBackendApplyReasonsGate:
    """File-backend: derive 'configured' from profile.status, not path().exists()."""

    def test_file_backend_no_file_no_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """No profile file → read() returns default draft → gate returns []."""
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(tmp_path / "social_autonomy.json"))
        set_social_autonomy_store_for_tests(None)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert result == [], f"Expected [] when no file exists, got {result!r}"

    def test_file_backend_draft_status_no_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Persisted draft profile → status == 'draft' → gate returns []."""
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        _write_profile(profile_path, status="draft")
        set_social_autonomy_store_for_tests(None)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert result == [], f"Expected [] for draft profile, got {result!r}"

    def test_file_backend_paused_profile_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Paused file-backend profile → gate returns ['autonomy_profile_not_running']."""
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        _write_profile(profile_path, status="paused")
        set_social_autonomy_store_for_tests(None)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert "autonomy_profile_not_running" in result, (
            f"Expected 'autonomy_profile_not_running' in result, got {result!r}"
        )
        assert result[0] == "autonomy_profile_not_running"

    def test_file_backend_running_permissive_no_autonomy_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Running file-backend profile with permissive settings → no autonomy blockers."""
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        _write_profile(profile_path, status="running")
        set_social_autonomy_store_for_tests(None)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        # Running + permissive → no autonomy-specific blockers
        assert not any(r.startswith("autonomy_") for r in result), (
            f"Expected no autonomy_* blockers for running profile, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Firestore-backend gate tests (fake store)
# ---------------------------------------------------------------------------


class TestFirestoreBackendApplyReasonsGate:
    """Firestore-backend (fake): derive 'configured' from profile.status.

    Uses _FakeStore whose path().exists() always returns False — matching the
    Firestore backend's real behaviour — to confirm the gate relies solely on
    read().status.
    """

    def test_firestore_no_document_no_block(self) -> None:
        """No Firestore document → read() returns default draft → gate returns []."""
        fake_store = _FakeStore(_profile(status="draft"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert result == [], f"Expected [] when Firestore has no document, got {result!r}"

    def test_firestore_paused_profile_blocks(self) -> None:
        """Paused Firestore profile → gate returns ['autonomy_profile_not_running']."""
        fake_store = _FakeStore(_profile(status="paused"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert "autonomy_profile_not_running" in result, (
            f"Expected 'autonomy_profile_not_running' in result, got {result!r}"
        )
        assert result[0] == "autonomy_profile_not_running"

    def test_firestore_running_permissive_no_autonomy_block(self) -> None:
        """Running Firestore profile with permissive settings → no autonomy blockers."""
        fake_store = _FakeStore(_profile(status="running"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert not any(r.startswith("autonomy_") for r in result), (
            f"Expected no autonomy_* blockers for running profile, got {result!r}"
        )

    def test_firestore_path_not_exists_does_not_affect_gate(self) -> None:
        """Confirm path().exists() is False for fake store, yet gate still works correctly.

        This asserts the precondition that the old store.path(root).exists() check
        would have returned False for our fake (and for the real Firestore store),
        while the new status-based check returns the correct result.
        """
        paused_profile = _profile(status="paused")
        fake_store = _FakeStore(paused_profile)
        # Verify the fake store's path().exists() is indeed False (simulating Firestore)
        assert not fake_store.path(None).exists(), (
            "_FakeStore.path().exists() must be False to simulate Firestore backend"
        )
        # Despite path().exists() == False, the gate must return the correct blocker.
        set_social_autonomy_store_for_tests(fake_store)
        try:
            result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)
        assert "autonomy_profile_not_running" in result, (
            "Gate must fire even when path().exists() is False (Firestore backend)"
        )


# ---------------------------------------------------------------------------
# Cross-backend parity tests
# ---------------------------------------------------------------------------


class TestCrossBackendParityApplyReasons:
    """File backend and Firestore backend produce byte-equal results for the same profile state."""

    def test_draft_state_parity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Both backends return [] for a draft profile (the 'not yet configured' state)."""
        # File backend: no file → read() returns default draft
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        set_social_autonomy_store_for_tests(None)
        try:
            file_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        # Firestore backend: fake store returns default draft
        fake_store = _FakeStore(_profile(status="draft"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            fs_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        assert file_result == [] and fs_result == [], (
            f"Both backends must return [] for draft state; "
            f"file={file_result!r}, firestore={fs_result!r}"
        )

    def test_paused_state_parity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Both backends return ['autonomy_profile_not_running'] for a paused profile."""
        # File backend: write paused profile
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        _write_profile(profile_path, status="paused")
        set_social_autonomy_store_for_tests(None)
        try:
            file_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        # Firestore backend: fake store returns paused profile
        fake_store = _FakeStore(_profile(status="paused"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            fs_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        assert file_result == fs_result, (
            f"Both backends must return identical results for paused state; "
            f"file={file_result!r}, firestore={fs_result!r}"
        )
        assert "autonomy_profile_not_running" in file_result

    def test_running_state_parity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Both backends return identical results for a running profile with the same settings."""
        # File backend: write running profile
        profile_path = tmp_path / "social_autonomy.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))
        _write_profile(profile_path, status="running")
        set_social_autonomy_store_for_tests(None)
        try:
            file_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        # Firestore backend: fake store returns running profile with same settings
        fake_store = _FakeStore(_profile(status="running"))
        set_social_autonomy_store_for_tests(fake_store)
        try:
            fs_result = _autonomy_apply_reasons(channel="telegram", action="message")
        finally:
            set_social_autonomy_store_for_tests(None)

        assert file_result == fs_result, (
            f"Both backends must return identical results for running state; "
            f"file={file_result!r}, firestore={fs_result!r}"
        )

    @pytest.mark.parametrize("status", ["paused", "stopped"])
    def test_non_running_states_parity_per_channel(
        self,
        status: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """For each non-running status, file backend and Firestore backend agree on all channels."""
        profile_path = tmp_path / f"social_autonomy_{status}.json"
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(profile_path))

        for channel, action in [("telegram", "message"), ("telegram", "reply"), ("x", "reply")]:
            # File backend
            _write_profile(profile_path, status=status)
            set_social_autonomy_store_for_tests(None)
            try:
                file_result = _autonomy_apply_reasons(channel=channel, action=action)  # type: ignore[arg-type]
            finally:
                set_social_autonomy_store_for_tests(None)

            # Firestore backend (fake)
            fake_store = _FakeStore(_profile(status=status))
            set_social_autonomy_store_for_tests(fake_store)
            try:
                fs_result = _autonomy_apply_reasons(channel=channel, action=action)  # type: ignore[arg-type]
            finally:
                set_social_autonomy_store_for_tests(None)

            assert file_result == fs_result, (
                f"Parity failed for status={status!r} channel={channel!r} action={action!r}; "
                f"file={file_result!r}, firestore={fs_result!r}"
            )
