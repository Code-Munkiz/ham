from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import logging
import os
import re
import shlex
import time
import uuid
from ipaddress import ip_address
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Header, Query, UploadFile
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.clerk_gate import enforce_clerk_session_and_email_for_request, get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store, require_perm
from src.ham.builder_cloud_runtime_job_runner import run_persist_builder_cloud_runtime_job
from src.ham.builder_runtime_worker import (
    get_cloud_runtime_experiment_status,
    get_cloud_runtime_provider_capability_status,
    get_cloud_runtime_provider_mode,
    get_runtime_job_lifecycle_status,
)
from src.ham.builder_zip_intake import ZipSafetyError, read_zip_upload_bytes, validate_zip_upload
from src.ham.clerk_auth import HamActor, verify_clerk_session_jwt
from src.ham.clerk_email_access import require_ham_clerk_email_allowed
from src.ham.harness_capabilities import HARNESS_CAPABILITIES
from src.ham.worker_adapters.claude_agent_adapter import check_claude_agent_readiness
from src.ham.worker_adapters.cursor_adapter import check_cursor_readiness
from src.ham.workspace_models import WorkspaceContext
from src.ham.workspace_perms import PERM_WORKSPACE_READ, PERM_WORKSPACE_WRITE
from src.ham.workspace_resolver import (
    WorkspaceForbidden,
    WorkspaceNotFound,
    WorkspaceResolveError,
    resolve_workspace_context,
)
from src.persistence.builder_source_store import (
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)
from src.persistence.builder_runtime_store import PreviewEndpoint, get_builder_runtime_store
from src.persistence.builder_run_profile_store import LocalRunProfile, get_builder_run_profile_store
from src.persistence.builder_runtime_job_store import get_builder_runtime_job_store
from src.persistence.builder_visual_edit_request_store import (
    VisualEditRequest,
    get_builder_visual_edit_request_store,
)
from src.persistence.builder_usage_event_store import (
    UsageEvent,
    UsageEventAttribution,
    get_builder_usage_event_store,
)
from src.persistence.project_store import get_project_store
from src.persistence.workspace_store import WorkspaceStore
from src.registry.projects import ProjectRecord

router = APIRouter(tags=["builder-sources"])
_LOG = logging.getLogger(__name__)

_ZIP_ERROR_MESSAGES = {
    "ZIP_TOO_LARGE": "ZIP exceeds the maximum compressed size.",
    "ZIP_TOO_MANY_FILES": "ZIP has too many files.",
    "ZIP_UNCOMPRESSED_TOO_LARGE": "ZIP exceeds the maximum expanded size.",
    "ZIP_ENTRY_TOO_LARGE": "ZIP contains a file that exceeds size limits.",
    "ZIP_PATH_TRAVERSAL": "ZIP contains unsafe path traversal entries.",
    "ZIP_ABSOLUTE_PATH": "ZIP contains absolute path entries.",
    "ZIP_UNSAFE_SYMLINK": "ZIP contains unsafe symbolic link entries.",
    "ZIP_INVALID": "ZIP archive is invalid or unsafe.",
    "ZIP_EMPTY": "ZIP archive is empty.",
}
_PREVIEW_PROXY_ALLOWED_HOST_SUFFIXES = (".run.app",)
_PREVIEW_PROXY_TIMEOUT_SECONDS = 8.0
_PREVIEW_PROXY_MAX_BYTES = 2 * 1024 * 1024
_PREVIEW_PROXY_SESSION_COOKIE_NAME = "ham_preview_proxy_session"
_PREVIEW_PROXY_SESSION_TTL_SECONDS = 600
_ACTIVITY_STREAM_MAX_ITEMS = 24
_ACTIVITY_STREAM_MAX_EVENTS = 64
_ACTIVITY_STREAM_MAX_PAYLOAD_BYTES = 24 * 1024


def _int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _float_env(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _project_workspace_id(record: ProjectRecord) -> str | None:
    raw = record.metadata.get("workspace_id")
    if raw is None:
        raw = record.metadata.get("workspaceId")
    text = str(raw or "").strip()
    if text:
        return text
    # Firestore/registry records often set top-level workspace_id without duplicating metadata.
    top = getattr(record, "workspace_id", None)
    tail = str(top or "").strip()
    return tail or None


def _project_in_workspace_or_404(*, project_id: str, workspace_id: str) -> ProjectRecord:
    record = get_project_store().get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    project_workspace_id = _project_workspace_id(record)
    if project_workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {project_id!r}.",
                }
            },
        )
    return record


def _source_snapshot_for_project_or_404(
    *,
    workspace_id: str,
    project_id: str,
    snapshot_id: str,
) -> SourceSnapshot:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=workspace_id)
    sid = str(snapshot_id or "").strip()
    if not sid:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "SNAPSHOT_NOT_FOUND", "message": "Unknown source snapshot."}},
        )
    for row in get_builder_source_store().list_source_snapshots(
        workspace_id=workspace_id,
        project_id=project_id,
    ):
        if row.id == sid:
            return row
    raise HTTPException(
        status_code=404,
        detail={"error": {"code": "SNAPSHOT_NOT_FOUND", "message": "Unknown source snapshot."}},
    )


_SNAPSHOT_LISTING_CAP = 512
_SNAPSHOT_CONTENT_MAX_BYTES = 262_144


def _artifact_stem_from_uri(artifact_uri: str) -> str | None:
    text = str(artifact_uri or "").strip()
    prefix = "builder-artifact://"
    if text.startswith(prefix):
        stem = text[len(prefix) :].strip()
        return stem or None
    return None


