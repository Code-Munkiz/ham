"""Read-only API for the Coding Agents Control Plane provider/capability registry."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.harness_capabilities import (
    HARNESS_CAPABILITIES,
    IMPLEMENTED_PROVIDERS,
    PLANNED_CANDIDATE_PROVIDERS,
)

EXPECTED_PROVIDER_KEYS = {
    "cursor_cloud_agent",
    "factory_droid",
    "claude_code",
    "claude_agent",
    "opencode_cli",
}

PUBLIC_FIELDS = {
    "provider",
    "display_name",
    "implemented",
    "registry_status",
    "supports_operator_preview",
    "supports_operator_launch",
    "launchable",
    "audit_sink",
    "harness_family",
    "topology_note",
}

NON_PUBLIC_FIELDS = {
    "digest_family",
    "base_revision_source",
    "status_mapping",
    "requires_local_root",
    "requires_remote_repo",
    "returns_stable_external_id",
    "requires_provider_side_auth",
    "supports_status_poll",
    "supports_follow_up",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_providers_returns_all_five_known_keys(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "coding_agent_provider_list"
    assert body["count"] == 5
    keys = {p["provider"] for p in body["providers"]}
    assert keys == EXPECTED_PROVIDER_KEYS


def test_list_providers_is_stable_sorted(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers")
    assert res.status_code == 200
    keys = [p["provider"] for p in res.json()["providers"]]
    assert keys == sorted(EXPECTED_PROVIDER_KEYS)


def test_list_providers_only_emits_public_fields(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers")
    assert res.status_code == 200
    for row in res.json()["providers"]:
        assert set(row.keys()) == PUBLIC_FIELDS, row
        for forbidden in NON_PUBLIC_FIELDS:
            assert forbidden not in row, (forbidden, row)


def test_implemented_providers_are_implemented_and_launchable(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers")
    rows = {p["provider"]: p for p in res.json()["providers"]}
    for key in ("cursor_cloud_agent", "factory_droid"):
        assert rows[key]["implemented"] is True, key
        assert rows[key]["registry_status"] == "implemented", key
        assert rows[key]["launchable"] is True, key
        assert rows[key]["supports_operator_launch"] is True, key
        assert rows[key]["audit_sink"] in ("cursor_jsonl", "droid_jsonl"), key


def test_planned_candidates_are_not_implemented_and_not_launchable(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers")
    rows = {p["provider"]: p for p in res.json()["providers"]}
    for key in ("claude_code", "opencode_cli"):
        assert rows[key]["implemented"] is False, key
        assert rows[key]["registry_status"] == "planned_candidate", key
        assert rows[key]["launchable"] is False, key
        assert rows[key]["audit_sink"] is None, key
        assert rows[key]["harness_family"] == "local_cli_planned", key


def test_launchable_set_matches_implemented_and_supports_launch(client: TestClient) -> None:
    """Cross-check the API result against the in-process registry invariant."""
    res = client.get("/api/coding-agents/providers")
    api_launchable = {p["provider"] for p in res.json()["providers"] if p["launchable"]}
    expected = {
        k for k in IMPLEMENTED_PROVIDERS
        if HARNESS_CAPABILITIES[k].supports_operator_launch
    }
    assert api_launchable == expected
    # Sanity: planned candidates are never launchable per the API.
    for key in PLANNED_CANDIDATE_PROVIDERS:
        assert key not in api_launchable, key


def test_get_provider_cursor_cloud_agent(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers/cursor_cloud_agent")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "coding_agent_provider"
    p = body["provider"]
    assert p["provider"] == "cursor_cloud_agent"
    assert p["implemented"] is True
    assert p["launchable"] is True
    assert set(p.keys()) == PUBLIC_FIELDS


def test_get_provider_planned_candidate(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers/claude_code")
    assert res.status_code == 200, res.text
    p = res.json()["provider"]
    assert p["registry_status"] == "planned_candidate"
    assert p["launchable"] is False
    assert p["audit_sink"] is None


def test_get_provider_unknown_returns_404(client: TestClient) -> None:
    res = client.get("/api/coding-agents/providers/nope_harness")
    assert res.status_code == 404
    body = res.json()
    assert body["detail"]["error"]["code"] == "CODING_AGENT_PROVIDER_NOT_FOUND"


def test_get_provider_strips_leading_trailing_whitespace(client: TestClient) -> None:
    """The router must accept a trimmed key (mirrors get_harness_capability semantics)."""
    res = client.get("/api/coding-agents/providers/%20cursor_cloud_agent%20")
    assert res.status_code == 200
    assert res.json()["provider"]["provider"] == "cursor_cloud_agent"


def test_list_requires_clerk_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When HAM_CLERK_REQUIRE_AUTH is on, list endpoint must 401 without Authorization header."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

    c = TestClient(app)
    res = c.get("/api/coding-agents/providers")

    assert res.status_code == 401, res.text
    body = res.json()
    assert body["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_get_requires_clerk_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same Clerk-gate semantics on the single-provider endpoint."""
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

    c = TestClient(app)
    res = c.get("/api/coding-agents/providers/cursor_cloud_agent")

    assert res.status_code == 401, res.text
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
