"""POST /api/cursor/managed/deploy-hook — Vercel hook proxy (per-repo + global)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.vercel_project_mapping import VercelHookResolution


def _patch_resolved(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str | None,
    configured: bool = True,
) -> None:
    from src.api import cursor_managed_deploy as m

    monkeypatch.setattr(m, "get_effective_cursor_api_key", lambda: "k")
    monkeypatch.setattr(
        m,
        "cursor_api_get_agent",
        lambda **kw: {"source": {"repository": "https://github.com/x/y"}},
    )
    monkeypatch.setattr(
        m,
        "resolve_vercel_hook_for_agent",
        lambda _a: VercelHookResolution(
            hook_url=url,
            hook_configured=configured and url is not None,
            deploy_hook_env_name="ENV" if url else "ENV",
            repo_key="x/y",
            mapping_tier="mapped" if url else "unavailable",
            used_global_hook_fallback=False,
            fail_closed=url is None,
            message="ok" if url else "no",
            map_load_error=None,
        ),
    )


def test_deploy_hook_status_no_agent_never_exposes_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api import cursor_managed_deploy as m

    monkeypatch.setattr(m, "_vercel_deploy_hook_url", lambda: "https://secret.example/hook")
    c = TestClient(app)
    r = c.get("/api/cursor/managed/deploy-hook")
    assert r.status_code == 200
    j = r.json()
    assert j.get("configured") is True
    assert "secret.example" not in str(j)


def test_trigger_posts_to_hook_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolved(monkeypatch, url="https://api.vercel.com/v1/integrations/test/hook")
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
    c = TestClient(app)
    r = c.post("/api/cursor/managed/deploy-hook", json={"agent_id": "cm_agent_1"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("outcome") == "hook_request_accepted"
    assert len(calls) == 1
    assert j.get("vercel_mapping", {}).get("hook_configured") is True


def test_trigger_returns_unavailable_when_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolved(monkeypatch, url=None, configured=False)
    c = TestClient(app)
    r = c.post("/api/cursor/managed/deploy-hook", json={"agent_id": "a1"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is False
    assert j.get("outcome") == "hook_unavailable"
    assert "vercel_mapping" in j