def _artifact_root() -> Path:
    raw = (os.environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def _save_zip_artifact(*, workspace_id: str, project_id: str, payload: bytes) -> tuple[str, dict[str, Any]]:
    artifact_id = f"bzip_{uuid.uuid4().hex}"
    root = _artifact_root()
    target_dir = root / workspace_id / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{artifact_id}.zip"
    zip_path.write_bytes(payload)
    return (
        f"builder-artifact://{artifact_id}",
        {
            "artifact_id": artifact_id,
            "artifact_name": zip_path.name,
        },
    )


def _safe_zip_error_message(code: str) -> str:
    return _ZIP_ERROR_MESSAGES.get(code, "ZIP import failed.")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_local_preview_url(raw_url: str | None) -> str | None:
    text = str(raw_url or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.username or parts.password:
        return None
    if parts.scheme != "http":
        return None
    host = (parts.hostname or "").strip().lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return None
    if parts.port is None:
        return None
    netloc_host = f"[{host}]" if ":" in host else host
    return urlunsplit((parts.scheme, f"{netloc_host}:{parts.port}", parts.path or "/", "", ""))


def _is_blocked_proxy_host(host: str) -> bool:
    name = host.strip().lower()
    if not name:
        return True
    if name in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ip_address(name)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    return False


def _safe_trusted_proxy_host(raw: Any) -> str | None:
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if _SENSITIVE_VALUE_RE.search(text):
        return None
    if "://" in text or "/" in text:
        return None
    return text[:200]


def _allows_provider_owned_internal_upstream(*, runtime: Any | None, endpoint: PreviewEndpoint | None) -> bool:
    if runtime is None or endpoint is None:
        return False
    if str(runtime.mode or "").strip().lower() != "cloud":
        return False
    if str(endpoint.runtime_session_id or "").strip() != str(runtime.id or "").strip():
        return False
    meta = endpoint.metadata or {}
    provider = str(meta.get("provider") or "").strip().lower()
    internal_flag = str(meta.get("internal_upstream") or "").strip().lower()
    return provider == "gcp_gke_sandbox" and internal_flag in {"1", "true", "yes", "on"}


def _sanitize_cloud_proxy_upstream_url(
    *,
    raw_url: str | None,
    trusted_host: str | None = None,
    allow_internal: bool = False,
) -> str | None:
    text = str(raw_url or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    scheme = str(parts.scheme or "").strip().lower()
    if scheme not in {"https", "http"}:
        return None
    if scheme != "https" and not allow_internal:
        return None
    if parts.username or parts.password:
        return None
    if parts.query or parts.fragment:
        return None
    host = (parts.hostname or "").strip().lower()
    if not host:
        return None
    if allow_internal:
        try:
            maybe_ip = ip_address(host)
        except ValueError:
            maybe_ip = None
        is_internal = bool(
            (maybe_ip is not None and (maybe_ip.is_private or maybe_ip.is_loopback or maybe_ip.is_link_local))
            or host.endswith(".svc.cluster.local")
        )
        if not is_internal:
            return None
    else:
        if _is_blocked_proxy_host(host):
            return None
    allowed = host.endswith(_PREVIEW_PROXY_ALLOWED_HOST_SUFFIXES)
    if not allowed and trusted_host:
        allowed = host == trusted_host
    if allow_internal:
        allowed = True
    if not allowed:
        return None
    path = parts.path or "/"
    netloc = parts.netloc
    if ":" in host and not host.startswith("["):
        netloc = netloc.replace(host, f"[{host}]")
    return urlunsplit((scheme, netloc, path, "", ""))


def _cloud_proxy_preview_url(*, workspace_id: str, project_id: str) -> str:
    return f"/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/"


def _preview_proxy_cookie_path(*, workspace_id: str, project_id: str) -> str:
    return f"/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/"


def _preview_proxy_session_ttl_seconds() -> int:
    return _int_env(
        "HAM_BUILDER_PREVIEW_PROXY_SESSION_TTL_SECONDS",
        _PREVIEW_PROXY_SESSION_TTL_SECONDS,
        min_value=60,
        max_value=900,
    )


def _preview_proxy_auth_diag_enabled() -> bool:
    raw = str(os.environ.get("HAM_BUILDER_PREVIEW_PROXY_AUTH_DIAGNOSTICS") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _diag_str(value: Any, *, max_len: int = 128) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_len]


def _emit_preview_proxy_diag(payload: dict[str, Any]) -> None:
    if not _preview_proxy_auth_diag_enabled():
        return
    # Keep logs bounded and value-safe. This path intentionally logs only
    # booleans/status enums/ids and never raw auth material.
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            safe[key] = value
        elif value is None:
            safe[key] = None
        elif isinstance(value, (int, float)):
            safe[key] = value
        else:
            safe[key] = _diag_str(value, max_len=180)
    line = f"preview_proxy_auth_diag {json.dumps(safe, ensure_ascii=True, sort_keys=True)}"
    # Emit to stdout so Cloud Run captures diagnostics even when app loggers are not configured.
    print(line)
    _LOG.warning(line)


def _classify_proxy_upstream_error(exc: Exception) -> str:
    text = str(exc).strip().lower()
    if isinstance(exc, httpx.TimeoutException):
        return "connect_timeout"
    if "name or service not known" in text or "temporary failure in name resolution" in text:
        return "dns_failed"
    if "connection refused" in text:
        return "connection_refused"
    if "timed out" in text or "timeout" in text:
        return "connect_timeout"
    return "http_error"


def _emit_preview_proxy_upstream_diag(
    *,
    workspace_id: str,
    project_id: str,
    runtime_session_id: str | None,
    endpoint_id: str | None,
    proxy_target_present: bool,
    upstream_connect_status: str,
    upstream_http_status: int | None = None,
) -> None:
    _emit_preview_proxy_diag(
        {
            "route": "preview_proxy_upstream",
            "workspace_id": _diag_str(workspace_id),
            "project_id": _diag_str(project_id),
            "runtime_session_id": _diag_str(runtime_session_id),
            "endpoint_id": _diag_str(endpoint_id),
            "proxy_target_present": bool(proxy_target_present),
            "upstream_connect_status": _diag_str(upstream_connect_status),
            "upstream_http_status": upstream_http_status,
        }
    )


def _clerk_session_cookie_name() -> str:
    raw = str(os.environ.get("HAM_CLERK_SESSION_COOKIE_NAME") or "").strip()
    return raw or "__session"


def _preview_proxy_session_secret_bytes() -> bytes:
    # Prefer dedicated secret; fallback to existing service secret so signatures remain
    # valid across Cloud Run instances without broad env rewrites.
    for key in (
        "HAM_PREVIEW_PROXY_SESSION_SECRET",
        "HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY",
    ):
        raw = str(os.environ.get(key) or "").strip()
        if raw:
            return raw.encode("utf-8")
    return b"ham-preview-proxy-dev-secret"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padded = text + ("=" * ((4 - (len(text) % 4)) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign_preview_proxy_session_token(payload_b64: str) -> str:
    mac = hmac.new(
        _preview_proxy_session_secret_bytes(),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(mac)


def _mint_preview_proxy_session_token(
    *,
    workspace_id: str,
    project_id: str,
    actor_user_id: str,
    org_id: str | None,
    actor_email: str | None,
    org_role: str | None,
) -> tuple[str, int]:
    now = int(time.time())
    exp = now + _preview_proxy_session_ttl_seconds()
    payload = {
        "v": 1,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "actor_user_id": actor_user_id,
        "org_id": str(org_id or "").strip() or None,
        "actor_email": str(actor_email or "").strip() or None,
        "org_role": str(org_role or "").strip() or None,
        "exp": exp,
        "nonce": uuid.uuid4().hex,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig_b64 = _sign_preview_proxy_session_token(payload_b64)
    return f"{payload_b64}.{sig_b64}", exp


def _decode_preview_proxy_session_token(token: str | None) -> tuple[dict[str, Any] | None, str]:
    raw = str(token or "").strip()
    if not raw or "." not in raw:
        return None, "missing"
    payload_b64, sig_b64 = raw.split(".", 1)
    if not payload_b64 or not sig_b64:
        return None, "invalid_signature"
    expected = _sign_preview_proxy_session_token(payload_b64)
    if not hmac.compare_digest(expected, sig_b64):
        return None, "invalid_signature"
    try:
        payload_obj = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid_signature"
    if not isinstance(payload_obj, dict):
        return None, "invalid_signature"
    exp_raw = payload_obj.get("exp")
    try:
        exp = int(exp_raw)
    except (TypeError, ValueError):
        return None, "invalid_signature"
    if exp < int(time.time()):
        return None, "expired"
    return payload_obj, "valid"


def _preview_proxy_session_claim_match(
    *,
    claims: dict[str, Any],
    workspace_id: str,
    project_id: str,
) -> bool:
    claim_ws = str(claims.get("workspace_id") or "").strip()
    claim_project = str(claims.get("project_id") or "").strip()
    claim_user = str(claims.get("actor_user_id") or "").strip()
    if not claim_ws or not claim_project or not claim_user:
        return False
    return claim_ws == workspace_id and claim_project == project_id


def _preview_proxy_actor_from_claims(claims: dict[str, Any]) -> HamActor | None:
    user_id = str(claims.get("actor_user_id") or "").strip()
    if not user_id:
        return None
    return HamActor(
        user_id=user_id,
        org_id=str(claims.get("org_id") or "").strip() or None,
        session_id=f"preview_proxy_cookie_{str(claims.get('nonce') or '').strip()[:32]}",
        email=str(claims.get("actor_email") or "").strip() or None,
        permissions=frozenset(),
        org_role=str(claims.get("org_role") or "").strip() or None,
        raw_permission_claim="preview_proxy_cookie",
    )


def _resolve_workspace_context_or_http(
    *,
    actor: HamActor,
    workspace_id: str,
    store: WorkspaceStore,
) -> WorkspaceContext:
    try:
        return resolve_workspace_context(actor, workspace_id, store)
    except (WorkspaceForbidden, WorkspaceNotFound) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.http_payload()) from exc
    except WorkspaceResolveError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=exc.status_code, detail=exc.http_payload()) from exc


def _require_preview_proxy_read_perm(ctx: WorkspaceContext) -> WorkspaceContext:
    if PERM_WORKSPACE_READ not in ctx.perms:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "HAM_PERMISSION_DENIED",
                    "message": f"This action requires the {PERM_WORKSPACE_READ!r} permission.",
                    "required_perm": PERM_WORKSPACE_READ,
                    "actor_role": ctx.role,
                    "workspace_id": ctx.workspace_id,
                }
            },
        )
    return ctx


async def _get_ham_clerk_actor_soft(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> HamActor | None:
    override = request.app.dependency_overrides.get(get_ham_clerk_actor)
    if override is not None:
        maybe_actor = override()
        if inspect.isawaitable(maybe_actor):
            maybe_actor = await maybe_actor
        return cast(HamActor | None, maybe_actor)
    try:
        route = f"{request.method} {request.url.path}"
        return enforce_clerk_session_and_email_for_request(authorization, route=route)
    except HTTPException:
        return None


async def require_preview_proxy_ctx(
    workspace_id: str,
    project_id: str,
    request: Request,
    actor: Annotated[HamActor | None, Depends(_get_ham_clerk_actor_soft)] = None,
    store: Annotated[WorkspaceStore, Depends(get_workspace_store)] = None,  # type: ignore[assignment]
) -> WorkspaceContext:
    has_authorization_header = bool(str(request.headers.get("authorization") or "").strip())
    has_cookie_header = bool(str(request.headers.get("cookie") or "").strip())
    clerk_cookie_name = _clerk_session_cookie_name()
    clerk_cookie = str(request.cookies.get(clerk_cookie_name) or "").strip()
    preview_cookie = str(request.cookies.get(_PREVIEW_PROXY_SESSION_COOKIE_NAME) or "").strip()
    diag: dict[str, Any] = {
        "route": "preview_proxy_get",
        "workspace_id": _diag_str(workspace_id),
        "project_id": _diag_str(project_id),
        "has_authorization_header": has_authorization_header,
        "has_cookie_header": has_cookie_header,
        "preview_session_cookie_present": bool(preview_cookie),
        "clerk_session_cookie_present": bool(clerk_cookie),
        "preview_cookie_decode_status": "missing",
        "bearer_auth_status": "missing" if not has_authorization_header else "not_attempted",
        "clerk_cookie_auth_status": "missing" if not clerk_cookie else "not_attempted",
        "final_auth_decision": "denied",
        "denial_reason": "no_auth_material",
    }
    cookie_actor_from_clerk: HamActor | None = None
    if actor is not None:
        diag["bearer_auth_status"] = "valid"
        ctx = _require_preview_proxy_read_perm(
            _resolve_workspace_context_or_http(actor=actor, workspace_id=workspace_id, store=store)
        )
        diag["final_auth_decision"] = "allowed"
        diag["denial_reason"] = ""
        _emit_preview_proxy_diag(diag)
        return ctx
    auth_header = str(request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        try:
            header_actor = verify_clerk_session_jwt(auth_header[7:].strip())
            require_ham_clerk_email_allowed(header_actor, route=f"{request.method} {request.url.path}")
            ctx = _require_preview_proxy_read_perm(
                _resolve_workspace_context_or_http(actor=header_actor, workspace_id=workspace_id, store=store)
            )
            diag["bearer_auth_status"] = "valid"
            diag["final_auth_decision"] = "allowed"
            diag["denial_reason"] = ""
            _emit_preview_proxy_diag(diag)
            return ctx
        except HTTPException:
            diag["bearer_auth_status"] = "invalid"
            diag["denial_reason"] = "invalid_clerk_cookie"
    elif has_authorization_header:
        diag["bearer_auth_status"] = "invalid"
        diag["denial_reason"] = "invalid_clerk_cookie"
    if clerk_cookie:
        try:
            cookie_actor_from_clerk = verify_clerk_session_jwt(clerk_cookie)
            require_ham_clerk_email_allowed(
                cookie_actor_from_clerk,
                route=f"{request.method} {request.url.path}",
            )
            diag["clerk_cookie_auth_status"] = "valid"
        except HTTPException:
            cookie_actor_from_clerk = None
            diag["clerk_cookie_auth_status"] = "invalid"
            diag["denial_reason"] = "invalid_clerk_cookie"
    if preview_cookie:
        claims, decode_status = _decode_preview_proxy_session_token(preview_cookie)
        diag["preview_cookie_decode_status"] = decode_status
        if claims is not None:
            if not _preview_proxy_session_claim_match(
                claims=claims,
                workspace_id=workspace_id,
                project_id=project_id,
            ):
                # Split mismatch reason for diagnostics.
                claim_ws = str(claims.get("workspace_id") or "").strip()
                claim_project = str(claims.get("project_id") or "").strip()
                if claim_ws != workspace_id:
                    diag["preview_cookie_decode_status"] = "workspace_mismatch"
                elif claim_project != project_id:
                    diag["preview_cookie_decode_status"] = "project_mismatch"
                else:
                    diag["preview_cookie_decode_status"] = "user_mismatch"
                diag["denial_reason"] = "ownership_mismatch"
            else:
                cookie_actor = _preview_proxy_actor_from_claims(claims)
                if cookie_actor is None:
                    diag["preview_cookie_decode_status"] = "invalid_signature"
                    diag["denial_reason"] = "invalid_preview_cookie"
                elif cookie_actor_from_clerk is not None and cookie_actor.user_id != cookie_actor_from_clerk.user_id:
                    diag["preview_cookie_decode_status"] = "user_mismatch"
                    diag["denial_reason"] = "ownership_mismatch"
                else:
                    try:
                        ctx = _require_preview_proxy_read_perm(
                            _resolve_workspace_context_or_http(
                                actor=cookie_actor,
                                workspace_id=workspace_id,
                                store=store,
                            )
                        )
                        diag["final_auth_decision"] = "allowed"
                        diag["denial_reason"] = ""
                        _emit_preview_proxy_diag(diag)
                        return ctx
                    except HTTPException:
                        diag["denial_reason"] = "ownership_mismatch"
        elif decode_status == "expired":
            diag["denial_reason"] = "expired_preview_cookie"
    if cookie_actor_from_clerk is not None:
        try:
            ctx = _require_preview_proxy_read_perm(
                _resolve_workspace_context_or_http(
                    actor=cookie_actor_from_clerk,
                    workspace_id=workspace_id,
                    store=store,
                )
            )
            diag["final_auth_decision"] = "allowed"
            diag["denial_reason"] = ""
            _emit_preview_proxy_diag(diag)
            return ctx
        except HTTPException:
            diag["denial_reason"] = "ownership_mismatch"
    if not has_authorization_header and not preview_cookie and not clerk_cookie:
        diag["denial_reason"] = "no_auth_material"
    elif preview_cookie and str(diag.get("preview_cookie_decode_status") or "") in {"invalid_signature", "missing"}:
        diag["denial_reason"] = "invalid_preview_cookie"
    _emit_preview_proxy_diag(diag)
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "code": "PREVIEW_PROXY_SESSION_REQUIRED",
                "message": "Preview authentication required. Refresh the preview session and try again.",
            }
        },
    )


def _auth_source_for_request(request: Request) -> str:
    auth_header = str(request.headers.get("authorization") or "").strip()
    if auth_header:
        return "bearer"
    if str(request.cookies.get(_clerk_session_cookie_name()) or "").strip():
        return "session"
    return "unknown"


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/session")
async def create_builder_preview_proxy_session(
    project_id: str,
    request: Request,
    response: Response,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    endpoint = _cloud_proxy_endpoint_or_none(workspace_id=ctx.workspace_id, project_id=project_id)
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_NOT_CONFIGURED",
                    "message": "Cloud preview proxy endpoint is not configured for this project.",
                }
            },
        )
    token, exp = _mint_preview_proxy_session_token(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        actor_user_id=ctx.actor_user_id,
        org_id=ctx.org_id,
        actor_email=ctx.actor_email,
        org_role=ctx.org_role,
    )
    ttl = _preview_proxy_session_ttl_seconds()
    cookie_path = _preview_proxy_cookie_path(workspace_id=ctx.workspace_id, project_id=project_id)
    response.set_cookie(
        key=_PREVIEW_PROXY_SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl,
        expires=ttl,
        path=cookie_path,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    _emit_preview_proxy_diag(
        {
            "route": "preview_proxy_session_mint",
            "workspace_id": _diag_str(ctx.workspace_id),
            "project_id": _diag_str(project_id),
            "auth_source": _auth_source_for_request(request),
            "set_cookie_attempted": True,
            "cookie_name": _PREVIEW_PROXY_SESSION_COOKIE_NAME,
            "cookie_path": cookie_path,
            "cookie_secure": True,
            "cookie_samesite": "lax",
            "cookie_max_age_seconds": ttl,
            "response_has_set_cookie": "set-cookie" in {k.lower() for k in response.headers.keys()},
        }
    )
    expires_at = datetime.fromtimestamp(exp, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "status": "ready",
        "expires_at": expires_at,
    }


async def _serve_builder_preview_proxy(
    project_id: str,
    path: str,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_preview_proxy_ctx)],
) -> Response:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    endpoint = _cloud_proxy_endpoint_or_none(workspace_id=ctx.workspace_id, project_id=project_id)
    if endpoint is None:
        _emit_preview_proxy_upstream_diag(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=None,
            endpoint_id=None,
            proxy_target_present=False,
            upstream_connect_status="no_endpoint",
            upstream_http_status=404,
        )
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_NOT_CONFIGURED",
                    "message": "Cloud preview proxy endpoint is not configured for this project.",
                }
            },
        )
    trusted_host = _safe_trusted_proxy_host((endpoint.metadata or {}).get("trusted_proxy_host"))
    runtime = _runtime_session_by_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        runtime_session_id=endpoint.runtime_session_id,
    )
    allow_internal = _allows_provider_owned_internal_upstream(runtime=runtime, endpoint=endpoint)
    upstream_base = _sanitize_cloud_proxy_upstream_url(
        raw_url=endpoint.url,
        trusted_host=trusted_host,
        allow_internal=allow_internal,
    )
    if upstream_base is None:
        _emit_preview_proxy_upstream_diag(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=str(endpoint.runtime_session_id or "").strip() or None,
            endpoint_id=endpoint.id,
            proxy_target_present=False,
            upstream_connect_status="unsafe_upstream",
            upstream_http_status=422,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_UNSAFE_UPSTREAM",
                    "message": "Configured cloud preview upstream URL is not allowed.",
                }
            },
        )
    upstream_parts = urlsplit(upstream_base)
    prefix = upstream_parts.path.rstrip("/")
    suffix = "/" + path.lstrip("/") if path else "/"
    target_path = (prefix + suffix) if prefix else suffix
    upstream_url = urlunsplit(
        (
            upstream_parts.scheme,
            upstream_parts.netloc,
            target_path,
            str(request.url.query or ""),
            "",
        )
    )
    headers = _build_proxy_forward_headers(request.headers)
    method = request.method.upper()
    try:
        upstream_response = await _proxy_upstream_fetch(method=method, url=upstream_url, headers=headers)
        _emit_preview_proxy_upstream_diag(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=str(endpoint.runtime_session_id or "").strip() or None,
            endpoint_id=endpoint.id,
            proxy_target_present=True,
            upstream_connect_status="ok",
            upstream_http_status=upstream_response.status_code,
        )
        if upstream_response.status_code in {301, 302, 303, 307, 308}:
            location = str(upstream_response.headers.get("location") or "").strip()
            if location:
                redirect_url = urljoin(upstream_url, location)
                safe_redirect = _sanitize_cloud_proxy_upstream_url(
                    raw_url=redirect_url,
                    trusted_host=trusted_host,
                    allow_internal=allow_internal,
                )
                if safe_redirect is None:
                    _emit_preview_proxy_upstream_diag(
                        workspace_id=ctx.workspace_id,
                        project_id=project_id,
                        runtime_session_id=str(endpoint.runtime_session_id or "").strip() or None,
                        endpoint_id=endpoint.id,
                        proxy_target_present=False,
                        upstream_connect_status="unsafe_upstream",
                        upstream_http_status=422,
                    )
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "error": {
                                "code": "PREVIEW_PROXY_UNSAFE_UPSTREAM",
                                "message": "Upstream redirect target is not allowed.",
                            }
                        },
                    )
                upstream_response = await _proxy_upstream_fetch(method=method, url=safe_redirect, headers=headers)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        _emit_preview_proxy_upstream_diag(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=str(endpoint.runtime_session_id or "").strip() or None,
            endpoint_id=endpoint.id,
            proxy_target_present=True,
            upstream_connect_status="connect_timeout",
            upstream_http_status=None,
        )
        raise HTTPException(
            status_code=504,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_TIMEOUT",
                    "message": "Cloud preview upstream timed out.",
                }
            },
        ) from exc
    except httpx.HTTPError as exc:
        _emit_preview_proxy_upstream_diag(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=str(endpoint.runtime_session_id or "").strip() or None,
            endpoint_id=endpoint.id,
            proxy_target_present=True,
            upstream_connect_status=_classify_proxy_upstream_error(exc),
            upstream_http_status=None,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_UPSTREAM_UNAVAILABLE",
                    "message": "Cloud preview upstream is unavailable.",
                }
            },
        ) from exc
    body = upstream_response.content or b""
    if len(body) > _PREVIEW_PROXY_MAX_BYTES:
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "PREVIEW_PROXY_UPSTREAM_UNAVAILABLE",
                    "message": "Cloud preview upstream response exceeded size limits.",
                }
            },
        )
    response_headers: dict[str, str] = {}
    content_type = str(upstream_response.headers.get("content-type") or "").strip()
    if content_type:
        response_headers["content-type"] = content_type[:240]
    return Response(
        content=(b"" if method == "HEAD" else body),
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


def _supersede_active_cloud_runtime_jobs(
    *,
    workspace_id: str,
    project_id: str,
    reason: str,
) -> int:
    store = get_builder_runtime_job_store()
    changed = 0
    for job in store.list_cloud_runtime_jobs(workspace_id=workspace_id, project_id=project_id):
        status = str(job.status or "").strip().lower()
        if status not in {"queued", "running"}:
            continue
        now_iso = _utc_now_iso()
        job.status = "cancelled"
        job.phase = "failed"
        job.completed_at = now_iso
        job.updated_at = now_iso
        job.error_code = "CLOUD_RUNTIME_JOB_SUPERSEDED"
        job.error_message = reason
        job.logs_summary = "Cloud runtime job superseded before fresh retry."
        job.metadata = {**(job.metadata or {}), "superseded_at": now_iso, "supersede_reason": reason}
        store.upsert_cloud_runtime_job(job)
        changed += 1
    if changed > 0:
        get_builder_runtime_store().clear_cloud_runtime(workspace_id=workspace_id, project_id=project_id)
    return changed


def _active_cloud_runtime_and_endpoint(
    *,
    workspace_id: str,
    project_id: str,
) -> tuple[Any | None, PreviewEndpoint | None]:
    runtime = get_builder_runtime_store().get_active_runtime_session(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if runtime is None:
        return None, None
    if str(runtime.mode or "").strip().lower() != "cloud":
        return None, None
    endpoint = get_builder_runtime_store().get_active_preview_endpoint(
        workspace_id=workspace_id,
        project_id=project_id,
        runtime_session_id=runtime.id,
    )
    return runtime, endpoint


def _cloud_proxy_endpoint_or_none(*, workspace_id: str, project_id: str) -> PreviewEndpoint | None:
    _runtime, endpoint = _active_cloud_runtime_and_endpoint(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if endpoint is None:
        return None
    if str(endpoint.access_mode or "").strip().lower() != "proxy":
        return None
    if str(endpoint.status or "").strip().lower() != "ready":
        return None
    return endpoint


async def _proxy_upstream_fetch(*, method: str, url: str, headers: dict[str, str]) -> httpx.Response:
    timeout = httpx.Timeout(_PREVIEW_PROXY_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.request(method=method, url=url, headers=headers)


def _build_proxy_forward_headers(request_headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    accept = str(request_headers.get("accept") or "").strip()
    if accept:
        out["accept"] = accept[:240]
    user_agent = str(request_headers.get("user-agent") or "").strip()
    if user_agent:
        out["user-agent"] = user_agent[:240]
    return out


def _runtime_session_by_id(*, workspace_id: str, project_id: str, runtime_session_id: str | None) -> Any | None:
    rid = str(runtime_session_id or "").strip()
    if not rid:
        return None
    for row in get_builder_runtime_store().list_runtime_sessions(
        workspace_id=workspace_id,
        project_id=project_id,
    ):
        if row.id == rid:
            return row
    return None


def _sse_pack(event_name: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_name}\ndata: "
        + json.dumps(payload, separators=(",", ":"), default=str)
        + "\n\n"
    ).encode("utf-8")


def _activity_stream_payload(*, workspace_id: str, project_id: str) -> dict[str, Any]:
    items = _build_activity_items(workspace_id=workspace_id, project_id=project_id)[:_ACTIVITY_STREAM_MAX_ITEMS]
    payload: dict[str, Any] = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "connection_state": "live",
        "items": [row.model_dump(mode="json") for row in items],
    }
    encoded = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    while len(encoded) > _ACTIVITY_STREAM_MAX_PAYLOAD_BYTES and payload["items"]:
        payload["items"] = payload["items"][:-1]
        encoded = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    payload["stream_cursor"] = f"{len(payload['items'])}:{(payload['items'][0]['id'] if payload['items'] else 'none')}"
    return payload


def _derive_preview_status(
    *,
    runtime_status: str | None,
    runtime_health: str | None,
    endpoint_status: str | None,
    safe_preview_url: str | None,
) -> tuple[str, str]:
    rs = str(runtime_status or "").strip().lower()
    rh = str(runtime_health or "").strip().lower()
    es = str(endpoint_status or "").strip().lower()
    if not rs:
        return ("not_connected", "Local preview runtime is not connected.")
    if rs in {"stopped", "expired"}:
        return ("not_connected", "Local preview runtime is not connected.")
    if rs == "failed":
        return ("error", "Local preview runtime is not available.")
    if rh == "unhealthy":
        return ("error", "Local preview runtime is unhealthy.")
    if rs == "starting":
        return ("building", "Local preview runtime is starting.")
    if rs == "waiting":
        return ("waiting", "Local preview runtime is waiting for work.")
    if rs == "not_connected":
        return ("not_connected", "Local preview runtime is not connected.")
    if rs == "running" and es == "ready" and safe_preview_url:
        return ("ready", "Preview is ready.")
    if rs == "running" and es in {"provisioning", ""}:
        return ("building", "Local preview endpoint is provisioning.")
    if rs == "running" and es in {"unavailable", "revoked"}:
        return ("error", "Local preview endpoint is unavailable.")
    if rs == "running" and es == "ready" and not safe_preview_url:
        return ("error", "Preview URL is unavailable due to safety policy.")
    return ("waiting", "Local preview status is waiting for endpoint readiness.")


def _build_preview_status_payload(*, workspace_id: str, project_id: str) -> dict[str, Any]:
    source_rows = get_builder_source_store().list_project_sources(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    active_snapshot_id = next((row.active_snapshot_id for row in source_rows if row.active_snapshot_id), None)
    runtime_store = get_builder_runtime_store()
    runtime = runtime_store.get_active_runtime_session(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if active_snapshot_id and runtime is None:
        experiment_status, _experiment_message = get_cloud_runtime_experiment_status()
        if experiment_status in {"experiment_not_enabled", "disabled", "config_missing"}:
            return {
                "project_id": project_id,
                "workspace_id": workspace_id,
                "mode": "cloud",
                "status": "waiting",
                "health": "unknown",
                "preview_url": None,
                "message": "Cloud preview is not configured in this environment.",
                "updated_at": _utc_now_iso(),
                "source_snapshot_id": active_snapshot_id,
                "runtime_session_id": None,
                "preview_endpoint_id": None,
                "logs_hint": None,
            }
        return {
            "project_id": project_id,
            "workspace_id": workspace_id,
            "mode": "cloud",
            "status": "building",
            "health": "unknown",
            "preview_url": None,
            "message": "Preparing your cloud preview…",
            "updated_at": _utc_now_iso(),
            "source_snapshot_id": active_snapshot_id,
            "runtime_session_id": None,
            "preview_endpoint_id": None,
            "logs_hint": None,
        }
    endpoint = None
    if runtime is not None:
        endpoint = runtime_store.get_active_preview_endpoint(
            workspace_id=workspace_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
        )
    mode = (runtime.mode if runtime is not None else "local") or "local"
    safe_preview_url: str | None = None
    if mode == "cloud":
        trusted_host = _safe_trusted_proxy_host((endpoint.metadata or {}).get("trusted_proxy_host")) if endpoint else None
        allow_internal = _allows_provider_owned_internal_upstream(runtime=runtime, endpoint=endpoint)
        safe_upstream = _sanitize_cloud_proxy_upstream_url(
            raw_url=endpoint.url if endpoint is not None else None,
            trusted_host=trusted_host,
            allow_internal=allow_internal,
        )
        runtime_status = str(runtime.status or "").strip().lower() if runtime is not None else ""
        endpoint_status = str(endpoint.status or "").strip().lower() if endpoint is not None else ""
        if safe_upstream and endpoint is not None and endpoint_status == "ready" and str(endpoint.access_mode or "").strip().lower() == "proxy":
            safe_preview_url = _cloud_proxy_preview_url(workspace_id=workspace_id, project_id=project_id)
            status = "ready"
            message = "Preview is ready via authenticated cloud proxy."
        elif runtime_status in {"queued", "provisioning", "running"}:
            status = "building"
            if runtime_status == "queued":
                message = "Starting preview environment…"
            elif runtime_status == "provisioning":
                message = "Preview environment is starting…"
            else:
                message = "Cloud runtime is running; preview will appear when the proxy endpoint is ready."
        elif runtime_status in {"failed", "unsupported"}:
            status = "error"
            message = "Cloud preview is unavailable."
        else:
            status = "waiting"
            message = "Cloud preview status is waiting for endpoint readiness."
    else:
        safe_preview_url = _sanitize_local_preview_url(endpoint.url if endpoint is not None else None)
        status, message = _derive_preview_status(
            runtime_status=runtime.status if runtime is not None else None,
            runtime_health=runtime.health if runtime is not None else None,
            endpoint_status=endpoint.status if endpoint is not None else None,
            safe_preview_url=safe_preview_url,
        )
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "mode": mode,
        "status": status,
        "health": runtime.health if runtime is not None else "unknown",
        "preview_url": safe_preview_url if status == "ready" else None,
        "message": message,
        "updated_at": runtime.updated_at if runtime is not None else _utc_now_iso(),
        "source_snapshot_id": runtime.snapshot_id if runtime and runtime.snapshot_id else active_snapshot_id,
        "runtime_session_id": runtime.id if runtime is not None else None,
        "preview_endpoint_id": endpoint.id if endpoint is not None else None,
        "logs_hint": None,
    }


def _validated_snapshot_id(*, workspace_id: str, project_id: str, source_snapshot_id: str | None) -> str | None:
    if source_snapshot_id is None:
        return None
    snapshot_rows = get_builder_source_store().list_source_snapshots(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    known_snapshot_ids = {row.id for row in snapshot_rows}
    if source_snapshot_id not in known_snapshot_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SOURCE_SNAPSHOT_NOT_FOUND",
                    "message": f"Unknown source_snapshot_id {source_snapshot_id!r} for this project.",
                }
            },
        )
    return source_snapshot_id


def _active_snapshot_id(*, workspace_id: str, project_id: str) -> str | None:
    source_rows = get_builder_source_store().list_project_sources(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    return next((row.active_snapshot_id for row in source_rows if row.active_snapshot_id), None)


def _serialize_local_run_profile(profile: LocalRunProfile | None, *, workspace_id: str, project_id: str) -> dict[str, Any]:
    configured = bool(profile and profile.status in {"configured", "draft"})
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "configured": configured,
        "status": profile.status if profile is not None else "not_configured",
        "profile": profile.model_dump(mode="json") if profile is not None else None,
    }


_CLOUD_RUNTIME_STATES = {
    "queued",
    "provisioning",
    "running",
    "failed",
    "expired",
    "unsupported",
}
_CLOUD_RUNTIME_VIEW_STATES = {
    "disabled",
    "experiment_not_enabled",
    "config_missing",
    "dry_run_ready",
    "provider_ready",
    "provider_accepted",
    "failed",
    "expired",
}
_CLOUD_RUNTIME_JOB_STATES = {"queued", "running", "succeeded", "failed", "cancelled", "unsupported"}
_CLOUD_RUNTIME_JOB_PHASES = {
    "received",
    "preparing",
    "validating_source",
    "validating_config",
    "submitting_cloud_runtime",
    "provider_accepted",
    "running_poc",
    "completed",
    "failed",
}


def _serialize_cloud_runtime(
    runtime: Any | None,
    *,
    workspace_id: str,
    project_id: str,
) -> dict[str, Any]:
    experiment_status, experiment_message = get_cloud_runtime_experiment_status()
    if runtime is None:
        return {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "mode": "cloud",
            "status": experiment_status,
            "message": experiment_message,
            "updated_at": _utc_now_iso(),
            "runtime_session_id": None,
            "source_snapshot_id": None,
            "metadata": {
                "provider_mode": get_cloud_runtime_provider_mode(),
                "provider_capability_status": get_cloud_runtime_provider_capability_status(),
            },
        }
    runtime_status = str(runtime.status or "").strip().lower()
    status = "provider_ready"
    if runtime_status in {"failed", "unsupported"}:
        status = "failed"
    elif runtime_status in {"expired", "stopped"}:
        status = "expired"
    elif runtime_status == "provisioning":
        provider_job_id = str((runtime.metadata or {}).get("provider_job_id") or "").strip()
        status = "provider_accepted" if provider_job_id else "provider_ready"
    elif runtime_status == "queued":
        status = "provider_ready"
    elif runtime_status == "running":
        status = "provider_ready"
    if status not in _CLOUD_RUNTIME_VIEW_STATES:
        status = "failed"
    message = _safe_text(
        runtime.message,
        fallback=experiment_message,
    )
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "mode": "cloud",
        "status": status,
        "message": message,
        "updated_at": runtime.updated_at or _utc_now_iso(),
        "runtime_session_id": runtime.id,
        "source_snapshot_id": runtime.snapshot_id,
        "metadata": runtime.metadata or {},
    }


class LocalPreviewRegisterRequest(BaseModel):
    preview_url: str
    source_snapshot_id: str | None = None
    display_name: str | None = None


class LocalRunProfilePayload(BaseModel):
    source_snapshot_id: str | None = None
    display_name: str = "Local run profile"
    working_directory: str = "."
    install_command: str | None = None
    dev_command: str
    build_command: str | None = None
    test_command: str | None = None
    expected_preview_url: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualEditRequestPayload(BaseModel):
    source_snapshot_id: str | None = None
    runtime_session_id: str | None = None
    preview_endpoint_id: str | None = None
    route: str | None = None
    preview_url_kind: Literal["local", "cloud_proxy", "unknown"] | None = None
    target: dict[str, Any] | None = None
    selector_hints: list[str] = Field(default_factory=list)
    bbox: dict[str, Any] | None = None
    instruction: str
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudRuntimeRequestPayload(BaseModel):
    source_snapshot_id: str | None = None
    status: str | None = None
    force_new: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudRuntimeJobPayload(BaseModel):
    source_snapshot_id: str | None = None
    force_new: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuilderActivityItem(BaseModel):
    id: str
    kind: str
    status: str
    title: str
    message: str
    timestamp: str
    source_id: str | None = None
    snapshot_id: str | None = None
    import_job_id: str | None = None
    runtime_session_id: str | None = None
    preview_endpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


BuilderWorkerStatus = Literal[
    "available",
    "needs_connection",
    "unavailable",
    "disabled",
    "unknown",
    "available_mock",
    "available_poc",
]


class BuilderWorkerCapabilityEntry(BaseModel):
    worker_kind: str
    provider: str
    display_name: str
    status: BuilderWorkerStatus
    capabilities: list[str] = Field(default_factory=list)
    environment_fit: str
    required_setup: str
    settings_href: str | None = None
    last_checked_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _to_worker_status(raw: str | None) -> BuilderWorkerStatus:
    value = str(raw or "").strip().lower()
    if value in {
        "available",
        "needs_connection",
        "unavailable",
        "disabled",
        "unknown",
        "available_mock",
        "available_poc",
    }:
        return cast(BuilderWorkerStatus, value)
    return "unknown"


def _cursor_cloud_agent_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    readiness = check_cursor_readiness()
    status: BuilderWorkerStatus = "needs_connection"
    if readiness.status == "ready":
        status = "available"
    elif readiness.status == "unavailable":
        status = "unavailable"
    row = HARNESS_CAPABILITIES.get("cursor_cloud_agent")
    metadata: dict[str, Any] = {
        "source": "cursor_readiness",
        "harness_provider": "cursor_cloud_agent",
        "readiness_status": readiness.status,
    }
    if row is not None:
        metadata["registry_status"] = row.registry_status
        metadata["supports_operator_launch"] = bool(row.supports_operator_launch)
    return BuilderWorkerCapabilityEntry(
        worker_kind="cursor_cloud_agent",
        provider="cursor_cloud_agent",
        display_name="Cursor Cloud Agent",
        status=status,
        capabilities=["plan", "edit_code", "run_tests", "open_pr"],
        environment_fit="Hosted/cloud coding runs against remote repositories.",
        required_setup="Add a Cursor API key in Connected Tools to enable cloud agent runs.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata=metadata,
    )


def _cursor_local_sdk_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    profile = os.environ.get("HAM_CURSOR_SDK_BRIDGE_ENABLED", "").strip().lower()
    enabled = profile in {"1", "true", "yes", "on"}
    status: BuilderWorkerStatus = "disabled" if not enabled else "unknown"
    return BuilderWorkerCapabilityEntry(
        worker_kind="cursor_local_sdk",
        provider="cursor_sdk_bridge",
        display_name="Cursor Local SDK Bridge",
        status=status,
        capabilities=["status_stream", "event_projection"],
        environment_fit="Optional local/bridge telemetry path for Cursor-native status streams.",
        required_setup="Enable HAM_CURSOR_SDK_BRIDGE_ENABLED and configure provider credentials.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "env_flag",
            "bridge_enabled": enabled,
        },
    )


