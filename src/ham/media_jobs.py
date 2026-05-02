"""In-memory media job registry for local/dev async generation flows."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any

_ID_PREFIX = "hammj_"
_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def is_safe_media_job_id(job_id: str) -> bool:
    s = (job_id or "").strip()
    if not s.startswith(_ID_PREFIX):
        return False
    suffix = s[len(_ID_PREFIX) :]
    return bool(suffix) and all(c.isalnum() or c in "_-" for c in suffix)


def new_media_job_id() -> str:
    return f"{_ID_PREFIX}{secrets.token_hex(24)}"


def create_media_job(*, status: str = "queued", owner_key: str = "") -> dict[str, Any]:
    job_id = new_media_job_id()
    now = int(time.time())
    rec: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "owner_key": owner_key,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        _JOBS[job_id] = rec
    return dict(rec)


def get_media_job(job_id: str) -> dict[str, Any] | None:
    if not is_safe_media_job_id(job_id):
        return None
    with _LOCK:
        rec = _JOBS.get(job_id)
        return dict(rec) if rec is not None else None


def update_media_job(job_id: str, **patch: Any) -> dict[str, Any] | None:
    if not is_safe_media_job_id(job_id):
        return None
    with _LOCK:
        rec = _JOBS.get(job_id)
        if rec is None:
            return None
        rec.update(patch)
        rec["updated_at"] = int(time.time())
        _JOBS[job_id] = rec
        return dict(rec)
