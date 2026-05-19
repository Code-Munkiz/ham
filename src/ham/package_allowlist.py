"""npm/pip package allowlist — Phase 1 #6 (Tier 1 #15).

Source of truth for allowed packages in builder previews.
The YAML file (src/ham/data/package-allowlist.yaml) is the only edit
required to add a package; no code change needed.

Spec: docs/MANUS_PARITY_ROADMAP.md § Tier 1 #15
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import yaml

from src.ham.builder_error_codes import PREVIEW_PACKAGE_INSTALL_DENIED, make_error
from src.ham.builder_plan import ErrorEnvelope

Manager = Literal["npm", "pip"]

_DEFAULT_YAML_PATH = Path(__file__).parent / "data" / "package-allowlist.yaml"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class AllowlistRecord:
    """Parsed allowlist keyed by manager name → frozenset of package names."""

    def __init__(self, npm: frozenset[str], pip: frozenset[str], version: str = "1") -> None:
        self.npm = npm
        self.pip = pip
        self.version = version

    def packages(self, manager: Manager) -> frozenset[str]:
        if manager == "npm":
            return self.npm
        if manager == "pip":
            return self.pip
        raise ValueError(f"Unknown manager {manager!r}; expected 'npm' or 'pip'")


def load_from_yaml(path: str | Path | None = None) -> AllowlistRecord:
    """Load and parse the allowlist YAML.  Cached by default path; call with
    an explicit path in tests to load fixtures without touching the singleton.
    """
    resolved = Path(path) if path is not None else _DEFAULT_YAML_PATH
    text = resolved.read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text) or {}

    def _load_set(key: str) -> frozenset[str]:
        raw = data.get(key) or []
        return frozenset(str(p).strip().lower() for p in raw if str(p).strip())

    return AllowlistRecord(
        npm=_load_set("npm"),
        pip=_load_set("pip"),
        version=str(data.get("version", "1")),
    )


# ---------------------------------------------------------------------------
# Protocol + singleton
# ---------------------------------------------------------------------------


@runtime_checkable
class PackageAllowlistProtocol(Protocol):
    def is_allowed(self, package_name: str, manager: Manager) -> bool: ...
    def list_allowed(self, manager: Manager) -> list[str]: ...
    def deny_error(self, package_name: str, manager: Manager) -> ErrorEnvelope: ...


class PackageAllowlist:
    """Queries the loaded allowlist record."""

    def __init__(self, record: AllowlistRecord) -> None:
        self._record = record

    def is_allowed(self, package_name: str, manager: Manager) -> bool:
        normalized = package_name.strip().lower()
        return normalized in self._record.packages(manager)

    def list_allowed(self, manager: Manager) -> list[str]:
        return sorted(self._record.packages(manager))

    def deny_error(self, package_name: str, manager: Manager) -> ErrorEnvelope:
        return make_error(
            PREVIEW_PACKAGE_INSTALL_DENIED,
            f"Package {package_name!r} ({manager}) is not in the builder allowlist.",
            fatal=True,
            retriable=False,
            details={"package": package_name, "manager": manager},
        )


_SINGLETON: list[PackageAllowlistProtocol | None] = [None]


def get_package_allowlist() -> PackageAllowlistProtocol:
    if _SINGLETON[0] is None:
        record = load_from_yaml()
        _SINGLETON[0] = PackageAllowlist(record)
    return _SINGLETON[0]


def set_package_allowlist_for_tests(impl: PackageAllowlistProtocol | None) -> None:
    _SINGLETON[0] = impl


# ---------------------------------------------------------------------------
# Public convenience functions (wrap singleton)
# ---------------------------------------------------------------------------


def is_allowed(package_name: str, manager: Manager) -> bool:
    return get_package_allowlist().is_allowed(package_name, manager)


def list_allowed(manager: Manager) -> list[str]:
    return get_package_allowlist().list_allowed(manager)


def packages_from_package_json(text: str) -> list[str]:
    """Return dependency names from a package.json body (dependencies + devDependencies)."""
    import json

    data = json.loads(text)
    names: list[str] = []
    for section in ("dependencies", "devDependencies"):
        block = data.get(section) or {}
        if isinstance(block, dict):
            names.extend(str(k).strip() for k in block if str(k).strip())
    return names


def packages_from_requirements(text: str) -> list[str]:
    """Return package names from a requirements.txt body (name only, no version pins)."""
    names: list[str] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("-"):
            continue
        token = re.split(r"[<>=!~\[]", raw, maxsplit=1)[0].strip()
        if token:
            names.append(token)
    return names


def _normalize_source_files(source_files: dict[str, Any] | list[Any] | None) -> dict[str, str]:
    if not source_files:
        return {}
    if isinstance(source_files, dict):
        return {str(k): str(v) for k, v in source_files.items()}
    out: dict[str, str] = {}
    for item in source_files:
        path = getattr(item, "path", None)
        data = getattr(item, "data", None)
        if path is None:
            continue
        if isinstance(data, (bytes, bytearray)):
            out[str(path)] = bytes(data).decode("utf-8", errors="replace")
        elif data is not None:
            out[str(path)] = str(data)
    return out


def _find_source_file(source_files: dict[str, Any] | list[Any] | None, suffix: str) -> str | None:
    normalized = _normalize_source_files(source_files)
    for path, content in normalized.items():
        if str(path).replace("\\", "/").endswith(suffix):
            return content
    return None


def check_install_allowed(
    command: list[str],
    *,
    source_files: dict[str, Any] | list[Any] | None = None,
) -> ErrorEnvelope | None:
    """Return a denial envelope if ``command`` is npm/pip install and a package is blocked."""
    if len(command) < 2:
        return None
    allowlist = get_package_allowlist()

    if command[0] == "npm" and command[1] == "install":
        body = _find_source_file(source_files, "package.json")
        if body is None:
            return None
        for package in packages_from_package_json(body):
            if not allowlist.is_allowed(package, "npm"):
                return allowlist.deny_error(package, "npm")
        return None

    # Pip-install allowlist support. No production caller as of Phase 1 (npm-only
    # scaffolds). Activate by wrapping any future pip install paths at the runtime
    # worker, mirroring the npm pattern in builder_runtime_worker.py.
    if command[0] == "pip" and command[1] == "install":
        if len(command) == 2:
            body = _find_source_file(source_files, "requirements.txt")
            if body is None:
                return None
            packages = packages_from_requirements(body)
        else:
            packages = [str(p).strip() for p in command[2:] if str(p).strip()]
        for package in packages:
            if not allowlist.is_allowed(package, "pip"):
                return allowlist.deny_error(package, "pip")
        return None

    return None
