"""
Tests for ``src/ham/coding_router/readiness.py`` — boolean collation only.

These tests lock that:

- No secret value is ever returned in any field of any provider readiness.
- Operator-only signals are populated only when ``include_operator_details=True``.
- Each provider's blocker copy is normie-safe (no env names, runner URLs,
  internal workflow ids).
- Project flags are presence-only and reflect ``ProjectRecord``.
- Audit and build readiness are independent: a host with a runner but no
  ``HAM_DROID_EXEC_TOKEN`` has audit ready and build blocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.ham.coding_router.readiness import collate_readiness
from src.persistence.project_store import (
    ProjectStore,
    set_project_store_for_tests,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every provider env var so each test starts from a known posture."""
    for name in (
        "HAM_DROID_RUNNER_URL",
        "HAM_DROID_RUNNER_TOKEN",
        "HAM_DROID_EXEC_TOKEN",
        "CURSOR_API_KEY",
        "HAM_CURSOR_CREDENTIALS_FILE",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "GCLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectStore:
    monkeypatch.setenv("HAM_CURSOR_CREDENTIALS_FILE", str(tmp_path / "cursor_creds.json"))
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture
def block_droid_local_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``shutil.which('droid')`` return None so local-runner readiness is False."""
    import src.ham.coding_router.readiness as readiness_mod

    monkeypatch.setattr(readiness_mod.shutil, "which", lambda _: None)


@pytest.fixture
def force_droid_local_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.ham.coding_router.readiness as readiness_mod

    monkeypatch.setattr(
        readiness_mod.shutil,
        "which",
        lambda name: "/usr/local/bin/droid" if name == "droid" else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FORBIDDEN_TOKENS = (
    "safe_edit_low",
    "low_edit",
    "--auto low",
    "ham_droid_exec_token",
    "ham_droid_runner_url",
    "ham_droid_runner_token",
    "anthropic_api_key",
    "cursor_api_key",
    "argv",
    "https://",
    "http://",
)


def _assert_no_secret_leakage(payload: Any) -> None:
    blob = json.dumps(payload, default=str).lower()
    for forbidden in _FORBIDDEN_TOKENS:
        assert forbidden not in blob, f"readiness leaks {forbidden!r}: {blob}"


def _provider(snapshot: Any, kind: str) -> Any:
    for p in snapshot.providers:
        if p.provider == kind:
            return p
    raise AssertionError(f"provider {kind!r} not in snapshot")


# ---------------------------------------------------------------------------
# All-unconfigured posture
# ---------------------------------------------------------------------------


def test_default_posture_no_agent_always_ready(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness()
    assert _provider(snap, "no_agent").available is True


def test_default_posture_audit_unavailable_without_runner(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness()
    audit = _provider(snap, "factory_droid_audit")
    assert audit.available is False
    assert audit.blockers
    assert all("HAM_" not in b for b in audit.blockers)


def test_default_posture_build_unavailable(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness()
    build = _provider(snap, "factory_droid_build")
    assert build.available is False
    # Blocker copy is normie-safe.
    assert all("HAM_DROID_EXEC_TOKEN" not in b for b in build.blockers)
    assert all("safe_edit_low" not in b for b in build.blockers)


def test_default_posture_cursor_unavailable_without_team_key(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness()
    cursor = _provider(snap, "cursor_cloud")
    assert cursor.available is False
    assert any("Cursor team key" in b for b in cursor.blockers)


def test_default_posture_claude_unavailable(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness()
    claude = _provider(snap, "claude_code")
    assert claude.available is False
    # Either SDK missing or auth missing — both copy variants are normie-safe.
    assert claude.blockers
    assert all("ANTHROPIC_API_KEY" not in b for b in claude.blockers)


# ---------------------------------------------------------------------------
# Audit independent from build (key product-truth lock)
# ---------------------------------------------------------------------------


def test_audit_ready_when_runner_present_even_without_build_token(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    # No HAM_DROID_EXEC_TOKEN.
    snap = collate_readiness()
    assert _provider(snap, "factory_droid_audit").available is True
    assert _provider(snap, "factory_droid_build").available is False


def test_build_ready_when_runner_and_token_both_set(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    snap = collate_readiness()
    assert _provider(snap, "factory_droid_audit").available is True
    assert _provider(snap, "factory_droid_build").available is True


# ---------------------------------------------------------------------------
# Cursor key
# ---------------------------------------------------------------------------


def test_cursor_ready_when_team_key_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "cur_" + "x" * 40)
    snap = collate_readiness()
    cursor = _provider(snap, "cursor_cloud")
    assert cursor.available is True
    assert cursor.blockers == ()


# ---------------------------------------------------------------------------
# Operator detail gating
# ---------------------------------------------------------------------------


def test_non_operator_snapshot_has_no_operator_signals(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    snap = collate_readiness(include_operator_details=False)
    for p in snap.providers:
        assert p.operator_signals == ()
    # public_dict strips operator_signals as defence in depth.
    pub = snap.public_dict()
    for entry in pub["providers"]:
        assert "operator_signals" not in entry


def test_operator_snapshot_contains_coarse_signals_only(
    monkeypatch: pytest.MonkeyPatch,
    force_droid_local_path: None,
    isolated_store: ProjectStore,
) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    snap = collate_readiness(include_operator_details=True)
    pub = snap.public_dict()
    audit = next(e for e in pub["providers"] if e["provider"] == "factory_droid_audit")
    assert "operator_signals" in audit
    # operator signals are coarse labels — not URLs, not values.
    for sig in audit["operator_signals"]:
        assert "http" not in sig.lower()
        assert "://" not in sig
    _assert_no_secret_leakage(pub)


# ---------------------------------------------------------------------------
# Project flags
# ---------------------------------------------------------------------------


def test_project_flags_when_project_missing(
    block_droid_local_path: None, isolated_store: ProjectStore
) -> None:
    snap = collate_readiness(project_id="project.does-not-exist")
    assert snap.project.found is False
    assert snap.project.project_id == "project.does-not-exist"
    assert snap.project.build_lane_enabled is False
    assert snap.project.has_github_repo is False


def test_project_flags_reflect_record(
    block_droid_local_path: None, isolated_store: ProjectStore, tmp_path: Path
) -> None:
    rec = isolated_store.make_record(name="demo", root=str(tmp_path))
    rec = rec.model_copy(update={"build_lane_enabled": True, "github_repo": "Code-Munkiz/ham"})
    isolated_store.register(rec)
    snap = collate_readiness(project_id=rec.id)
    assert snap.project.found is True
    assert snap.project.project_id == rec.id
    assert snap.project.build_lane_enabled is True
    assert snap.project.has_github_repo is True
    # github_repo *value* never appears in public_dict.
    pub = snap.public_dict()
    assert "Code-Munkiz/ham" not in json.dumps(pub)


# ---------------------------------------------------------------------------
# Sanitisation lock
# ---------------------------------------------------------------------------


def test_public_dict_never_leaks_secrets(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_URL", "https://runner.example/private")
    monkeypatch.setenv("HAM_DROID_RUNNER_TOKEN", "test-only-not-deployed-runner-token")
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    monkeypatch.setenv("CURSOR_API_KEY", "cur_" + "y" * 40)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only")
    pub = collate_readiness(include_operator_details=True).public_dict()
    _assert_no_secret_leakage(pub)
    # And specifically: secret values are absent.
    blob = json.dumps(pub).lower()
    assert "test-only-not-deployed" not in blob
    assert "sk-ant-test-only" not in blob
    assert "cur_" + "y" * 40 not in blob
    assert "runner.example/private" not in blob


# ---------------------------------------------------------------------------
# OpenCode readiness collator
# ---------------------------------------------------------------------------


def test_opencode_readiness_reports_available_when_fully_configured(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    """Env gates on + CLI present + auth set → snapshot's opencode_cli row available."""
    from src.ham.worker_adapters import opencode_adapter as _opencode_adapter

    monkeypatch.setenv("HAM_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("HAM_OPENCODE_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-opencode-canary")
    monkeypatch.setattr(
        _opencode_adapter.shutil,
        "which",
        lambda name: "/usr/local/bin/opencode" if name == "opencode" else None,
    )
    _opencode_adapter.reset_opencode_readiness_cache()
    snap = collate_readiness()
    oc = _provider(snap, "opencode_cli")
    assert oc.available is True
    assert oc.blockers == ()


def test_opencode_readiness_blockers_normie_safe(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    """Mirror the per-builder lock at the collator level for defence-in-depth."""
    monkeypatch.delenv("HAM_OPENCODE_ENABLED", raising=False)
    monkeypatch.delenv("HAM_OPENCODE_EXECUTION_ENABLED", raising=False)
    snap = collate_readiness()
    oc = _provider(snap, "opencode_cli")
    for blocker in oc.blockers:
        for forbidden in (
            "HAM_OPENCODE_ENABLED",
            "HAM_OPENCODE_EXECUTION_ENABLED",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "/usr/",
            "http://",
            "https://",
            "subprocess",
        ):
            assert forbidden not in blocker, (forbidden, blocker)
