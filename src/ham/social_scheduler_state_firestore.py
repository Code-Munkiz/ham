"""Firestore-backed social scheduler state store (M1 F6 implementation).

Implements the ``FirestoreSocialSchedulerStateStore`` backend for the
``SocialSchedulerStateStoreProtocol``. Selected by the factory in
:mod:`src.ham.social_scheduler_state_store` when
``HAM_SOCIAL_SCHEDULER_STATE_BACKEND=firestore``.

Collection layout::

    ham_social_scheduler_state/{_SINGLETON_DOC_ID}

The scheduler state is a singleton document — one document per deployment.
The document ID is fixed at ``"singleton"``.  Each document stores:

- ``scheduler_enabled`` (bool)
- ``last_scheduled_tick_at`` (ISO 8601 string or absent)
- ``last_tick_summary`` (dict or absent)

Defaults:
    When no document exists, ``read_state()`` returns
    ``SocialSchedulerState(scheduler_enabled=False, last_scheduled_tick_at=None,
    last_tick_summary=None)`` — the safe default.

Fail-closed:
    Any exception from the Firestore SDK is wrapped in
    :class:`FirestoreSocialSchedulerStateStoreError` and re-raised.  The store
    **never** silently falls back to the file backend.

Per-store env-var overrides::

    HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_PROJECT_ID  -> HAM_FIRESTORE_PROJECT_ID
    HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_DATABASE    -> HAM_FIRESTORE_DATABASE
    HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_COLLECTION  (default ham_social_scheduler_state)
"""

from __future__ import annotations

import os
from typing import Any

from src.ham.social_scheduler_state_store import SocialSchedulerState

_FS_PROJECT_ENV = "HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_PROJECT_ID"
_FS_DATABASE_ENV = "HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_DATABASE"
_FS_COLLECTION_ENV = "HAM_SOCIAL_SCHEDULER_STATE_FIRESTORE_COLLECTION"
_FALLBACK_PROJECT_ENV = "HAM_FIRESTORE_PROJECT_ID"
_FALLBACK_DATABASE_ENV = "HAM_FIRESTORE_DATABASE"
_DEFAULT_COLLECTION = "ham_social_scheduler_state"

# Fixed document ID for the singleton scheduler-state document.
_SINGLETON_DOC_ID = "singleton"


def _resolve_env(primary: str, fallback: str | None = None) -> str | None:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    if fallback is not None:
        val = (os.environ.get(fallback) or "").strip()
        if val:
            return val
    return None


class FirestoreSocialSchedulerStateStoreError(RuntimeError):
    """Wrapper for unexpected errors from the Firestore SDK.

    Raised by every method when the Firestore client raises, ensuring callers
    never silently swallow SDK errors and the API layer can convert them to
    structured ``503 firestore_unavailable`` responses.
    """


class FirestoreSocialSchedulerStateStore:
    """Firestore-backed social scheduler state store.

    Satisfies :class:`~src.ham.social_scheduler_state_store.SocialSchedulerStateStoreProtocol`.

    The constructor accepts an injected ``client`` for tests; in production
    the real ``google.cloud.firestore.Client`` is constructed lazily on first
    method call so importing this module never contacts Firestore at import time.

    State is stored as a singleton document at
    ``{collection}/{_SINGLETON_DOC_ID}``.  ``read_state()`` returns
    safe defaults (``scheduler_enabled=False``, both timestamps ``None``) when
    the document is absent.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project or _resolve_env(_FS_PROJECT_ENV, _FALLBACK_PROJECT_ENV)
        self._database = database or _resolve_env(_FS_DATABASE_ENV, _FALLBACK_DATABASE_ENV)
        coll = collection or _resolve_env(_FS_COLLECTION_ENV) or _DEFAULT_COLLECTION
        self._coll_name = coll.strip() or _DEFAULT_COLLECTION
        self._client = client

    # ------------------------------------------------------------------
    # Lazy client helper
    # ------------------------------------------------------------------

    def _db(self) -> Any:
        """Return the Firestore client, constructing it lazily when not injected."""
        if self._client is not None:
            return self._client
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            msg = (
                "google-cloud-firestore is required when "
                "HAM_SOCIAL_SCHEDULER_STATE_BACKEND=firestore."
            )
            raise FirestoreSocialSchedulerStateStoreError(msg) from exc
        kwargs: dict[str, Any] = {}
        if self._project:
            kwargs["project"] = self._project
        if self._database:
            kwargs["database"] = self._database
        self._client = firestore.Client(**kwargs) if kwargs else firestore.Client()
        return self._client

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def read_state(self) -> SocialSchedulerState:
        """Return the current scheduler state; returns safe defaults when absent.

        Reads the singleton document from Firestore.  When the document does not
        exist, returns ``SocialSchedulerState()`` with
        ``scheduler_enabled=False``, ``last_scheduled_tick_at=None``, and
        ``last_tick_summary=None``.

        Returns:
            The current :class:`~src.ham.social_scheduler_state_store.SocialSchedulerState`.

        Raises:
            FirestoreSocialSchedulerStateStoreError: On any Firestore SDK error.
        """
        db = self._db()
        try:
            snap = db.collection(self._coll_name).document(_SINGLETON_DOC_ID).get()
        except FirestoreSocialSchedulerStateStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialSchedulerStateStoreError(
                f"Firestore read_state failed: {exc}"
            ) from exc

        if not snap.exists:
            return SocialSchedulerState()

        data = snap.to_dict() or {}
        try:
            return SocialSchedulerState.model_validate(data)
        except Exception:  # noqa: BLE001
            # Defensive: corrupt document → safe defaults
            return SocialSchedulerState()

    def write_state(self, state: SocialSchedulerState) -> None:
        """Persist the scheduler state as the singleton document.

        Serializes the :class:`~src.ham.social_scheduler_state_store.SocialSchedulerState`
        via ``model_dump(mode="json", exclude_none=True)`` and overwrites the
        singleton document at ``{collection}/{_SINGLETON_DOC_ID}`` using
        Firestore ``set()`` (full document replace, atomic at the document level).

        Args:
            state: The scheduler state to persist.

        Raises:
            FirestoreSocialSchedulerStateStoreError: On any Firestore SDK error.
        """
        db = self._db()
        # Serialize to a JSON-compatible dict; exclude_none=True keeps the
        # document clean (absent fields read back as Pydantic defaults).
        payload: dict[str, Any] = state.model_dump(mode="json", exclude_none=True)
        try:
            db.collection(self._coll_name).document(_SINGLETON_DOC_ID).set(payload)
        except FirestoreSocialSchedulerStateStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FirestoreSocialSchedulerStateStoreError(
                f"Firestore write_state failed: {exc}"
            ) from exc


__all__ = [
    "FirestoreSocialSchedulerStateStore",
    "FirestoreSocialSchedulerStateStoreError",
]
