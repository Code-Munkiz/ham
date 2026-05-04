"""Optional write-through: persist validated Anthropic keys to Secret Manager (admin MVP).

Used when ``HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH`` is enabled on a
Cloud Run–style host. Never logs raw keys or secret payloads.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Final

import httpx

_LOG = logging.getLogger(__name__)

ANTHROPIC_SECRET_ID: Final[str] = "anthropic-api-key"


def connected_tools_secret_manager_write_through_enabled() -> bool:
    raw = (os.environ.get("HAM_CONNECTED_TOOLS_SECRET_MANAGER_WRITE_THROUGH") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _gcp_project_id() -> str:
    return (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT") or "").strip()


def _cloud_run_region() -> str:
    reg = (os.environ.get("HAM_CLOUD_RUN_REGION") or "").strip()
    if reg:
        return reg
    try:
        r = httpx.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/region",
            headers={"Metadata-Flavor": "Google"},
            timeout=2.0,
        )
        r.raise_for_status()
        return r.text.strip().split("/")[-1]
    except Exception:
        return ""


def publish_anthropic_api_key_to_secret_manager(api_key: str) -> None:
    """Append ``api_key`` as a new version of ``anthropic-api-key``.

    Raises ``RuntimeError`` with a caller-safe message (no secret values).
    """
    from google.cloud import secretmanager  # dep: google-cloud-secret-manager

    project = _gcp_project_id()
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set; cannot write Anthropic credential to Secret Manager."
        )
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("Refused to publish an empty Anthropic API key.")
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project}/secrets/{ANTHROPIC_SECRET_ID}"
    try:
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": key.encode("utf-8")}}
        )
    except Exception as exc:
        _LOG.warning(
            "anthropic secret write-through failed: %s (secret id=%s)",
            type(exc).__name__,
            ANTHROPIC_SECRET_ID,
        )
        raise RuntimeError(
            "Could not save the Anthropic API key to Secret Manager. "
            "Ensure the Cloud Run service account can add secret versions on "
            f"'{ANTHROPIC_SECRET_ID}' (for example roles/secretmanager.secretVersionAdder "
            "or Secret Manager Admin on that secret)."
        ) from exc


def try_rollout_cloud_run_service_for_new_secrets() -> None:
    """Best-effort new revision so ``ANTHROPIC_API_KEY`` env picks up ``latest`` secret.

    Skips quietly when not on Cloud Run or when IAM blocks ``run.services.update``.
    """
    from google.cloud import run_v2  # dep: google-cloud-run

    project = _gcp_project_id()
    service_id = (os.environ.get("K_SERVICE") or "").strip()
    region = _cloud_run_region()
    if not project or not service_id or not region:
        return
    name = f"projects/{project}/locations/{region}/services/{service_id}"
    client = run_v2.ServicesClient()
    try:
        svc = client.get_service(name=name)
    except Exception as exc:
        _LOG.warning("Cloud Run get_service for rollout skipped: %s", type(exc).__name__)
        return
    try:
        labels = dict(svc.template.labels or {})
        labels["ham-connected-tools-nonce"] = str(time.time_ns())
        svc.template.labels = labels
        op = client.update_service(service=svc)
        op.result(timeout=180)
    except Exception as exc:
        _LOG.warning(
            "Cloud Run self-rollout after secret write skipped: %s. "
            "Grant run.services.update on this service if cold instances should see new secrets immediately.",
            type(exc).__name__,
        )
