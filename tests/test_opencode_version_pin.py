"""Drift detection between the Python OpenCode version pin and the Dockerfile.

The ``src/ham/opencode_runner/version_pin.py`` constants and the
``Dockerfile`` ARG defaults must agree, and the Dockerfile must keep
its SHA-256 verification, install location, and deterministic ENV vars
in place. These assertions are pure-Python: they only read the
Dockerfile and the version-pin module — no Docker build, no OpenCode
binary execution.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.ham.opencode_runner import (
    OPENCODE_PINNED_LINUX_X64_SHA256,
    OPENCODE_PINNED_VERSION,
)
from src.ham.opencode_runner.version_pin import (
    OPENCODE_PINNED_LINUX_X64_SHA256 as PIN_SHA,
)
from src.ham.opencode_runner.version_pin import (
    OPENCODE_PINNED_VERSION as PIN_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_python_pin_version_appears_in_dockerfile() -> None:
    assert PIN_VERSION in _dockerfile_text(), (
        f"OPENCODE_PINNED_VERSION={PIN_VERSION!r} not found in Dockerfile; "
        "bump the Dockerfile ARG OPENCODE_VERSION to match."
    )


def test_python_pin_sha_appears_in_dockerfile() -> None:
    assert PIN_SHA in _dockerfile_text(), (
        "OPENCODE_PINNED_LINUX_X64_SHA256 not found in Dockerfile; "
        "bump the Dockerfile ARG OPENCODE_LINUX_X64_SHA256 to match."
    )


def test_dockerfile_installs_opencode_to_usr_local_bin() -> None:
    assert "/usr/local/bin/opencode" in _dockerfile_text()


def test_dockerfile_sets_disable_autoupdate() -> None:
    assert "OPENCODE_DISABLE_AUTOUPDATE=1" in _dockerfile_text()


def test_dockerfile_sets_disable_models_fetch() -> None:
    assert "OPENCODE_DISABLE_MODELS_FETCH=1" in _dockerfile_text()


def test_dockerfile_sets_disable_claude_code() -> None:
    assert "OPENCODE_DISABLE_CLAUDE_CODE=1" in _dockerfile_text()


def test_dockerfile_uses_anomalyco_repo() -> None:
    text = _dockerfile_text()
    assert "anomalyco/opencode" in text, (
        "Dockerfile must source OpenCode from github.com/anomalyco/opencode; "
        "the sst/opencode and opencode-ai/opencode repos are legacy/unrelated."
    )
    assert "sst/opencode" not in text
    assert "opencode-ai/opencode" not in text


def test_dockerfile_uses_sha256sum_verification() -> None:
    assert "sha256sum -c" in _dockerfile_text(), (
        "Dockerfile must verify the OpenCode tarball with `sha256sum -c` "
        "before installing the binary."
    )


def test_python_pin_constants_re_exported_from_init() -> None:
    assert OPENCODE_PINNED_VERSION == PIN_VERSION
    assert OPENCODE_PINNED_LINUX_X64_SHA256 == PIN_SHA


def test_python_pin_version_format() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", PIN_VERSION), (
        f"OPENCODE_PINNED_VERSION must be a bare semver triple, got {PIN_VERSION!r}"
    )


def test_python_pin_sha_format() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", PIN_SHA), (
        "OPENCODE_PINNED_LINUX_X64_SHA256 must be 64 lowercase hex chars."
    )
