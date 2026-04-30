from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.ham_x import x_readonly_client
from src.ham.ham_x.execution_journal import ExecutionJournal
from src.ham.ham_x.goham_reactive_inbox import discover_reactive_inbox_once, state_from_journal
from src.ham.ham_x.inbound_client import InboundClient
from src.ham.ham_x.reactive_governor import ReactiveGovernorState, response_fingerprint

from tests.test_ham_x_goham_reactive import _test_config


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def _inbox_config(tmp_path: Path, **overrides: Any):
    cfg = _test_config(tmp_path, **overrides.pop("reactive_overrides", {}))
    values = {
        "enable_reactive_inbox_discovery": True,
        "reactive_inbox_query": "",
        "reactive_inbox_max_results": 25,
        "reactive_inbox_max_threads": 5,
        "reactive_inbox_lookback_hours": 24,
        "reactive_handle": "Ham",
        "reactive_inbox_include_replies_to_own_posts": True,
    }
    values.update(overrides)
    return cfg.__class__(**{**cfg.__dict__, **values})


def _tweet(
    idx: int,
    text: str,
    *,
    author_id: str | None = None,
    username: str | None = None,
    conversation_id: str | None = None,
    replied_to: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if created_at is None:
        created_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
    tweet_id = f"tweet-{idx}"
    user_id = author_id or f"user-{idx}"
    tweet: dict[str, Any] = {
        "id": tweet_id,
        "text": text,
        "author_id": user_id,
        "conversation_id": conversation_id or f"thread-{idx}",
        "created_at": created_at,
    }
    if replied_to:
        tweet["referenced_tweets"] = [{"type": "replied_to", "id": replied_to}]
    return tweet


def _body(*tweets: dict[str, Any]) -> dict[str, Any]:
    users = []
    for tweet in tweets:
        users.append({"id": tweet["author_id"], "username": f"author{tweet['author_id'].split('-')[-1]}"})
    return {"data": list(tweets), "includes": {"users": users}}


def _client(cfg, body: dict[str, Any], calls: list[dict[str, Any]] | None = None) -> InboundClient:
    def http_get(url: str, **kwargs: Any) -> _Response:
        if calls is not None:
            calls.append({"url": url, **kwargs})
        return _Response(200, body)

    return InboundClient(config=cfg, http_get=http_get)


def test_missing_bearer_token_blocks_discovery(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path, x_bearer_token="")
    calls = 0

    def fail_if_called(*args: Any, **kwargs: Any) -> _Response:
        nonlocal calls
        calls += 1
        raise AssertionError("network should not be called without bearer token")

    client = InboundClient(config=cfg, http_get=fail_if_called)
    result = discover_reactive_inbox_once(config=cfg)
    assert result.status == "blocked"
    assert "x_bearer_token_missing" in result.reasons
    assert result.mutation_attempted is False
    assert calls == 0


def test_discovery_disabled_blocks(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path, enable_reactive_inbox_discovery=False)
    result = discover_reactive_inbox_once(config=cfg)
    assert result.status == "blocked"
    assert "reactive_inbox_discovery_disabled" in result.reasons


def test_mention_search_response_normalizes_into_inbound_items(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    calls: list[dict[str, Any]] = []
    body = _body(_tweet(1, "Hey Ham, are you online?"))
    client = _client(cfg, body, calls)

    result = discover_reactive_inbox_once(config=cfg, inbound_client=client)

    assert result.status == "completed"
    assert result.inbound_count == 1
    assert result.selected_inbound is not None
    assert result.selected_inbound.inbound_id == "tweet-1"
    assert result.selected_inbound.post_id == "tweet-1"
    assert result.selected_inbound.thread_id == "thread-1"
    assert result.selected_inbound.author_handle == "author1"
    assert calls[0]["params"]["tweet.fields"]
    assert calls[0]["params"]["expansions"]
    assert calls[0]["params"]["user.fields"]


def test_default_readonly_transport_used_when_enabled_without_injection(tmp_path: Path, monkeypatch: Any) -> None:
    cfg = _inbox_config(tmp_path)
    calls: list[dict[str, Any]] = []
    body = _body(_tweet(1, "Hey Ham, are you online?"))

    def default_get(url: str, **kwargs: Any) -> _Response:
        calls.append({"url": url, **kwargs})
        return _Response(200, body)

    monkeypatch.setattr(x_readonly_client, "_httpx_get", default_get)
    result = discover_reactive_inbox_once(config=cfg)
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)

    assert result.status == "completed"
    assert result.selected_inbound is not None
    assert len(calls) == 1
    assert calls[0]["headers"]["Authorization"].startswith("Bearer ")
    assert cfg.x_bearer_token not in dumped
    assert result.execution_allowed is False
    assert result.mutation_attempted is False


def test_replies_normalize_with_conversation_post_and_reply_target(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(_tweet(1, "Question for Ham: how do replies work?", conversation_id="conv-1", replied_to="ham-post-1"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))

    assert result.selected_inbound is not None
    assert result.selected_inbound.inbound_type == "comment"
    assert result.selected_inbound.conversation_id == "conv-1"
    assert result.selected_inbound.post_id == "tweet-1"
    assert result.selected_inbound.in_reply_to_post_id == "ham-post-1"
    assert result.reply_target_id == "tweet-1"


def test_already_handled_journal_inbound_is_not_selected(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="action-1",
        idempotency_key="key-1",
        action_type="reply",
        provider_post_id="reply-1",
        execution_kind="goham_reactive_reply",
        source_action_id="tweet-1",
    )
    body = _body(_tweet(1, "Hey Ham, are you online?"))

    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body), journal=journal)

    assert result.selected_candidate is None
    assert result.candidates[0].inbound.already_answered is True
    assert "policy_route_ignore" in result.candidates[0].governor_decision.reasons


