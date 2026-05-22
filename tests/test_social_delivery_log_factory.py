"""Env-switch factory tests for the social delivery log store.

VAL-M15-M1-STORE-ENVSWITCH-DELIVERY-015
VAL-M15-M1-STORE-FAILCLOSED-DELIVERY-021
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.ham.social_delivery_log import (
    SocialDeliveryLogFileStore,
    build_social_delivery_log_store,
    set_social_delivery_log_store_for_tests,
)


class TestEnvSwitchSelectsBackend:
    """VAL-M15-M1-STORE-ENVSWITCH-DELIVERY-015"""

    def test_env_switch_selects_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_social_delivery_log_store_for_tests(None)

        monkeypatch.delenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", raising=False)
        assert isinstance(build_social_delivery_log_store(), SocialDeliveryLogFileStore)

        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "file")
        assert isinstance(build_social_delivery_log_store(), SocialDeliveryLogFileStore)

        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        store_fs = build_social_delivery_log_store()
        from src.ham.social_delivery_log_firestore import FirestoreSocialDeliveryLogStore

        assert isinstance(store_fs, FirestoreSocialDeliveryLogStore)

    def test_unknown_backend_falls_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "mystery")
        assert isinstance(build_social_delivery_log_store(), SocialDeliveryLogFileStore)


class TestFirestoreFailClosedDelivery:
    """VAL-M15-M1-STORE-FAILCLOSED-DELIVERY-021

    With HAM_SOCIAL_DELIVERY_LOG_BACKEND=firestore and a fake client that
    raises on .stream, count_actions_in_window (or its protocol equivalent)
    surfaces a typed error rather than scanning the JSONL fallback.
    """

    def test_firestore_failure_does_not_fall_back_to_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from src.ham.social_delivery_log_firestore import (
            FirestoreSocialDeliveryLogStore,
            FirestoreSocialDeliveryLogStoreError,
        )

        # Build a Firestore store
        monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_BACKEND", "firestore")
        set_social_delivery_log_store_for_tests(None)

        # Create a failing fake client
        class _FailingCollection:
            def stream(self):
                raise RuntimeError("Simulated Firestore SDK error")

            def document(self, doc_id):
                raise RuntimeError("Simulated Firestore SDK error")

        class _FailingClient:
            def collection(self, name: str) -> _FailingCollection:
                return _FailingCollection()

        store = FirestoreSocialDeliveryLogStore(client=_FailingClient())

        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

        # iter_records_in_window must surface a typed error, not return silently
        with pytest.raises(FirestoreSocialDeliveryLogStoreError):
            list(store.iter_records_in_window(start=now, end=now))

        # Verify no file I/O: the JSONL fallback file was never created
        jsonl_path = tmp_path / "social_delivery_log.jsonl"
        assert not jsonl_path.exists(), (
            "Firestore failure caused a silent fallback to the file backend"
        )

    def test_append_record_raises_on_sdk_error(self) -> None:
        from src.ham.social_delivery_log_firestore import (
            FirestoreSocialDeliveryLogStore,
            FirestoreSocialDeliveryLogStoreError,
        )

        class _FailingCollection:
            def document(self, doc_id):
                class _FailDoc:
                    def set(self, data):
                        raise RuntimeError("Simulated SDK write error")

                return _FailDoc()

        class _FailingClient:
            def collection(self, name: str):
                return _FailingCollection()

        store = FirestoreSocialDeliveryLogStore(client=_FailingClient())
        record = {
            "provider_id": "telegram",
            "idempotency_key": "key-fail",
            "status": "sent",
            "executed_at": "2026-05-20T12:00:00Z",
        }
        with pytest.raises(FirestoreSocialDeliveryLogStoreError):
            store.append_record(record)
