"""HTTP contract tests for POST /api/social/autonomy/scheduled-tick.

Covers all VAL-M15-M4-SCHEDULER-*, VAL-M15-M4-OIDC-*, VAL-M15-M4-BEARER-*,
VAL-M15-M4-INTERLOCK-* and VAL-M15-CROSS-SCHEDULER-E2E-001 assertions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_autonomy.schema import GoHamSocialProfile
from src.ham.social_autonomy.store import save_profile
from src.ham.social_autonomy.tick import (
    AUTONOMY_EMERGENCY_STOP,
    SocialAutonomyTickResult,
)
from src.ham.social_scheduler_state_store import (
    SocialSchedulerStateFileStore,
    set_social_scheduler_state_store_for_tests,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SYNTHETIC_SA = "scheduler-sa@clarity-staging-488201.iam.gserviceaccount.com"
_SYNTHETIC_AUD = "https://goham.space/api/social/autonomy/scheduled-tick"
_SYNTHETIC_BEARER = "synthetic-scheduler-bearer-token-XYZ"


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate filesystem + scheduler envs for one test."""
    target = tmp_path / "social_autonomy.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_PATH", str(target))
    # Clear scheduler envs by default
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    return target


def _enable_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED", "true")


def _set_oidc_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT", _SYNTHETIC_SA)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE", _SYNTHETIC_AUD)


def _set_bearer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN", _SYNTHETIC_BEARER)


def _bearer_headers(token: str = _SYNTHETIC_BEARER) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _xham_bearer_headers(token: str = _SYNTHETIC_BEARER) -> dict[str, str]:
    return {"X-Ham-Operator-Authorization": f"Bearer {token}"}


def _oidc_headers(token: str = "fake.oidc.jwt") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _stamp() -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _profile_payload(**overrides: Any) -> dict[str, Any]:
    stamp = _stamp()
    payload: dict[str, Any] = {
        "profile_id": "scheduler-test-profile",
        "status": "running",
        "goal": "Grow HAM safely.",
        "persona_id": "ham-canonical",
        "channels": {
            "x": {"enabled": False, "available": False},
            "telegram": {"enabled": True, "available": True},
            "discord": {"enabled": False, "available": False},
        },
        "actions_allowed_per_channel": {
            "x": [],
            "telegram": ["message", "activity"],
            "discord": [],
        },
        "daily_caps": {"x": 0, "telegram": 5, "discord": 0},
        "cadence": "manual",
        "quiet_hours": None,
        "forbidden_topics": [],
        "safety_rules": [],
        "learning_enabled": False,
        "emergency_stop": False,
        "created_at": stamp,
        "updated_at": stamp,
    }
    payload.update(overrides)
    return payload


def _write_profile(path: Path, **overrides: Any) -> GoHamSocialProfile:
    profile = GoHamSocialProfile.model_validate(_profile_payload(**overrides))
    save_profile(path.parent, profile, actor="test")
    return profile


def _mock_tick_result(dry_run: bool = True) -> SocialAutonomyTickResult:
    return SocialAutonomyTickResult(
        ran=False,
        dry_run=dry_run,
        actions_considered=[],
        actions_taken=[],
        blocked_reasons=[],
        next_run_summary=None,
        profile_status="running",
    )


def _fake_oidc_payload(
    email: str = _SYNTHETIC_SA,
    aud: str = _SYNTHETIC_AUD,
    iss: str = "https://accounts.google.com",
) -> dict[str, Any]:
    return {"iss": iss, "aud": aud, "email": email, "sub": "123"}


# ---------------------------------------------------------------------------
# VAL-M15-M4-SCHEDULER-001: Route disabled by default → 503 AUTONOMY_SCHEDULER_DISABLED
# ---------------------------------------------------------------------------


