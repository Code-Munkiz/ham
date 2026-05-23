"""Tests for scripts/social_telegram_inbound_poll.py (Cloud Run Job entrypoint).

Covers:
  VAL-M15-M3-POLLER-001 through VAL-M15-M3-POLLER-005
  VAL-M15-M3-RUNBOOK-001 through VAL-M15-M3-RUNBOOK-006
"""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# In-memory store helpers (reuse same pattern as collector tests)
# ---------------------------------------------------------------------------


class InMemoryOffsetStore:
    def __init__(self, initial: int | None = None) -> None:
        self._offset = initial
        self._last_run_at: str | None = None
        self._last_error: str | None = None

    def read_offset(self, bot_digest: str) -> int | None:
        return self._offset

    def write_offset(self, bot_digest: str, update_offset: int) -> None:
        self._offset = update_offset

    def read_poller_metadata(self, bot_digest: str) -> dict[str, Any]:
        return {"last_run_at": self._last_run_at, "last_error": self._last_error}

    def write_poller_metadata(
        self,
        bot_digest: str,
        *,
        last_run_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        if last_run_at is not None:
            self._last_run_at = last_run_at
        if last_error is not None:
            self._last_error = last_error


class InMemoryTranscriptStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append_row(self, row: dict[str, Any]) -> None:
        self.rows.append(dict(row))

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)


