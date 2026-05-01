"""Read-only Social workspace API facade tests.

These tests cover:

- Auth gates (Clerk session + email allowlist) reuse the same patterns as
  other protected workspace routes.
- Provider list includes X first and future providers marked coming soon.
- DTOs are bounded and never expose secrets, raw env values, auth headers,
  or unbounded file contents.
- Journal/audit summaries are resilient to missing/malformed JSONL files.
- ``src/api/social.py`` does not import or call any provider write/execution
  helpers.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BEARER = "bearer-token-1234567890"
_API_KEY = "consumer-key-1234567890"
_API_SECRET = "consumer-secret-9876543210"
_ACCESS_TOKEN = "access-token-1234567890"
_ACCESS_TOKEN_SECRET = "access-token-secret-9876543210"
_XAI_KEY = "xai-secret-value-1234567890"


def _set_x_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", _BEARER)
    monkeypatch.setenv("X_API_KEY", _API_KEY)
    monkeypatch.setenv("X_API_SECRET", _API_SECRET)
    monkeypatch.setenv("X_ACCESS_TOKEN", _ACCESS_TOKEN)
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", _ACCESS_TOKEN_SECRET)
    monkeypatch.setenv("XAI_API_KEY", _XAI_KEY)


def _clear_x_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "X_BEARER_TOKEN",
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
        "X_BEARER_TOKEN",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def _isolate_journal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    journal = tmp_path / "execution_journal.jsonl"
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("HAM_X_EXECUTION_JOURNAL_PATH", str(journal))
    monkeypatch.setenv("HAM_X_AUDIT_LOG_PATH", str(audit))
    monkeypatch.setenv("HAM_X_REVIEW_QUEUE_PATH", str(tmp_path / "review.jsonl"))
    monkeypatch.setenv("HAM_X_EXCEPTION_QUEUE_PATH", str(tmp_path / "exceptions.jsonl"))
    monkeypatch.setenv("HAM_HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HAM_HERMES_GATEWAY_STATUS_PATH", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "TELEGRAM_ALLOW_ALL_USERS",
        "TELEGRAM_HOME_CHANNEL",
        "TELEGRAM_TEST_GROUP",
        "TELEGRAM_TEST_GROUP_ID",
        "TELEGRAM_TEST_CHAT_ID",
        "TELEGRAM_MODE",
        "HERMES_TELEGRAM_MODE",
        "TELEGRAM_GATEWAY_MODE",
        "TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_WEBHOOK_BASE_URL",
        "GATEWAY_ALLOWED_USERS",
        "GATEWAY_ALLOW_ALL_USERS",
        "DISCORD_BOT_TOKEN",
        "DISCORD_ALLOWED_USERS",
        "DISCORD_ALLOWED_ROLES",
        "DISCORD_ALLOW_ALL_USERS",
        "DISCORD_HOME_CHANNEL",
        "DISCORD_ALLOWED_CHANNELS",
        "DISCORD_FREE_RESPONSE_CHANNELS",
    ):
        monkeypatch.delenv(var, raising=False)
    return journal, audit


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _make_actor(email: str | None) -> HamActor:
    return HamActor(
        user_id="u1",
        org_id="o1",
        session_id="s1",
        email=email.strip().lower() if email else None,
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _now_iso(offset_seconds: int = 0) -> str:
    base = datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)
    return base.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_journal_row(path: Path, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "action_id": "action-1",
        "idempotency_key": "key-1",
        "action_type": "post",
        "execution_kind": "goham_autonomous",
        "provider_post_id": "post-1",
        "status": "executed",
        "executed_at": _now_iso(),
    }
    row.update(fields)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_audit_row(path: Path, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "audit_id": "audit-1",
        "event_type": "goham_execution_executed",
        "ts": _now_iso(),
        "payload": {"status": "ok", "execution_allowed": False, "mutation_attempted": False},
    }
    row.update(fields)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_hermes_gateway_state(path: Path, **fields: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "gateway_state": "running",
        "active_agents": 0,
        "platforms": {},
    }
    row.update(fields)
    path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")


def _fake_discovery(
    *,
    inbound_id: str = "inbound-1",
    reply_target_id: str = "post-1",
    reply_text: str = "@user1 Good question. Ham keeps live replies governed and auditable.",
):
    inbound = SimpleNamespace(
        inbound_id=inbound_id,
        inbound_type="mention",
        text="Question for Ham: are live replies governed?",
        author_id="user-1",
        author_handle="user1",
        post_id=reply_target_id,
        thread_id="thread-1",
        conversation_id="thread-1",
        redacted_dump=lambda: {
            "inbound_id": inbound_id,
            "post_id": reply_target_id,
            "author_handle": "user1",
            "text": "Question for Ham: are live replies governed?",
        },
    )
    policy = SimpleNamespace(
        classification="genuine_question",
        reply_text=reply_text,
        redacted_dump=lambda: {
            "classification": "genuine_question",
            "route": "reply_candidate",
            "allowed": True,
            "reply_text": reply_text,
        },
    )
    governor = SimpleNamespace(
        allowed=True,
        action_tier="reply_candidate",
        reasons=[],
        response_fingerprint="fingerprint-1",
        redacted_dump=lambda: {
            "allowed": True,
            "action_tier": "reply_candidate",
            "reasons": [],
            "response_fingerprint": "fingerprint-1",
        },
    )
    selected = SimpleNamespace(
        inbound=inbound,
        policy_decision=policy,
        governor_decision=governor,
        status="selected",
        reply_target_id=reply_target_id,
        redacted_dump=lambda: {
            "inbound": inbound.redacted_dump(),
            "policy_decision": policy.redacted_dump(),
            "governor_decision": governor.redacted_dump(),
            "status": "selected",
            "reply_target_id": reply_target_id,
        },
    )
    return SimpleNamespace(
        status="completed",
        reasons=[],
        candidates=[selected],
        selected_candidate=selected,
        selected_inbound=inbound,
        reply_target_id=reply_target_id,
        redacted_dump=lambda: {
            "status": "completed",
            "selected_candidate": selected.redacted_dump(),
            "reply_target_id": reply_target_id,
            "execution_allowed": False,
            "mutation_attempted": False,
        },
    )


def _fake_live_result(
    *,
    status: str = "executed",
    provider_status_code: int | None = 201,
    provider_post_id: str | None = "reply-post-1",
):
    execution_result = SimpleNamespace(
        provider_status_code=provider_status_code,
        provider_post_id=provider_post_id,
    )
    return SimpleNamespace(
        status=status,
        execution_allowed=status != "blocked",
        mutation_attempted=status != "blocked",
        execution_result=execution_result,
        audit_ids=["audit-1", "audit-2"],
        journal_path=".data/ham-x/execution_journal.jsonl",
        audit_path=".data/ham-x/audit.jsonl",
        reasons=[] if status == "executed" else ["provider_failed"],
        redacted_dump=lambda: {
            "status": status,
            "execution_allowed": status != "blocked",
            "mutation_attempted": status != "blocked",
            "execution_result": {
                "provider_status_code": provider_status_code,
                "provider_post_id": provider_post_id,
            },
            "audit_ids": ["audit-1", "audit-2"],
            "journal_path": ".data/ham-x/execution_journal.jsonl",
            "audit_path": ".data/ham-x/audit.jsonl",
            "reasons": [] if status == "executed" else ["provider_failed"],
        },
    )


def _fake_batch_result(
    *,
    status: str = "completed",
    provider_post_ids: list[str] | None = None,
):
    ids = provider_post_ids or ["reply-post-1", "reply-post-2"]
    items = [SimpleNamespace(execution_result=SimpleNamespace(provider_post_id=provider_post_id)) for provider_post_id in ids]
    return SimpleNamespace(
        status=status,
        execution_allowed=status != "blocked",
        mutation_attempted=status != "blocked",
        attempted_count=len(ids),
        executed_count=len(ids) if status == "completed" else 0,
        failed_count=0 if status == "completed" else 1,
        blocked_count=0,
        items=items,
        audit_ids=["audit-batch-1"],
        journal_path=".data/ham-x/execution_journal.jsonl",
        audit_path=".data/ham-x/audit.jsonl",
        reasons=[] if status == "completed" else ["provider_failed"],
        redacted_dump=lambda: {
            "status": status,
            "execution_allowed": status != "blocked",
            "mutation_attempted": status != "blocked",
            "attempted_count": len(ids),
            "executed_count": len(ids) if status == "completed" else 0,
            "failed_count": 0 if status == "completed" else 1,
            "blocked_count": 0,
            "items": [{"execution_result": {"provider_post_id": provider_post_id}} for provider_post_id in ids],
            "audit_ids": ["audit-batch-1"],
            "journal_path": ".data/ham-x/execution_journal.jsonl",
            "audit_path": ".data/ham-x/audit.jsonl",
            "reasons": [] if status == "completed" else ["provider_failed"],
        },
    )


def _fake_broadcast_result(
    *,
    status: str = "executed",
    provider_status_code: int | None = 201,
    provider_post_id: str | None = "broadcast-post-1",
):
    return SimpleNamespace(
        status=status,
        execution_allowed=status != "blocked",
        mutation_attempted=status != "blocked",
        provider_status_code=provider_status_code,
        provider_post_id=provider_post_id,
        audit_ids=["audit-post-1"],
        journal_path=".data/ham-x/execution_journal.jsonl",
        audit_path=".data/ham-x/audit.jsonl",
        reasons=[] if status == "executed" else ["provider_failed"],
        redacted_dump=lambda: {
            "status": status,
            "execution_allowed": status != "blocked",
            "mutation_attempted": status != "blocked",
            "provider_status_code": provider_status_code,
            "provider_post_id": provider_post_id,
            "audit_ids": ["audit-post-1"],
            "journal_path": ".data/ham-x/execution_journal.jsonl",
            "audit_path": ".data/ham-x/audit.jsonl",
            "reasons": [] if status == "executed" else ["provider_failed"],
        },
    )


def _enable_apply_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_REACTIVE", "true")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_DRY_RUN", "false")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_LIVE_CANARY", "true")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_RUN", "1")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_BLOCK_LINKS", "true")
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "false")


def _enable_batch_apply_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_REACTIVE", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_REACTIVE_BATCH", "true")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_BATCH_DRY_RUN", "false")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_BATCH_MAX_REPLIES_PER_RUN", "3")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_BLOCK_LINKS", "true")
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "false")


def _enable_broadcast_apply_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_EXECUTION", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_CONTROLLER", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_LIVE_CONTROLLER", "true")
    monkeypatch.setenv("HAM_X_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_X_DRY_RUN", "false")
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_EXECUTION", "true")
    monkeypatch.setenv("HAM_X_GOHAM_LIVE_MAX_ACTIONS_PER_RUN", "1")
    monkeypatch.setenv("HAM_X_GOHAM_MAX_ACTIONS_PER_RUN", "1")
    monkeypatch.setenv("HAM_X_GOHAM_BLOCK_LINKS", "true")
    monkeypatch.setenv("HAM_X_GOHAM_ALLOWED_ACTIONS", "post")
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "false")


def _preview_digest(headers: dict[str, str] | None = None) -> str:
    res = client.post("/api/social/providers/x/reactive/inbox/preview", headers=headers or {}, json={})
    assert res.status_code == 200
    digest = res.json().get("proposal_digest")
    assert isinstance(digest, str)
    return digest


def _batch_preview_digest(headers: dict[str, str] | None = None) -> str:
    res = client.post("/api/social/providers/x/reactive/batch/dry-run", headers=headers or {}, json={})
    assert res.status_code == 200
    digest = res.json().get("proposal_digest")
    assert isinstance(digest, str)
    return digest


def _broadcast_preview_digest(headers: dict[str, str] | None = None) -> str:
    res = client.post("/api/social/providers/x/broadcast/preflight", headers=headers or {}, json={})
    assert res.status_code == 200
    digest = res.json().get("proposal_digest")
    assert isinstance(digest, str)
    return digest


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


_PROTECTED_ROUTES = (
    "/api/social/providers",
    "/api/social/persona/current",
    "/api/social/personas/ham-canonical",
    "/api/social/providers/telegram/status",
    "/api/social/providers/telegram/capabilities",
    "/api/social/providers/telegram/setup/checklist",
    "/api/social/providers/discord/status",
    "/api/social/providers/discord/capabilities",
    "/api/social/providers/discord/setup/checklist",
    "/api/social/providers/x/status",
    "/api/social/providers/x/capabilities",
    "/api/social/providers/x/setup/checklist",
    "/api/social/providers/x/setup/summary",
    "/api/social/providers/x/journal/summary",
    "/api/social/providers/x/audit/summary",
)

_PREVIEW_ROUTES = (
    "/api/social/providers/x/reactive/inbox/preview",
    "/api/social/providers/x/reactive/batch/dry-run",
    "/api/social/providers/x/broadcast/preflight",
)

_APPLY_ROUTE = "/api/social/providers/x/reactive/reply/apply"
_BATCH_APPLY_ROUTE = "/api/social/providers/x/reactive/batch/apply"
_BROADCAST_APPLY_ROUTE = "/api/social/providers/x/broadcast/apply"
_SOCIAL_TOKEN = "social-live-apply-token-1234567890"
_CONFIRM = "SEND ONE LIVE REPLY"
_BATCH_CONFIRM = "SEND LIVE REACTIVE BATCH"
_BROADCAST_CONFIRM = "SEND ONE LIVE POST"


def test_routes_require_clerk_session_when_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    for route in _PROTECTED_ROUTES:
        res = client.get(route)
        assert res.status_code == 401, f"{route} expected 401, got {res.status_code}"
        assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    for route in _PREVIEW_ROUTES:
        res = client.post(route, json={})
        assert res.status_code == 401, f"{route} expected 401, got {res.status_code}"
        assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_routes_403_when_email_not_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "good.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("user@bad.test")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.get(
            "/api/social/providers",
            headers={"Authorization": "Bearer fake.jwt"},
        )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "HAM_EMAIL_RESTRICTION"
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.post(
            "/api/social/providers/x/broadcast/preflight",
            headers={"Authorization": "Bearer fake.jwt"},
            json={},
        )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "HAM_EMAIL_RESTRICTION"


def test_routes_ok_when_email_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "good.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("User@GOOD.TEST")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        for route in _PROTECTED_ROUTES:
            res = client.get(route, headers={"Authorization": "Bearer fake.jwt"})
            assert res.status_code == 200, f"{route} expected 200, got {res.status_code}"
        for route in _PREVIEW_ROUTES:
            res = client.post(route, headers={"Authorization": "Bearer fake.jwt"}, json={})
            assert res.status_code == 200, f"{route} expected 200, got {res.status_code}"


def test_routes_ok_when_clerk_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    for route in _PROTECTED_ROUTES:
        res = client.get(route)
        assert res.status_code == 200, f"{route} expected 200, got {res.status_code}"
    for route in _PREVIEW_ROUTES:
        res = client.post(route, json={})
        assert res.status_code == 200, f"{route} expected 200, got {res.status_code}"


# ---------------------------------------------------------------------------
# Provider list
# ---------------------------------------------------------------------------


def test_provider_list_includes_x_first_td_providers_setup_and_future_providers_coming_soon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers")
    assert res.status_code == 200
    body = res.json()
    providers = body["providers"]
    assert providers[0]["id"] == "x"
    assert providers[0]["coming_soon"] is False
    assert providers[0]["configured"] is True
    assert providers[0]["status"] == "active"
    telegram = providers[1]
    discord = providers[2]
    assert telegram["id"] == "telegram"
    assert telegram["coming_soon"] is False
    assert telegram["configured"] is False
    assert telegram["status"] == "setup_required"
    assert telegram["enabled_lanes"] == ["readiness"]
    assert discord["id"] == "discord"
    assert discord["coming_soon"] is False
    assert discord["configured"] is False
    assert discord["status"] == "setup_required"
    assert discord["enabled_lanes"] == ["readiness"]
    other = {p["id"]: p for p in providers[3:]}
    for pid in ("bluesky", "farcaster", "linkedin"):
        assert pid in other
        assert other[pid]["coming_soon"] is True
        assert other[pid]["configured"] is False
        assert other[pid]["status"] == "coming_soon"
        assert other[pid]["enabled_lanes"] == []


def test_provider_list_marks_td_provider_active_when_gateway_reports_connected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token-1234567890")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", "-1009876543210")
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    status_path = tmp_path / "hermes-home" / "gateway_state.json"
    _write_hermes_gateway_state(
        status_path,
        platforms={"telegram": {"state": "connected"}},
    )
    providers = client.get("/api/social/providers").json()["providers"]
    telegram = next(provider for provider in providers if provider["id"] == "telegram")
    assert telegram["coming_soon"] is False
    assert telegram["configured"] is True
    assert telegram["status"] == "active"


def test_provider_status_setup_required_when_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _clear_x_creds(monkeypatch)
    res = client.get("/api/social/providers")
    assert res.status_code == 200
    x = res.json()["providers"][0]
    assert x["id"] == "x"
    assert x["configured"] is False
    assert x["status"] == "setup_required"


def test_provider_status_blocked_when_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    res = client.get("/api/social/providers")
    assert res.status_code == 200
    x = res.json()["providers"][0]
    assert x["status"] == "blocked"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_capabilities_default_safe_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _clear_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/capabilities")
    assert res.status_code == 200
    body = res.json()
    assert body["provider_id"] == "x"
    assert body["live_apply_available"] is False
    assert body["read_only"] is True
    assert body["live_read_available"] is False
    assert body["live_model_available"] is False
    assert body["broadcast_dry_run_available"] is False
    assert body["broadcast_live_available"] is False
    assert body["reactive_inbox_discovery_available"] is False
    assert body["reactive_dry_run_available"] is False
    assert body["reactive_reply_canary_available"] is False
    assert body["reactive_batch_available"] is False
    assert body["reactive_reply_apply_available"] is False


def test_capabilities_live_read_and_model_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/capabilities")
    body = res.json()
    assert body["live_read_available"] is True
    assert body["live_model_available"] is True
    assert body["live_apply_available"] is False


def test_capabilities_reports_reactive_reply_apply_available_when_gated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    body = client.get("/api/social/providers/x/capabilities").json()
    assert body["reactive_reply_canary_available"] is True
    assert body["reactive_reply_apply_available"] is True
    assert body["live_apply_available"] is True


def test_capabilities_broadcast_dry_run_requires_full_dry_run_gate_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_READ_MODEL_DRY_RUN", "true")
    monkeypatch.setenv("HAM_X_DRY_RUN", "true")
    monkeypatch.setenv("HAM_X_AUTONOMY_ENABLED", "false")
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_EXECUTION", "false")
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_SMOKE", "false")
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "false")
    monkeypatch.setenv("HAM_X_READONLY_TRANSPORT", "direct")
    res = client.get("/api/social/providers/x/capabilities")
    assert res.json()["broadcast_dry_run_available"] is True


def test_capabilities_reports_broadcast_apply_available_when_gated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    body = client.get("/api/social/providers/x/capabilities").json()
    assert body["broadcast_live_available"] is True
    assert body["broadcast_apply_available"] is True
    assert body["live_apply_available"] is True


def test_capabilities_reactive_inbox_discovery_requires_handle_or_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_REACTIVE_INBOX_DISCOVERY", "true")
    monkeypatch.delenv("HAM_X_REACTIVE_INBOX_QUERY", raising=False)
    monkeypatch.delenv("HAM_X_REACTIVE_HANDLE", raising=False)
    assert client.get("/api/social/providers/x/capabilities").json()["reactive_inbox_discovery_available"] is False
    monkeypatch.setenv("HAM_X_REACTIVE_HANDLE", "@HamOfficial")
    assert client.get("/api/social/providers/x/capabilities").json()["reactive_inbox_discovery_available"] is True


def test_telegram_status_capabilities_and_checklist_are_read_only_and_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    token = "telegram-token-secret-1234567890"
    allowed = "123456789"
    channel = "-1001234567890"
    test_group = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", allowed)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", channel)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", test_group)
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8765")
    _write_hermes_gateway_state(
        tmp_path / "hermes-home" / "gateway_state.json",
        active_agents=1,
        platforms={"telegram": {"state": "connected"}},
    )

    status = client.get("/api/social/providers/telegram/status")
    assert status.status_code == 200
    body = status.json()
    assert body["provider_id"] == "telegram"
    assert body["overall_readiness"] == "ready"
    assert body["required_connections"] == {
        "bot_token_present": True,
        "allowed_users_configured": True,
        "home_channel_configured": True,
        "test_group_configured": True,
    }
    assert body["hermes_gateway"]["provider_runtime_state"] == "connected"
    assert body["hermes_gateway"]["base_url_configured"] is True
    assert body["hermes_gateway"]["status_path_configured"] is True
    assert body["hermes_gateway"]["active_agents"] == 1
    assert body["telegram_bot_token_present"] is True
    assert body["telegram_allowed_users_present"] is True
    assert body["telegram_home_channel_configured"] is True
    assert body["telegram_test_group_configured"] is True
    assert body["telegram_mode"] == "polling"
    assert body["hermes_gateway_base_url_present"] is True
    assert body["hermes_gateway_status_path_present"] is True
    assert body["hermes_gateway_runtime_state"] == "connected"
    assert body["telegram_platform_state"] == "connected"
    assert body["readiness"] == "ready"
    assert body["missing_requirements"] == []
    assert body["recommended_next_steps"]
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False
    assert body["live_apply_available"] is False
    assert body["safe_identifiers"]["home_channel"].startswith("configured:")
    assert body["safe_identifiers"]["test_group"].startswith("configured:")

    caps = client.get("/api/social/providers/telegram/capabilities").json()
    assert caps["bot_token_present"] is True
    assert caps["allowed_users_configured"] is True
    assert caps["home_channel_configured"] is True
    assert caps["test_group_configured"] is True
    assert caps["telegram_mode"] == "polling"
    assert caps["hermes_gateway_base_url_present"] is True
    assert caps["hermes_gateway_status_path_present"] is True
    assert caps["hermes_gateway_runtime_state"] == "connected"
    assert caps["telegram_platform_state"] == "connected"
    assert caps["readiness"] == "ready"
    assert caps["missing_requirements"] == []
    assert caps["polling_supported"] is True
    assert caps["webhook_supported"] is True
    assert caps["groups_supported"] is True
    assert caps["topics_supported"] is True
    assert caps["media_supported"] is True
    assert caps["voice_supported"] is True
    assert caps["inbound_available"] is True
    assert caps["preview_available"] is False
    assert caps["live_message_available"] is False
    assert caps["live_apply_available"] is False
    assert caps["read_only"] is True
    assert caps["mutation_attempted"] is False

    checklist = client.get("/api/social/providers/telegram/setup/checklist").json()
    assert checklist["provider_id"] == "telegram"
    assert checklist["read_only"] is True
    assert checklist["mutation_attempted"] is False
    assert {item["id"] for item in checklist["items"]} == {
        "telegram_bot_token",
        "telegram_allowed_users",
        "telegram_home_channel",
        "telegram_test_group",
        "telegram_mode",
        "hermes_gateway_status",
        "hermes_gateway_runtime",
    }
    assert all(isinstance(item["ok"], bool) for item in checklist["items"])

    text = status.text + json.dumps(caps, sort_keys=True) + json.dumps(checklist, sort_keys=True)
    for raw in (token, allowed, channel, test_group):
        assert raw not in text


def test_discord_status_capabilities_and_checklist_are_read_only_and_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    token = "discord-token-secret-1234567890"
    allowed = "284102345871466496"
    channel = "123456789012345678"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", token)
    monkeypatch.setenv("DISCORD_ALLOWED_USERS", allowed)
    monkeypatch.setenv("DISCORD_HOME_CHANNEL", channel)
    _write_hermes_gateway_state(
        tmp_path / "hermes-home" / "gateway_state.json",
        platforms={"discord": {"state": "connected"}},
    )

    status = client.get("/api/social/providers/discord/status")
    assert status.status_code == 200
    body = status.json()
    assert body["provider_id"] == "discord"
    assert body["overall_readiness"] == "ready"
    assert body["required_connections"] == {
        "bot_token_present": True,
        "allowed_users_or_roles_configured": True,
        "guild_or_channel_configured": True,
    }
    assert body["hermes_gateway"]["provider_runtime_state"] == "connected"
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False
    assert body["live_apply_available"] is False
    assert body["safe_identifiers"]["home_channel"].startswith("configured:")

    caps = client.get("/api/social/providers/discord/capabilities").json()
    assert caps["bot_token_present"] is True
    assert caps["allowed_users_or_roles_configured"] is True
    assert caps["guild_or_channel_configured"] is True
    assert caps["dms_supported"] is True
    assert caps["channels_supported"] is True
    assert caps["threads_supported"] is True
    assert caps["slash_commands_supported"] is True
    assert caps["media_supported"] is True
    assert caps["voice_supported"] is True
    assert caps["inbound_available"] is True
    assert caps["preview_available"] is False
    assert caps["live_message_available"] is False
    assert caps["live_apply_available"] is False
    assert caps["read_only"] is True
    assert caps["mutation_attempted"] is False

    checklist = client.get("/api/social/providers/discord/setup/checklist").json()
    assert checklist["provider_id"] == "discord"
    assert checklist["read_only"] is True
    assert checklist["mutation_attempted"] is False
    assert {item["id"] for item in checklist["items"]} == {
        "discord_bot_token",
        "discord_allowed_users_or_roles",
        "discord_guild_or_channel",
        "hermes_gateway_runtime",
    }
    assert all(isinstance(item["ok"], bool) for item in checklist["items"])

    text = status.text + json.dumps(caps, sort_keys=True) + json.dumps(checklist, sort_keys=True)
    for raw in (token, allowed, channel):
        assert raw not in text


def test_td_missing_or_unknown_gateway_status_is_limited_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token-secret-1234567890")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123456789")
    body = client.get("/api/social/providers/telegram/status").json()
    assert body["overall_readiness"] == "limited"
    assert "home_channel_not_configured" in body["readiness_reasons"]
    assert "hermes_gateway_runtime_unknown" in body["readiness_reasons"]
    assert body["hermes_gateway"]["source"] == "unknown"
    assert body["hermes_gateway"]["status_file_available"] is False
    assert body["hermes_gateway"]["status_path_configured"] is True
    assert body["hermes_gateway"]["provider_runtime_state"] == "unknown"
    assert body["telegram_platform_state"] == "unknown"
    assert body["telegram_mode"] == "unset"
    assert "telegram_home_channel" in body["missing_requirements"]
    assert "telegram_test_group" in body["missing_requirements"]
    assert body["live_apply_available"] is False


def test_telegram_malformed_gateway_state_returns_unknown_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    token = "telegram-token-secret-1234567890"
    allowed = "123456789"
    status_path = tmp_path / "gateway_state.json"
    status_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("HAM_HERMES_GATEWAY_STATUS_PATH", str(status_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", allowed)

    body = client.get("/api/social/providers/telegram/status").json()
    text = json.dumps(body, sort_keys=True)
    assert body["overall_readiness"] == "limited"
    assert body["hermes_gateway"]["source"] == "status_file"
    assert body["hermes_gateway"]["status_file_available"] is True
    assert body["hermes_gateway"]["provider_runtime_state"] == "unknown"
    assert body["telegram_platform_state"] == "not_reported"
    assert body["mutation_attempted"] is False
    assert body["live_apply_available"] is False
    assert token not in text
    assert allowed not in text
    assert str(status_path) not in text


def test_telegram_gateway_state_extracts_platform_state_without_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    token = "telegram-token-secret-1234567890"
    allowed = "123456789"
    channel = "-1001234567890"
    test_group = "-1009876543210"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", allowed)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", channel)
    monkeypatch.setenv("TELEGRAM_TEST_GROUP_ID", test_group)
    monkeypatch.setenv("HERMES_TELEGRAM_MODE", "webhook")
    _write_hermes_gateway_state(
        tmp_path / "hermes-home" / "gateway_state.json",
        platforms={
            "telegram": {
                "state": "retrying",
                "chat_id": channel,
                "token": token,
                "error_message": f"failed for chat {channel} with token {token}",
            }
        },
    )

    status = client.get("/api/social/providers/telegram/status").json()
    caps = client.get("/api/social/providers/telegram/capabilities").json()
    text = json.dumps(status, sort_keys=True) + json.dumps(caps, sort_keys=True)
    assert status["telegram_platform_state"] == "retrying"
    assert status["hermes_gateway_runtime_state"] == "retrying"
    assert caps["telegram_platform_state"] == "retrying"
    assert caps["telegram_mode"] == "webhook"
    assert status["telegram_bot_token_present"] is True
    assert status["telegram_allowed_users_present"] is True
    assert status["telegram_test_group_configured"] is True
    for raw in (token, allowed, channel, test_group):
        assert raw not in text


def test_td_runtime_status_redacts_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    secret = "tok_abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    _write_hermes_gateway_state(
        tmp_path / "hermes-home" / "gateway_state.json",
        platforms={"discord": {"state": "fatal", "error_code": "auth", "error_message": f"Authorization: Bearer {secret}"}},
    )
    body = client.get("/api/social/providers/discord/status").json()
    text = json.dumps(body, sort_keys=True)
    assert body["overall_readiness"] == "blocked"
    assert body["hermes_gateway"]["provider_runtime_state"] == "fatal"
    assert secret not in text
    assert "[REDACTED]" in text


def test_td_has_no_preview_or_apply_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    for provider in ("telegram", "discord"):
        assert client.post(f"/api/social/providers/{provider}/messages/preview", json={}).status_code == 404
        assert client.post(f"/api/social/providers/{provider}/messages/apply", json={}).status_code == 404
        assert client.post(f"/api/social/providers/{provider}/reactive/reply/apply", json={}).status_code == 404


def test_social_persona_api_returns_read_only_bounded_dto(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    res = client.get("/api/social/persona/current")
    assert res.status_code == 200
    body = res.json()
    assert body["persona_id"] == "ham-canonical"
    assert body["version"] == 1
    assert body["display_name"] == "Ham"
    assert body["persona_digest"]
    assert len(body["persona_digest"]) == 64
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False
    assert {"x", "telegram", "discord"} <= set(body["platform_adaptations"])
    assert body["prohibited_content"]
    assert body["safety_boundaries"]
    assert body["example_replies"]
    assert body["example_announcements"]
    assert body["refusal_examples"]
    assert len(res.text) < 20_000


def test_social_persona_api_alias_matches_current(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    current = client.get("/api/social/persona/current").json()
    canonical = client.get("/api/social/personas/ham-canonical").json()
    assert canonical == current


def test_social_persona_api_does_not_expose_secret_shaped_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    text = client.get("/api/social/persona/current").text
    for value in ("api_key", "access_token", "Bearer ", "sk-", ".env", _BEARER, _XAI_KEY):
        assert value not in text


# ---------------------------------------------------------------------------
# Setup checklist
# ---------------------------------------------------------------------------


def test_setup_checklist_returns_booleans_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/setup/checklist")
    assert res.status_code == 200
    body = res.json()
    assert body["provider_id"] == "x"
    assert body["read_only"] is True
    item_ids = {item["id"]: item for item in body["items"]}
    assert {"x_read_credential", "x_write_credential", "xai_key", "reactive_handle", "emergency_stop"} <= set(
        item_ids.keys()
    )
    for item in body["items"]:
        assert isinstance(item["ok"], bool)
        assert isinstance(item["label"], str)
    assert item_ids["x_read_credential"]["ok"] is True
    assert item_ids["x_write_credential"]["ok"] is True
    assert item_ids["xai_key"]["ok"] is True
    assert item_ids["emergency_stop"]["ok"] is True
    flags = body["feature_flags"]
    for flag, value in flags.items():
        assert isinstance(value, bool), f"feature flag {flag} must be a bool"


def test_setup_checklist_does_not_expose_raw_credential_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_REACTIVE_HANDLE", "@SecretHandle1234")
    monkeypatch.setenv("HAM_X_REACTIVE_INBOX_QUERY", "secret query test 9999")
    res = client.get("/api/social/providers/x/setup/checklist")
    text = res.text
    for raw in (
        _BEARER,
        _API_KEY,
        _API_SECRET,
        _ACCESS_TOKEN,
        _ACCESS_TOKEN_SECRET,
        _XAI_KEY,
        "@SecretHandle1234",
        "secret query test 9999",
    ):
        assert raw not in text, f"raw value leaked: {raw!r}"


def test_x_write_credential_requires_all_four_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _clear_x_creds(monkeypatch)
    monkeypatch.setenv("X_API_KEY", _API_KEY)
    monkeypatch.setenv("X_API_SECRET", _API_SECRET)
    monkeypatch.setenv("X_ACCESS_TOKEN", _ACCESS_TOKEN)
    body = client.get("/api/social/providers/x/setup/checklist").json()
    item_ids = {item["id"]: item for item in body["items"]}
    assert item_ids["x_write_credential"]["ok"] is False
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", _ACCESS_TOKEN_SECRET)
    body = client.get("/api/social/providers/x/setup/checklist").json()
    item_ids = {item["id"]: item for item in body["items"]}
    assert item_ids["x_write_credential"]["ok"] is True


def test_setup_summary_returns_booleans_safe_ids_and_next_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_X_REACTIVE_HANDLE", "HamOfficial")
    body = client.get("/api/social/providers/x/setup/summary").json()
    assert body["provider_id"] == "x"
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False
    assert body["provider_configured"] is True
    assert isinstance(body["ready_for_dry_run"], bool)
    assert isinstance(body["ready_for_confirmed_live_reply"], bool)
    assert isinstance(body["ready_for_reactive_batch"], bool)
    assert isinstance(body["ready_for_broadcast"], bool)
    for value in body["required_connections"].values():
        assert isinstance(value, bool)
    for value in body["feature_flags"].values():
        assert isinstance(value, bool)
    assert body["safe_identifiers"]["campaign_id"]
    assert body["recommended_next_steps"]


def test_setup_summary_does_not_expose_raw_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _SOCIAL_TOKEN)
    monkeypatch.setenv("HAM_X_REACTIVE_HANDLE", "@SecretHandle1234")
    monkeypatch.setenv("HAM_X_REACTIVE_INBOX_QUERY", "secret query test 9999")
    text = client.get("/api/social/providers/x/setup/summary").text
    for raw in (
        _BEARER,
        _API_KEY,
        _API_SECRET,
        _ACCESS_TOKEN,
        _ACCESS_TOKEN_SECRET,
        _XAI_KEY,
        _SOCIAL_TOKEN,
        "@SecretHandle1234",
        "secret query test 9999",
    ):
        assert raw not in text


def test_setup_summary_missing_requirements_and_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _clear_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    body = client.get("/api/social/providers/x/setup/summary").json()
    missing = set(body["missing_requirement_ids"])
    assert "x_read_credential" in missing
    assert "x_write_credential" in missing
    assert "xai_key" in missing
    assert "social_live_apply_token" in missing
    assert "emergency_stop_disabled" in missing
    assert body["overall_readiness"] == "blocked"
    assert body["ready_for_broadcast"] is False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_status_emergency_stop_marks_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    res = client.get("/api/social/providers/x/status")
    assert res.status_code == 200
    body = res.json()
    assert body["provider_id"] == "x"
    assert body["overall_readiness"] == "blocked"
    assert body["emergency_stop"] == {"enabled": True}
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False


def test_status_paths_are_safe_display_strings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/status")
    body = res.json()
    paths = body["paths"]
    assert isinstance(paths["execution_journal_path"], str)
    assert isinstance(paths["audit_log_path"], str)
    assert _BEARER not in res.text
    assert _XAI_KEY not in res.text


def test_status_reports_last_autonomous_post_redacted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, _ = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    secret_token = "tok_abcdefghijklmnopqrstuvwxyz1234567890SECRET"
    _write_journal_row(
        journal,
        action_id=secret_token,
        provider_post_id=secret_token,
        idempotency_key=secret_token,
    )
    res = client.get("/api/social/providers/x/status")
    body = res.json()
    assert body["last_autonomous_post"] is not None
    text = json.dumps(body, sort_keys=True)
    assert secret_token not in text
    assert "[REDACTED" in text


def test_status_cap_summary_includes_reactive_caps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/status")
    summary = res.json()["cap_cooldown_summary"]
    assert summary["broadcast_daily_cap"] >= 0
    assert summary["reactive_max_replies_per_hour"] >= 0
    assert summary["reactive_max_replies_per_15m"] >= 0


# ---------------------------------------------------------------------------
# Journal summary
# ---------------------------------------------------------------------------


def test_journal_summary_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.get("/api/social/providers/x/journal/summary")
    body = res.json()
    assert res.status_code == 200
    assert body["total_count_scanned"] == 0
    assert body["malformed_count"] == 0
    assert body["counts_by_execution_kind"] == {}
    assert body["latest_broadcast_post"] is None
    assert body["latest_reactive_reply"] is None
    assert body["recent_items"] == []
    assert body["read_only"] is True
    assert body["mutation_attempted"] is False


def test_journal_summary_handles_malformed_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, _ = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("{not-json}\n[]\n\n", encoding="utf-8")
    body = client.get("/api/social/providers/x/journal/summary").json()
    assert body["malformed_count"] >= 1
    assert body["total_count_scanned"] == 0


def test_journal_summary_counts_by_execution_kind_and_latest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, _ = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _write_journal_row(journal, action_id="b1", provider_post_id="p-old", executed_at=_now_iso(120))
    _write_journal_row(journal, action_id="b2", provider_post_id="p-new", executed_at=_now_iso(0))
    _write_journal_row(
        journal,
        action_id="r1",
        provider_post_id="r-old",
        action_type="reply",
        execution_kind="goham_reactive_reply",
        executed_at=_now_iso(60),
    )
    body = client.get("/api/social/providers/x/journal/summary").json()
    counts = body["counts_by_execution_kind"]
    assert counts.get("goham_autonomous") == 2
    assert counts.get("goham_reactive_reply") == 1
    assert body["latest_broadcast_post"]["action_id"] == "b2"
    assert body["latest_reactive_reply"]["action_id"] == "r1"


def test_journal_summary_recent_items_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, _ = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    for idx in range(50):
        _write_journal_row(
            journal,
            action_id=f"a-{idx}",
            provider_post_id=f"p-{idx}",
            executed_at=_now_iso(50 - idx),
        )
    body = client.get("/api/social/providers/x/journal/summary").json()
    assert body["bounds"]["max_recent_items"] == 10
    assert len(body["recent_items"]) <= 10


# ---------------------------------------------------------------------------
# Audit summary
# ---------------------------------------------------------------------------


def test_audit_summary_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    body = client.get("/api/social/providers/x/audit/summary").json()
    assert body["total_count_scanned"] == 0
    assert body["malformed_count"] == 0
    assert body["counts_by_event_type"] == {}
    assert body["latest_audit_ids"] == []
    assert body["recent_events"] == []


def test_audit_summary_counts_event_types_and_redacts_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    secret = "tok_abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    _write_audit_row(
        audit,
        audit_id="aud-1",
        event_type="goham_execution_executed",
        payload={
            "status": "ok",
            "diagnostic": f"Authorization: Bearer {secret}",
            "execution_allowed": False,
            "mutation_attempted": False,
            "raw_credential": secret,
        },
    )
    _write_audit_row(audit, audit_id="aud-2", event_type="goham_reactive_completed")
    body = client.get("/api/social/providers/x/audit/summary").json()
    text = json.dumps(body, sort_keys=True)
    assert body["counts_by_event_type"]["goham_execution_executed"] == 1
    assert body["counts_by_event_type"]["goham_reactive_completed"] == 1
    assert "aud-1" in body["latest_audit_ids"]
    assert "aud-2" in body["latest_audit_ids"]
    # raw secret-shaped value should be redacted out of any payload field.
    assert secret not in text
    # raw_credential is not in the allowlisted scalar keys; it must not appear.
    assert "raw_credential" not in text


def test_audit_summary_recent_events_and_audit_ids_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    for idx in range(50):
        _write_audit_row(audit, audit_id=f"aud-{idx}", event_type="goham_execution_executed")
    body = client.get("/api/social/providers/x/audit/summary").json()
    assert body["bounds"]["max_recent_events"] == 10
    assert len(body["recent_events"]) <= 10
    assert len(body["latest_audit_ids"]) <= 10


def test_audit_summary_does_not_append_audit_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    assert not audit.exists()
    res = client.get("/api/social/providers/x/audit/summary")
    assert res.status_code == 200
    assert not audit.exists()


# ---------------------------------------------------------------------------
# Preview routes
# ---------------------------------------------------------------------------


def _assert_preview_invariants(body: dict[str, object]) -> None:
    assert body["provider_id"] == "x"
    assert body["persona_id"] == "ham-canonical"
    assert body["persona_version"] == 1
    assert isinstance(body["persona_digest"], str)
    assert len(str(body["persona_digest"])) == 64
    assert body["execution_allowed"] is False
    assert body["mutation_attempted"] is False
    assert body["live_apply_available"] is False
    assert body["read_only"] is True
    assert isinstance(body["result"], dict)


def test_preview_routes_are_post_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    for route in _PREVIEW_ROUTES:
        assert client.post(route, json={}).status_code == 200
        assert client.get(route).status_code == 405


def test_reactive_inbox_preview_is_bounded_redacted_and_non_mutating(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_REACTIVE_INBOX_DISCOVERY", "false")
    res = client.post("/api/social/providers/x/reactive/inbox/preview", json={"client_request_id": "abc"})
    body = res.json()
    _assert_preview_invariants(body)
    assert body["preview_kind"] == "reactive_inbox"
    assert body["status"] == "blocked"
    assert "reactive_inbox_discovery_disabled" in body["reasons"]
    assert journal.exists() is False
    assert audit.exists() is False
    text = json.dumps(body, sort_keys=True)
    for raw in (_BEARER, _API_KEY, _API_SECRET, _ACCESS_TOKEN, _ACCESS_TOKEN_SECRET, _XAI_KEY):
        assert raw not in text


def test_reactive_batch_dry_run_forces_no_provider_call_and_no_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_REACTIVE", "true")
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_REACTIVE_BATCH", "true")
    monkeypatch.setenv("HAM_X_GOHAM_REACTIVE_BATCH_DRY_RUN", "false")
    payload = {
        "candidates": [
            {
                "inbound_id": "inbound-1",
                "inbound_type": "mention",
                "text": "Question for Ham: how does governed autonomy stay audited?",
                "author_id": "user-1",
                "author_handle": "user1",
                "post_id": "post-1",
                "thread_id": "thread-1",
                "conversation_id": "thread-1",
                "relevance_score": 0.95,
            }
        ]
    }
    res = client.post("/api/social/providers/x/reactive/batch/dry-run", json=payload)
    body = res.json()
    _assert_preview_invariants(body)
    assert body["preview_kind"] == "reactive_batch_dry_run"
    assert body["status"] == "completed"
    assert body["result"]["attempted_count"] == 1
    assert body["result"]["items"][0]["status"] == "dry_run"
    assert body["result"]["items"][0]["execution_allowed"] is False
    assert body["result"]["items"][0]["mutation_attempted"] is False
    assert journal.exists() is False
    assert audit.exists() is False


def test_reactive_batch_dry_run_blocks_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    res = client.post("/api/social/providers/x/reactive/batch/dry-run", json={"candidates": []})
    body = res.json()
    _assert_preview_invariants(body)
    assert body["status"] == "blocked"
    assert "reactive_disabled" in body["reasons"]
    assert "reactive_batch_disabled" in body["reasons"]
    assert "no_candidates_provided" in body["warnings"]


def test_broadcast_preflight_preview_does_not_write_or_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal, audit = _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_X_ENABLE_GOHAM_EXECUTION", "true")
    monkeypatch.setenv("HAM_X_AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("HAM_X_DRY_RUN", "false")
    monkeypatch.setenv("HAM_X_ENABLE_LIVE_EXECUTION", "true")
    res = client.post(
        "/api/social/providers/x/broadcast/preflight",
        json={
            "preflight_candidate": {
                "text": "Ham preview-only check: governed social automation stays capped and audited.",
                "action_id": "preview-action-1",
                "source_action_id": "preview-source-1",
                "idempotency_key": "preview-idem-1",
            }
        },
    )
    body = res.json()
    _assert_preview_invariants(body)
    assert body["preview_kind"] == "broadcast_preflight"
    assert body["result"]["eligibility"]["execution_allowed"] is False
    assert body["result"]["eligibility"]["mutation_attempted"] is False
    assert journal.exists() is False
    assert audit.exists() is False


def test_broadcast_preflight_server_candidate_returns_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    body = client.post("/api/social/providers/x/broadcast/preflight", json={}).json()
    _assert_preview_invariants(body)
    assert body["preview_kind"] == "broadcast_preflight"
    assert body["proposal_digest"]
    assert body["result"]["candidate"]["action_type"] == "post"


def test_preview_payloads_do_not_expose_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    payload = {
        "preflight_candidate": {
            "text": f"Safe preview text with Authorization: Bearer {_ACCESS_TOKEN}",
            "idempotency_key": _ACCESS_TOKEN_SECRET,
        }
    }
    body = client.post("/api/social/providers/x/broadcast/preflight", json=payload).json()
    text = json.dumps(body, sort_keys=True)
    for raw in (_BEARER, _API_KEY, _API_SECRET, _ACCESS_TOKEN, _ACCESS_TOKEN_SECRET, _XAI_KEY):
        assert raw not in text
    assert "[REDACTED" in text


def test_preview_payloads_include_persona_reference_not_full_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    body = client.post("/api/social/providers/x/broadcast/preflight", json={}).json()
    _assert_preview_invariants(body)
    text = json.dumps(body, sort_keys=True)
    assert "persona_id" in body
    assert "persona_version" in body
    assert "persona_digest" in body
    assert "platform_adaptations" not in text
    assert "safety_boundaries" not in text


# ---------------------------------------------------------------------------
# Confirmed live reactive reply apply
# ---------------------------------------------------------------------------


def test_apply_routes_exist_only_for_supported_live_controls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    assert client.post(_APPLY_ROUTE, json={}).status_code in {200, 422}
    assert client.post(_BATCH_APPLY_ROUTE, json={}).status_code in {200, 422}
    assert client.post(_BROADCAST_APPLY_ROUTE, json={}).status_code in {200, 422}
    assert client.post("/api/social/providers/x/quote/apply", json={}).status_code == 404
    assert client.post("/api/social/providers/x/like/apply", json={}).status_code == 404
    assert client.post("/api/social/providers/x/follow/apply", json={}).status_code == 404
    assert client.post("/api/social/providers/x/dm/apply", json={}).status_code == 404


def test_apply_blocked_without_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    body = client.post(
        _APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"confirmation_phrase": _CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert body["execution_allowed"] is False
    assert body["mutation_attempted"] is False
    assert "proposal_digest_required" in body["reasons"]


def test_apply_blocked_with_stale_or_wrong_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        body = client.post(
            _APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": "0" * 64, "confirmation_phrase": _CONFIRM},
        ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_apply_blocked_without_operator_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
    res = client.post(_APPLY_ROUTE, json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM})
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_REQUIRED"


def test_apply_blocked_with_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
    res = client.post(
        _APPLY_ROUTE,
        headers={"Authorization": "Bearer wrong-token"},
        json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_INVALID"


def test_apply_blocked_without_exact_confirmation_phrase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
    body = client.post(
        _APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": "send one live reply"},
    ).json()
    assert body["status"] == "blocked"
    assert "confirmation_phrase_required" in body["reasons"]


def test_apply_blocked_by_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    body = client.post(
        _APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert "emergency_stop" in body["reasons"]


def test_apply_blocked_when_preview_candidate_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(inbound_id="inbound-1")):
        digest = _preview_digest()
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(inbound_id="inbound-2")):
        body = client.post(
            _APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
        ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_apply_blocks_when_persona_digest_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
        original = {"persona_id": "ham-canonical", "persona_version": 1, "persona_digest": "b" * 64}
        with patch("src.api.social._persona_ref", return_value=original):
            body = client.post(
                _APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
            ).json()
    assert body["status"] == "blocked"
    assert "persona_digest_mismatch" in body["reasons"]
    assert body["persona_digest"] == "b" * 64


def test_apply_calls_live_reply_once_and_returns_journal_audit_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
        with patch("src.api.social.run_reactive_live_once", return_value=_fake_live_result()) as live:
            body = client.post(
                _APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
            ).json()
    assert live.call_count == 1
    assert body["status"] == "executed"
    assert body["persona_id"] == "ham-canonical"
    assert body["persona_version"] == 1
    assert len(body["persona_digest"]) == 64
    assert body["execution_allowed"] is True
    assert body["mutation_attempted"] is True
    assert body["provider_status_code"] == 201
    assert body["provider_post_id"] == "reply-post-1"
    assert body["execution_kind"] == "goham_reactive_reply"
    assert body["audit_ids"] == ["audit-1", "audit-2"]
    assert body["journal_path"]
    assert body["audit_path"]


def test_apply_does_not_accept_arbitrary_reply_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
    res = client.post(
        _APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM, "reply_text": "client supplied"},
    )
    assert res.status_code == 422


def test_apply_provider_failure_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _preview_digest()
        with patch(
            "src.api.social.run_reactive_live_once",
            return_value=_fake_live_result(status="failed", provider_status_code=500, provider_post_id=None),
        ) as live:
            body = client.post(
                _APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
            ).json()
    assert live.call_count == 1
    assert body["status"] == "failed"
    assert body["provider_status_code"] == 500
    assert body["provider_post_id"] is None


def test_apply_response_redacted_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_apply_env(monkeypatch)
    secret = "tok_abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(reply_text=secret)):
        digest = _preview_digest()
        with patch("src.api.social.run_reactive_live_once", return_value=_fake_live_result(provider_post_id=secret)):
            body = client.post(
                _APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _CONFIRM},
            ).json()
    text = json.dumps(body, sort_keys=True)
    assert secret not in text
    assert "[REDACTED" in text


def test_batch_apply_blocked_without_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    body = client.post(
        _BATCH_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"confirmation_phrase": _BATCH_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert body["execution_allowed"] is False
    assert body["mutation_attempted"] is False
    assert "proposal_digest_required" in body["reasons"]


def test_batch_apply_blocked_with_stale_or_wrong_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        body = client.post(
            _BATCH_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": "0" * 64, "confirmation_phrase": _BATCH_CONFIRM},
        ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_batch_apply_blocked_without_operator_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
    res = client.post(_BATCH_APPLY_ROUTE, json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM})
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_REQUIRED"


def test_batch_apply_blocked_with_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
    res = client.post(
        _BATCH_APPLY_ROUTE,
        headers={"Authorization": "Bearer wrong-token"},
        json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_INVALID"


def test_batch_apply_blocked_without_exact_confirmation_phrase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
    body = client.post(
        _BATCH_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": "send live reactive batch"},
    ).json()
    assert body["status"] == "blocked"
    assert "confirmation_phrase_required" in body["reasons"]


def test_batch_apply_blocked_by_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    body = client.post(
        _BATCH_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert "emergency_stop" in body["reasons"]


def test_batch_apply_blocked_when_dry_run_candidate_set_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(inbound_id="inbound-1")):
        digest = _batch_preview_digest()
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(inbound_id="inbound-2")):
        body = client.post(
            _BATCH_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
        ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_batch_apply_blocks_when_persona_digest_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
        changed = {"persona_id": "ham-canonical", "persona_version": 1, "persona_digest": "c" * 64}
        with patch("src.api.social._persona_ref", return_value=changed):
            body = client.post(
                _BATCH_APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
            ).json()
    assert body["status"] == "blocked"
    assert "persona_digest_mismatch" in body["reasons"]
    assert body["persona_digest"] == "c" * 64


def test_batch_apply_calls_batch_runner_once_and_returns_journal_audit_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
        with patch("src.api.social.run_reactive_batch_once", return_value=_fake_batch_result()) as batch:
            body = client.post(
                _BATCH_APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
            ).json()
    assert batch.call_count == 1
    assert body["status"] == "completed"
    assert body["persona_id"] == "ham-canonical"
    assert body["persona_version"] == 1
    assert len(body["persona_digest"]) == 64
    assert body["execution_allowed"] is True
    assert body["mutation_attempted"] is True
    assert body["attempted_count"] == 2
    assert body["executed_count"] == 2
    assert body["execution_kind"] == "goham_reactive_reply"
    assert body["audit_ids"] == ["audit-batch-1"]
    assert body["provider_post_ids"] == ["reply-post-1", "reply-post-2"]


def test_batch_apply_does_not_accept_arbitrary_reply_text_or_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
    res = client.post(
        _BATCH_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={
            "proposal_digest": digest,
            "confirmation_phrase": _BATCH_CONFIRM,
            "reply_text": "client supplied",
            "candidates": [{"inbound_id": "client"}],
        },
    )
    assert res.status_code == 422


def test_batch_apply_provider_failure_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery()):
        digest = _batch_preview_digest()
        with patch("src.api.social.run_reactive_batch_once", return_value=_fake_batch_result(status="stopped", provider_post_ids=[])) as batch:
            body = client.post(
                _BATCH_APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
            ).json()
    assert batch.call_count == 1
    assert body["status"] == "stopped"
    assert body["failed_count"] == 1


def test_batch_apply_response_redacted_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_batch_apply_env(monkeypatch)
    secret = "tok_abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    with patch("src.api.social.discover_reactive_inbox_once", return_value=_fake_discovery(reply_text=secret)):
        digest = _batch_preview_digest()
        with patch("src.api.social.run_reactive_batch_once", return_value=_fake_batch_result(provider_post_ids=[secret])):
            body = client.post(
                _BATCH_APPLY_ROUTE,
                headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
                json={"proposal_digest": digest, "confirmation_phrase": _BATCH_CONFIRM},
            ).json()
    text = json.dumps(body, sort_keys=True)
    assert secret not in text
    assert "[REDACTED" in text


def test_broadcast_apply_blocked_without_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    body = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"confirmation_phrase": _BROADCAST_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert body["execution_allowed"] is False
    assert body["mutation_attempted"] is False
    assert "proposal_digest_required" in body["reasons"]


def test_broadcast_apply_blocked_with_stale_or_wrong_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    body = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": "0" * 64, "confirmation_phrase": _BROADCAST_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_broadcast_apply_blocked_without_operator_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    res = client.post(_BROADCAST_APPLY_ROUTE, json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM})
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_REQUIRED"


def test_broadcast_apply_blocked_with_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    res = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": "Bearer wrong-token"},
        json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_LIVE_APPLY_AUTH_INVALID"


def test_broadcast_apply_blocked_without_exact_confirmation_phrase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    body = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": "send one live post"},
    ).json()
    assert body["status"] == "blocked"
    assert "confirmation_phrase_required" in body["reasons"]


def test_broadcast_apply_blocked_by_emergency_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    monkeypatch.setenv("HAM_X_EMERGENCY_STOP", "true")
    body = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert "emergency_stop" in body["reasons"]


def test_broadcast_apply_blocked_when_preflight_candidate_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    monkeypatch.setenv("HAM_X_CAMPAIGN_ID", "changed-campaign")
    body = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
    ).json()
    assert body["status"] == "blocked"
    assert "proposal_digest_mismatch" in body["reasons"]


def test_broadcast_apply_blocks_when_persona_digest_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    changed = {"persona_id": "ham-canonical", "persona_version": 1, "persona_digest": "d" * 64}
    with patch("src.api.social._persona_ref", return_value=changed):
        body = client.post(
            _BROADCAST_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
        ).json()
    assert body["status"] == "blocked"
    assert "persona_digest_mismatch" in body["reasons"]
    assert body["persona_digest"] == "d" * 64


def test_broadcast_apply_calls_governed_controller_once_and_returns_journal_audit_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    with patch("src.api.social.run_live_controller_once", return_value=_fake_broadcast_result()) as live:
        body = client.post(
            _BROADCAST_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
        ).json()
    assert live.call_count == 1
    assert body["status"] == "executed"
    assert body["persona_id"] == "ham-canonical"
    assert body["persona_version"] == 1
    assert len(body["persona_digest"]) == 64
    assert body["execution_allowed"] is True
    assert body["mutation_attempted"] is True
    assert body["provider_status_code"] == 201
    assert body["provider_post_id"] == "broadcast-post-1"
    assert body["execution_kind"] == "goham_autonomous"
    assert body["audit_ids"] == ["audit-post-1"]


def test_broadcast_apply_does_not_accept_arbitrary_post_text_or_candidate_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    res = client.post(
        _BROADCAST_APPLY_ROUTE,
        headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
        json={
            "proposal_digest": digest,
            "confirmation_phrase": _BROADCAST_CONFIRM,
            "post_text": "client supplied",
            "candidate": {"text": "client supplied"},
        },
    )
    assert res.status_code == 422


def test_broadcast_apply_provider_failure_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    digest = _broadcast_preview_digest()
    with patch(
        "src.api.social.run_live_controller_once",
        return_value=_fake_broadcast_result(status="failed", provider_status_code=500, provider_post_id=None),
    ) as live:
        body = client.post(
            _BROADCAST_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
        ).json()
    assert live.call_count == 1
    assert body["status"] == "failed"
    assert body["provider_status_code"] == 500
    assert body["provider_post_id"] is None


def test_broadcast_apply_response_redacted_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_journal(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_broadcast_apply_env(monkeypatch)
    secret = "tok_abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    digest = _broadcast_preview_digest()
    with patch("src.api.social.run_live_controller_once", return_value=_fake_broadcast_result(provider_post_id=secret)):
        body = client.post(
            _BROADCAST_APPLY_ROUTE,
            headers={"Authorization": f"Bearer {_SOCIAL_TOKEN}"},
            json={"proposal_digest": digest, "confirmation_phrase": _BROADCAST_CONFIRM},
        ).json()
    text = json.dumps(body, sort_keys=True)
    assert secret not in text
    assert "[REDACTED" in text


# ---------------------------------------------------------------------------
# Static safety: import isolation
# ---------------------------------------------------------------------------


_SOCIAL_API_PATH = Path(__file__).parents[1] / "src" / "api" / "social.py"


def test_social_api_does_not_import_write_or_execution_modules() -> None:
    text = _SOCIAL_API_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)
    forbidden_modules = {
        "src.ham.ham_x.x_executor",
        "src.ham.ham_x.manual_canary",
        "src.ham.ham_x.goham_controller",
        "src.ham.ham_x.reactive_reply_executor",
        "src.ham.ham_x.goham_reactive",
        "src.ham.ham_x.live_dry_run",
        "src.ham.ham_x.smoke",
        "src.ham.ham_x.pipeline",
        "src.ham.ham_x.audit",
    }
    assert imported_modules.isdisjoint(forbidden_modules), (
        f"forbidden modules imported: {sorted(imported_modules & forbidden_modules)}"
    )
    forbidden_names = {
        "append_audit_event",
        "run_goham_guarded_post",
        "run_controller_once",
        "ReactiveReplyExecutor",
        "XExecutor",
    }
    assert imported_names.isdisjoint(forbidden_names), (
        f"forbidden names imported: {sorted(imported_names & forbidden_names)}"
    )


def test_social_api_text_does_not_call_planner_route() -> None:
    text = _SOCIAL_API_PATH.read_text(encoding="utf-8")
    assert "/api/goham/planner" not in text
    assert "goham_planner" not in text


def test_social_api_text_does_not_import_send_message_or_gateway_controls() -> None:
    text = _SOCIAL_API_PATH.read_text(encoding="utf-8")
    forbidden = (
        "send_message_tool",
        "start_gateway",
        "stop_gateway",
        "restart_gateway",
        "terminate_pid",
        "gateway start",
        "gateway stop",
        "gateway restart",
    )
    for value in forbidden:
        assert value not in text
