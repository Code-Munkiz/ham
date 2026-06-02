"""Durable NativeBuildContext store — file-backed + Firestore parity.

Covers the requirement that the HAM Native Builder v2 execution context survive
across Cloud Run instances: it must be loadable by ``import_job_id`` from a store
instance other than the one that wrote it (different process / instance), in both
the file-backed (local/dev) and Firestore (hosted) backends, and the backend
selector must wire the right implementation. No build-kit internals are stored.
"""

from __future__ import annotations

import json
from typing import Any

from src.persistence.firestore_native_build_context_store import (
    FirestoreNativeBuildContextStore,
)
from src.persistence.native_build_context_store import (
    NativeBuildContext,
    NativeBuildContextStore,
    build_native_build_context_store,
)

_FORBIDDEN_TOKENS = (
    "registry_v2",
    "proposal_digest",
    "base_revision",
    "hermes_native_build",
    "inline_files",
    "hermes-builder",
    "hermes_gateway",
    "openrouter",
)


def _ctx(import_job_id: str = "ijob_abc", **over: Any) -> NativeBuildContext:
    base = {
        "import_job_id": import_job_id,
        "workspace_id": "ws_v2",
        "project_id": "proj_v2",
        "session_id": "sess_v2",
        "user_prompt": "build a small native app",
        "created_by": "user_v2",
    }
    base.update(over)
    return NativeBuildContext(**base)


# ---------------------------------------------------------------------------
# Minimal in-memory Firestore fake (flat collection/document set+get)
# ---------------------------------------------------------------------------


class _FakeDocSnap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data) if self._data is not None else {}


class _FakeDocRef:
    def __init__(self, bag: dict[str, dict[str, Any]], doc_id: str) -> None:
        self._bag = bag
        self._id = doc_id

    def set(self, payload: dict[str, Any]) -> None:
        self._bag[self._id] = dict(payload)

    def get(self) -> _FakeDocSnap:
        return _FakeDocSnap(self._bag.get(self._id))


class _FakeCollection:
    def __init__(self, bag: dict[str, dict[str, Any]]) -> None:
        self._bag = bag

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._bag, doc_id)


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self.tree: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.tree.setdefault(name, {}))


# ---------------------------------------------------------------------------
# File-backed store
# ---------------------------------------------------------------------------


def test_file_store_cross_instance_reload(tmp_path) -> None:
    """A worker on another instance (a fresh store over the same file) loads context."""
    path = tmp_path / "native_build_contexts.json"
    writer = NativeBuildContextStore(store_path=path)
    writer.put_native_build_context(_ctx("ijob_x"))

    reader = NativeBuildContextStore(store_path=path)
    loaded = reader.get_native_build_context(import_job_id="ijob_x")
    assert loaded is not None
    assert loaded.import_job_id == "ijob_x"
    assert loaded.workspace_id == "ws_v2"
    assert loaded.project_id == "proj_v2"
    assert loaded.session_id == "sess_v2"
    assert loaded.user_prompt == "build a small native app"
    assert loaded.created_by == "user_v2"


def test_file_store_get_unknown_returns_none(tmp_path) -> None:
    store = NativeBuildContextStore(store_path=tmp_path / "c.json")
    store.put_native_build_context(_ctx("ijob_a"))
    assert store.get_native_build_context(import_job_id="ijob_missing") is None


def test_file_store_get_blank_id_returns_none(tmp_path) -> None:
    store = NativeBuildContextStore(store_path=tmp_path / "c.json")
    assert store.get_native_build_context(import_job_id="") is None


def test_file_store_put_overwrites_same_job_id(tmp_path) -> None:
    path = tmp_path / "c.json"
    store = NativeBuildContextStore(store_path=path)
    store.put_native_build_context(_ctx("ijob_same", user_prompt="first"))
    store.put_native_build_context(_ctx("ijob_same", user_prompt="second"))

    loaded = store.get_native_build_context(import_job_id="ijob_same")
    assert loaded is not None
    assert loaded.user_prompt == "second"
    # Exactly one row persisted for the id (no duplicate accumulation).
    rows = json.loads(path.read_text(encoding="utf-8"))["native_build_contexts"]
    assert [r for r in rows if r["import_job_id"] == "ijob_same"] == rows
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Firestore-backed store (fake client, no network)
# ---------------------------------------------------------------------------


def test_firestore_store_put_then_get_by_id() -> None:
    store = FirestoreNativeBuildContextStore(client=_FakeFirestoreClient())
    store.put_native_build_context(_ctx("ijob_fs"))

    loaded = store.get_native_build_context(import_job_id="ijob_fs")
    assert loaded is not None
    assert loaded.import_job_id == "ijob_fs"
    assert loaded.user_prompt == "build a small native app"


def test_firestore_store_cross_instance_reload() -> None:
    """Two store instances over one Firestore client model two Cloud Run instances."""
    client = _FakeFirestoreClient()
    enqueuer = FirestoreNativeBuildContextStore(client=client)
    worker = FirestoreNativeBuildContextStore(client=client)

    enqueuer.put_native_build_context(_ctx("ijob_shared"))
    loaded = worker.get_native_build_context(import_job_id="ijob_shared")
    assert loaded is not None
    assert loaded.workspace_id == "ws_v2"
    assert loaded.created_by == "user_v2"


def test_firestore_store_doc_id_is_import_job_id() -> None:
    client = _FakeFirestoreClient()
    store = FirestoreNativeBuildContextStore(client=client, collection="native_build_contexts")
    store.put_native_build_context(_ctx("ijob_docid"))
    assert "ijob_docid" in client.tree["native_build_contexts"]


def test_firestore_store_get_missing_returns_none() -> None:
    store = FirestoreNativeBuildContextStore(client=_FakeFirestoreClient())
    assert store.get_native_build_context(import_job_id="ijob_nope") is None
    assert store.get_native_build_context(import_job_id="") is None


# ---------------------------------------------------------------------------
# Backend selector
# ---------------------------------------------------------------------------


def test_backend_selector_defaults_to_file(monkeypatch) -> None:
    monkeypatch.delenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", raising=False)
    assert isinstance(build_native_build_context_store(), NativeBuildContextStore)


def test_backend_selector_selects_firestore(monkeypatch) -> None:
    monkeypatch.setenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", "firestore")
    assert isinstance(build_native_build_context_store(), FirestoreNativeBuildContextStore)


def test_backend_selector_follows_builder_source_firestore(monkeypatch) -> None:
    monkeypatch.delenv("HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND", raising=False)
    monkeypatch.setenv("HAM_BUILDER_SOURCE_STORE_BACKEND", "firestore")
    assert isinstance(build_native_build_context_store(), FirestoreNativeBuildContextStore)


def test_context_payload_carries_no_internals() -> None:
    payload = json.dumps(_ctx().model_dump(mode="json")).lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in payload