class RaisingTransport:
    """Transport that raises on call — used to verify it was never called."""

    def get_updates(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Transport should not have been called")


class MockGetUpdatesTransport:
    """Hand-rolled mock transport — no inheritance, no httpx."""

    def __init__(self, updates: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._updates: list[dict[str, Any]] = updates or []

    def get_updates(
        self,
        *,
        bot_token: str,
        offset: int,
        limit: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "bot_token": bot_token,
                "offset": offset,
                "limit": limit,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"ok": True, "result": list(self._updates)}


def _make_update(
    update_id: int = 1,
    message_id: int = 100,
    chat_id: int = -100100100,
    author_id: int = 99887766,
    text: str = "Hello from Telegram",
    date: int = 1700000000,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": author_id, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "supergroup"},
            "date": date,
            "text": text,
        },
    }


_SYNTHETIC_TOKEN = "synthetic-bot-token-XYZ"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "social_telegram_inbound_poll.py"
_RUNBOOK_PATH = _REPO_ROOT / "docs" / "M15_TELEGRAM_INBOUND_POLLER_RUNBOOK.md"


# ===========================================================================
# VAL-M15-M3-POLLER-001
# Job entrypoint script exists at the canonical path.
# ===========================================================================


def test_poller_script_exists() -> None:
    """VAL-M15-M3-POLLER-001: script file exists at the canonical path."""
    assert _SCRIPT_PATH.exists(), f"Expected script at {_SCRIPT_PATH}"


def test_poller_script_is_importable() -> None:
    """VAL-M15-M3-POLLER-001: script is importable and exposes main() callable."""
    mod = importlib.import_module("scripts.social_telegram_inbound_poll")
    assert callable(getattr(mod, "main", None)), (
        "scripts.social_telegram_inbound_poll must expose a 'main' callable"
    )


def test_no_new_poller_dockerfile() -> None:
    """VAL-M15-M3-POLLER-001: no new Dockerfile.poller or docker/poller/Dockerfile added."""
    assert not (_REPO_ROOT / "Dockerfile.poller").exists(), (
        "Dockerfile.poller must not be added; reuse existing Dockerfile"
    )
    assert not (_REPO_ROOT / "docker" / "poller" / "Dockerfile").exists(), (
        "docker/poller/Dockerfile must not be added; reuse existing Dockerfile"
    )


def test_dockerfile_copies_poller_entrypoint_script() -> None:
    """Mission 19 M1: ham-api image must ship the Cloud Run Job poller entrypoint."""
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "scripts/social_telegram_inbound_poll.py" in dockerfile, (
        "Dockerfile must COPY scripts/social_telegram_inbound_poll.py into the image"
    )


# ===========================================================================
# VAL-M15-M3-POLLER-002
# Job entrypoint refuses to run without TELEGRAM_BOT_TOKEN.
# ===========================================================================


def test_main_refuses_without_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """VAL-M15-M3-POLLER-002: absent token → non-zero exit, telegram_bot_token_missing in output."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        main(
            transport=RaisingTransport(),  # type: ignore[arg-type]
            offset_store=InMemoryOffsetStore(),
            transcript_store=InMemoryTranscriptStore(),
        )

    assert excinfo.value.code != 0, "Must exit with non-zero status when token is absent"
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "telegram_bot_token_missing" in combined, (
        "stderr/stdout must contain 'telegram_bot_token_missing'"
    )


def test_main_refuses_with_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-M15-M3-POLLER-002: empty token → non-zero exit, no transport call."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")

    with pytest.raises(SystemExit) as excinfo:
        main(
            transport=RaisingTransport(),  # type: ignore[arg-type]
            offset_store=InMemoryOffsetStore(),
            transcript_store=InMemoryTranscriptStore(),
        )

    assert excinfo.value.code != 0


# ===========================================================================
# VAL-M15-M3-POLLER-003
# Job entrypoint exits 0 when no updates are returned.
# ===========================================================================


def test_main_exits_0_on_no_updates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """VAL-M15-M3-POLLER-003: empty result → exit 0, no rows written, polled_count=0 in summary."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
    transcript_store = InMemoryTranscriptStore()
    offset_store = InMemoryOffsetStore(initial=0)

    with pytest.raises(SystemExit) as excinfo:
        main(
            transport=MockGetUpdatesTransport(updates=[]),
            offset_store=offset_store,
            transcript_store=transcript_store,
        )

    assert excinfo.value.code == 0, "Must exit with 0 when no updates are available"
    assert len(transcript_store.rows) == 0, "No transcript rows must be written"

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # Summary line must be present and report polled_count=0
    parsed = json.loads(combined.strip())
    assert parsed["polled_count"] == 0, "Summary must report polled_count=0"


# ===========================================================================
# VAL-M15-M3-POLLER-004
# Job entrypoint exits 0 after writing rows.
# ===========================================================================


def test_main_exits_0_after_writing_rows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """VAL-M15-M3-POLLER-004: one update → one row written, offset committed, exit 0."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)
    transcript_store = InMemoryTranscriptStore()
    offset_store = InMemoryOffsetStore(initial=0)
    updates = [_make_update(update_id=1)]

    with pytest.raises(SystemExit) as excinfo:
        main(
            transport=MockGetUpdatesTransport(updates=updates),
            offset_store=offset_store,
            transcript_store=transcript_store,
        )

    assert excinfo.value.code == 0, "Must exit with 0 after writing rows"
    assert len(transcript_store.rows) == 1, "One transcript row must be written"
    assert offset_store._offset == 2, "Offset must advance to max(update_id)+1 = 2"

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    parsed = json.loads(combined.strip())
    assert parsed["polled_count"] == 1, "Summary must report polled_count=1"
    assert parsed["new_offset"] == 2, "Summary must report new_offset=2"


# ===========================================================================
# VAL-M15-M3-POLLER-005
# Job entrypoint never logs the bot token.
# ===========================================================================


def test_main_token_absent_path_never_logs_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-M15-M3-POLLER-005: token-missing path → token never in stdout/stderr/logs."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit):
        main(
            transport=RaisingTransport(),  # type: ignore[arg-type]
            offset_store=InMemoryOffsetStore(),
            transcript_store=InMemoryTranscriptStore(),
        )

    captured = capsys.readouterr()
    assert _SYNTHETIC_TOKEN not in captured.out
    assert _SYNTHETIC_TOKEN not in captured.err
    assert _SYNTHETIC_TOKEN not in caplog.text


def test_main_no_updates_path_never_logs_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-M15-M3-POLLER-005: no-updates path → synthetic token never in stdout/stderr/logs."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)

    with pytest.raises(SystemExit):
        main(
            transport=MockGetUpdatesTransport(updates=[]),
            offset_store=InMemoryOffsetStore(),
            transcript_store=InMemoryTranscriptStore(),
        )

    captured = capsys.readouterr()
    assert _SYNTHETIC_TOKEN not in captured.out, "Token must not appear in stdout"
    assert _SYNTHETIC_TOKEN not in captured.err, "Token must not appear in stderr"
    assert _SYNTHETIC_TOKEN not in caplog.text, "Token must not appear in logs"


def test_main_with_updates_path_never_logs_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VAL-M15-M3-POLLER-005: with-updates path → synthetic token never in stdout/stderr/logs."""
    from scripts.social_telegram_inbound_poll import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _SYNTHETIC_TOKEN)

    with pytest.raises(SystemExit):
        main(
            transport=MockGetUpdatesTransport(updates=[_make_update(update_id=1)]),
            offset_store=InMemoryOffsetStore(initial=0),
            transcript_store=InMemoryTranscriptStore(),
        )

    captured = capsys.readouterr()
    assert _SYNTHETIC_TOKEN not in captured.out, "Token must not appear in stdout"
    assert _SYNTHETIC_TOKEN not in captured.err, "Token must not appear in stderr"
    assert _SYNTHETIC_TOKEN not in caplog.text, "Token must not appear in logs"


