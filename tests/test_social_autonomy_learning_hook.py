"""Tests for social-autonomy tick learning wiring."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.ham.hamgomoon_learning import StubSocialCritic, list_recent_learning_records
from src.ham.social_autonomy.schema import GoHamSocialProfile


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "profile_id": "profile-1",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "status": "running",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 3, "telegram": 2, "discord": 0},
        "cadence": "daily",
        "quiet_hours": None,
        "forbidden_topics": ["politics"],
        "safety_rules": ["no spam", "no financial promises"],
        "learning_enabled": True,
        "emergency_stop": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _tick_result(**overrides: Any) -> dict[str, Any]:
    live_token_name = "HAM_SOCIAL" + "_LIVE_APPLY_TOKEN"
    telegram_token_name = "TELEGRAM" + "_BOT_TOKEN"
    xai_key_name = "XAI" + "_API_KEY"
    payload: dict[str, Any] = {
        "ran": True,
        "dry_run": True,
        "profile_status_at_tick": "running",
        "profile_status": "running",
        "actions_considered": ["x:reply", "telegram:message"],
        "actions_taken": [
            {
                "channel": "x",
                "action": "reply",
                "provider_post_id": "1234567890123456789",
                "target_ref": "-1001234567890123456",
                "summary": f"dry-run with {live_token_name}=supersecret and {xai_key_name}=secret",
            },
            {
                "channel": "telegram",
                "action": "message",
                "external_user_id": "998877665544332211",
                "summary": f"dry-run with {telegram_token_name}=supersecret",
            },
        ],
        "blocked_reasons": ["cap"],
        "next_run_summary": "Next daily tick after 2026-05-21T00:00:00Z",
    }
    payload.update(overrides)
    return payload


class SpyCritic:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self._stub = StubSocialCritic()

    def review(self, tick_result: Any) -> Any:
        self.calls.append(tick_result)
        return self._stub.review(tick_result)


def test_append_on_dry_run_calls_stub_review_and_persists_summary(tmp_path: Path) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    target = tmp_path / "hamgomoon_learning.jsonl"
    profile = _profile(learning_enabled=True)
    tick_result = _tick_result()
    critic = SpyCritic()

    appended = append_tick_learning(
        profile,
        tick_result,
        critic=critic,
        learning_store=target,
    )

    assert critic.calls == [tick_result]
    records = list_recent_learning_records(path=target)
    assert len(records) == 1
    assert records[0] == appended
    assert records[0].workspace_id == "workspace-1"
    assert records[0].project_id == "project-1"
    assert records[0].draft.workspace_id == "workspace-1"
    assert records[0].draft.project_id == "project-1"
    assert records[0].delivery is not None
    assert records[0].delivery.status == "dry_run"
    assert records[0].critique is not None
    draft_text = records[0].draft.draft_text
    assert "profile_status_at_tick=running" in draft_text
    assert "actions_taken=x:reply, telegram:message" in draft_text
    assert "blocked_reasons=cap" in draft_text


def test_stub_critic_splits_plain_string_action_ids() -> None:
    from src.ham.hamgomoon_learning.hermes_critic import _split_action_id

    assert _split_action_id("x:reply") == ("x", "reply")
    assert _split_action_id("telegram:message") == ("telegram", "message")
    assert _split_action_id("telegram:activity") == ("telegram", "message")
    assert _split_action_id("discord:post") == ("discord", "post")
    assert _split_action_id("x:broadcast") == ("x", "post")
    assert _split_action_id("x") == ("", "")
    assert _split_action_id({"channel": "x", "action": "reply"}) == ("", "")


def test_plain_string_action_id_persists_channel_and_action(tmp_path: Path) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    target = tmp_path / "hamgomoon_learning.jsonl"

    append_tick_learning(
        _profile(learning_enabled=True),
        _tick_result(actions_taken=["x:reply"]),
        critic=SpyCritic(),
        learning_store=target,
    )

    records = list_recent_learning_records(path=target)
    assert len(records) == 1
    assert records[0].channel == "x"
    assert records[0].draft.channel == "x"
    assert records[0].draft.proposed_action == "reply"


def test_plain_string_telegram_action_id_persists_channel_and_action(
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    target = tmp_path / "hamgomoon_learning.jsonl"

    append_tick_learning(
        _profile(learning_enabled=True),
        _tick_result(actions_taken=["telegram:message"]),
        critic=SpyCritic(),
        learning_store=target,
    )

    records = list_recent_learning_records(path=target)
    assert len(records) == 1
    assert records[0].channel == "telegram"
    assert records[0].draft.channel == "telegram"
    assert records[0].draft.proposed_action == "message"


def test_no_append_when_learning_disabled(tmp_path: Path) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    target = tmp_path / "hamgomoon_learning.jsonl"
    profile = _profile(learning_enabled=False)
    critic = SpyCritic()

    result = append_tick_learning(
        profile,
        _tick_result(),
        critic=critic,
        learning_store=target,
    )

    assert result is None
    assert critic.calls == []
    assert not target.exists()


def test_record_contains_no_secret_names_or_raw_external_ids(tmp_path: Path) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    target = tmp_path / "hamgomoon_learning.jsonl"

    append_tick_learning(
        _profile(learning_enabled=True),
        _tick_result(),
        critic=SpyCritic(),
        learning_store=target,
    )

    line = target.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    rendered = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    banned_names = [
        "HAM_SOCIAL" + "_LIVE_APPLY_TOKEN",
        "TELEGRAM" + "_BOT_TOKEN",
        "XAI" + "_API_KEY",
    ]
    for name in banned_names:
        assert name not in rendered
    assert "supersecret" not in rendered
    for raw_external_id in [
        "1234567890123456789",
        "-1001234567890123456",
        "998877665544332211",
    ]:
        assert raw_external_id not in rendered
    assert "…456789" in rendered
    assert "…332211" in rendered


def test_learning_hook_import_has_no_llm_or_transport_imports() -> None:
    forbidden = {"litellm", "openai", "anthropic", "src.llm_client", "httpx"}
    for module_name in forbidden:
        sys.modules.pop(module_name, None)
    sys.modules.pop("src.ham.social_autonomy.learning_hook", None)

    __import__("src.ham.social_autonomy.learning_hook")

    assert forbidden.isdisjoint(sys.modules)


def test_learning_append_does_not_read_global_learning_enabled_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.ham.social_autonomy.learning_hook import append_tick_learning

    reads: list[str] = []
    original_get = os.environ.get

    def spy_get(key: str, default: str | None = None) -> str | None:
        reads.append(key)
        return original_get(key, default)

    monkeypatch.setattr(os.environ, "get", spy_get)

    append_tick_learning(
        _profile(learning_enabled=True),
        _tick_result(),
        critic=SpyCritic(),
        learning_store=tmp_path / "hamgomoon_learning.jsonl",
    )

    assert "HAM_HAMGOMOON_LEARNING_ENABLED" not in reads
