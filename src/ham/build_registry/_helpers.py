"""Shared parsing helpers for build registry validation and compose."""

from __future__ import annotations

from typing import Any

from src.ham.build_registry.errors import BuildRegistryConfigError


def require_str(data: dict[str, Any], field: str, *, source: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BuildRegistryConfigError(f"{source}: missing or empty field {field!r}")
    return value.strip()


def require_str_list(data: dict[str, Any], field: str, *, source: str) -> list[str]:
    raw = data.get(field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise BuildRegistryConfigError(
            f"{source}: field {field!r} must be a list when present"
        )
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise BuildRegistryConfigError(
                f"{source}: field {field!r}[{i}] must be a non-empty string"
            )
        out.append(item.strip())
    return out


def string_list_field(module: dict[str, Any], field: str) -> list[str]:
    raw = module.get(field)
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str)]
