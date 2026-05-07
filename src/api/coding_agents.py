"""
Read-only Coding Agents Control Plane API.

Surfaces the in-memory ``src/ham/harness_capabilities.py`` registry as JSON for the
hosted cockpit. No secrets, no provider URLs, no project ids; no write/launch surface.

Spec: ``docs/CODING_AGENTS_CONTROL_PLANE.md`` (cockpit vocabulary) and
``docs/HARNESS_PROVIDER_CONTRACT.md`` (authoritative capability registry).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.harness_capabilities import (
    HARNESS_CAPABILITIES,
    HarnessCapabilityRow,
    is_provider_launchable,
)

router = APIRouter(
    prefix="/api/coding-agents",
    tags=["control-plane"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


def _public_provider(row: HarnessCapabilityRow) -> dict[str, Any]:
    """HAM-safe projection — vocabulary fields only.

    Intentionally omits ``digest_family``, ``base_revision_source``, ``status_mapping``,
    ``requires_local_root`` / ``requires_remote_repo`` / ``returns_stable_external_id``
    / ``requires_provider_side_auth`` / ``supports_status_poll`` / ``supports_follow_up``
    so the hosted read API stays a small, stable cockpit-vocabulary projection.
    """
    return {
        "provider": row.provider,
        "display_name": row.display_name,
        "implemented": row.implemented,
        "registry_status": row.registry_status,
        "supports_operator_preview": row.supports_operator_preview,
        "supports_operator_launch": row.supports_operator_launch,
        "launchable": is_provider_launchable(row.provider),
        "audit_sink": row.audit_sink,
        "harness_family": row.harness_family,
        "topology_note": row.topology_note,
    }


@router.get("/providers")
async def list_coding_agent_providers() -> dict[str, Any]:
    """List all coding-agent providers (implemented + planned candidate) in stable order."""
    providers = [
        _public_provider(HARNESS_CAPABILITIES[k])
        for k in sorted(HARNESS_CAPABILITIES.keys())
    ]
    return {
        "kind": "coding_agent_provider_list",
        "providers": providers,
        "count": len(providers),
    }


@router.get("/providers/{provider}")
async def get_coding_agent_provider(
    provider: str = Path(..., min_length=1, max_length=64),
) -> dict[str, Any]:
    """Return one provider row by key, or 404 if not registered."""
    row = HARNESS_CAPABILITIES.get(provider.strip())
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CODING_AGENT_PROVIDER_NOT_FOUND",
                    "message": f"Unknown coding-agent provider {provider!r}.",
                }
            },
        )
    return {
        "kind": "coding_agent_provider",
        "provider": _public_provider(row),
    }
