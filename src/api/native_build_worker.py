"""Internal worker endpoint for HAM Native Builder v2 — out-of-process execution.

POST /api/internal/native-build/execute

Cloud Tasks (or any authenticated internal caller) pushes a
:class:`NativeBuildExecuteEnvelope` here. The handler:
  1. Validates the OIDC token (same verifier / env as the plan dispatcher).
  2. Parses the body as a NativeBuildExecuteEnvelope (extra="forbid").
  3. Loads the durable execution context persisted by ``import_job_id``.
  4. Idempotency: if the job is already terminal, returns 200 and exits.
  5. Calls ``execute_native_build_job`` by id — running the bounded Hermes build
     off the chat request path — and returns 200.

Auth reuses :func:`src.api.internal_dispatcher._validate_oidc_token`, so
``HAM_CLOUD_TASKS_SERVICE_ACCOUNT`` + ``HAM_DISPATCHER_AUDIENCE`` gate the
endpoint (503 when unset) and the same service account / audience used by the
existing worker pipeline authorize native-build pushes.

No build-kit internals, raw JSON bundles, env names, provider ids, digests, or
secrets are returned to callers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from src.api.internal_dispatcher import _validate_oidc_token
from src.ham.builder_native_hermes import (
    NATIVE_BUILD_PHASE_FAILED,
    execute_native_build_job,
)
from src.ham.native_build_worker_enqueue import NativeBuildExecuteEnvelope
from src.persistence.builder_source_store import get_builder_source_store
from src.persistence.native_build_context_store import get_native_build_context_store

_LOG = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])

_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

_WORKER_ERROR_CODE = "HAM_NATIVE_BUILDER_V2_EXECUTOR_ERROR"
_WORKER_ERROR_MESSAGE = "HAM Native Builder could not complete the native build."


@router.post("/api/internal/native-build/execute")
async def execute_native_build(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Run a queued native build by job id. Returns 200 once the build resolves."""
    _validate_oidc_token(authorization)

    try:
        body_json = json.loads((await request.body()).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NATIVE_BUILD_WORKER_BODY_INVALID",
                    "message": f"Request body is not valid JSON: {exc}",
                }
            },
        ) from exc

    try:
        envelope = NativeBuildExecuteEnvelope.model_validate(body_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NATIVE_BUILD_WORKER_ENVELOPE_INVALID",
                    "message": f"Request body does not match the native build envelope: {exc}",
                }
            },
        ) from exc

    store = get_builder_source_store()
    context = get_native_build_context_store().get_native_build_context(
        import_job_id=envelope.import_job_id
    )
    if context is None:
        # No durable context (already cleaned up, or never created) — non-retryable.
        _LOG.info(
            "native-build worker: no context for import_job_id=%s — idempotent skip",
            envelope.import_job_id,
        )
        return {"ok": True, "import_job_id": envelope.import_job_id, "skipped": True}

    job = store.get_import_job(import_job_id=context.import_job_id)
    if job is None:
        # Context exists but import job row is missing (split store or cleanup) — non-retryable.
        _LOG.info(
            "native-build worker: no import job for import_job_id=%s — idempotent skip",
            context.import_job_id,
        )
        return {"ok": True, "import_job_id": context.import_job_id, "skipped": True}

    if job.status in _TERMINAL_STATUSES:
        _LOG.info(
            "native-build worker: import_job_id=%s already terminal (%s) — idempotent skip",
            context.import_job_id,
            job.status,
        )
        return {
            "ok": True,
            "import_job_id": context.import_job_id,
            "status": job.status,
            "skipped": True,
        }

    try:
        result = execute_native_build_job(
            import_job_id=context.import_job_id,
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            session_id=context.session_id,
            user_prompt=context.user_prompt,
            created_by=context.created_by,
        )
    except Exception as exc:  # noqa: BLE001
        _LOG.exception(
            "native-build worker: execution crashed for import_job_id=%s",
            context.import_job_id,
        )
        try:
            store.mark_import_job_failed(
                import_job_id=context.import_job_id,
                phase=NATIVE_BUILD_PHASE_FAILED,
                error_code=_WORKER_ERROR_CODE,
                error_message=_WORKER_ERROR_MESSAGE,
            )
        except KeyError:
            _LOG.info(
                "native-build worker: import job missing while marking failed for import_job_id=%s",
                context.import_job_id,
            )
        except Exception:  # noqa: BLE001
            _LOG.exception(
                "native-build worker: failed to mark import_job_id=%s failed",
                context.import_job_id,
            )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "NATIVE_BUILD_WORKER_EXEC_FAILED",
                    "message": "Native build execution failed.",
                }
            },
        ) from exc

    status = str((result.get("ham_native_builder") or {}).get("status") or "")
    return {"ok": True, "import_job_id": context.import_job_id, "status": status, "skipped": False}
