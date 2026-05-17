"""Unit tests for the Custom Builder persistence store."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.ham.custom_builder import CustomBuilderProfile
from src.persistence.custom_builder_store import (
    FirestoreCustomBuilderStore,
    LocalJsonCustomBuilderStore,
    build_custom_builder_store,
    get_profile,
    list_profiles_for_workspace,
    put_profile,
    soft_delete_profile,
    workspace_builder_scope_key,
)

_SECRET_LIKE_RE = re.compile(r"[A-Za-z0-9]{32,}")


def _profile(
    *,
    builder_id: str = "game-builder",
    workspace_id: str = "ws_a",
    updated_at: str = "2026-05-16T12:00:00Z",
    enabled: bool = True,
    **overrides: Any,
) -> CustomBuilderProfile:
    kwargs: dict[str, Any] = {
        "builder_id": builder_id,
        "workspace_id": workspace_id,
        "owner_user_id": "user_owner",
        "name": "Game Builder",
        "created_at": "2026-05-16T12:00:00Z",
        "updated_at": updated_at,
        "updated_by": "user_owner",
        "enabled": enabled,
    }
    kwargs.update(overrides)
    return CustomBuilderProfile(**kwargs)


def test_workspace_builder_scope_key_stable() -> None:
    assert workspace_builder_scope_key("ws_a", "game-builder") == (
        "workspace:ws_a:builder:game-builder"
    )


def test_local_store_round_trip(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    profile = _profile()
    put_profile(store, profile)
    fetched = get_profile(store, "ws_a", "game-builder")
    assert fetched == profile


def test_local_store_missing_returns_none(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    assert get_profile(store, "ws_a", "missing") is None


def test_local_store_list_by_workspace(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    put_profile(store, _profile(builder_id="game-builder", updated_at="2026-05-16T12:00:00Z"))
    put_profile(
        store,
        _profile(builder_id="docs-builder", updated_at="2026-05-16T13:00:00Z"),
    )
    put_profile(
        store,
        _profile(
            builder_id="other-builder",
            workspace_id="ws_b",
            updated_at="2026-05-16T14:00:00Z",
        ),
    )
    ws_a = list_profiles_for_workspace(store, "ws_a")
    ws_b = list_profiles_for_workspace(store, "ws_b")
    assert [p.builder_id for p in ws_a] == ["docs-builder", "game-builder"]
    assert [p.builder_id for p in ws_b] == ["other-builder"]


def test_soft_delete_retains_row_and_disables(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    put_profile(store, _profile())
    deleted = soft_delete_profile(
        store,
        "ws_a",
        "game-builder",
        updated_by="user_admin",
        updated_at="2026-05-16T15:00:00Z",
    )
    assert deleted is not None
    assert deleted.enabled is False
    assert deleted.updated_by == "user_admin"
    fetched = get_profile(store, "ws_a", "game-builder")
    assert fetched is not None
    assert fetched.enabled is False
    listed = list_profiles_for_workspace(store, "ws_a")
    assert [p.builder_id for p in listed] == ["game-builder"]


def test_soft_delete_missing_returns_none(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    result = soft_delete_profile(
        store,
        "ws_a",
        "absent",
        updated_by="user_admin",
        updated_at="2026-05-16T15:00:00Z",
    )
    assert result is None


def test_no_secret_in_serialized_local_blob(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    profile = _profile(model_ref="openrouter/anthropic/claude-sonnet-4.6")
    put_profile(store, profile)
    files = list((tmp_path / "builders").glob("cb_*.json"))
    assert files, "expected one persisted blob"
    blob = files[0].read_text(encoding="utf-8")
    matches = _SECRET_LIKE_RE.findall(blob)
    assert matches == [], f"serialized blob contains secret-shaped substring: {matches!r}"


def test_firestore_store_calls_collection_and_doc() -> None:
    mock_client = MagicMock()
    store = FirestoreCustomBuilderStore("ham_custom_builders", client=mock_client)
    profile = _profile()
    put_profile(store, profile)
    scope_key = workspace_builder_scope_key("ws_a", "game-builder")
    expected_doc_id = "cb_" + hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
    mock_client.collection.assert_called_with("ham_custom_builders")
    mock_client.collection.return_value.document.assert_called_with(expected_doc_id)
    set_call = mock_client.collection.return_value.document.return_value.set
    assert set_call.called
    args, kwargs = set_call.call_args
    payload = args[0]
    assert payload["scope_key"] == scope_key
    assert payload["workspace_id"] == "ws_a"
    assert payload["profile"]["builder_id"] == "game-builder"
    assert kwargs.get("merge") is True


def test_firestore_list_uses_where_workspace_id() -> None:
    mock_client = MagicMock()
    mock_client.collection.return_value.where.return_value.stream.return_value = iter([])
    store = FirestoreCustomBuilderStore("ham_custom_builders", client=mock_client)
    result = list_profiles_for_workspace(store, "ws_a")
    assert result == []
    mock_client.collection.return_value.where.assert_called_with("workspace_id", "==", "ws_a")
    mock_client.collection.return_value.where.return_value.stream.assert_called_once()


def test_firestore_collection_override_env() -> None:
    mock_client = MagicMock()
    store = FirestoreCustomBuilderStore("custom_coll", client=mock_client)
    put_profile(store, _profile())
    mock_client.collection.assert_called_with("custom_coll")


def test_firestore_get_returns_none_when_doc_missing() -> None:
    mock_client = MagicMock()
    snap = MagicMock()
    snap.exists = False
    mock_client.collection.return_value.document.return_value.get.return_value = snap
    store = FirestoreCustomBuilderStore("ham_custom_builders", client=mock_client)
    assert get_profile(store, "ws_a", "absent") is None


def test_build_store_factory_local_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "HAM_CUSTOM_BUILDER_STORE",
        "HAM_WORKSPACE_STORE_BACKEND",
        "HAM_CUSTOM_BUILDER_FIRESTORE_COLLECTION",
        "HAM_CUSTOM_BUILDER_FIRESTORE_PROJECT",
        "HAM_CUSTOM_BUILDER_FIRESTORE_DATABASE",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_LOCAL_PATH", str(tmp_path / "builders"))
    store = build_custom_builder_store()
    assert isinstance(store, LocalJsonCustomBuilderStore)


def test_build_store_factory_firestore_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_STORE", "firestore")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_FIRESTORE_COLLECTION", "ham_custom_builders_test")

    constructed: dict[str, Any] = {}

    class _StubClient:
        def __init__(self, **kwargs: Any) -> None:
            constructed.update(kwargs)

        def collection(self, _name: str) -> Any:
            return MagicMock()

    import src.persistence.custom_builder_store as mod

    monkeypatch.setattr(mod.firestore, "Client", _StubClient)
    store = build_custom_builder_store()
    assert isinstance(store, FirestoreCustomBuilderStore)


def test_local_store_falls_back_to_workspace_store_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HAM_CUSTOM_BUILDER_STORE", raising=False)
    monkeypatch.setenv("HAM_WORKSPACE_STORE_BACKEND", "local")
    monkeypatch.setenv("HAM_CUSTOM_BUILDER_LOCAL_PATH", str(tmp_path / "builders"))
    store = build_custom_builder_store()
    assert isinstance(store, LocalJsonCustomBuilderStore)


def test_local_blob_layout_has_workspace_id_for_listing(tmp_path: Path) -> None:
    store = LocalJsonCustomBuilderStore(tmp_path / "builders")
    put_profile(store, _profile())
    files = list((tmp_path / "builders").glob("cb_*.json"))
    raw = json.loads(files[0].read_text(encoding="utf-8"))
    assert raw["workspace_id"] == "ws_a"
    assert raw["scope_key"] == "workspace:ws_a:builder:game-builder"
    assert raw["profile"]["builder_id"] == "game-builder"