def test_scheduler_route_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-SCHEDULER-001: No scheduler envs → 503 AUTONOMY_SCHEDULER_DISABLED."""
    _isolate(monkeypatch, tmp_path)
    resp = client.post("/api/social/autonomy/scheduled-tick", json={})
    assert resp.status_code == 503
    body = resp.json()
    # FastAPI wraps HTTPException.detail under "detail" key
    assert body["detail"]["error"]["code"] == "AUTONOMY_SCHEDULER_DISABLED"


def test_scheduler_route_disabled_returns_503_regardless_of_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-SCHEDULER-001: Disabled endpoint 503s even with valid token."""
    _isolate(monkeypatch, tmp_path)
    _set_bearer_env(monkeypatch)  # bearer configured but scheduler not enabled
    resp = client.post(
        "/api/social/autonomy/scheduled-tick",
        json={},
        headers=_bearer_headers(),
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "AUTONOMY_SCHEDULER_DISABLED"


# ---------------------------------------------------------------------------
# VAL-M15-M4-SCHEDULER-002: Route lives in its own module (static grep test)
# ---------------------------------------------------------------------------


def test_scheduler_route_in_own_module() -> None:
    """VAL-M15-M4-SCHEDULER-002: Handler registered from social_scheduler.py."""
    import pathlib

    scheduler_src = pathlib.Path("src/api/social_scheduler.py").read_text(encoding="utf-8")
    # Ensure @router.post("/autonomy/scheduled-tick") is in the module
    assert (
        '"/autonomy/scheduled-tick"' in scheduler_src
        or "'/autonomy/scheduled-tick'" in scheduler_src
    )

    social_src = pathlib.Path("src/api/social.py").read_text(encoding="utf-8")
    # Ensure the handler is NOT in social.py
    assert "scheduled-tick" not in social_src


def test_scheduler_router_registered_on_app() -> None:
    """VAL-M15-M4-SCHEDULER-002: Router is reachable on the FastAPI app."""
    # server.py wraps FastAPI in middleware: `app = middleware(fastapi_app)`.
    # Import fastapi_app directly for route introspection.
    from src.api.server import fastapi_app

    routes = [r.path for r in fastapi_app.routes if hasattr(r, "path")]
    assert "/api/social/autonomy/scheduled-tick" in routes


# ---------------------------------------------------------------------------
# VAL-M15-M4-SCHEDULER-003: Existing /tick route untouched
# ---------------------------------------------------------------------------


def test_existing_tick_route_still_requires_clerk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-SCHEDULER-003: POST /autonomy/tick still requires Clerk session."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    resp = client.post("/api/social/autonomy/tick", json={})
    assert resp.status_code == 401
    assert "CLERK_SESSION_REQUIRED" in resp.text


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-001: Valid OIDC token + correct audience + allowlisted SA → 200
# ---------------------------------------------------------------------------


def test_oidc_valid_token_returns_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-OIDC-001: Valid OIDC token → 200."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result(dry_run=True)

    with (
        patch(
            "google.oauth2.id_token.verify_oauth2_token",
            return_value=_fake_oidc_payload(),
        ),
        patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-002: Missing bearer header → 401
# ---------------------------------------------------------------------------


def test_oidc_missing_auth_header_returns_401(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-OIDC-002: No Authorization header → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)
    resp = client.post("/api/social/autonomy/scheduled-tick", json={})
    assert resp.status_code == 401
    body = resp.json()
    assert "SCHEDULED_TICK_TOKEN_MISSING" in body["detail"]["error"]["code"]


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-003: Wrong audience → 401
# ---------------------------------------------------------------------------


def test_oidc_wrong_audience_returns_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-OIDC-003: Token with wrong aud → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)

    wrong_aud_payload = _fake_oidc_payload(aud="https://wrong.example/aud")

    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=wrong_aud_payload,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-004: Non-allowlisted service account email → 401
# ---------------------------------------------------------------------------


def test_oidc_non_allowlisted_sa_returns_401(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-OIDC-004: Verified token but wrong SA email → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)

    rogue_payload = _fake_oidc_payload(email="rogue-sa@attacker.iam.gserviceaccount.com")

    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=rogue_payload,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-005: Malformed / unverifiable JWT → 401; runner not invoked
# ---------------------------------------------------------------------------


def test_oidc_malformed_jwt_returns_401_no_runner_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-OIDC-005: verify_oauth2_token raises → 401; tick not called."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)

    tick_mock = Mock(side_effect=AssertionError("tick must not be called"))

    with (
        patch(
            "google.oauth2.id_token.verify_oauth2_token",
            side_effect=ValueError("Invalid token"),
        ),
        patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_mock),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers("not.a.real.jwt"),
        )
    assert resp.status_code == 401
    tick_mock.assert_not_called()


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-006: Issuer must be a Google issuer
# ---------------------------------------------------------------------------