def _claude_agent_entry(actor: HamActor | None) -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    readiness = check_claude_agent_readiness(actor)
    status: BuilderWorkerStatus = "unknown"
    if readiness.status == "ready":
        status = "available"
    elif readiness.status == "needs_sign_in":
        status = "needs_connection"
    elif readiness.status == "unavailable":
        status = "unavailable"
    return BuilderWorkerCapabilityEntry(
        worker_kind="claude_agent",
        provider="claude_agent_sdk",
        display_name="Claude Agent",
        status=status,
        capabilities=["plan", "edit_code", "run_tests"],
        environment_fit="Server-side Claude Agent SDK with BYOK auth channels.",
        required_setup="Install claude-agent-sdk on host and connect Anthropic/Bedrock/Vertex auth.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "claude_agent_readiness",
            "sdk_available": bool(readiness.sdk_available),
            "sdk_version": readiness.sdk_version,
            "readiness_status": readiness.status,
        },
    )


def _factory_droid_entry() -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    token_present = bool((os.environ.get("HAM_DROID_EXEC_TOKEN") or "").strip())
    row = HARNESS_CAPABILITIES.get("factory_droid")
    return BuilderWorkerCapabilityEntry(
        worker_kind="factory_droid",
        provider="factory_droid",
        display_name="Factory Droid",
        status="available" if token_present else "unknown",
        capabilities=["edit_code", "run_tests"],
        environment_fit="Local bounded workflow execution on registered project roots.",
        required_setup="Configure HAM_DROID_EXEC_TOKEN and keep allowlisted droid workflows enabled.",
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=now,
        metadata={
            "source": "env_and_registry",
            "token_configured": token_present,
            "registry_status": row.registry_status if row is not None else "unknown",
        },
    )


