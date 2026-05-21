"""Default-deny regression tests for the autonomous tick runner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.ham.social_autonomy.store import social_autonomy_path


def test_default_deny_missing_profile_for_new_tick_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.tick import (
        AUTONOMY_PROFILE_MISSING,
        run_social_autonomy_tick,
    )

    target = tmp_path / "profile.json"
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))

    result = run_social_autonomy_tick(
        store_path=tmp_path,
        now=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
    )

    assert result.ran is False
    assert result.actions_taken == []
    assert result.blocked_reasons == [AUTONOMY_PROFILE_MISSING]
    assert social_autonomy_path(tmp_path) == target
    assert not target.exists()
