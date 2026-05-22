"""Env-switch factory tests for the social delivery log store.

VAL-M15-M1-STORE-ENVSWITCH-DELIVERY-015
"""

from __future__ import annotations

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
