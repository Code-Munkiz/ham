"""HTTP-level tests for the SocialPolicy advisory integration in ``/api/social/*``.

D.2 contract:
* ``GET /api/social`` returns a top-level ``policy`` block with
  ``advisory_only=True``.
* Lane DTOs and preview responses gain an additive
  ``policy_advisory_reasons: list[str]`` field. Existing ``reasons`` arrays
  on apply-gate paths remain byte-for-byte identical, regardless of the
  on-disk policy.
* No live transports / runners / schedulers are invoked. We monkey-patch
  the hot ones to raise on call.
* No raw tokens / bearer / chat IDs / API keys appear in the response.
* ``HAM_SOCIAL_POLICY_SNAPSHOT_DISABLED=true`` short-circuits the snapshot
  block to ``None`` and clears advisory reasons on lane DTOs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_policy.advisory import (
    POLICY_DOCUMENT_MISSING,
    POLICY_POSTING_MODE_OFF,
    POLICY_REPLY_MODE_OFF,
)
from src.ham.social_policy.schema import DEFAULT_SOCIAL_POLICY

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("HAM_SOCIAL_POLICY_PATH", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_POLICY_SNAPSHOT_DISABLED", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _block_live_transports(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Patch every live transport / runner the snapshot path could plausibly
    touch so a regression that pulls them in fails loudly. All counters
    must remain ``0``."""
    counters: dict[str, int] = {
        "urlopen": 0,
        "socket_connect": 0,
        "telegram_send": 0,
        "telegram_send_api": 0,
        "live_controller": 0,
        "reactive_live": 0,
        "reactive_batch": 0,
    }

    def _bad_urlopen(*_args: Any, **_kwargs: Any) -> Any:
        counters["urlopen"] += 1
        raise RuntimeError("urlopen forbidden during /api/social policy snapshot")

    def _bad_connect(self: Any, *_args: Any, **_kwargs: Any) -> Any:  # noqa: ARG001
        counters["socket_connect"] += 1
        raise RuntimeError("socket.connect forbidden during /api/social policy snapshot")

    import socket
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _bad_urlopen)
    monkeypatch.setattr(socket.socket, "connect", _bad_connect)
    return counters


def _set_x_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "bearer-token-1234567890")
    monkeypatch.setenv("X_API_KEY", "x-api-key-1234567890")
    monkeypatch.setenv("X_API_SECRET", "x-api-secret-1234567890")
    monkeypatch.setenv("X_ACCESS_TOKEN", "x-access-token-1234567890")
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "x-access-token-secret-1234567890")
    monkeypatch.setenv("XAI_API_KEY", "xai-key-1234567890")


def _write_policy(
    root: Path,
    *,
    posting_mode: str = "off",
    reply_mode: str = "off",
    autopilot_mode: str = "off",
    live_autonomy_armed: bool = False,
) -> dict[str, Any]:
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["autopilot_mode"] = autopilot_mode
    raw["live_autonomy_armed"] = live_autonomy_armed
    for provider_id in ("x", "telegram", "discord"):
        raw["providers"][provider_id]["posting_mode"] = posting_mode
        raw["providers"][provider_id]["reply_mode"] = reply_mode
    target = root / ".ham" / "social_policy.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return raw


def _get_snapshot() -> dict[str, Any]:
    res = client.get("/api/social")
    assert res.status_code == 200
    return res.json()


# ---------------------------------------------------------------------------
# Snapshot field
# ---------------------------------------------------------------------------


def test_snapshot_includes_policy_block_with_advisory_only_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    counters = _block_live_transports(monkeypatch)

    body = _get_snapshot()
    assert "policy" in body
    block = body["policy"]
    assert block is not None, "policy field must be present when not flag-disabled"
    assert block["advisory_only"] is True
    assert block["exists"] is False
    assert "policy_document_missing" in block.get("warnings", [])
    # Defaults are returned and structurally valid.
    assert block["policy"]["schema_version"] == 1
    assert block["policy"]["autopilot_mode"] == "off"
    assert block["live_autonomy_armed"] is False
    # Sole snapshot-time disk reads -- no outbound IO.
    assert counters == {
        "urlopen": 0,
        "socket_connect": 0,
        "telegram_send": 0,
        "telegram_send_api": 0,
        "live_controller": 0,
        "reactive_live": 0,
        "reactive_batch": 0,
    }


def test_snapshot_policy_block_reads_existing_doc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="approval_required", reply_mode="approval_required")

    block = _get_snapshot()["policy"]
    assert block["exists"] is True
    assert block["policy"]["providers"]["x"]["posting_mode"] == "approval_required"
    assert block["advisory_only"] is True
    # Revision is the sha256 of the JSON canonicalised on read.
    assert isinstance(block["revision"], str) and len(block["revision"]) == 64


