"""Read-only HAM Capability Directory API (Phase 1).

Static first-party registry only; no apply, no mutation, no remote registries.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.capability_directory import (
    directory_index_payload,
    get_bundle_payload,
    list_bundles_payload,
    list_capabilities_payload,
)

router = APIRouter(tags=["capability-directory"], dependencies=[Depends(get_ham_clerk_actor)])


def _unknown_bundle(bundle_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "CAPABILITY_BUNDLE_UNKNOWN",
                "message": f"No bundle with id {bundle_id!r} in first-party directory.",
            }
        },
    )


@router.get("/api/capability-directory")
async def get_capability_directory() -> dict[str, Any]:
    """Index: schema, counts, trust summary, sub-endpoints."""
    return directory_index_payload()


@router.get("/api/capability-directory/capabilities")
async def list_capability_directory_capabilities() -> dict[str, Any]:
    """Atomic capability records (first-party static registry)."""
    return list_capabilities_payload()


@router.get("/api/capability-directory/bundles")
async def list_capability_directory_bundles() -> dict[str, Any]:
    """Bundle/template records."""
    return list_bundles_payload()


@router.get("/api/capability-directory/bundles/{bundle_id}")
async def get_capability_directory_bundle(bundle_id: str) -> dict[str, Any]:
    """Single bundle by id; 404 if unknown."""
    payload = get_bundle_payload(bundle_id)
    if payload is None:
        raise _unknown_bundle(bundle_id.strip())
    return payload
