from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND
from src.ham.ham_x.reactive_reply_executor import (
    ReactiveReplyExecutor,
    ReactiveReplyRequest,
)

from tests.test_ham_x_goham_reactive import _test_config


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


def _request(**overrides: Any) -> ReactiveReplyRequest:
    data = {
        "action_id": "reply-action-1",
        "inbound_id": "inbound-1",
        "source_post_id": "post-1",
        "reply_target_id": "post-1",
        "author_id": "user-1",
        "thread_id": "thread-1",
        "text": "@user1 Good question. Ham keeps replies governed and auditable.",
        "idempotency_key": "goham-reactive-reply-test-1",
    }
    data.update(overrides)
    return ReactiveReplyRequest(**data)


def test_missing_reply_target_blocks_without_provider_call(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    executor = ReactiveReplyExecutor(
        config=_test_config(tmp_path),
        http_post=lambda *args, **kwargs: calls.append(kwargs),
    )

    result = executor.execute(_request(reply_target_id=""))

    assert result.status == "blocked"
    assert "reply_target_required" in result.reasons
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert calls == []


def test_successful_mocked_reply_posts_only_reply_payload(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def http_post(url: str, **kwargs: Any) -> _Response:
        calls.append({"url": url, **kwargs})
        return _Response(201, {"data": {"id": "reply-post-123", "text": "ok"}})

    executor = ReactiveReplyExecutor(config=_test_config(tmp_path), http_post=http_post)
    result = executor.execute(_request())

    assert result.status == "executed"
    assert result.execution_allowed is True
    assert result.mutation_attempted is True
    assert result.provider_status_code == 201
    assert result.provider_post_id == "reply-post-123"
    assert len(calls) == 1
    body = calls[0]["json"]
    assert body == {
        "text": "@user1 Good question. Ham keeps replies governed and auditable.",
        "reply": {"in_reply_to_tweet_id": "post-1"},
    }
    assert "quote_tweet_id" not in json.dumps(body)
    assert "like" not in json.dumps(body).lower()
    assert "follow" not in json.dumps(body).lower()
    assert "dm" not in json.dumps(body).lower()


def test_provider_failure_is_redacted_and_not_retried(tmp_path: Path) -> None:
    calls = 0
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"

    def http_post(*args: Any, **kwargs: Any) -> _Response:
        nonlocal calls
        calls += 1
        return _Response(401, {"detail": f"bad token {secret}"})

    executor = ReactiveReplyExecutor(config=_test_config(tmp_path), http_post=http_post)
    result = executor.execute(_request())
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)

    assert calls == 1
    assert result.status == "failed"
    assert result.provider_status_code == 401
    assert secret not in dumped
    assert "[REDACTED" in dumped


def test_execution_kind_is_narrow_reactive_reply() -> None:
    request = _request()
    assert request.execution_kind == GOHAM_REACTIVE_EXECUTION_KIND
    bad = _request(execution_kind="manual_canary")
    executor = ReactiveReplyExecutor(config=_test_config(Path("/tmp")))
    result = executor.execute(bad)
    assert result.status == "blocked"
    assert "invalid_execution_kind" in result.reasons


def test_executor_has_no_forbidden_runtime_paths() -> None:
    path = Path(__file__).parents[1] / "src" / "ham" / "ham_x" / "reactive_reply_executor.py"
    text = path.read_text(encoding="utf-8")
    assert "while True" not in text
    assert "schedule" not in text
    assert "daemon" not in text
    assert "xurl" not in text
    assert "manual_canary" not in text
    assert "x_executor" not in text
    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "src.ham.ham_x.x_executor" not in imported
    assert "src.ham.ham_x.manual_canary" not in imported
