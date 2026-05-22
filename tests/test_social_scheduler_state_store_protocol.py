"""Protocol conformance tests for the scheduler-state file-backend skeleton.

VAL-M15-M1-STORE-PROTOCOL-SCHEDSTATE-FILE-006
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.ham.social_scheduler_state_store import (
    SocialSchedulerState,
    SocialSchedulerStateFileStore,
    SocialSchedulerStateStoreProtocol,
    set_social_scheduler_state_store_for_tests,
)


class TestFileBackendConformsToProtocol:
    """VAL-M15-M1-STORE-PROTOCOL-SCHEDSTATE-FILE-006"""

    def test_file_backend_conforms_to_protocol(self) -> None:
        store = SocialSchedulerStateFileStore()
        assert isinstance(store, SocialSchedulerStateStoreProtocol)

    def test_default_state_has_scheduler_disabled(self, tmp_path: Path) -> None:
        """Empty state defaults: scheduler_enabled=False, last_scheduled_tick_at=None."""
        store = SocialSchedulerStateFileStore(path=tmp_path / "state.json")
        state = store.read_state()
        assert state.scheduler_enabled is False
        assert state.last_scheduled_tick_at is None

    def test_write_state_then_read_roundtrip(self, tmp_path: Path) -> None:
        store = SocialSchedulerStateFileStore(path=tmp_path / "state.json")
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        new_state = SocialSchedulerState(
            scheduler_enabled=True,
            last_scheduled_tick_at=now,
            last_tick_summary={"actions_taken": []},
        )
        store.write_state(new_state)
        recovered = store.read_state()
        assert recovered.scheduler_enabled is True
        assert recovered.last_scheduled_tick_at == now
        assert recovered.last_tick_summary == {"actions_taken": []}

    def test_read_state_returns_defaults_when_file_missing(self, tmp_path: Path) -> None:
        store = SocialSchedulerStateFileStore(path=tmp_path / "nonexistent.json")
        state = store.read_state()
        assert isinstance(state, SocialSchedulerState)
        assert state.scheduler_enabled is False
        assert state.last_scheduled_tick_at is None

    def test_set_scheduler_state_store_for_tests(self) -> None:
        custom = SocialSchedulerStateFileStore()
        set_social_scheduler_state_store_for_tests(custom)
        try:
            from src.ham.social_scheduler_state_store import get_social_scheduler_state_store

            assert get_social_scheduler_state_store() is custom
        finally:
            set_social_scheduler_state_store_for_tests(None)
