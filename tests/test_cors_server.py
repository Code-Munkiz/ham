"""CORS middleware: optional HAM_CORS_ORIGIN_REGEX for Vercel previews."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def test_options_preflight_vercel_preview_matches_origin_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    monkeypatch.delenv("HAM_CORS_ORIGINS", raising=False)
    import src.api.server as srv

    importlib.reload(srv)
    client = TestClient(srv.app)
    origin = "https://my-preview-abc123.vercel.app"
    res = client.options(
        "/api/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == origin
