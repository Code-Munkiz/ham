"""Verify that google.cloud.firestore is NOT imported in file-mode (lazy import).

VAL-M15-M1-STORE-LAZY-IMPORT-026
"""

from __future__ import annotations

import sys

import pytest


def _evict_firestore() -> None:
    """Remove google.cloud.firestore from sys.modules if present."""
    to_remove = [k for k in sys.modules if k.startswith("google.cloud.firestore")]
    for key in to_remove:
        del sys.modules[key]


class TestFirestoreModuleNotImportedInFileMode:
    """VAL-M15-M1-STORE-LAZY-IMPORT-026"""

    def test_firestore_module_not_imported_in_file_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All six file-mode factory calls must not import google.cloud.firestore."""
        # Force file mode for all stores
        for env_var in (
            "HAM_SOCIAL_AUTONOMY_STORE_BACKEND",
            "HAM_SOCIAL_DELIVERY_LOG_BACKEND",
            "HAM_HAMGOMOON_LEARNING_BACKEND",
            "HAM_TELEGRAM_TRANSCRIPT_BACKEND",
            "HAM_TELEGRAM_OFFSET_BACKEND",
            "HAM_SOCIAL_SCHEDULER_STATE_BACKEND",
        ):
            monkeypatch.delenv(env_var, raising=False)

        # Reset all singletons
        from src.ham.hamgomoon_learning.store import set_hamgomoon_learning_store_for_tests
        from src.ham.social_autonomy.store import set_social_autonomy_store_for_tests
        from src.ham.social_delivery_log import set_social_delivery_log_store_for_tests
        from src.ham.social_scheduler_state_store import set_social_scheduler_state_store_for_tests
        from src.ham.social_telegram_offset_store import set_telegram_offset_store_for_tests
        from src.ham.social_telegram_transcript_store import set_telegram_transcript_store_for_tests

        for reset in (
            set_social_autonomy_store_for_tests,
            set_social_delivery_log_store_for_tests,
            set_hamgomoon_learning_store_for_tests,
            set_telegram_transcript_store_for_tests,
            set_telegram_offset_store_for_tests,
            set_social_scheduler_state_store_for_tests,
        ):
            reset(None)

        # Evict firestore from sys.modules
        _evict_firestore()

        # Invoke each factory in file mode
        from src.ham.hamgomoon_learning.store import build_hamgomoon_learning_store
        from src.ham.social_autonomy.store import build_social_autonomy_store
        from src.ham.social_delivery_log import build_social_delivery_log_store
        from src.ham.social_scheduler_state_store import build_social_scheduler_state_store
        from src.ham.social_telegram_offset_store import build_telegram_offset_store
        from src.ham.social_telegram_transcript_store import build_telegram_transcript_store

        build_social_autonomy_store()
        build_social_delivery_log_store()
        build_hamgomoon_learning_store()
        build_telegram_transcript_store()
        build_telegram_offset_store()
        build_social_scheduler_state_store()

        # google.cloud.firestore must NOT be in sys.modules
        firestore_keys = [k for k in sys.modules if k.startswith("google.cloud.firestore")]
        assert firestore_keys == [], (
            f"google.cloud.firestore was imported in file mode: {firestore_keys}"
        )
