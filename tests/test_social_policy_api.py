"""HTTP-level tests for ``/api/social/policy/*``."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.social_policy import APPLY_CONFIRMATION_PHRASE, ROLLBACK_CONFIRMATION_PHRASE
from src.ham.social_policy.schema import DEFAULT_SOCIAL_POLICY

client = TestClient(app)


# Test placeholders only; these are *not* credentials. The auth layer
# compares against the HAM_SOCIAL_POLICY_WRITE_TOKEN env, so any
# deterministic literal we set in both places will satisfy the check.
_TOKEN = "changeme-write"  # noqa: S105
_LIVE_TOKEN = "changeme-live"  # noqa: S105


def _disable_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)


def _isolate_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("HAM_SOCIAL_POLICY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _disable_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)


def _enable_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", _TOKEN)


def _enable_live_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", _LIVE_TOKEN)


def _baseline_changes() -> dict[str, Any]:
    return {"changes": {"policy": DEFAULT_SOCIAL_POLICY.model_dump(mode="json")}}


def test_get_policy_returns_default_when_no_doc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _disable_token(monkeypatch)

    res = client.get("/api/social/policy")
    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is False
    assert body["writes_enabled"] is False
    assert body["live_apply_token_present"] is False
    assert body["policy"]["schema_version"] == 1
    assert body["policy"]["autopilot_mode"] == "off"
    assert "revision" in body and len(body["revision"]) == 64
    assert body["read_only"] is True


def test_preview_returns_diff_and_proposal_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _disable_token(monkeypatch)

    payload = _baseline_changes()
    res = client.post("/api/social/policy/preview", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert "proposal_digest" in body and len(body["proposal_digest"]) == 64
    assert "base_revision" in body
    assert body["live_autonomy_change"] is False
    assert (
        "no_existing_policy_document_first_apply_will_create_one" in body["warnings"]
    )


def test_apply_blocked_without_write_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _disable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_WRITES_DISABLED"


def test_apply_requires_bearer_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_AUTH_REQUIRED"


def test_apply_rejects_wrong_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_AUTH_INVALID"


def test_apply_rejects_wrong_phrase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": "DO IT",
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_PHRASE_INVALID"


def test_apply_succeeds_with_token_and_phrase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "backup_id" in body
    assert "audit_id" in body
    assert body["live_autonomy_change"] is False
    assert (root / ".ham" / "social_policy.json").is_file()


def test_apply_409_on_revision_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    headers = {"Authorization": f"Bearer {_TOKEN}"}
    apply_body = {
        **_baseline_changes(),
        "base_revision": pre["base_revision"],
        "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
    }
    first = client.post("/api/social/policy/apply", json=apply_body, headers=headers)
    assert first.status_code == 200
    # Second apply uses the *stale* revision -> 409.
    second = client.post("/api/social/policy/apply", json=apply_body, headers=headers)
    assert second.status_code == 409
    assert second.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_REVISION_CONFLICT"


def test_apply_live_autonomy_blocked_without_live_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)

    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["autopilot_mode"] = "armed"
    raw["live_autonomy_armed"] = True
    payload = {"changes": {"policy": raw}}

    pre = client.post("/api/social/policy/preview", json=payload).json()
    assert pre["live_autonomy_change"] is True
    res = client.post(
        "/api/social/policy/apply",
        json={
            **payload,
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
            "live_autonomy_phrase": "ARM SOCIAL AUTONOMY",
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_LIVE_AUTONOMY_DISABLED"


def test_apply_live_autonomy_blocked_without_live_phrase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)
    _enable_live_token(monkeypatch)

    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["autopilot_mode"] = "armed"
    raw["live_autonomy_armed"] = True
    payload = {"changes": {"policy": raw}}

    pre = client.post("/api/social/policy/preview", json=payload).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **payload,
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
            # no live_autonomy_phrase
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 403
    assert (
        res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_LIVE_AUTONOMY_PHRASE_INVALID"
    )


def test_apply_live_autonomy_succeeds_with_both_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)
    _enable_live_token(monkeypatch)

    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["autopilot_mode"] = "armed"
    raw["live_autonomy_armed"] = True
    payload = {"changes": {"policy": raw}}

    pre = client.post("/api/social/policy/preview", json=payload).json()
    res = client.post(
        "/api/social/policy/apply",
        json={
            **payload,
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
            "live_autonomy_phrase": "ARM SOCIAL AUTONOMY",
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["live_autonomy_change"] is True


def test_rollback_requires_token_and_phrase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    # First apply a baseline so we have a backup to roll back.
    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    apply_res = client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    ).json()

    # No phrase -> 403
    no_phrase = client.post(
        "/api/social/policy/rollback",
        json={"backup_id": apply_res["backup_id"], "confirmation_phrase": "WRONG"},
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert no_phrase.status_code == 403
    assert (
        no_phrase.json()["detail"]["error"]["code"]
        == "SOCIAL_POLICY_ROLLBACK_PHRASE_INVALID"
    )

    # No token -> 401
    no_tok = client.post(
        "/api/social/policy/rollback",
        json={
            "backup_id": apply_res["backup_id"],
            "confirmation_phrase": ROLLBACK_CONFIRMATION_PHRASE,
        },
    )
    assert no_tok.status_code == 401

    # Both supplied -> 200
    ok = client.post(
        "/api/social/policy/rollback",
        json={
            "backup_id": apply_res["backup_id"],
            "confirmation_phrase": ROLLBACK_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert "pre_rollback_backup_id" in body
    assert "audit_id" in body


def test_rollback_404_on_unknown_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)
    res = client.post(
        "/api/social/policy/rollback",
        json={
            "backup_id": "20260503T040000Z_aaaaaaaa",
            "confirmation_phrase": ROLLBACK_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "SOCIAL_POLICY_BACKUP_NOT_FOUND"


def test_rollback_422_on_malformed_backup_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)
    res = client.post(
        "/api/social/policy/rollback",
        json={
            "backup_id": "../etc/passwd",
            "confirmation_phrase": ROLLBACK_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert res.status_code == 422


def test_history_and_audit_are_bounded_lists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    _enable_token(monkeypatch)

    pre = client.post("/api/social/policy/preview", json=_baseline_changes()).json()
    client.post(
        "/api/social/policy/apply",
        json={
            **_baseline_changes(),
            "base_revision": pre["base_revision"],
            "confirmation_phrase": APPLY_CONFIRMATION_PHRASE,
        },
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )

    history = client.get("/api/social/policy/history").json()
    audit = client.get("/api/social/policy/audit").json()
    assert isinstance(history["backups"], list)
    assert isinstance(audit["audits"], list)
    assert len(history["backups"]) >= 1
    assert len(audit["audits"]) >= 1


def test_preview_rejects_extra_unknown_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cwd(monkeypatch, tmp_path)
    _disable_clerk(monkeypatch)
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["unknown_top_level"] = "anything"
    res = client.post(
        "/api/social/policy/preview",
        json={"changes": {"policy": raw}},
    )
    assert res.status_code == 422
