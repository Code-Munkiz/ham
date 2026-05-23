"""Unit tests for review_queue read path (no FastAPI / sentry imports)."""

from __future__ import annotations

import json
from pathlib import Path

from src.ham.ham_x.review_queue import read_recent_review_records


def test_read_recent_review_records_bounded_tail(tmp_path: Path) -> None:
    """Large JSONL must use a bounded tail read; last N rows stay correct."""
    review = tmp_path / "big_review.jsonl"
    n_lines = 400
    pad = "x" * 5000
    with review.open("w", encoding="utf-8") as fh:
        for idx in range(n_lines):
            fh.write(
                json.dumps(
                    {
                        "action_id": f"id-{idx:04d}",
                        "action_type": "post",
                        "channel": "x",
                        "text": f"{pad} {idx}",
                        "created_at": "2026-05-01T00:00:00Z",
                    }
                )
                + "\n"
            )
    rows = read_recent_review_records(limit=50, path=review)
    assert len(rows) == 50
    ids = [r["record_id"] for r in rows]
    assert ids == [f"id-{i:04d}" for i in range(n_lines - 50, n_lines)]


def test_read_recent_review_records_small_file_roundtrip(tmp_path: Path) -> None:
    review = tmp_path / "small.jsonl"
    review.write_text(
        json.dumps(
            {
                "action_id": "a1",
                "action_type": "post",
                "channel": "x",
                "text": "hello",
                "created_at": "2026-05-01T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = read_recent_review_records(limit=10, path=review)
    assert len(rows) == 1
    assert rows[0]["record_id"] == "a1"
    assert "hello" in (rows[0].get("text") or "")
