"""POST /api/cursor/managed/deploy-hook — Vercel hook proxy (env-gated)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.api import cursor_managed_deploy as m

    monkeypatch.setattr(m, "_vercel_deploy_hook_url", lambda: "https://api.vercel.com/v1/integrations/test/hook")
    return TestClient(app)


def test_deploy_hook_status_never_exposes_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import cursor_managed_deploy as m

    monkeypatch.setattr(m, "_vercel_deploy_hook_url", lambda: "https://secret.example/hook")
    c = TestClient(app)
    r = c.get("/api/cursor/managed/deploy-hook")
    assert r.status_code == 200
    j = r.json()
    assert j.get("configured") is True
    assert "http" not in str(j).lower() or "configured" in j


def test_trigger_posts_to_hook_2xx(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.cursor_managed_deploy as m

    calls: list[str] = []

    class FakeClient:
        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def post(self, url: str) -> object:
            calls.append(url)
            r = MagicMock()
            r.status_code = 201
            r.text = "ok"
            return r

    def fake_client_class(**_kwargs: object) -> FakeClient:
        return FakeClient()

    monkeypatch.setattr(m.httpx, "Client", fake_client_class)
    r = client.post("/api/cursor/managed/deploy-hook", json={"agent_id": "cm_agent_1"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("outcome") == "hook_request_accepted"
    assert len(calls) == 1
    assert "http" in calls[0].lower()


def test_trigger_not_configured_503(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import cursor_managed_deploy as m

    monkeypatch.setattr(m, "_vercel_deploy_hook_url", lambda: None)
    c = TestClient(app)
    r = c.post("/api/cursor/managed/deploy-hook", json={"agent_id": "a"})
    assert r.status_code == 503
    assert "not configured" in (r.json().get("detail") or "").lower()