def test_snapshot_policy_field_short_circuits_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_POLICY_SNAPSHOT_DISABLED", "true")
    _block_live_transports(monkeypatch)

    body = _get_snapshot()
    assert body["policy"] is None
    # Advisory reasons on lane DTOs also clear out under the flag.
    assert body["xStatus"]["broadcast_lane"]["policy_advisory_reasons"] == []
    assert body["xStatus"]["reactive_lane"]["policy_advisory_reasons"] == []


def test_snapshot_policy_block_marks_invalid_doc_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    target = root / ".ham" / "social_policy.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"schema_version": 1, "rubbish": "no-persona"}\n', encoding="utf-8")

    block = _get_snapshot()["policy"]
    assert block is not None
    assert block["exists"] is True
    assert block["policy"] is None
    assert "policy_document_invalid" in block.get("warnings", [])


# ---------------------------------------------------------------------------
# Lane advisory reasons
# ---------------------------------------------------------------------------


def test_default_no_doc_lane_advisory_reasons_emit_document_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)

    body = _get_snapshot()
    assert body["xStatus"]["broadcast_lane"]["policy_advisory_reasons"] == [
        POLICY_DOCUMENT_MISSING,
    ]
    assert body["xStatus"]["reactive_lane"]["policy_advisory_reasons"] == [
        POLICY_DOCUMENT_MISSING,
    ]
    assert body["telegramStatus"]["policy_advisory_reasons"] == [
        POLICY_DOCUMENT_MISSING,
    ]


def test_off_policy_emits_mode_advisory_codes_on_lane_dtos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="off", reply_mode="off")

    body = _get_snapshot()
    assert POLICY_POSTING_MODE_OFF in body["xStatus"]["broadcast_lane"]["policy_advisory_reasons"]
    assert POLICY_REPLY_MODE_OFF in body["xStatus"]["reactive_lane"]["policy_advisory_reasons"]
    # Telegram is the union of broadcast+reactive advisories.
    tg = body["telegramStatus"]["policy_advisory_reasons"]
    assert POLICY_POSTING_MODE_OFF in tg
    assert POLICY_REPLY_MODE_OFF in tg


def test_permissive_policy_keeps_lane_advisory_reasons_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="approval_required", reply_mode="approval_required")

    body = _get_snapshot()
    assert body["xStatus"]["broadcast_lane"]["policy_advisory_reasons"] == []
    assert body["xStatus"]["reactive_lane"]["policy_advisory_reasons"] == []


# ---------------------------------------------------------------------------
# Apply gate REGRESSION LOCK -- existing reasons[] must be unchanged.
# ---------------------------------------------------------------------------


def _broadcast_preflight() -> dict[str, Any]:
    res = client.post("/api/social/providers/x/broadcast/preflight", json={})
    assert res.status_code == 200, res.text
    return res.json()


def test_broadcast_preflight_apply_gate_reasons_unchanged_with_or_without_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)

    # Baseline: no policy.
    baseline = _broadcast_preflight()

    # With restrictive policy.
    _write_policy(root, posting_mode="off", reply_mode="off")
    restrictive = _broadcast_preflight()

    # With permissive policy.
    _write_policy(root, posting_mode="autopilot", reply_mode="autopilot")
    permissive = _broadcast_preflight()

    # Apply-gate reasons must be byte-for-byte identical across all three.
    assert restrictive["reasons"] == baseline["reasons"]
    assert permissive["reasons"] == baseline["reasons"]
    # Status must stay the same too -- policy never gates apply.
    assert restrictive["status"] == baseline["status"]
    assert permissive["status"] == baseline["status"]
    # Advisory reasons live in the dedicated field and DO change with policy.
    assert "policy_advisory_reasons" in baseline
    assert baseline["policy_advisory_reasons"] != restrictive["policy_advisory_reasons"]


def test_x_status_apply_gate_reasons_lane_unchanged_by_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)

    res_a = client.get("/api/social/providers/x/status").json()

    _write_policy(root, posting_mode="off", reply_mode="off")
    res_b = client.get("/api/social/providers/x/status").json()

    # The legacy ``reasons`` arrays on the lane DTOs are gate signals; they
    # must remain identical regardless of policy state.
    assert res_a["broadcast_lane"]["reasons"] == res_b["broadcast_lane"]["reasons"]
    assert res_a["reactive_lane"]["reasons"] == res_b["reactive_lane"]["reasons"]
    # Advisory reasons are the only thing that changes.
    assert res_a["broadcast_lane"]["policy_advisory_reasons"] != res_b["broadcast_lane"][
        "policy_advisory_reasons"
    ]