def test_oidc_wrong_issuer_returns_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-OIDC-006: Non-Google issuer → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)

    bad_issuer_payload = _fake_oidc_payload(iss="https://attacker.example/")

    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=bad_issuer_payload,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# VAL-M15-M4-OIDC-007: google.auth runtime missing → 503
# ---------------------------------------------------------------------------


def test_oidc_runtime_missing_returns_503(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-OIDC-007: google.auth unavailable → 503 SCHEDULED_TICK_AUTH_RUNTIME_MISSING."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)

    with patch(
        "src.api.social_scheduler._verify_google_oidc_token",
        side_effect=__import__("fastapi").HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_AUTH_RUNTIME_MISSING",
                    "message": "google-auth runtime is required for OIDC verification.",
                }
            },
        ),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "SCHEDULED_TICK_AUTH_RUNTIME_MISSING"


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-001: Valid HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN bearer → 200
# ---------------------------------------------------------------------------


def test_bearer_valid_token_returns_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-BEARER-001: Valid shared bearer → 200."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()

    with patch(
        "src.ham.social_autonomy.tick.run_social_autonomy_tick",
        return_value=mock_result,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-002: Invalid shared-bearer → 401
# ---------------------------------------------------------------------------


def test_bearer_invalid_token_returns_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """VAL-M15-M4-BEARER-002: Wrong bearer value → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    resp = client.post(
        "/api/social/autonomy/scheduled-tick",
        json={},
        headers=_bearer_headers("wrong-token"),
    )
    assert resp.status_code == 401
    assert "SCHEDULED_TICK_TOKEN_INVALID" in resp.json()["detail"]["error"]["code"]


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-003: Missing bearer when shared-token mode → 401
# ---------------------------------------------------------------------------


def test_bearer_missing_header_in_bearer_mode_returns_401(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-BEARER-003: No Authorization header in bearer mode → 401."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    resp = client.post("/api/social/autonomy/scheduled-tick", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-004: Constant-time comparison (hmac.compare_digest)
# ---------------------------------------------------------------------------


def test_bearer_uses_hmac_compare_digest() -> None:
    """VAL-M15-M4-BEARER-004: hmac.compare_digest referenced in social_scheduler.py."""
    import pathlib

    src = pathlib.Path("src/api/social_scheduler.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src
    # Ensure plain == of token against env value does not appear
    # (Simple static check that compare_digest is used for token comparison)
    assert "compare_digest" in src


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-005: OIDC + bearer simultaneously configured → both paths accepted
# ---------------------------------------------------------------------------


def test_oidc_and_bearer_both_configured_oidc_path_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-BEARER-005(a): Both configured, valid OIDC → 200."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()

    with (
        patch(
            "google.oauth2.id_token.verify_oauth2_token",
            return_value=_fake_oidc_payload(),
        ),
        patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers("valid.oidc.jwt"),
        )
    assert resp.status_code == 200


def test_oidc_and_bearer_both_configured_bearer_path_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-BEARER-005(b): Both configured, valid bearer (OIDC fails) → 200."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()

    # OIDC verification fails (bearer token is not an OIDC JWT)
    with (
        patch(
            "google.oauth2.id_token.verify_oauth2_token",
            side_effect=ValueError("Not an OIDC token"),
        ),
        patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(_SYNTHETIC_BEARER),
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VAL-M15-M4-BEARER-006: Bearer accepted on X-Ham-Operator-Authorization
# ---------------------------------------------------------------------------


def test_bearer_accepted_on_x_ham_operator_authorization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-BEARER-006: X-Ham-Operator-Authorization preferred over Authorization."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()

    with patch(
        "src.ham.social_autonomy.tick.run_social_autonomy_tick",
        return_value=mock_result,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_xham_bearer_headers(_SYNTHETIC_BEARER),
        )
    assert resp.status_code == 200


def test_x_ham_operator_authorization_preferred_over_authorization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-BEARER-006: X-Ham-Operator-Authorization wins when both present."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()

    with patch(
        "src.ham.social_autonomy.tick.run_social_autonomy_tick",
        return_value=mock_result,
    ):
        # X-Ham has correct token; Authorization has wrong token
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers={
                "Authorization": "Bearer wrong-token",
                "X-Ham-Operator-Authorization": f"Bearer {_SYNTHETIC_BEARER}",
            },
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-001: Default body resolves dry_run=True
# ---------------------------------------------------------------------------


def test_interlock_default_body_dry_run_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-001: Empty body → dry_run=True passed to runner."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    tick_spy = Mock(return_value=_mock_tick_result(dry_run=True))

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs["dry_run"] is True
    assert resp.json()["dry_run"] is True


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-002: DRY_RUN env != "false" forces dry_run=True
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dry_run_env_val", ["true", "True", "1", "0", "", "yes"])
def test_interlock_dry_run_env_not_false_forces_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dry_run_env_val: str,
) -> None:
    """VAL-M15-M4-INTERLOCK-002: DRY_RUN env != "false" → dry_run=True regardless of body."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", dry_run_env_val)
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "some-token")
    _write_profile(tmp_path / "social_autonomy.json")

    tick_spy = Mock(return_value=_mock_tick_result(dry_run=True))

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={"dry_run": False},  # body says live but env overrides
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs["dry_run"] is True