def _local_runtime_entry(*, workspace_id: str, project_id: str) -> BuilderWorkerCapabilityEntry:
    now = _utc_now_iso()
    preview = _build_preview_status_payload(workspace_id=workspace_id, project_id=project_id)
    profile = get_builder_run_profile_store().get_active_local_run_profile(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    preview_status = str(preview.get("status") or "").strip().lower()
    status: BuilderWorkerStatus = "needs_connection"
    if preview_status == "ready":
        status = "available"
    elif preview_status == "error":
        status = "unavailable"
    elif profile is not None and profile.status == "disabled":
        status = "disabled"
    elif profile is None and preview_status == "not_connected":
        status = "needs_connection"
    return BuilderWorkerCapabilityEntry(
        worker_kind="local_runtime",
        provider="builder_local_runtime",
        display_name="Local Runtime",
        status=_to_worker_status(status),
        capabilities=["local_preview_registration", "local_run_profile"],
        environment_fit="Operator-run local dev server + loopback preview URL registration.",
        required_setup="Save a local run profile and connect a safe localhost preview URL.",
        settings_href=None,
        last_checked_at=now,
        metadata={
            "source": "builder_preview_and_run_profile",
            "preview_status": preview_status or "unknown",
            "run_profile_status": profile.status if profile is not None else "not_configured",
            "runtime_session_id": preview.get("runtime_session_id"),
            "preview_endpoint_id": preview.get("preview_endpoint_id"),
        },
    )


def _hermes_planner_entry() -> BuilderWorkerCapabilityEntry:
    return BuilderWorkerCapabilityEntry(
        worker_kind="hermes_planner",
        provider="hermes_supervisor",
        display_name="Hermes Planner",
        status="available",
        capabilities=["plan", "critique", "route"],
        environment_fit="Built-in HAM supervisory planning and critique loops.",
        required_setup="No additional setup for read-only planner visibility.",
        settings_href="/workspace/settings?section=agents",
        last_checked_at=_utc_now_iso(),
        metadata={
            "source": "static_control_plane",
        },
    )


def _cloud_runtime_worker_entry() -> BuilderWorkerCapabilityEntry:
    provider_mode = get_cloud_runtime_provider_mode()
    provider_status = get_cloud_runtime_provider_capability_status()
    experiment_status, _ = get_cloud_runtime_experiment_status()
    status = _to_worker_status(provider_status)
    fit = "Cloud runtime control-plane path; production sandbox lifecycle is staged behind provider gates."
    setup = "Set HAM_BUILDER_CLOUD_RUNTIME_PROVIDER=local_mock for safe simulation in dev/test."
    if experiment_status == "experiment_not_enabled":
        setup = (
            "Set HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED=true, "
            "or configure HAM_BUILDER_CLOUD_RUNTIME_PROVIDER for explicit POC tests."
        )
    elif provider_mode == "cloud_run_poc":
        if provider_status == "disabled":
            setup = "Enable HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED=true to activate cloud_run_poc planning."
        elif provider_status == "unavailable":
            setup = "Set HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT and HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION for plan-only POC."
        else:
            setup = "cloud_run_poc is plan-only in this PR. No cloud resources are provisioned by default."
    elif provider_mode == "gcp_gke_sandbox":
        if provider_status == "disabled":
            setup = (
                "Set HAM_BUILDER_GCP_RUNTIME_ENABLED=true plus scaffold vars "
                "(project, region, cluster, namespace prefix, bucket, runner image)."
            )
        elif provider_status == "unavailable":
            setup = (
                "Complete HAM_BUILDER_GCP_PROJECT_ID / REGION / GKE_CLUSTER / "
                "GKE_NAMESPACE_PREFIX / PREVIEW_SOURCE_BUCKET / PREVIEW_RUNNER_IMAGE."
            )
        else:
            setup = (
                "gcp_gke_sandbox is scaffolding only: dry-run or explicit fake mode until live GKE preview lands."
            )
    return BuilderWorkerCapabilityEntry(
        worker_kind="cloud_runtime_worker",
        provider="builder_cloud_runtime",
        display_name="Cloud Runtime Worker (POC)",
        status=status,
        capabilities=["request_runtime_job", "read_job_status"],
        environment_fit=fit,
        required_setup=setup,
        settings_href="/workspace/settings?section=integrations",
        last_checked_at=_utc_now_iso(),
        metadata={
            "source": "builder_runtime_worker",
            "provider_mode": provider_mode,
            "provider_status": provider_status,
            "production_ready": False,
        },
    )


def _build_worker_capabilities(*, workspace_id: str, project_id: str, actor: HamActor | None) -> list[BuilderWorkerCapabilityEntry]:
    return [
        _cursor_cloud_agent_entry(),
        _cursor_local_sdk_entry(),
        _claude_agent_entry(actor),
        _factory_droid_entry(),
        _local_runtime_entry(workspace_id=workspace_id, project_id=project_id),
        _cloud_runtime_worker_entry(),
        _hermes_planner_entry(),
    ]


_SENSITIVE_VALUE_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|bearer|authorization)", re.IGNORECASE)


