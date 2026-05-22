"""Verify the per-store Firestore env-var override chain.

VAL-M15-M1-STORE-FIRESTORE-ENV-VARS-028

Each store constructor reads per-store env vars (primary) falling back to the
shared workspace vars (fallback). This test verifies the resolution logic for
all six stores.
"""

from __future__ import annotations

import pytest


class TestPerStoreEnvOverridesSharedFallback:
    """VAL-M15-M1-STORE-FIRESTORE-ENV-VARS-028"""

    def test_autonomy_store_uses_per_store_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID", "my-project")
        monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "fallback-project")
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore

        store = FirestoreSocialAutonomyStore()
        assert store._project == "my-project"

    def test_autonomy_store_falls_back_to_shared_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_FIRESTORE_PROJECT_ID", raising=False)
        monkeypatch.setenv("HAM_FIRESTORE_PROJECT_ID", "shared-project")
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore

        store = FirestoreSocialAutonomyStore()
        assert store._project == "shared-project"

    def test_autonomy_store_uses_per_store_collection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION", "custom_autonomy_coll")
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore

        store = FirestoreSocialAutonomyStore()
        assert store._coll_name == "custom_autonomy_coll"

    def test_delivery_log_store_per_store_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_PROJECT_ID", "delivery-project")
        from src.ham.social_delivery_log_firestore import FirestoreSocialDeliveryLogStore

        store = FirestoreSocialDeliveryLogStore()
        assert store._project == "delivery-project"

    def test_learning_store_per_store_collection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_HAMGOMOON_LEARNING_FIRESTORE_COLLECTION", "custom_learning_coll")
        from src.ham.hamgomoon_learning.firestore_store import FirestoreHamgomoonLearningStore

        store = FirestoreHamgomoonLearningStore()
        assert store._coll_name == "custom_learning_coll"

    def test_transcript_store_per_store_collection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_COLLECTION", "custom_transcript_coll")
        from src.ham.social_telegram_transcript_firestore import FirestoreTelegramTranscriptStore

        store = FirestoreTelegramTranscriptStore()
        assert store._coll_name == "custom_transcript_coll"

    def test_offset_store_per_store_collection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_TELEGRAM_OFFSET_FIRESTORE_COLLECTION", "custom_offset_coll")
        from src.ham.social_telegram_offset_firestore import FirestoreTelegramOffsetStore

        store = FirestoreTelegramOffsetStore()
        assert store._coll_name == "custom_offset_coll"

    def test_scheduler_state_store_per_store_collection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(
            "HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_COLLECTION", "custom_scheduler_coll"
        )
        from src.ham.social_scheduler_state_firestore import FirestoreSocialSchedulerStateStore

        store = FirestoreSocialSchedulerStateStore()
        assert store._coll_name == "custom_scheduler_coll"

    def test_default_collections(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no env vars set, each store uses its documented default collection."""
        for env_var in (
            "HAM_SOCIAL_AUTONOMY_FIRESTORE_COLLECTION",
            "HAM_SOCIAL_DELIVERY_LOG_FIRESTORE_COLLECTION",
            "HAM_HAMGOMOON_LEARNING_FIRESTORE_COLLECTION",
            "HAM_TELEGRAM_TRANSCRIPT_FIRESTORE_COLLECTION",
            "HAM_TELEGRAM_OFFSET_FIRESTORE_COLLECTION",
            "HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_COLLECTION",
        ):
            monkeypatch.delenv(env_var, raising=False)

        from src.ham.hamgomoon_learning.firestore_store import FirestoreHamgomoonLearningStore
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore
        from src.ham.social_delivery_log_firestore import FirestoreSocialDeliveryLogStore
        from src.ham.social_scheduler_state_firestore import FirestoreSocialSchedulerStateStore
        from src.ham.social_telegram_offset_firestore import FirestoreTelegramOffsetStore
        from src.ham.social_telegram_transcript_firestore import FirestoreTelegramTranscriptStore

        assert FirestoreSocialAutonomyStore()._coll_name == "ham_social_autonomy_profiles"
        assert FirestoreSocialDeliveryLogStore()._coll_name == "ham_social_delivery_log"
        assert FirestoreHamgomoonLearningStore()._coll_name == "ham_hamgomoon_learning"
        assert FirestoreTelegramTranscriptStore()._coll_name == "ham_social_telegram_transcripts"
        assert FirestoreTelegramOffsetStore()._coll_name == "ham_social_telegram_poller_state"
        assert FirestoreSocialSchedulerStateStore()._coll_name == "ham_social_scheduler_state"