def test_interlock_dry_run_env_unset_body_false_forces_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-002: DRY_RUN env unset + body dry_run=false → forced True."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    # DRY_RUN env not set → not "false"
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "some-token")
    _write_profile(tmp_path / "social_autonomy.json")

    tick_spy = Mock(return_value=_mock_tick_result(dry_run=True))

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={"dry_run": False},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs["dry_run"] is True


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-003: Live mode requires full triple env
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dry_run_false,token",
    [
        # One of two missing (ENABLED is always true — route gate guarantees it)
        (True, False),  # DRY_RUN=false, TOKEN missing
        (False, True),  # DRY_RUN not false, TOKEN set
        # Both missing
        (False, False),  # Neither set
    ],
)
def test_interlock_missing_any_env_forces_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dry_run_false: bool,
    token: bool,
) -> None:
    """VAL-M15-M4-INTERLOCK-003: Missing DRY_RUN=false or TOKEN → dry_run=True."""
    _isolate(monkeypatch, tmp_path)
    # Scheduler must be enabled for the route to be reachable
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED", "true")
    _set_bearer_env(monkeypatch)

    if dry_run_false:
        monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", "false")
    else:
        monkeypatch.delenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", raising=False)

    if token:
        monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "live-token-XYZ")
    else:
        monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)

    _write_profile(tmp_path / "social_autonomy.json")
    tick_spy = Mock(return_value=_mock_tick_result(dry_run=True))

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={"dry_run": False},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs["dry_run"] is True


def test_interlock_all_three_envs_present_allows_live_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-003: All three envs set + body dry_run=false → live mode."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", "false")
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "live-token-XYZ")
    _write_profile(tmp_path / "social_autonomy.json")

    tick_spy = Mock(return_value=_mock_tick_result(dry_run=False))

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={"dry_run": False},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs["dry_run"] is False


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-004: Live mode does not bypass autonomy tick gates
# ---------------------------------------------------------------------------


