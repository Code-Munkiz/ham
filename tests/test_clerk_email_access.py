"""HAM defense-in-depth email/domain allowlist for Clerk-authenticated chat."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.clerk_auth import HamActor
from src.ham.clerk_email_access import (
    evaluate_ham_clerk_email_denial_reason,
    require_ham_clerk_email_allowed,
)

client = TestClient(app)


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


@pytest.fixture
def mock_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def test_evaluate_allowed_exact_email_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAILS", "Admin@EXAMPLE.com")
    monkeypatch.delenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", raising=False)
    assert evaluate_ham_clerk_email_denial_reason(_make_actor("admin@example.com")) is None


def test_evaluate_allowed_domain_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.delenv("HAM_CLERK_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "MyCorp.COM, other.org")
    assert evaluate_ham_clerk_email_denial_reason(_make_actor("x@myCorp.com")) is None


def test_evaluate_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAILS", "a@b.c")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "allowed.com")
    assert evaluate_ham_clerk_email_denial_reason(_make_actor("nope@elsewhere.net")) == "disallowed_email_or_domain"


def test_evaluate_missing_email_when_allowlist_nonempty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "corp.test")
    assert evaluate_ham_clerk_email_denial_reason(_make_actor(None)) == "missing_email_claim"


def test_evaluate_empty_allowlists_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.delenv("HAM_CLERK_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", raising=False)
    assert evaluate_ham_clerk_email_denial_reason(_make_actor("a@b.c")) == "no_allowlist_configured"


def test_require_noop_when_enforcement_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    require_ham_clerk_email_allowed(_make_actor("any@where.com"), route="test")


def test_denial_writes_audit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAILS", "only@here.test")
    audit = tmp_path / "a.jsonl"
    monkeypatch.setenv("HAM_OPERATOR_AUDIT_FILE", str(audit))
    with pytest.raises(HTTPException) as ei:
        require_ham_clerk_email_allowed(_make_actor("bad@other.test"), route="unit_test")
    assert ei.value.status_code == 403
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert detail["error"]["code"] == "HAM_EMAIL_RESTRICTION"
    line = audit.read_text(encoding="utf-8").strip().splitlines()[0]
    row = json.loads(line)
    assert row["event"] == "ham_access_denied"
    assert row["denial_reason"] == "disallowed_email_or_domain"
    assert row["clerk_user_id"] == "u1"
    assert row["evaluated_email"] == "bad@other.test"
    assert row["audit_sink"] == "ham_local_jsonl"


def test_chat_403_when_email_not_allowed(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "corp.example")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("user@wrong.example")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"Authorization": "Bearer fake.jwt"},
        )
    assert res.status_code == 403
    body = res.json()
    assert body["detail"]["error"]["code"] == "HAM_EMAIL_RESTRICTION"


def test_chat_ok_when_enforcement_off_without_clerk_headers(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    res = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert res.status_code == 200


def test_chat_ok_allowed_domain(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "good.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("User@GOOD.TEST")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"Authorization": "Bearer fake.jwt"},
        )
    assert res.status_code == 200


def test_models_catalog_403_when_email_not_allowed(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "corp.example")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("user@wrong.example")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.get("/api/models", headers={"Authorization": "Bearer fake.jwt"})
    assert res.status_code == 403
    body = res.json()
    assert body["detail"]["error"]["code"] == "HAM_EMAIL_RESTRICTION"


def test_models_catalog_ok_allowed_domain(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "good.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("User@GOOD.TEST")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.get("/api/models", headers={"Authorization": "Bearer fake.jwt"})
    assert res.status_code == 200
    payload = res.json()
    assert "items" in payload


def test_models_catalog_denial_writes_audit(mock_gateway, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAILS", "only@here.test")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("HAM_OPERATOR_AUDIT_FILE", str(audit))
    actor = _make_actor("bad@other.test")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.get("/api/models", headers={"Authorization": "Bearer fake.jwt"})
    assert res.status_code == 403
    line = audit.read_text(encoding="utf-8").strip().splitlines()[0]
    row = json.loads(line)
    assert row["event"] == "ham_access_denied"
    assert row["denial_reason"] == "disallowed_email_or_domain"
    assert "GET /api/models" in row.get("route", "")


def test_status_unauthenticated_ok_when_enforcement_on(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAILS", "a@b.c")
    res = client.get("/api/status")
    assert res.status_code == 200


def test_clerk_access_probe_403_when_email_not_allowed(mock_gateway, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", "true")
    monkeypatch.setenv("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", "corp.example")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    actor = _make_actor("user@wrong.example")
    with patch("src.api.clerk_gate.verify_clerk_session_jwt", return_value=actor):
        res = client.get("/api/clerk-access-probe", headers={"Authorization": "Bearer fake.jwt"})
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "HAM_EMAIL_RESTRICTION"
