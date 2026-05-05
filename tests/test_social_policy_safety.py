"""Safety contract tests for the Social Policy Store.

These tests assert structural / static invariants:

* The new modules do not import live transports, schedulers, or daemon helpers.
* Source files contain no scheduler / loop / daemon constructs.
* Pydantic schema rejects raw IDs and token-shaped strings.
* The full preview/apply/rollback round-trip never opens a network socket
  or calls ``urllib.request.urlopen`` (caught via monkey-patched fakes that
  raise on call).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.server import app
from src.ham.social_policy import APPLY_CONFIRMATION_PHRASE
from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    SocialPolicy,
)

client = TestClient(app)
_TOKEN = "changeme-write"  # noqa: S105


_REPO_ROOT = Path(__file__).resolve().parent.parent
_POLICY_FILES = [
    _REPO_ROOT / "src" / "ham" / "social_policy" / "__init__.py",
    _REPO_ROOT / "src" / "ham" / "social_policy" / "schema.py",
    _REPO_ROOT / "src" / "ham" / "social_policy" / "store.py",
    _REPO_ROOT / "src" / "api" / "social_policy.py",
]


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("HAM_SOCIAL_POLICY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_scheduler_loop_or_daemon_constructs_in_policy_modules() -> None:
    """Static AST scan: prohibit asyncio loops, threading, signal handlers."""
    forbidden_modules = {
        "threading",
        "multiprocessing",
        "subprocess",
        "signal",
        "sched",
        "schedule",
    }
    forbidden_calls = {
        "asyncio.create_task",
        "asyncio.get_event_loop",
        "asyncio.new_event_loop",
        "asyncio.run",
        "asyncio.ensure_future",
    }
    for path in _POLICY_FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    assert name not in forbidden_modules, (
                        f"{path} imports forbidden module {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    assert root not in forbidden_modules, (
                        f"{path} imports forbidden module {node.module}"
                    )
            elif isinstance(node, ast.Call):
                # Best-effort dotted-name match, e.g. asyncio.create_task(...).
                func = node.func
                names: list[str] = []
                while isinstance(func, ast.Attribute):
                    names.insert(0, func.attr)
                    func = func.value
                if isinstance(func, ast.Name):
                    names.insert(0, func.id)
                joined = ".".join(names)
                assert joined not in forbidden_calls, (
                    f"{path} calls forbidden {joined}"
                )


def test_no_live_transport_module_imports_in_policy_layer() -> None:
    forbidden_substrings = (
        "social_telegram_send",
        "goham_live_controller",
        "goham_reactive_live",
        "send_confirmed_telegram_message",
        "TelegramBotApiTransport",
    )
    for path in _POLICY_FILES:
        source = path.read_text(encoding="utf-8")
        for needle in forbidden_substrings:
            assert needle not in source, (
                f"{path} mentions forbidden live-transport symbol {needle!r}"
            )


def test_schema_rejects_raw_ids_and_secrets_at_string_fields() -> None:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    # Raw numeric Telegram-style chat id smuggled into nature_tags.
    raw["content_style"] = {
        "tone": "warm",
        "length_preference": "standard",
        "emoji_policy": "sparingly",
        "nature_tags": ["chat-100123456789"],
    }
    with pytest.raises(ValidationError):
        SocialPolicy.model_validate(raw)

    # Token-shaped string in blocked_topics.
    raw["content_style"] = {"tone": "warm", "length_preference": "standard", "emoji_policy": "sparingly", "nature_tags": []}
    raw["safety_rules"] = {
        "blocked_topics": ["sk-secret1234567890abcdef"],
        "block_links": True,
        "min_relevance": 0.75,
        "consecutive_failure_stop": 2,
        "policy_rejection_stop": 10,
    }
    with pytest.raises(ValidationError):
        SocialPolicy.model_validate(raw)


def test_full_round_trip_does_not_call_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", _TOKEN)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)

    counters = {"urlopen": 0, "socket_connect": 0, "telegram_send": 0}

    def _block_urlopen(*args: Any, **kwargs: Any) -> Any:
        counters["urlopen"] += 1
        raise RuntimeError("urlopen forbidden during policy operation")

    def _block_socket_connect(self: Any, *args: Any, **kwargs: Any) -> Any:
        counters["socket_connect"] += 1
        raise RuntimeError("socket.connect forbidden during policy operation")

    def _block_telegram_send(*args: Any, **kwargs: Any) -> Any:
        counters["telegram_send"] += 1
        raise RuntimeError("send_confirmed_telegram_message forbidden during policy operation")

    import socket
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _block_urlopen)
    monkeypatch.setattr(socket.socket, "connect", _block_socket_connect)
    # Catch the live transport function too (defense-in-depth).
    monkeypatch.setattr(
        "src.ham.social_telegram_send.send_confirmed_telegram_message",
        _block_telegram_send,
    )

    payload = {"changes": {"policy": DEFAULT_SOCIAL_POLICY.model_dump(mode="json")}}

    pre = client.post("/api/social/policy/preview", json=payload)
    assert pre.status_code == 200

    apply_res = client.post(
        "/api/social/policy/apply",
        json={
            **payload,
            "base_revision": pre.json()["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert apply_res.status_code == 200

    history = client.get("/api/social/policy/history")
    assert history.status_code == 200
    audit = client.get("/api/social/policy/audit")
    assert audit.status_code == 200

    assert counters == {"urlopen": 0, "socket_connect": 0, "telegram_send": 0}


def test_response_payloads_never_contain_raw_token_shapes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", _TOKEN)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "changeme-live-env")

    body = client.get("/api/social/policy").text
    # The presence boolean is fine, but the token literal must not appear.
    assert _TOKEN not in body
    assert "changeme-live-env" not in body
    # No bearer-shaped strings either.
    assert not re.search(r"Bearer\s+[a-z0-9._~+/=-]{8,}", body, re.IGNORECASE)


def test_default_policy_serialises_round_trip_safely() -> None:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    again = SocialPolicy.model_validate(raw)
    assert again.model_dump(mode="json") == raw
