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
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_options_preflight_patch_allowed(
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
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"
    assert res.headers.get("access-control-allow-methods", "").find("PATCH") != -1


def test_options_preflight_private_network_access_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Browsers (Chrome) send this preflight for https://* → http://127.0.0.1.
    Without Access-Control-Allow-Private-Network, fetch() fails with 'Failed to fetch'.
    """
    monkeypatch.setenv("HAM_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    monkeypatch.delenv("HAM_CORS_ORIGINS", raising=False)
    import src.api.server as srv

    importlib.reload(srv)
    client = TestClient(srv.app)
    origin = "https://ham-nine-mu.vercel.app"
    res = client.options(
        "/api/workspace/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"
    assert res.headers.get("access-control-allow-private-network", "").lower() == "true"


def test_options_preflight_production_vercel_in_default_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No HAM_CORS env: built-in list still allows the production HAM Vercel origin (local runtime)."""
    monkeypatch.delenv("HAM_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("HAM_CORS_ORIGIN_REGEX", raising=False)
    import src.api.server as srv

    importlib.reload(srv)
    client = TestClient(srv.app)
    origin = "https://ham-nine-mu.vercel.app"
    res = client.options(
        "/api/workspace/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == origin
    assert res.headers.get("access-control-allow-credentials") == "true"