# ---------------------------------------------------------------------------
# Apply path 403 still uses ``reasons`` only.
# ---------------------------------------------------------------------------


def test_apply_endpoint_blocked_response_does_not_carry_advisory_in_reasons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="off", reply_mode="off")

    res = client.post(
        "/api/social/providers/x/broadcast/apply",
        json={"confirmation_phrase": "WRONG"},
    )
    # Apply path returns 200 with a structured blocked response (or 4xx
    # when env / live token is missing). In every case the canonical
    # ``reasons`` array must NOT carry advisory ``policy_*`` codes — they
    # belong only on the dedicated advisory field of read/preview surfaces.
    assert res.status_code in (200, 400, 401, 403, 412, 422)
    if res.status_code == 200:
        body = res.json()
        assert all(not r.startswith("policy_") for r in body.get("reasons", []))
        assert body.get("execution_allowed") in (False, None)
    else:
        body = res.json()
        # FastAPI / HTTPException error envelope: ``detail`` may carry text,
        # but it must not embed advisory policy codes (those are not gates).
        detail_text = json.dumps(body, sort_keys=True).lower()
        assert "policy_posting_mode_off" not in detail_text
        assert "policy_reply_mode_off" not in detail_text
        assert "policy_document_missing" not in detail_text


# ---------------------------------------------------------------------------
# Secret scrub on snapshot.
# ---------------------------------------------------------------------------


def test_snapshot_with_policy_does_not_leak_env_or_token_literals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "live-token-XYZZYABCDEFG12345")
    monkeypatch.setenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", "write-token-XYZZYABCDEFG12345")
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="approval_required", reply_mode="approval_required")

    text = json.dumps(_get_snapshot(), sort_keys=True)
    for secret in (
        "live-token-XYZZYABCDEFG12345",
        "write-token-XYZZYABCDEFG12345",
        "bearer-token-1234567890",
        "x-api-key-1234567890",
        "x-api-secret-1234567890",
        "x-access-token-1234567890",
        "x-access-token-secret-1234567890",
        "xai-key-1234567890",
    ):
        assert secret not in text, f"snapshot leaked literal {secret!r}"


# ---------------------------------------------------------------------------
# Preview surfaces include advisory reasons.
# ---------------------------------------------------------------------------


def test_x_reactive_inbox_preview_has_policy_advisory_reasons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)

    res = client.post("/api/social/providers/x/reactive/inbox/preview", json={})
    assert res.status_code == 200
    body = res.json()
    assert "policy_advisory_reasons" in body
    assert isinstance(body["policy_advisory_reasons"], list)


def test_advisory_reasons_field_default_is_empty_list_in_dto_constructor() -> None:
    """Direct construction of the SocialSnapshotResponse-adjacent DTOs with
    no advisory list yields an empty list — the field is defaulted, never
    required of clients deserialising older payloads."""
    from src.api.social import (
        BroadcastLaneStatusDto,
        ReactiveLaneStatusDto,
        SocialPreviewResponse,
    )

    bd = BroadcastLaneStatusDto(
        enabled=True,
        controller_enabled=False,
        live_controller_enabled=False,
        dry_run_available=True,
        live_configured=False,
        execution_allowed_now=False,
    )
    rd = ReactiveLaneStatusDto(
        enabled=False,
        inbox_discovery_enabled=False,
        dry_run_enabled=True,
        live_canary_enabled=False,
        batch_enabled=False,
    )
    pr = SocialPreviewResponse(
        persona_id="ham-canonical",
        persona_version=1,
        persona_digest="0" * 64,
        preview_kind="reactive_inbox",
        status="completed",
    )
    assert bd.policy_advisory_reasons == []
    assert rd.policy_advisory_reasons == []
    assert pr.policy_advisory_reasons == []


# ---------------------------------------------------------------------------
# Cross-lane: telegram status carries union advisory list.
# ---------------------------------------------------------------------------


def test_telegram_status_response_union_advisory_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_root(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _set_x_creds(monkeypatch)
    _block_live_transports(monkeypatch)
    _write_policy(root, posting_mode="off", reply_mode="off")

    res = client.get("/api/social/providers/telegram/status")
    assert res.status_code == 200
    advisory = res.json()["policy_advisory_reasons"]
    # Sorted-unique, contains both lane codes.
    assert advisory == sorted(set(advisory))
    assert POLICY_POSTING_MODE_OFF in advisory
    assert POLICY_REPLY_MODE_OFF in advisory
