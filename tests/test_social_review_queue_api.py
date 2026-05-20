"""Tests for GET /api/social/review-queue/summary (read-only, safe projection)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def _set_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    review = tmp_path / "review.jsonl"
    monkeypatch.setenv("HAM_X_REVIEW_QUEUE_PATH", str(review))
    monkeypatch.setenv("HAM_X_EXECUTION_JOURNAL_PATH", str(tmp_path / "journal.jsonl"))
    monkeypatch.setenv("HAM_X_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("HAM_X_EXCEPTION_QUEUE_PATH", str(tmp_path / "exceptions.jsonl"))
    return review


def test_review_queue_summary_empty_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_paths(monkeypatch, tmp_path)
    res = client.get("/api/social/review-queue/summary")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pending_count"] == 0
    assert body["items"] == []
    assert body["approved_recent_count"] == 0
    assert body["rejected_recent_count"] == 0
    assert isinstance(body["generated_at"], str) and body["generated_at"]


def test_review_queue_summary_seeded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    review = _set_paths(monkeypatch, tmp_path)
    review.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "action_id": "act-1",
            "action_type": "post",
            "channel": "x",
            "text": "Hello world (no secrets here).",
            "created_at": "2026-05-01T00:00:00Z",
            "provider_post_id": "1234567890",
            "auth": "Bearer reallyVeryLongSecretValue9876543210",
            "tenant_id": "tenant-x",
        },
        {
            "action_id": "act-2",
            "action_type": "reply",
            "channel": "x",
            "text": "Reply with xai-LeakySecretAbcdef987",
            "created_at": "2026-05-02T00:00:00Z",
            "provider_post_id": "987654",
        },
    ]
    with review.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    res = client.get("/api/social/review-queue/summary?limit=5")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pending_count"] == 2
    assert len(body["items"]) == 2
    blob = json.dumps(body)
    # Never leak raw provider IDs, bearer tokens, or xai keys
    assert "reallyVeryLongSecretValue9876543210" not in blob
    assert "LeakySecretAbcdef987" not in blob
    assert "1234567890" not in blob
    assert "987654" not in blob
    # Sanity: text snippets present
    assert any("Hello world" in (item.get("text") or "") for item in body["items"])
    # Action type and channel preserved
    types = {item["action_type"] for item in body["items"]}
    assert {"post", "reply"} <= types


def test_review_queue_summary_limit_clamped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    review = _set_paths(monkeypatch, tmp_path)
    review.parent.mkdir(parents=True, exist_ok=True)
    with review.open("w", encoding="utf-8") as fh:
        for idx in range(150):
            fh.write(
                json.dumps(
                    {
                        "action_id": f"a-{idx}",
                        "action_type": "post",
                        "channel": "x",
                        "text": f"row {idx}",
                        "created_at": f"2026-05-01T00:00:{idx:02d}Z",
                    }
                )
                + "\n"
            )

    # Default limit (no query) is 20
    body = client.get("/api/social/review-queue/summary").json()
    assert len(body["items"]) == 20

    # Over-cap limit clamped to 100
    body = client.get("/api/social/review-queue/summary?limit=999").json()
    assert len(body["items"]) == 100

    # Zero clamped to 1
    body = client.get("/api/social/review-queue/summary?limit=0").json()
    assert len(body["items"]) == 1


def test_review_queue_summary_does_not_mutate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    review = _set_paths(monkeypatch, tmp_path)
    review.parent.mkdir(parents=True, exist_ok=True)
    contents = json.dumps({"action_id": "x", "action_type": "post", "channel": "x", "text": "hi"})
    review.write_text(contents + "\n", encoding="utf-8")
    before = review.read_bytes()
    client.get("/api/social/review-queue/summary")
    after = review.read_bytes()
    assert before == after
