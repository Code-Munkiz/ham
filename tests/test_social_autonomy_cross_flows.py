"""Cross-flow integration coverage for the GoHAM Social autonomy runner."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import requests
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.ham.ham_x.goham_policy import GOHAM_EXECUTION_KIND
from src.ham.ham_x.reactive_governor import GOHAM_REACTIVE_EXECUTION_KIND
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import (
    apply_social_autonomy_profile,
    read_social_autonomy_profile,
)
from src.ham.social_autonomy.tick import (
    AUTONOMY_CADENCE_NOT_DUE,
    AUTONOMY_CAP_EXCEEDED,
    AUTONOMY_CAP_TRACKING_UNAVAILABLE,
    AUTONOMY_CHANNEL_UNAVAILABLE,
    AUTONOMY_EMERGENCY_STOP,
    AUTONOMY_FORBIDDEN_TOPIC_MATCHED,
    AUTONOMY_PROFILE_NOT_RUNNING,
    AUTONOMY_QUIET_HOURS_ACTIVE,
    AUTONOMY_SAFETY_RULE_VIOLATION,
)
from src.ham.social_delivery_log import append_delivery_record
from src.ham.social_telegram_activity import TELEGRAM_ACTIVITY_EXECUTION_KIND
from src.ham.social_telegram_send import TELEGRAM_EXECUTION_KIND

client = TestClient(app)

_TOKEN = "cross-flow-autonomy-token"  # noqa: S105
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _actor() -> HamActor:
    return HamActor(
        user_id="user_cross_flow",
        org_id="org_cross_flow",
        session_id="session_cross_flow",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _auth_headers(*, write: bool = False) -> dict[str, str]:
    headers = {"Authorization": "Bearer fake.clerk.jwt"}
    if write:
        headers["X-Ham-Operator-Authorization"] = f"Bearer {_TOKEN}"
    return headers


def _with_actor(call: Callable[[], Any]) -> Any:
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=_actor()):
        return call()


def _get(path: str) -> Any:
    return _with_actor(lambda: client.get(path, headers=_auth_headers()))


def _post(path: str, *, body: dict[str, Any] | None = None, write: bool = False) -> Any:
    return _with_actor(
        lambda: client.post(path, headers=_auth_headers(write=write), json=body or {})
    )


def _prepare_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    monkeypatch.chdir(tmp_path)
    paths = {
        "profile": tmp_path / "profile.json",
        "x_journal": tmp_path / "execution_journal.jsonl",
        "x_audit": tmp_path / "x_audit.jsonl",
        "delivery_log": tmp_path / "social_delivery_log.jsonl",
        "learning": tmp_path / "hamgomoon_learning.jsonl",
    }
    paths["x_journal"].parent.mkdir(parents=True, exist_ok=True)
    paths["x_journal"].write_text("", encoding="utf-8")
    paths["delivery_log"].write_text("", encoding="utf-8")
    paths["learning"].write_text("", encoding="utf-8")

    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(paths["profile"]))
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN", _TOKEN)
    monkeypatch.setenv("HAM_X_EXECUTION_JOURNAL_PATH", str(paths["x_journal"]))
    monkeypatch.setenv("HAM_X_AUDIT_LOG_PATH", str(paths["x_audit"]))
    monkeypatch.setenv("HAM_SOCIAL_DELIVERY_LOG_PATH", str(paths["delivery_log"]))
    monkeypatch.setenv("HAM_HAMGOMOON_LEARNING_PATH", str(paths["learning"]))
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.test")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAMGOMOON_AUTOPILOT_ENABLED", raising=False)
    monkeypatch.delenv("HAMGOMOON_AUTOPILOT_DRY_RUN", raising=False)
    _block_outbound_network(monkeypatch)
    return paths


def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_httpx_send = httpx.Client.send
    original_async_httpx_send = httpx.AsyncClient.send

    def blocked_connect(_self: socket.socket, _address: object) -> None:
        raise AssertionError("live network attempted in test")

    def blocked_requests_send(
        _self: requests.adapters.HTTPAdapter, _request: object, **_kwargs: object
    ) -> None:
        raise AssertionError("live network attempted in test")

    def blocked_httpx_send(
        _self: httpx.Client,
        _request: httpx.Request,
        **_kwargs: object,
    ) -> httpx.Response:
        if _request.url.host == "testserver":
            return original_httpx_send(_self, _request, **_kwargs)
        raise AssertionError("live network attempted in test")

    async def blocked_async_httpx_send(
        _self: httpx.AsyncClient,
        _request: httpx.Request,
        **_kwargs: object,
    ) -> httpx.Response:
        if _request.url.host == "testserver":
            return await original_async_httpx_send(_self, _request, **_kwargs)
        raise AssertionError("live network attempted in test")

    def blocked_telegram_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("live send attempted in test")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked_requests_send)
    monkeypatch.setattr(httpx.Client, "send", blocked_httpx_send)
    monkeypatch.setattr(httpx.AsyncClient, "send", blocked_async_httpx_send)
    monkeypatch.setattr(
        "src.ham.social_telegram_send.TelegramBotApiTransport.send_message",
        blocked_telegram_send,
    )


def _patch_successful_transports(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    calls: dict[str, list[str]] = {"x": [], "telegram": []}

    def run_live(_prepared: object, *, dry_run: bool = False, **_kwargs: object) -> Any:
        assert dry_run is True
        calls["x"].append("live")
        return SimpleNamespace(status="dry_run", reasons=[])

    def run_batch(_candidates: object, *, dry_run: bool = False, **_kwargs: object) -> Any:
        assert dry_run is True
        calls["x"].append("batch")
        return SimpleNamespace(
            status="completed",
            reasons=[],
            items=[SimpleNamespace(status="dry_run", reasons=[])],
        )

    def run_telegram_once(config: object) -> Any:
        assert getattr(config, "dry_run", False) is True
        calls["telegram"].append("autopilot")
        return SimpleNamespace(
            lane_order=["reactive"],
            selected_lane="reactive",
            status="completed",
            dry_run=True,
            blocking_reasons=[],
            reasons=[],
        )

    monkeypatch.setattr(
        "src.ham.ham_x.goham_reactive_live.run_reactive_live_once",
        run_live,
    )
    monkeypatch.setattr(
        "src.ham.ham_x.goham_reactive_batch.run_reactive_batch_once",
        run_batch,
    )
    monkeypatch.setattr(
        "src.ham.social_telegram_autopilot.run_hamgomoon_autopilot_once",
        run_telegram_once,
    )
    return calls


def _set_route_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    monkeypatch.setattr("src.api.social._utc_now", lambda: now)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    created_at = _NOW - timedelta(days=1)
    payload: dict[str, Any] = {
        "profile_id": "cross-flow-profile",
        "workspace_id": "workspace-cross-flow",
        "project_id": "project-cross-flow",
        "status": "draft",
        "goal": "Grow awareness for HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": True, "available": True},
        },
        "actions_allowed_per_channel": {
            "x": ["reply", "broadcast"],
        },
        "daily_caps": {"x": 3},
        "cadence": "hourly",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    payload.update(overrides)
    return payload


def _profile(**overrides: Any) -> GoHamSocialProfile:
    return GoHamSocialProfile.model_validate(_profile_payload(**overrides))


def _persist(tmp_path: Path, profile: GoHamSocialProfile) -> None:
    apply_social_autonomy_profile(tmp_path, profile, token=_TOKEN, actor="pytest")


def _read_profile_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_launch_tick_pause_stop_flow_and_same_clock_idempotency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _prepare_environment(monkeypatch, tmp_path)
    calls = _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(tmp_path, _profile(status="draft"))

    launch = _post("/api/social/autonomy/launch", write=True)
    assert launch.status_code == 200, launch.text
    assert launch.json()["status"] == "running"

    first_tick = _post("/api/social/autonomy/tick")
    assert first_tick.status_code == 200, first_tick.text
    first_body = first_tick.json()
    assert first_body["ran"] is True
    assert first_body["dry_run"] is True
    assert first_body["actions_taken"] == ["x:reply", "x:broadcast"]
    assert first_body["blocked_reasons"] == []
    persisted_after_first = read_social_autonomy_profile(tmp_path)
    assert persisted_after_first.status == "running"
    assert persisted_after_first.last_run_at == _NOW
    assert persisted_after_first.next_run_at == _NOW + timedelta(hours=1)
    assert persisted_after_first.last_tick_summary is not None

    second_tick = _post("/api/social/autonomy/tick")
    third_tick = _post("/api/social/autonomy/tick")
    assert second_tick.status_code == 200, second_tick.text
    assert third_tick.status_code == 200, third_tick.text
    assert second_tick.json() == third_tick.json()
    assert second_tick.json()["ran"] is False
    assert second_tick.json()["blocked_reasons"] == [AUTONOMY_CADENCE_NOT_DUE]
    assert read_social_autonomy_profile(tmp_path).last_run_at == _NOW

    pause = _post("/api/social/autonomy/pause", write=True)
    assert pause.status_code == 200, pause.text
    paused_tick = _post("/api/social/autonomy/tick")
    assert paused_tick.json()["blocked_reasons"] == [AUTONOMY_PROFILE_NOT_RUNNING]
    assert _read_profile_file(paths["profile"])["status"] == "paused"

    stop = _post("/api/social/autonomy/stop", write=True)
    assert stop.status_code == 200, stop.text
    stopped_tick = _post("/api/social/autonomy/tick")
    assert stopped_tick.json()["blocked_reasons"] == [AUTONOMY_PROFILE_NOT_RUNNING]
    assert _read_profile_file(paths["profile"])["status"] == "stopped"
    assert calls["x"] == ["live", "batch"]


def test_emergency_stop_blocks_before_status_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(tmp_path, _profile(status="running"))

    stop = _post(
        "/api/social/autonomy/stop",
        body={"emergency_stop": True},
        write=True,
    )
    assert stop.status_code == 200, stop.text

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is False
    assert tick.json()["blocked_reasons"][0] == AUTONOMY_EMERGENCY_STOP


def test_mission12_profile_fixture_loads_and_ticks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _prepare_environment(monkeypatch, tmp_path)
    _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    fixture = _profile_payload(status="running")
    fixture.pop("last_run_at", None)
    fixture.pop("next_run_at", None)
    fixture.pop("last_tick_summary", None)
    paths["profile"].write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    before = _get("/api/social/autonomy")
    assert before.status_code == 200, before.text
    assert before.json()["last_run_at"] is None
    assert before.json()["next_run_at"] is None
    assert before.json()["last_tick_summary"] is None

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is True
    after = _get("/api/social/autonomy").json()
    assert after["last_run_at"] is not None
    assert after["next_run_at"] is not None
    assert after["last_tick_summary"]["ran"] is True


@pytest.mark.parametrize(
    ("channel", "records"),
    [
        (
            "x",
            [
                ("x", GOHAM_REACTIVE_EXECUTION_KIND),
                ("x", GOHAM_EXECUTION_KIND),
            ],
        ),
        (
            "telegram",
            [
                ("telegram", TELEGRAM_EXECUTION_KIND),
                ("telegram", TELEGRAM_ACTIVITY_EXECUTION_KIND),
            ],
        ),
    ],
)
def test_cap_exhaustion_blocks_x_and_telegram_without_dispatch(
    channel: str,
    records: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _prepare_environment(monkeypatch, tmp_path)
    calls = _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    profile = _profile(
        status="running",
        channels={channel: {"enabled": True, "available": True}},
        actions_allowed_per_channel={
            "x": ["reply", "broadcast"],
            "telegram": ["message", "activity"],
        },
        daily_caps={channel: 1},
    )
    _persist(tmp_path, profile)
    for _, execution_kind in records:
        if channel == "x":
            with paths["x_journal"].open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "action_id": f"{execution_kind}-1",
                            "execution_kind": execution_kind,
                            "executed_at": _NOW.isoformat().replace("+00:00", "Z"),
                            "idempotency_key": f"{execution_kind}-key",
                            "provider_post_id": "post-1",
                            "status": "executed",
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        else:
            append_delivery_record(
                {
                    "provider_id": "telegram",
                    "execution_kind": execution_kind,
                    "status": "sent",
                    "executed_at": _NOW.isoformat().replace("+00:00", "Z"),
                },
                path=paths["delivery_log"],
            )
    before_journal = paths["x_journal"].read_text(encoding="utf-8")
    before_delivery = paths["delivery_log"].read_text(encoding="utf-8")

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    body = tick.json()
    assert body["ran"] is False
    assert body["actions_taken"] == []
    assert body["blocked_reasons"] == [AUTONOMY_CAP_EXCEEDED]
    assert paths["x_journal"].read_text(encoding="utf-8") == before_journal
    assert paths["delivery_log"].read_text(encoding="utf-8") == before_delivery
    assert calls["x"] == []
    assert calls["telegram"] == []


def test_telegram_adapter_is_composed_on_successful_tick(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    calls = _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(
        tmp_path,
        _profile(
            status="running",
            channels={"telegram": {"enabled": True, "available": True}},
            actions_allowed_per_channel={"telegram": ["message", "activity"]},
            daily_caps={"telegram": 3},
        ),
    )

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is True
    assert tick.json()["actions_taken"] == ["telegram:message"]
    assert tick.json()["blocked_reasons"] == []
    assert calls["telegram"] == ["autopilot", "autopilot"]


def test_discord_only_profile_blocks_without_discord_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(
        tmp_path,
        _profile(
            status="running",
            channels={"discord": {"enabled": True, "available": True}},
            actions_allowed_per_channel={"discord": ["message"]},
            daily_caps={"discord": 1},
        ),
    )

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is False
    assert tick.json()["blocked_reasons"] == [AUTONOMY_CHANNEL_UNAVAILABLE]


def test_learning_enabled_appends_one_record_and_disabled_keeps_file_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _prepare_environment(monkeypatch, tmp_path)
    _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(tmp_path, _profile(status="running", learning_enabled=True))

    enabled = _post("/api/social/autonomy/tick")
    assert enabled.status_code == 200, enabled.text
    assert len(paths["learning"].read_text(encoding="utf-8").splitlines()) == 1

    paths["learning"].write_text("{}", encoding="utf-8")
    _persist(
        tmp_path,
        _profile(
            profile_id="learning-disabled-profile",
            status="running",
            learning_enabled=False,
        ),
    )
    before = paths["learning"].read_bytes()
    disabled = _post("/api/social/autonomy/tick")

    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["ran"] is True
    assert paths["learning"].read_bytes() == before


@pytest.mark.parametrize(
    ("profile_overrides", "expected_reason"),
    [
        (
            {"forbidden_topics": ["bitcoin"], "goal": "Discuss BITCOIN price safely."},
            AUTONOMY_FORBIDDEN_TOPIC_MATCHED,
        ),
        (
            {"safety_rules": ["mass_tagging"], "goal": "@a @b @c @d @e @f hello"},
            AUTONOMY_SAFETY_RULE_VIOLATION,
        ),
    ],
)
def test_content_guards_block_forbidden_topics_and_safety_violations(
    profile_overrides: dict[str, Any],
    expected_reason: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    calls = _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    _persist(tmp_path, _profile(status="running", **profile_overrides))

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is False
    assert tick.json()["blocked_reasons"] == [expected_reason]
    assert calls["x"] == []


def test_quiet_hours_active_blocks_and_persists_next_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_environment(monkeypatch, tmp_path)
    _patch_successful_transports(monkeypatch)
    quiet_now = datetime(2026, 5, 20, 7, 0, tzinfo=UTC)
    _set_route_now(monkeypatch, quiet_now)
    _persist(
        tmp_path,
        _profile(
            status="running",
            quiet_hours={"start_hour": 22, "end_hour": 6, "timezone": "America/New_York"},
        ),
    )

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is False
    assert tick.json()["blocked_reasons"] == [AUTONOMY_QUIET_HOURS_ACTIVE]
    persisted = read_social_autonomy_profile(tmp_path)
    assert persisted.next_run_at is not None
    assert persisted.next_run_at >= quiet_now


def test_unreadable_cap_source_fails_closed_before_x_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _prepare_environment(monkeypatch, tmp_path)
    calls = _patch_successful_transports(monkeypatch)
    _set_route_now(monkeypatch, _NOW)
    paths["x_journal"].write_text("{not-json\n", encoding="utf-8")
    _persist(tmp_path, _profile(status="running"))

    tick = _post("/api/social/autonomy/tick")

    assert tick.status_code == 200, tick.text
    assert tick.json()["ran"] is False
    assert tick.json()["blocked_reasons"] == [AUTONOMY_CAP_TRACKING_UNAVAILABLE]
    assert calls["x"] == []