def test_spam_off_topic_toxic_and_price_are_not_selected(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(
        _tweet(1, "free money giveaway airdrop follow back #a #b #c #d #e #f"),
        _tweet(2, "what is your favorite sandwich?"),
        _tweet(3, "Ham is worthless idiot trash, go die"),
        _tweet(4, "Ham token price 10x soon? should I buy now?"),
    )
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))

    assert result.selected_candidate is None
    assert {candidate.policy_decision.classification for candidate in result.candidates} == {
        "spam_bot",
        "off_topic",
        "toxic_harassing",
        "price_token_bait",
    }


def test_genuine_question_selected_before_other_categories(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(
        _tweet(1, "Love Ham, nice work"),
        _tweet(2, "Ham support: can you help with an issue?"),
        _tweet(3, "Question for Ham: how do audit trails work?"),
        _tweet(4, "Ham seems confusing and I am skeptical"),
    )
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))

    assert result.selected_inbound is not None
    assert result.selected_inbound.inbound_id == "tweet-3"
    assert result.selected_candidate is not None
    assert result.selected_candidate.policy_decision.classification == "genuine_question"


def test_support_selected_when_no_question_exists(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(_tweet(1, "Love Ham, nice work"), _tweet(2, "Ham support: can you help with an issue"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))
    assert result.selected_inbound is not None
    assert result.selected_inbound.inbound_id == "tweet-2"


def test_positive_selected_after_higher_priorities(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(_tweet(1, "Love Ham, nice work"), _tweet(2, "Ham seems confusing and I am skeptical"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))
    assert result.selected_inbound is not None
    assert result.selected_inbound.inbound_id == "tweet-1"


def test_per_user_and_thread_cooldowns_block(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path, reactive_overrides={"min_seconds": 3600})
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    user_state = ReactiveGovernorState(per_user_last_reply_at={"user-1": now})
    body = _body(_tweet(1, "Question for Ham: how do audit trails work?", author_id="user-1"))
    user = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body), state=user_state)
    assert user.selected_candidate is None
    assert "per_user_cooldown_active" in user.candidates[0].governor_decision.reasons

    thread_state = ReactiveGovernorState(per_thread_last_reply_at={"thread-1": now})
    thread = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body), state=thread_state)
    assert thread.selected_candidate is None
    assert "per_thread_cooldown_active" in thread.candidates[0].governor_decision.reasons


def test_duplicate_response_fingerprint_blocks(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    expected = "@author1 Good question. Ham is designed to keep autonomous social actions governed by caps, policy checks, audit trails, and operator controls."
    state = ReactiveGovernorState(response_fingerprints={response_fingerprint(expected)})
    body = _body(_tweet(1, "Question for Ham: how do audit trails work?"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body), state=state)
    assert result.selected_candidate is None
    assert "duplicate_response_text" in result.candidates[0].governor_decision.reasons


def test_no_live_write_or_reply_executor_call(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    body = _body(_tweet(1, "Hey Ham, are you online?"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert result.execution_allowed is False
    assert result.mutation_attempted is False
    assert "provider_status_code" not in dumped
    assert "ReactiveReplyExecutor" not in dumped


def test_redaction_masks_tokens_in_summary(tmp_path: Path) -> None:
    secret = "tok_1234567890abcdefghijklmnopqrstuvwxyzSECRET"
    cfg = _inbox_config(tmp_path)
    body = _body(_tweet(1, f"Question for Ham: are you online with {secret}?"))
    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body))
    dumped = json.dumps(result.redacted_dump(), sort_keys=True)
    assert secret not in dumped
    assert "[REDACTED" in dumped


def test_recent_live_reply_journal_row_treated_as_handled(tmp_path: Path) -> None:
    cfg = _inbox_config(tmp_path)
    journal = ExecutionJournal(config=cfg)
    journal.append_executed(
        action_id="reactive-action",
        idempotency_key="reactive-key",
        action_type="reply",
        provider_post_id="2049408257391726763",
        execution_kind="goham_reactive_reply",
        source_action_id="2048626833608896627",
    )
    state = state_from_journal(journal)
    assert "2048626833608896627" in state.handled_inbound_ids
    body = _body(_tweet(1, "Hey Ham, are you online?", conversation_id="2048626833608896627"))
    body["data"][0]["id"] = "2048626833608896627"

    result = discover_reactive_inbox_once(config=cfg, inbound_client=_client(cfg, body), journal=journal)

    assert result.selected_candidate is None
    assert result.candidates[0].inbound.already_answered is True


def test_no_scheduler_loop_or_forbidden_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "ham" / "ham_x"
    for name in ("goham_reactive_inbox.py", "inbound_client.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "while True" not in text
        assert "schedule" not in text
        assert "daemon" not in text
        assert "xurl" not in text
        assert "ReactiveReplyExecutor" not in text
        assert "run_reactive_live_once" not in text
        assert "manual_canary" not in text
        assert "x_executor" not in text
        tree = ast.parse(text)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {
            "src.ham.ham_x.reactive_reply_executor",
            "src.ham.ham_x.goham_reactive_live",
            "src.ham.ham_x.x_executor",
            "src.ham.ham_x.manual_canary",
            "src.ham.ham_x.goham_controller",
            "src.ham.ham_x.goham_live_controller",
        }
        assert imported.isdisjoint(forbidden)