# ===========================================================================
# VAL-M15-M3-RUNBOOK-001
# Runbook exists at the canonical path.
# ===========================================================================


def test_runbook_exists_at_canonical_path() -> None:
    """VAL-M15-M3-RUNBOOK-001: runbook file exists at docs/M15_TELEGRAM_INBOUND_POLLER_RUNBOOK.md."""
    assert _RUNBOOK_PATH.exists(), f"Expected runbook at {_RUNBOOK_PATH}"


def test_runbook_is_git_tracked() -> None:
    """VAL-M15-M3-RUNBOOK-001: runbook is git-tracked."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(_RUNBOOK_PATH)],
        capture_output=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, f"Runbook must be git-tracked: {_RUNBOOK_PATH}"


def test_runbook_is_nonempty_and_ends_with_newline() -> None:
    """VAL-M15-M3-RUNBOOK-001: runbook has size > 0 and ends with newline."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    assert len(content) > 0, "Runbook must not be empty"
    assert content.endswith("\n"), "Runbook must end with a trailing newline"


# ===========================================================================
# VAL-M15-M3-RUNBOOK-002
# Runbook documents `gcloud run jobs create`.
# ===========================================================================


def test_runbook_documents_gcloud_run_jobs_create() -> None:
    """VAL-M15-M3-RUNBOOK-002: runbook contains gcloud run jobs create + project + entrypoint."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "gcloud run jobs create" in content, "Runbook must document 'gcloud run jobs create'"
    assert "clarity-staging-488201" in content, (
        "Runbook must reference the staging project 'clarity-staging-488201'"
    )
    assert "social_telegram_inbound_poll" in content, (
        "Runbook must name the entrypoint script 'social_telegram_inbound_poll'"
    )


# ===========================================================================
# VAL-M15-M3-RUNBOOK-003
# Runbook documents `gcloud scheduler jobs create http`.
# ===========================================================================


def test_runbook_documents_gcloud_scheduler_jobs_create_http() -> None:
    """VAL-M15-M3-RUNBOOK-003: runbook contains gcloud scheduler jobs create http."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "gcloud scheduler jobs create http" in content, (
        "Runbook must document 'gcloud scheduler jobs create http'"
    )


# ===========================================================================
# VAL-M15-M3-RUNBOOK-004
# Runbook documents IAM grants required.
# ===========================================================================


def test_runbook_documents_iam_roles() -> None:
    """VAL-M15-M3-RUNBOOK-004: runbook contains roles/datastore.user and roles/run.invoker."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "roles/datastore.user" in content, (
        "Runbook must document roles/datastore.user (Firestore access)"
    )
    assert "roles/run.invoker" in content, (
        "Runbook must document roles/run.invoker (Cloud Scheduler → Cloud Run invoker)"
    )


# ===========================================================================
# VAL-M15-M3-RUNBOOK-005
# Runbook documents the smoke-test sequence.
# ===========================================================================


def test_runbook_documents_smoke_test_sequence() -> None:
    """VAL-M15-M3-RUNBOOK-005: runbook contains gcloud run jobs execute and smoke steps."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "gcloud run jobs execute" in content, (
        "Runbook must include 'gcloud run jobs execute' in the smoke-test sequence"
    )
    # Check for smoke-step language (offset advance or transcript rows)
    has_offset_language = any(
        phrase in content for phrase in ["offset", "offset advanced", "update_offset"]
    )
    has_transcript_language = any(
        phrase in content for phrase in ["transcript", "ham_social_telegram_transcripts"]
    )
    assert has_offset_language or has_transcript_language, (
        "Runbook must describe verifying offset advancement or transcript row presence"
    )


# ===========================================================================
# VAL-M15-M3-RUNBOOK-006
# Runbook explicitly states "operator-only" execution boundary.
# ===========================================================================


def test_runbook_states_operator_only_boundary() -> None:
    """VAL-M15-M3-RUNBOOK-006: runbook explicitly states workers do not execute these commands."""
    content = _RUNBOOK_PATH.read_text(encoding="utf-8")
    has_operator_only = any(
        phrase in content
        for phrase in [
            "Workers do not execute",
            "workers do not execute",
            "operator-only",
            "operator only",
            "Workers do NOT execute",
        ]
    )
    assert has_operator_only, (
        "Runbook must explicitly state that workers/agents do not execute the gcloud commands"
    )