def _safe_text(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    text = " ".join(raw.replace("\r", " ").replace("\n", " ").split())
    if _SENSITIVE_VALUE_RE.search(text):
        return fallback
    return text[:240]


def _safe_stats(stats: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in ("file_count", "dir_count", "compressed_bytes", "uncompressed_bytes"):
        value = stats.get(key)
        if isinstance(value, int):
            out[key] = max(0, value)
    return out


_COMMAND_META_RE = re.compile(r"(;|&&|\|\||\||>|<|`|\$\(|\r|\n)")
_DISALLOWED_COMMANDS = {"rm", "del", "format", "shutdown", "powershell", "pwsh"}
_WORKDIR_DRIVE_RE = re.compile(r"^[a-zA-Z]:")
_VISUAL_EDIT_ALLOWED_STATUS = {"draft", "queued", "processing", "resolved", "failed", "cancelled"}


def _normalize_working_directory(raw: str | None) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return "."
    if len(text) > 180:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Working directory is too long."}},
        )
    if text.startswith("/") or text.startswith("\\") or text.startswith("//") or _WORKDIR_DRIVE_RE.match(text):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Working directory must be project-relative."}},
        )
    parts = [seg for seg in text.split("/") if seg not in {"", "."}]
    if any(seg == ".." for seg in parts):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_WORKDIR_INVALID", "message": "Path traversal is not allowed in working_directory."}},
        )
    normalized = "/".join(parts)
    return normalized or "."


def _parse_command_argv(raw: str | None, *, field_name: str, required: bool = False) -> list[str] | None:
    text = str(raw or "").strip()
    if not text:
        if required:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is required."}},
            )
        return None
    if len(text) > 240:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is too long."}},
        )
    if _COMMAND_META_RE.search(text):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} contains unsupported shell metacharacters."}},
        )
    try:
        argv = shlex.split(text, posix=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} could not be parsed."}},
        ) from exc
    if not argv:
        if required:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} is required."}},
            )
        return None
    if len(argv) > 24 or any((not arg) or len(arg) > 120 for arg in argv):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} exceeds argument safety limits."}},
        )
    command_name = argv[0].split("/")[-1].split("\\")[-1].lower()
    if command_name in _DISALLOWED_COMMANDS:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} command is not allowed for local run profile."}},
        )
    if command_name in {"curl", "wget"} and any("|" in arg for arg in argv[1:]):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_COMMAND_INVALID", "message": f"{field_name} contains an unsafe download pattern."}},
        )
    return argv


def _sanitize_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for idx, (key, value) in enumerate(raw.items()):
        if idx >= 20:
            break
        key_text = str(key).strip()[:64]
        if not key_text:
            continue
        if _SENSITIVE_VALUE_RE.search(key_text):
            continue
        if isinstance(value, bool) or value is None:
            safe[key_text] = value
        elif isinstance(value, int):
            safe[key_text] = value
        elif isinstance(value, float):
            safe[key_text] = round(value, 6)
        else:
            text = _safe_text(str(value), fallback="")
            if text:
                safe[key_text] = text
    return safe


_SAFE_RUNTIME_DIAGNOSTIC_FIELDS = {
    "lifecycle_stage",
    "exception_class",
    "normalized_error_code",
    "normalized_error_message",
    "retry_count",
    "retryable",
}


def _safe_runtime_diagnostics(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = (metadata or {}).get("runtime_diagnostics")
    if not isinstance(payload, dict):
        payload = (metadata or {}).get("sandbox_diagnostics")
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _SAFE_RUNTIME_DIAGNOSTIC_FIELDS:
        value = payload.get(key)
        if key == "retry_count":
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                out[key] = max(0, value)
            elif isinstance(value, str):
                text = value.strip()
                if text.isdigit():
                    out[key] = max(0, int(text))
            continue
        if key == "retryable":
            if isinstance(value, bool):
                out[key] = value
            elif isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "false"}:
                    out[key] = lowered == "true"
            continue
        text = _safe_text(value, fallback="")
        if text:
            out[key] = text
    return out


