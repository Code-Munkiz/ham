from __future__ import annotations

import importlib
import pytest

from src.registry.backends import (
    BackendRecord,
    DEFAULT_BACKEND_REGISTRY,
    DEFAULT_BACKEND_ID,
    LocalDroidBackend,
)
from src.tools.droid_executor import DroidExecutionRecord


def test_default_registry_contains_only_local_droid():
    assert DEFAULT_BACKEND_REGISTRY.ids() == ["local.droid"]


def test_default_backend_record_has_id_version_metadata():
    record = DEFAULT_BACKEND_REGISTRY.get_record(DEFAULT_BACKEND_ID)
    assert record.id == "local.droid"
    assert record.version
    assert isinstance(record.metadata, dict)


def test_registry_get_unknown_backend_raises_keyerror_with_clear_message():
    unknown_id = "backend.unknown"
    with pytest.raises(KeyError) as exc_info:
        DEFAULT_BACKEND_REGISTRY.get(unknown_id)
    assert unknown_id in str(exc_info.value)


def test_local_droid_backend_delegates_to_droid_executor(monkeypatch):
    seen: dict[str, object] = {}

    def fake_droid_executor(
        argv: list[str],
        *,
        working_dir: str | None = None,
        timeout_sec: int = 30,
        max_stdout_chars: int = 8_000,
        max_stderr_chars: int = 8_000,
        env_overrides: dict[str, str] | None = None,
    ) -> DroidExecutionRecord:
        seen["argv"] = argv
        seen["working_dir"] = working_dir
        seen["timeout_sec"] = timeout_sec
        seen["max_stdout_chars"] = max_stdout_chars
        seen["max_stderr_chars"] = max_stderr_chars
        seen["env_overrides"] = env_overrides
        return DroidExecutionRecord(
            argv=argv,
            working_dir=working_dir or ".",
            exit_code=0,
            timed_out=False,
            stdout="ok",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
        )

    droid_executor_module = importlib.import_module("src.tools.droid_executor")
    monkeypatch.setattr(droid_executor_module, "droid_executor", fake_droid_executor)
    backend = LocalDroidBackend()
    result = backend.execute(
        ["python", "-c", "print('ok')"],
        working_dir=".",
        timeout_sec=7,
        max_stdout_chars=123,
        max_stderr_chars=456,
        env_overrides={"PYTHONUTF8": "1"},
    )

    assert seen["argv"] == ["python", "-c", "print('ok')"]
    assert seen["working_dir"] == "."
    assert seen["timeout_sec"] == 7
    assert seen["max_stdout_chars"] == 123
    assert seen["max_stderr_chars"] == 456
    assert seen["env_overrides"] == {"PYTHONUTF8": "1"}
    assert result.stdout == "ok"


def test_get_record_returns_record_for_known_id_and_raises_for_unknown():
    record = DEFAULT_BACKEND_REGISTRY.get_record(DEFAULT_BACKEND_ID)
    assert isinstance(record, BackendRecord)
    assert record.id == DEFAULT_BACKEND_ID
    assert record.version

    unknown_id = "backend.unknown"
    with pytest.raises(KeyError) as exc_info:
        DEFAULT_BACKEND_REGISTRY.get_record(unknown_id)
    assert unknown_id in str(exc_info.value)
