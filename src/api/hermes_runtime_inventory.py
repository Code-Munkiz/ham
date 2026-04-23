"""Read-only Hermes local/runtime inventory (CLI + sanitized config)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.hermes_runtime_inventory import build_runtime_inventory

router = APIRouter(tags=["hermes-runtime"], dependencies=[Depends(get_ham_clerk_actor)])


@router.get("/api/hermes-runtime/inventory")
async def get_hermes_runtime_inventory() -> dict:
    """Hermes-owned capability snapshot via allowlisted read-only CLI + safe config fields."""
    return build_runtime_inventory()