def _safe_sandbox_diagnostics(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Deprecated alias — use `_safe_runtime_diagnostics`."""
    return _safe_runtime_diagnostics(metadata)


def _serialize_cloud_runtime_job(record: Any) -> dict[str, Any]:
    row = record.model_dump(mode="json")
    row["runtime_diagnostics"] = _safe_runtime_diagnostics(row.get("metadata"))
    return row


def _sanitize_selector_hints(raw: list[str]) -> list[str]:
    safe: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if len(safe) >= 20:
            break
        text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
        if not text:
            continue
        if _SENSITIVE_VALUE_RE.search(text):
            continue
        normalized = text[:120]
        if normalized in seen:
            continue
        seen.add(normalized)
        safe.append(normalized)
    return safe


def _sanitize_route(raw_route: str | None) -> str | None:
    text = str(raw_route or "").strip()
    if not text:
        return None
    text = text.replace("\r", "").replace("\n", "")
    if "://" in text:
        try:
            parts = urlsplit(text)
            text = parts.path or "/"
        except ValueError:
            text = "/"
    else:
        text = text.split("?", 1)[0].split("#", 1)[0]
    text = text.strip() or "/"
    if not text.startswith("/"):
        text = "/" + text
    if len(text) > 240:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_ROUTE_INVALID", "message": "route is too long."}},
        )
    return text


def _sanitize_preview_url_kind(raw: str | None) -> str | None:
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if text not in {"local", "cloud_proxy", "unknown"}:
        return "unknown"
    return text


def _sanitize_visual_edit_target(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    safe: dict[str, Any] = {}
    numeric_fields = ("x", "y", "width", "height", "viewport_width", "viewport_height")
    for key in numeric_fields:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VISUAL_EDIT_TARGET_INVALID", "message": f"{key} must be numeric."}},
            )
        num = float(value)
        if num < 0 or num > 100000:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "VISUAL_EDIT_TARGET_INVALID",
                        "message": f"{key} is out of allowed bounds.",
                    }
                },
            )
        safe[key] = round(num, 4)
    device_mode = str(raw.get("device_mode") or "").strip().lower()
    if device_mode in {"desktop", "mobile"}:
        safe["device_mode"] = device_mode
    selector_hints = _sanitize_selector_hints(list(raw.get("selector_hints") or []))
    if selector_hints:
        safe["selector_hints"] = selector_hints
    for text_key in ("element_text", "tag_name", "aria_label"):
        text = _safe_text(raw.get(text_key), fallback="")
        if text and not _SENSITIVE_VALUE_RE.search(text):
            safe[text_key] = text[:160]
    return safe or None


def _sanitize_visual_edit_bbox(raw: dict[str, Any] | None) -> dict[str, float] | None:
    if raw is None:
        return None
    required = ("x", "y", "width", "height")
    out: dict[str, float] = {}
    for key in required:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox values must be numeric."}},
            )
        numeric = float(value)
        if numeric < 0 or numeric > 100000:
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox values are out of allowed bounds."}},
            )
        out[key] = round(numeric, 4)
    if not out:
        return None
    missing = [key for key in required if key not in out]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_BBOX_INVALID", "message": "bbox requires x, y, width, and height."}},
        )
    return out


def _normalize_visual_edit_status(raw_status: str | None) -> str:
    text = str(raw_status or "draft").strip().lower()
    if text not in _VISUAL_EDIT_ALLOWED_STATUS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "VISUAL_EDIT_STATUS_INVALID",
                    "message": "status must be one of draft, queued, processing, resolved, failed, or cancelled.",
                }
            },
        )
    return text


def _sanitize_visual_edit_instruction(raw_instruction: str) -> str:
    text = " ".join(str(raw_instruction or "").replace("\r", " ").replace("\n", " ").split())
    if not text:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_INSTRUCTION_INVALID", "message": "instruction is required."}},
        )
    if len(text) > 1200:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VISUAL_EDIT_INSTRUCTION_INVALID", "message": "instruction exceeds max length."}},
        )
    return text

def _build_activity_items(*, workspace_id: str, project_id: str) -> list[BuilderActivityItem]:
    source_store = get_builder_source_store()
    runtime_store = get_builder_runtime_store()
    items: list[BuilderActivityItem] = []

    for job in source_store.list_import_jobs(workspace_id=workspace_id, project_id=project_id):
        meta = job.metadata or {}
        custom_title = str(meta.get("activity_title") or "").strip()
        custom_message = str(meta.get("activity_message") or "").strip()
        title = "Source import queued"
        if job.status == "running":
            title = "Validating source archive"
        elif job.status == "succeeded":
            title = "Source snapshot created"
        elif job.status == "failed":
            title = "Source import failed"
        if custom_title:
            title = custom_title
        message = _safe_text(job.error_message, fallback="Source import failed.") if job.status == "failed" else title
        if custom_message and job.status != "failed":
            message = custom_message
        items.append(
            BuilderActivityItem(
                id=f"act_{job.id}",
                kind="source_import",
                status=job.status if job.status in {"queued", "running", "succeeded", "failed"} else "info",
                title=title,
                message=message,
                timestamp=job.updated_at or job.created_at,
                source_id=job.project_source_id,
                snapshot_id=job.source_snapshot_id,
                import_job_id=job.id,
                metadata=_safe_stats(job.stats),
            )
        )

    for snapshot in source_store.list_source_snapshots(workspace_id=workspace_id, project_id=project_id):
        snapshot_status = "succeeded" if snapshot.status == "materialized" else "error"
        snapshot_title = "Source snapshot materialized" if snapshot.status == "materialized" else "Source snapshot invalid"
        items.append(
            BuilderActivityItem(
                id=f"act_{snapshot.id}",
                kind="source_snapshot",
                status=snapshot_status,
                title=snapshot_title,
                message=snapshot_title,
                timestamp=snapshot.created_at,
                source_id=snapshot.project_source_id,
                snapshot_id=snapshot.id,
                metadata={"size_bytes": max(0, int(snapshot.size_bytes))},
            )
        )

    for runtime in runtime_store.list_runtime_sessions(workspace_id=workspace_id, project_id=project_id):
        runtime_status = runtime.status.lower().strip()
        if runtime.mode == "cloud":
            if runtime_status in {"running", "starting", "waiting", "queued", "provisioning"}:
                title = "Cloud runtime active"
                status = "ready" if runtime_status == "running" else "running"
                kind = "runtime_status"
            elif runtime_status in {"stopped", "expired"}:
                title = "Cloud runtime stopped"
                status = "stopped"
                kind = "preview_disconnected"
            else:
                title = "Cloud runtime failed"
                status = "error"
                kind = "preview_error"
        else:
            if runtime_status in {"running", "starting", "waiting"}:
                title = "Local preview connected"
                status = "ready" if runtime_status == "running" else "running"
                kind = "runtime_status"
            elif runtime_status in {"stopped", "expired"}:
                title = "Local preview disconnected"
                status = "stopped"
                kind = "preview_disconnected"
            else:
                title = "Local preview runtime error"
                status = "error"
                kind = "preview_error"
        items.append(
            BuilderActivityItem(
                id=f"act_{runtime.id}",
                kind=kind,
                status=status,
                title=title,
                message=_safe_text(runtime.message, fallback=title),
                timestamp=runtime.updated_at,
                snapshot_id=runtime.snapshot_id,
                runtime_session_id=runtime.id,
                metadata={"health": runtime.health, "mode": runtime.mode},
            )
        )

    for endpoint in runtime_store.list_preview_endpoints(workspace_id=workspace_id, project_id=project_id):
        endpoint_status = endpoint.status.lower().strip()
        is_proxy = str(endpoint.access_mode or "").strip().lower() == "proxy"
        if endpoint_status == "ready":
            kind = "preview_connected"
            status = "ready"
            title = "Cloud preview proxy ready" if is_proxy else "Local preview connected"
        elif endpoint_status in {"revoked", "unavailable"}:
            kind = "preview_disconnected" if endpoint_status == "revoked" else "preview_error"
            status = "stopped" if endpoint_status == "revoked" else "error"
            if endpoint_status == "revoked":
                title = "Cloud preview proxy stopped" if is_proxy else "Local preview disconnected"
            else:
                title = "Cloud preview proxy unavailable" if is_proxy else "Preview endpoint unavailable"
        else:
            kind = "runtime_status"
            status = "running"
            title = "Cloud preview proxy provisioning" if is_proxy else "Local preview endpoint provisioning"
        safe_url = _sanitize_local_preview_url(endpoint.url)
        items.append(
            BuilderActivityItem(
                id=f"act_{endpoint.id}",
                kind=kind,
                status=status,
                title=title,
                message=title,
                timestamp=endpoint.last_checked_at or _utc_now_iso(),
                runtime_session_id=endpoint.runtime_session_id,
                preview_endpoint_id=endpoint.id,
                metadata={
                    "access_mode": endpoint.access_mode,
                    "status": endpoint.status,
                    "preview_url": safe_url if safe_url else None,
                },
            )
        )

    run_profile_store = get_builder_run_profile_store()
    for profile in run_profile_store.list_local_run_profiles(workspace_id=workspace_id, project_id=project_id):
        if profile.status == "configured":
            title = "Local run profile configured"
            status = "ready"
        elif profile.status == "disabled":
            title = "Local run profile cleared"
            status = "stopped"
        else:
            title = "Local run profile draft"
            status = "info"
        items.append(
            BuilderActivityItem(
                id=f"act_{profile.id}",
                kind="runtime_status",
                status=status,
                title=title,
                message=title,
                timestamp=profile.updated_at,
                snapshot_id=profile.source_snapshot_id,
                metadata={
                    "working_directory": profile.working_directory,
                    "expected_preview_url": profile.expected_preview_url,
                },
            )
        )

    for job in get_builder_runtime_job_store().list_cloud_runtime_jobs(
        workspace_id=workspace_id,
        project_id=project_id,
    ):
        status = job.status if job.status in _CLOUD_RUNTIME_JOB_STATES else "info"
        title = "Cloud runtime job queued"
        if job.phase == "validating_source":
            title = "Cloud runtime source handoff planned"
        if job.status == "running":
            title = "Cloud runtime job running"
            if job.phase == "provider_accepted":
                title = "Cloud runtime provider accepted request"
        elif job.status == "succeeded":
            title = "Cloud runtime job completed"
        elif job.status in {"failed", "unsupported"}:
            title = "Cloud runtime job failed"
            if str((job.metadata or {}).get("source_handoff_status") or "").lower() == "failed":
                title = "Cloud runtime source handoff failed"
        elif job.status == "cancelled":
            title = "Cloud runtime job cancelled"
        message = _safe_text(job.error_message, fallback=job.logs_summary or title)
        items.append(
            BuilderActivityItem(
                id=f"act_{job.id}",
                kind="runtime_status",
                status=status,
                title=title,
                message=message,
                timestamp=job.updated_at,
                snapshot_id=job.source_snapshot_id,
                runtime_session_id=job.runtime_session_id,
                metadata={
                    "provider": job.provider,
                    "phase": job.phase,
                    "job_id": job.id,
                },
            )
        )

    for request in get_builder_visual_edit_request_store().list_visual_edit_requests(
        workspace_id=workspace_id,
        project_id=project_id,
    ):
        request_status = request.status.strip().lower()
        if request_status in {"draft", "queued", "processing"}:
            if request_status == "processing":
                status = "running"
            else:
                status = "queued"
            title = "Visual edit request saved"
        elif request_status == "resolved":
            status = "succeeded"
            title = "Visual edit request resolved"
        elif request_status in {"failed", "cancelled"}:
            status = "failed" if request_status == "failed" else "stopped"
            title = "Visual edit request closed"
        else:
            status = "info"
            title = "Visual edit request updated"
        items.append(
            BuilderActivityItem(
                id=f"act_{request.id}",
                kind="runtime_status",
                status=status,
                title=title,
                message=_safe_text(request.instruction, fallback=title),
                timestamp=request.updated_at,
                snapshot_id=request.source_snapshot_id,
                runtime_session_id=request.runtime_session_id,
                preview_endpoint_id=request.preview_endpoint_id,
                metadata={"visual_edit_request_id": request.id, "status": request.status},
            )
        )

    items.sort(key=lambda row: (row.timestamp, row.id), reverse=True)
    return items


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/sources")
async def list_project_sources(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_project_sources(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "sources": [r.model_dump(mode="json") for r in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/source-snapshots")
async def list_source_snapshots(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_source_snapshots(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "source_snapshots": [r.model_dump(mode="json") for r in rows],
    }


@router.post("/api/workspaces/{workspace_id}/builder/default-project")
async def ensure_default_builder_project_route(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    from src.ham.builder_default_project import ensure_default_builder_project as _ensure_default_builder

    rec = _ensure_default_builder(ctx.workspace_id)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": rec.id,
        "project": rec.model_dump(mode="json"),
    }


@router.get(
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/source-snapshots/{snapshot_id}/files",
)
async def list_builder_snapshot_files(
    project_id: str,
    snapshot_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    snap = _source_snapshot_for_project_or_404(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
    )
    manifest = snap.manifest or {}
    files_out: list[dict[str, Any]] = []
    kind = str(manifest.get("kind") or "")
    if kind == "inline_text_bundle":
        entries = manifest.get("entries")
        if isinstance(entries, list):
            for e in entries[:_SNAPSHOT_LISTING_CAP]:
                if isinstance(e, dict) and isinstance(e.get("path"), str):
                    files_out.append(
                        {"path": e["path"], "size_bytes": int(e.get("size_bytes") or 0)},
                    )
    else:
        entries = manifest.get("entries")
        if isinstance(entries, list):
            for e in entries[:_SNAPSHOT_LISTING_CAP]:
                if isinstance(e, dict) and isinstance(e.get("path"), str):
                    files_out.append(
                        {
                            "path": e["path"],
                            "size_bytes": int(e.get("size_bytes") or 0),
                            "is_dir": bool(e.get("is_dir")),
                        },
                    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "source_snapshot_id": snap.id,
        "files": files_out,
    }


@router.get(
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/source-snapshots/{snapshot_id}/files/content",
)
async def read_builder_snapshot_file_content(
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    project_id: str,
    snapshot_id: str,
    path: str = Query(..., min_length=1, max_length=2048),
) -> dict[str, Any]:
    from src.ham.builder_chat_scaffold import (
        load_zip_bytes_for_snapshot,
        read_inline_snapshot_file,
        read_zip_snapshot_file_bytes,
    )

    snap = _source_snapshot_for_project_or_404(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
    )
    manifest = snap.manifest or {}
    kind = str(manifest.get("kind") or "")


    if kind == "inline_text_bundle":
        hit = read_inline_snapshot_file(snapshot=snap, rel_path=path)
        if hit is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "File not found in snapshot.",
                    },
                },
            )
        text, nbytes = hit
        return {
            "path": path.replace("\\", "/").lstrip("/"),
            "encoding": "utf-8",
            "content": text,
            "size_bytes": nbytes,
        }
    stem = _artifact_stem_from_uri(snap.artifact_uri) or str(
        (snap.metadata or {}).get("artifact_id") or "",
    ).strip()
    if not stem:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ARTIFACT_NOT_FOUND", "message": "Snapshot has no artifact."}},
        )
    zbytes = load_zip_bytes_for_snapshot(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        artifact_id=stem,
    )
    if zbytes is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ARTIFACT_NOT_FOUND", "message": "ZIP artifact missing."}},
        )
    raw = read_zip_snapshot_file_bytes(
        zip_bytes=zbytes,
        rel_path=path,
        max_out=_SNAPSHOT_CONTENT_MAX_BYTES,
    )
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "File not found in archive."}},
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail={"error": {"code": "BINARY_FILE", "message": "Binary files are not shown."}},
        ) from None
    return {
        "path": path.replace("\\", "/").lstrip("/"),
        "encoding": "utf-8",
        "content": text,
        "size_bytes": len(raw),
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/import-jobs")
async def list_import_jobs(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_source_store().list_import_jobs(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "workspace_id": ctx.workspace_id,
        "import_jobs": [r.model_dump(mode="json") for r in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-status")
async def get_builder_preview_status(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    return _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id)


@router.api_route(
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/",
    methods=["GET", "HEAD"],
)
async def get_builder_preview_proxy_root(
    project_id: str,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_preview_proxy_ctx)],
) -> Response:
    return await _serve_builder_preview_proxy(
        project_id=project_id,
        path="",
        request=request,
        ctx=ctx,
    )


@router.api_route(
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/preview-proxy/{path:path}",
    methods=["GET", "HEAD"],
)
async def get_builder_preview_proxy(
    project_id: str,
    path: str,
    request: Request,
    ctx: Annotated[WorkspaceContext, Depends(require_preview_proxy_ctx)],
) -> Response:
    return await _serve_builder_preview_proxy(
        project_id=project_id,
        path=path,
        request=request,
        ctx=ctx,
    )


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/activity")
async def get_builder_activity(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    items = _build_activity_items(workspace_id=ctx.workspace_id, project_id=project_id)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "items": [row.model_dump(mode="json") for row in items],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/activity/stream")
async def stream_builder_activity(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> StreamingResponse:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    max_seconds = _float_env("HAM_BUILDER_ACTIVITY_STREAM_MAX_SECONDS", 25.0, min_value=5.0, max_value=120.0)
    poll_seconds = _float_env("HAM_BUILDER_ACTIVITY_STREAM_POLL_SECONDS", 1.5, min_value=0.5, max_value=5.0)
    max_events = _int_env("HAM_BUILDER_ACTIVITY_STREAM_MAX_EVENTS", _ACTIVITY_STREAM_MAX_EVENTS, min_value=4, max_value=256)

    async def _gen() -> Any:
        started = datetime.now(UTC)
        events_sent = 0
        last_cursor: str | None = None
        while events_sent < max_events:
            payload = _activity_stream_payload(workspace_id=ctx.workspace_id, project_id=project_id)
            cursor = str(payload.get("stream_cursor") or "")
            if cursor != last_cursor:
                yield _sse_pack("activity", payload)
                last_cursor = cursor
                events_sent += 1
            else:
                yield _sse_pack("heartbeat", {"ts": _utc_now_iso(), "connection_state": "live"})
                events_sent += 1
            elapsed = (datetime.now(UTC) - started).total_seconds()
            if elapsed >= max_seconds:
                break
            await asyncio.sleep(poll_seconds)
        yield _sse_pack("done", {"reason": "stream_closed", "ts": _utc_now_iso()})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
        },
    )


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/usage-events")
async def list_builder_usage_events(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_usage_event_store().list_usage_events(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "usage_events": [row.model_dump(mode="json") for row in rows],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests")
async def list_builder_visual_edit_requests(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    rows = get_builder_visual_edit_request_store().list_visual_edit_requests(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_requests": [row.model_dump(mode="json") for row in rows],
    }


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests")
async def create_builder_visual_edit_request(
    project_id: str,
    body: VisualEditRequestPayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    target = _sanitize_visual_edit_target(body.target)
    preview_url_kind = _sanitize_preview_url_kind(body.preview_url_kind)
    selector_hints = _sanitize_selector_hints(body.selector_hints)
    target_selector_hints = _sanitize_selector_hints(
        list((target or {}).get("selector_hints") or []) if target is not None else []
    )
    merged_selector_hints = _sanitize_selector_hints(selector_hints + target_selector_hints)
    bbox = _sanitize_visual_edit_bbox(body.bbox)
    if bbox is None and target is not None and all(
        key in target for key in ("x", "y", "width", "height")
    ):
        bbox = _sanitize_visual_edit_bbox(
            {
                "x": target.get("x"),
                "y": target.get("y"),
                "width": target.get("width"),
                "height": target.get("height"),
            }
        )
    safe_metadata = _sanitize_metadata(body.metadata)
    if target is not None:
        safe_metadata["target"] = target
    if preview_url_kind is not None:
        safe_metadata["preview_url_kind"] = preview_url_kind
    request = VisualEditRequest(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        runtime_session_id=str(body.runtime_session_id or "").strip() or None,
        preview_endpoint_id=str(body.preview_endpoint_id or "").strip() or None,
        route=_sanitize_route(body.route),
        selector_hints=merged_selector_hints,
        bbox=bbox,
        instruction=_sanitize_visual_edit_instruction(body.instruction),
        status=_normalize_visual_edit_status(body.status),
        created_by=actor.user_id if actor is not None else None,
        metadata=safe_metadata,
    )
    saved = get_builder_visual_edit_request_store().upsert_visual_edit_request(request)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_request": saved.model_dump(mode="json"),
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/visual-edit-requests/{request_id}")
async def cancel_builder_visual_edit_request(
    project_id: str,
    request_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    cancelled = get_builder_visual_edit_request_store().cancel_visual_edit_request(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        request_id=request_id,
    )
    if cancelled is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "VISUAL_EDIT_REQUEST_NOT_FOUND",
                    "message": f"Unknown visual edit request {request_id!r}.",
                }
            },
        )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "visual_edit_request": cancelled.model_dump(mode="json"),
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/worker-capabilities")
async def get_builder_worker_capabilities(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    entries = _build_worker_capabilities(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        actor=actor,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "workers": [entry.model_dump(mode="json") for entry in entries],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def get_builder_local_run_profile(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    profile = get_builder_run_profile_store().get_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return _serialize_local_run_profile(profile, workspace_id=ctx.workspace_id, project_id=project_id)


@router.put("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def put_builder_local_run_profile(
    project_id: str,
    body: LocalRunProfilePayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    profile_store = get_builder_run_profile_store()
    existing = profile_store.get_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    expected_preview_url = _sanitize_local_preview_url(body.expected_preview_url)
    if body.expected_preview_url and expected_preview_url is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "LOCAL_RUN_PREVIEW_URL_INVALID",
                    "message": "expected_preview_url must be a safe local loopback http URL with explicit port.",
                }
            },
        )
    status = str(body.status or "configured").strip().lower()
    if status not in {"draft", "configured", "disabled"}:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "LOCAL_RUN_PROFILE_STATUS_INVALID", "message": "status must be draft, configured, or disabled."}},
        )
    install_argv = _parse_command_argv(body.install_command, field_name="install_command")
    dev_argv = _parse_command_argv(body.dev_command, field_name="dev_command", required=True) or []
    build_argv = _parse_command_argv(body.build_command, field_name="build_command")
    test_argv = _parse_command_argv(body.test_command, field_name="test_command")
    if existing is None:
        profile = LocalRunProfile(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            dev_command_argv=dev_argv,
            created_by=actor.user_id if actor is not None else None,
        )
    else:
        profile = existing
    profile.source_snapshot_id = source_snapshot_id
    profile.display_name = _safe_text(body.display_name, fallback="Local run profile")
    profile.working_directory = _normalize_working_directory(body.working_directory)
    profile.install_command_argv = install_argv
    profile.dev_command_argv = dev_argv
    profile.build_command_argv = build_argv
    profile.test_command_argv = test_argv
    profile.expected_preview_url = expected_preview_url
    profile.execution_mode = "local_only"
    profile.status = status
    profile.metadata = _sanitize_metadata(body.metadata)
    saved = profile_store.upsert_local_run_profile(profile)
    return _serialize_local_run_profile(saved, workspace_id=ctx.workspace_id, project_id=project_id)


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-run-profile")
async def delete_builder_local_run_profile(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    cleared = get_builder_run_profile_store().clear_active_local_run_profile(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return _serialize_local_run_profile(cleared, workspace_id=ctx.workspace_id, project_id=project_id)


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime")
async def get_builder_cloud_runtime(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    runtime = get_builder_runtime_store().get_latest_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        mode="cloud",
    )
    return _serialize_cloud_runtime(runtime, workspace_id=ctx.workspace_id, project_id=project_id)


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/request")
async def request_builder_cloud_runtime(
    project_id: str,
    body: CloudRuntimeRequestPayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    effective_snapshot_id = source_snapshot_id or _active_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    requested_status = str(body.status or "").strip().lower()
    if requested_status and requested_status not in _CLOUD_RUNTIME_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CLOUD_RUNTIME_STATUS_INVALID",
                    "message": "status must be queued, provisioning, running, failed, expired, or unsupported.",
                }
            },
        )
    force_new = bool(body.force_new)
    provider_mode = get_cloud_runtime_provider_mode()
    experiment_status, _ = get_cloud_runtime_experiment_status()
    should_execute_job = (
        requested_status in {"", "queued"}
        and effective_snapshot_id is not None
        and provider_mode != "disabled"
        and experiment_status not in {"experiment_not_enabled", "disabled", "config_missing"}
    )
    if force_new:
        _supersede_active_cloud_runtime_jobs(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            reason="Superseded by explicit force_new cloud runtime request.",
        )
    if should_execute_job:
        metadata = _sanitize_metadata(body.metadata)
        if force_new:
            metadata = {**metadata, "force_new": True}
        saved_job, runtime = run_persist_builder_cloud_runtime_job(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            source_snapshot_id=effective_snapshot_id,
            requested_by=actor.user_id if actor is not None else None,
            metadata=metadata,
        )
        return {
            "runtime": runtime.model_dump(mode="json") if runtime is not None else None,
            "cloud_runtime": _serialize_cloud_runtime(
                runtime,
                workspace_id=ctx.workspace_id,
                project_id=project_id,
            ),
            "job": saved_job.model_dump(mode="json"),
            "preview_status": _build_preview_status_payload(
                workspace_id=ctx.workspace_id,
                project_id=project_id,
            ),
        }
    runtime = get_builder_runtime_store().request_cloud_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=effective_snapshot_id,
        requested_by=actor.user_id if actor is not None else None,
        metadata={**_sanitize_metadata(body.metadata), **({"force_new": True} if force_new else {})},
    )
    if requested_status and requested_status != "queued":
        runtime.status = requested_status
        runtime.updated_at = _utc_now_iso()
        runtime = get_builder_runtime_store().upsert_runtime_session(runtime)
    return {
        "runtime": runtime.model_dump(mode="json"),
        "cloud_runtime": _serialize_cloud_runtime(
            runtime,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        ),
    }


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/jobs")
async def create_builder_cloud_runtime_job(
    project_id: str,
    body: CloudRuntimeJobPayload,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    force_new = bool(body.force_new)
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    if force_new:
        _supersede_active_cloud_runtime_jobs(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            reason="Superseded by explicit force_new cloud runtime job request.",
        )
    metadata = _sanitize_metadata(body.metadata)
    if force_new:
        metadata = {**metadata, "force_new": True}
    saved_job, runtime = run_persist_builder_cloud_runtime_job(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        requested_by=actor.user_id if actor is not None else None,
        metadata=metadata,
    )
    return {
        "job": _serialize_cloud_runtime_job(saved_job),
        "runtime_session": runtime.model_dump(mode="json") if runtime is not None else None,
        "cloud_runtime": _serialize_cloud_runtime(
            runtime,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        ),
        "preview_status": _build_preview_status_payload(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        ),
        "activity_item": _build_activity_items(workspace_id=ctx.workspace_id, project_id=project_id)[0],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/jobs")
async def list_builder_cloud_runtime_jobs(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    jobs = get_builder_runtime_job_store().list_cloud_runtime_jobs(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "jobs": [_serialize_cloud_runtime_job(row) for row in jobs],
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/jobs/{job_id}")
async def get_builder_cloud_runtime_job(
    project_id: str,
    job_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    job = get_builder_runtime_job_store().get_cloud_runtime_job(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        job_id=job_id,
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CLOUD_RUNTIME_JOB_NOT_FOUND",
                    "message": f"Unknown cloud runtime job {job_id!r}.",
                }
            },
        )
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "job": _serialize_cloud_runtime_job(job),
    }


@router.get("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime/jobs/{job_id}/status")
async def get_builder_cloud_runtime_job_status(
    project_id: str,
    job_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_READ))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    job = get_builder_runtime_job_store().get_cloud_runtime_job(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        job_id=job_id,
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CLOUD_RUNTIME_JOB_NOT_FOUND",
                    "message": f"Unknown cloud runtime job {job_id!r}.",
                }
            },
        )
    runtime = _runtime_session_by_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        runtime_session_id=job.runtime_session_id,
    )
    preview_status = _build_preview_status_payload(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    lifecycle = get_runtime_job_lifecycle_status(job=job, runtime_session=runtime)
    return {
        "workspace_id": ctx.workspace_id,
        "project_id": project_id,
        "job": _serialize_cloud_runtime_job(job),
        "runtime_session": runtime.model_dump(mode="json") if runtime is not None else None,
        "preview_status": preview_status,
        "runtime_diagnostics": _safe_runtime_diagnostics(job.metadata),
        "lifecycle": {
            "phase": lifecycle.phase,
            "message": lifecycle.message,
            "updated_at": lifecycle.updated_at,
            "provider_status": lifecycle.provider_status,
            "logs_summary": lifecycle.logs_summary,
        },
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime")
async def delete_builder_cloud_runtime(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    runtime = get_builder_runtime_store().clear_cloud_runtime(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    return {
        "cloud_runtime": _serialize_cloud_runtime(
            runtime,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
        )
    }


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-preview")
async def register_local_preview(
    project_id: str,
    body: LocalPreviewRegisterRequest,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    safe_preview_url = _sanitize_local_preview_url(body.preview_url)
    if safe_preview_url is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "LOCAL_PREVIEW_URL_INVALID",
                    "message": "Preview URL must be a safe local loopback http URL without credentials.",
                }
            },
        )
    source_snapshot_id = _validated_snapshot_id(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=body.source_snapshot_id,
    )
    runtime_store = get_builder_runtime_store()
    runtime = runtime_store.upsert_local_runtime_session(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        source_snapshot_id=source_snapshot_id,
        message=(body.display_name or "").strip() or "Local preview connected.",
    )
    endpoint = runtime_store.get_active_preview_endpoint(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        runtime_session_id=runtime.id,
    )
    if endpoint is None:
        endpoint = PreviewEndpoint(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            runtime_session_id=runtime.id,
        )
    endpoint.url = safe_preview_url
    endpoint.access_mode = "local_url"
    endpoint.status = "ready"
    endpoint.last_checked_at = _utc_now_iso()
    endpoint = runtime_store.upsert_preview_endpoint(endpoint)
    runtime.preview_endpoint_id = endpoint.id
    runtime.updated_at = _utc_now_iso()
    runtime = runtime_store.upsert_runtime_session(runtime)
    return {
        "runtime_session": runtime.model_dump(mode="json"),
        "preview_endpoint": endpoint.model_dump(mode="json"),
        "preview_status": _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id),
    }


@router.delete("/api/workspaces/{workspace_id}/projects/{project_id}/builder/local-preview")
async def clear_local_preview(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    get_builder_runtime_store().clear_local_preview(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
    )
    status_payload = _build_preview_status_payload(workspace_id=ctx.workspace_id, project_id=project_id)
    if status_payload["status"] == "error":
        status_payload["status"] = "not_connected"
        status_payload["preview_url"] = None
        status_payload["message"] = "Local preview runtime is not connected."
    return {"preview_status": status_payload}


@router.post("/api/workspaces/{workspace_id}/projects/{project_id}/builder/import-jobs/zip")
async def create_zip_import_job(
    project_id: str,
    ctx: Annotated[WorkspaceContext, Depends(require_perm(PERM_WORKSPACE_WRITE))],
    actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    _project_in_workspace_or_404(project_id=project_id, workspace_id=ctx.workspace_id)
    try:
        payload = await read_zip_upload_bytes(file)
    except ZipSafetyError as exc:
        store = get_builder_source_store()
        created_by = actor.user_id if actor is not None else ""
        job = store.create_import_job(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            created_by=created_by,
            phase="received",
            status="queued",
        )
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="failed",
            error_code=exc.code,
            error_message=_safe_zip_error_message(exc.code),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": job.error_code,
                    "message": job.error_message,
                },
                "import_job": job.model_dump(mode="json"),
            },
        ) from exc
    store = get_builder_source_store()
    created_by = actor.user_id if actor is not None else ""
    job = store.create_import_job(
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase="received",
        status="queued",
    )
    try:
        job = store.mark_import_job_running(import_job_id=job.id, phase="validating")
        zip_info = validate_zip_upload(payload)
        artifact_uri, artifact_meta = _save_zip_artifact(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            payload=payload,
        )
        existing_sources = store.list_project_sources(workspace_id=ctx.workspace_id, project_id=project_id)
        source = next((row for row in existing_sources if row.kind == "zip_upload"), None)
        if source is None:
            source = ProjectSource(
                workspace_id=ctx.workspace_id,
                project_id=project_id,
                kind="zip_upload",
                status="ready",
                display_name=file.filename or "uploaded.zip",
                origin_ref="zip_upload",
                created_by=created_by,
                metadata={"latest_import_job_id": job.id},
            )
        else:
            source.status = "ready"
            source.display_name = file.filename or source.display_name
            source.origin_ref = "zip_upload"
            source.metadata = {**source.metadata, "latest_import_job_id": job.id}
        source = store.upsert_project_source(source)
        snapshot = SourceSnapshot(
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            project_source_id=source.id,
            digest_sha256=zip_info.digest_sha256,
            size_bytes=zip_info.uncompressed_bytes,
            artifact_uri=artifact_uri,
            manifest={
                "compressed_bytes": zip_info.compressed_bytes,
                "uncompressed_bytes": zip_info.uncompressed_bytes,
                "file_count": zip_info.file_count,
                "dir_count": zip_info.dir_count,
                "entries": [
                    {
                        "path": e.path,
                        "size_bytes": e.size_bytes,
                        "compressed_bytes": e.compressed_bytes,
                        "is_dir": e.is_dir,
                    }
                    for e in zip_info.entries
                ],
                "truncated_entries": max(0, zip_info.file_count + zip_info.dir_count - len(zip_info.entries)),
            },
            created_by=created_by,
            metadata=artifact_meta,
        )
        snapshot = store.upsert_source_snapshot(snapshot)
        source.active_snapshot_id = snapshot.id
        source = store.upsert_project_source(source)
        job = store.mark_import_job_succeeded(
            import_job_id=job.id,
            phase="materialized",
            source_snapshot_id=snapshot.id,
            stats={
                "file_count": zip_info.file_count,
                "dir_count": zip_info.dir_count,
                "compressed_bytes": zip_info.compressed_bytes,
                "uncompressed_bytes": zip_info.uncompressed_bytes,
            },
        )
        return {
            "project_id": project_id,
            "workspace_id": ctx.workspace_id,
            "import_job": job.model_dump(mode="json"),
            "project_source": source.model_dump(mode="json"),
            "source_snapshot": snapshot.model_dump(mode="json"),
        }
    except ZipSafetyError as exc:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="failed",
            error_code=exc.code,
            error_message=_safe_zip_error_message(exc.code),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": job.error_code,
                    "message": job.error_message,
                },
                "import_job": job.model_dump(mode="json"),
            },
        ) from exc
    except (OSError, ValueError) as exc:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="failed",
            error_code="ZIP_INVALID",
            error_message=_safe_zip_error_message("ZIP_INVALID"),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "ZIP_INVALID",
                    "message": _safe_zip_error_message("ZIP_INVALID"),
                },
                "import_job": job.model_dump(mode="json"),
            },
        ) from exc