def test_interlock_live_mode_respects_emergency_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-004: Even with triple env, emergency_stop blocks the tick."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    monkeypatch.setenv("HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN", "false")
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", "live-token-XYZ")
    _write_profile(tmp_path / "social_autonomy.json", emergency_stop=True)

    # Don't mock run_social_autonomy_tick — let it run for real
    # with the emergency stop profile
    resp = client.post(
        "/api/social/autonomy/scheduled-tick",
        json={"dry_run": False},
        headers=_bearer_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran"] is False
    assert AUTONOMY_EMERGENCY_STOP in body["blocked_reasons"]


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-005: Audit envelope uses distinguishing actor
# ---------------------------------------------------------------------------


def test_interlock_audit_actor_is_scheduled_tick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-005: save_profile called with actor='social-autonomy-scheduled-tick'."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    save_spy = Mock(wraps=save_profile)

    with patch(
        "src.ham.social_autonomy.store.SocialAutonomyFileStore.save",
        save_spy,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    # Verify save_profile was called with the distinguishing actor
    calls = save_spy.call_args_list
    assert any(
        call.kwargs.get("actor") == "social-autonomy-scheduled-tick"
        or (len(call.args) >= 3 and call.args[2] == "social-autonomy-scheduled-tick")
        for call in calls
    ), f"Expected actor='social-autonomy-scheduled-tick' in save_profile calls. Got: {calls}"


# ---------------------------------------------------------------------------
# VAL-M15-M4-INTERLOCK-006: Scheduler-state store updated on each tick
# ---------------------------------------------------------------------------


def test_interlock_scheduler_state_store_updated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-006: After tick, state store has last_scheduled_tick_at + summary."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    # Use a real file store backed by tmp_path
    state_store = SocialSchedulerStateFileStore(tmp_path / "scheduler_state.json")
    set_social_scheduler_state_store_for_tests(state_store)

    try:
        mock_result = _mock_tick_result()
        with patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/social/autonomy/scheduled-tick",
                json={},
                headers=_bearer_headers(),
            )
        assert resp.status_code == 200

        # Verify state store was updated
        state = state_store.read_state()
        assert state.last_scheduled_tick_at is not None
        assert state.last_tick_summary is not None

        # Verify no secrets in snapshot
        snapshot_json = json.dumps(state.last_tick_summary)
        assert "TELEGRAM_BOT_TOKEN" not in snapshot_json
        assert "HAM_SOCIAL_LIVE_APPLY_TOKEN" not in snapshot_json
    finally:
        set_social_scheduler_state_store_for_tests(None)


def test_interlock_scheduler_state_store_no_long_numeric_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-M4-INTERLOCK-006: State snapshot contains no 18+-digit sequences."""
    import re

    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    state_store = SocialSchedulerStateFileStore(tmp_path / "scheduler_state2.json")
    set_social_scheduler_state_store_for_tests(state_store)

    try:
        mock_result = _mock_tick_result()
        with patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/social/autonomy/scheduled-tick",
                json={},
                headers=_bearer_headers(),
            )
        assert resp.status_code == 200

        state = state_store.read_state()
        assert state.last_scheduled_tick_at is not None
        snapshot_json = json.dumps(state.last_tick_summary)
        # No 18+ digit sequences
        assert not re.search(r"\d{18,}", snapshot_json), (
            f"18+ digit sequence found in snapshot: {snapshot_json}"
        )
    finally:
        set_social_scheduler_state_store_for_tests(None)


# ---------------------------------------------------------------------------
# VAL-M15-CROSS-SCHEDULER-E2E-001: Endpoint returns 503 by default
# ---------------------------------------------------------------------------


def test_e2e_endpoint_returns_503_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-CROSS-SCHEDULER-E2E-001: Default configuration returns 503."""
    _isolate(monkeypatch, tmp_path)
    resp = client.post("/api/social/autonomy/scheduled-tick", json={})
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "AUTONOMY_SCHEDULER_DISABLED"


def test_e2e_bearer_path_verified_via_local_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-CROSS-SCHEDULER-E2E-001: Bearer path verified locally with mocked verifier."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()
    with patch(
        "src.ham.social_autonomy.tick.run_social_autonomy_tick",
        return_value=mock_result,
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200


def test_e2e_oidc_path_verified_via_local_tests_with_mocked_verifier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """VAL-M15-CROSS-SCHEDULER-E2E-001: OIDC path verified locally with mocked verifier."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_oidc_envs(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    mock_result = _mock_tick_result()
    with (
        patch(
            "google.oauth2.id_token.verify_oauth2_token",
            return_value=_fake_oidc_payload(),
        ),
        patch(
            "src.ham.social_autonomy.tick.run_social_autonomy_tick",
            return_value=mock_result,
        ),
    ):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_oidc_headers(),
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Additional: run_once=True and actor are passed to the runner
# ---------------------------------------------------------------------------


def test_runner_called_with_run_once_true_and_correct_actor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scheduled tick always passes run_once=True and actor='social-autonomy-scheduled-tick'."""
    _isolate(monkeypatch, tmp_path)
    _enable_scheduler(monkeypatch)
    _set_bearer_env(monkeypatch)
    _write_profile(tmp_path / "social_autonomy.json")

    tick_spy = Mock(return_value=_mock_tick_result())

    with patch("src.ham.social_autonomy.tick.run_social_autonomy_tick", tick_spy):
        resp = client.post(
            "/api/social/autonomy/scheduled-tick",
            json={},
            headers=_bearer_headers(),
        )
    assert resp.status_code == 200
    call_kwargs = tick_spy.call_args.kwargs
    assert call_kwargs.get("run_once") is True
    assert call_kwargs.get("actor") == "social-autonomy-scheduled-tick"
