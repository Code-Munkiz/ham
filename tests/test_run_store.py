from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.persistence.run_store import RunStore


def _created_at_for_filename(created_at: str) -> str:
    dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _write_run_file(root: Path, run_id: str, created_at: str, **extra: Any) -> Path:
    """Write a valid run JSON to root/.ham/runs/<timestamp>-<run_id>.json. Matches main.py::_persist_run_record serialization."""
    ex = dict(extra)
    bridge_result = ex.pop("bridge_result", {})
    hermes_review = ex.pop("hermes_review", {})
    record: dict[str, Any] = {
        "run_id": run_id,
        "created_at": created_at,
        "profile_id": ex.pop("profile_id", "inspect.cwd"),
        "profile_version": ex.pop("profile_version", "1.0.0"),
        "backend_id": ex.pop("backend_id", "local.droid"),
        "backend_version": ex.pop("backend_version", "1.0.0"),
        "prompt_summary": ex.pop("prompt_summary", "test"),
        "bridge_result": bridge_result,
        "hermes_review": hermes_review,
    }
    record.update(ex)

    runs_dir = root / ".ham" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = _created_at_for_filename(created_at)
    path = runs_dir / f"{ts}-{run_id}.json"
    payload = json.dumps(record, sort_keys=True, ensure_ascii=True, indent=2)
    path.write_text(payload, encoding="utf-8")
    return path


def test_list_runs_empty_when_no_directory(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    assert store.list_runs() == []


def test_list_runs_returns_all_runs_newest_first_by_default(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-a", "2026-01-01T00:00:00Z")
    _write_run_file(tmp_path, "run-b", "2026-01-03T00:00:00Z")
    _write_run_file(tmp_path, "run-c", "2026-01-02T00:00:00Z")
    store = RunStore(tmp_path)
    rows = store.list_runs()
    assert len(rows) == 3
    assert [r.run_id for r in rows] == ["run-b", "run-c", "run-a"]


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    for i in range(5):
        _write_run_file(tmp_path, f"run-{i}", f"2026-01-0{i + 1}T00:00:00Z")
    store = RunStore(tmp_path)
    rows = store.list_runs(limit=2)
    assert len(rows) == 2


def test_list_runs_ascending_when_newest_first_false(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-a", "2026-01-01T00:00:00Z")
    _write_run_file(tmp_path, "run-b", "2026-01-03T00:00:00Z")
    _write_run_file(tmp_path, "run-c", "2026-01-02T00:00:00Z")
    store = RunStore(tmp_path)
    rows = store.list_runs(newest_first=False)
    assert [r.run_id for r in rows] == ["run-a", "run-c", "run-b"]


def test_list_runs_skips_malformed_files_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_run_file(tmp_path, "run-ok1", "2026-01-01T00:00:00Z")
    _write_run_file(tmp_path, "run-ok2", "2026-01-02T00:00:00Z")
    bad = tmp_path / ".ham" / "runs" / "20260103T000000Z-bad.json"
    bad.write_text("not valid json", encoding="utf-8")
    store = RunStore(tmp_path)
    rows = store.list_runs()
    assert len(rows) == 2
    err = capsys.readouterr().err
    assert "bad.json" in err
    assert "JSONDecodeError" in err


def test_get_run_returns_record_for_known_id(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-abc123", "2026-01-01T12:00:00Z")
    store = RunStore(tmp_path)
    rec = store.get_run("run-abc123")
    assert rec is not None
    assert rec.run_id == "run-abc123"


def test_get_run_returns_none_for_unknown_id(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-only", "2026-01-01T00:00:00Z")
    store = RunStore(tmp_path)
    assert store.get_run("nonexistent") is None


def test_count_returns_zero_when_no_directory(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    assert store.count() == 0


def test_count_returns_number_of_json_files(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "a", "2026-01-01T00:00:00Z")
    _write_run_file(tmp_path, "b", "2026-01-02T00:00:00Z")
    store = RunStore(tmp_path)
    assert store.count() == 2


def test_list_runs_rejects_non_positive_limit(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    for bad_limit in (0, -1):
        with pytest.raises(ValueError, match="limit must be positive"):
            store.list_runs(limit=bad_limit)


def test_list_runs_ignores_non_json_files(tmp_path: Path) -> None:
    runs = tmp_path / ".ham" / "runs"
    runs.mkdir(parents=True)
    _write_run_file(tmp_path, "good", "2026-01-01T00:00:00Z")
    (runs / "notes.txt").write_text("hello", encoding="utf-8")
    (runs / "backup.json.bak").write_text("{}", encoding="utf-8")
    store = RunStore(tmp_path)
    assert len(store.list_runs()) == 1


def test_run_record_parses_with_author_field(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-auth", "2026-01-01T00:00:00Z", author="aaron")
    store = RunStore(tmp_path)
    rec = store.get_run("run-auth")
    assert rec is not None
    assert rec.author == "aaron"


def test_run_record_parses_without_author_field(tmp_path: Path) -> None:
    _write_run_file(tmp_path, "run-no-auth", "2026-01-01T00:00:00Z")
    store = RunStore(tmp_path)
    rec = store.get_run("run-no-auth")
    assert rec is not None
    assert rec.author is None


def test_list_runs_tolerates_extra_fields_in_json(tmp_path: Path) -> None:
    path = _write_run_file(
        tmp_path,
        "run-x",
        "2026-01-01T00:00:00Z",
        author="aaron",
    )
    store = RunStore(tmp_path)
    rows = store.list_runs()
    assert len(rows) == 1
    assert rows[0].run_id == "run-x"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["author"] == "aaron"


def test_get_run_duplicate_files_uses_lexicographic_max_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / ".ham" / "runs"
    runs.mkdir(parents=True)
    older = runs / "20260101T000000Z-run-dup.json"
    newer = runs / "20260102T000000Z-run-dup.json"
    base = {
        "run_id": "run-dup",
        "created_at": "2026-01-01T00:00:00Z",
        "profile_id": "inspect.cwd",
        "profile_version": "1.0.0",
        "backend_id": "local.droid",
        "backend_version": "1.0.0",
        "prompt_summary": "x",
        "bridge_result": {},
        "hermes_review": {},
    }
    older.write_text(
        json.dumps(base, sort_keys=True, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    newer.write_text(
        json.dumps(
            {**base, "prompt_summary": "from-newer"},
            sort_keys=True,
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    store = RunStore(tmp_path)
    rec = store.get_run("run-dup")
    assert rec is not None
    assert rec.prompt_summary == "from-newer"
    err = capsys.readouterr().err
    assert "duplicate" in err.lower()
    assert "20260102T000000Z-run-dup.json" in err
