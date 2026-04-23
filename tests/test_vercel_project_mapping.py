"""Per-repo Vercel project + deploy hook resolution (no secrets in map)."""
from __future__ import annotations

import os

import pytest

from src.ham import vercel_project_mapping as mp
from src.ham.vercel_project_mapping import (
    normalize_repo_key,
    reset_vercel_project_map_for_tests,
    resolve_vercel_hook_for_agent,
    resolve_vercel_list_for_agent,
    vercel_hook_resolution_to_dict,
    vercel_list_resolution_to_dict,
)


def test_normalize_repo_key() -> None:
    assert normalize_repo_key("https://github.com/Acme/Repo/") == "acme/repo"
    assert normalize_repo_key("acme/Repo") == "acme/repo"


def test_duplicate_repo_rows_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        mp._parse_mapping_payload(  # type: ignore[attr-defined]
            {
                "mappings": [
                    {"repo": "a/b", "project_id": "p1", "deploy_hook_env": "H1"},
                    {"repo": "A/B", "project_id": "p2"},
                ]
            },
            source="t",
        )


def test_list_uses_mapped_project_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_VERCEL_PROJECT_MAP_JSON", raising=False)
    os.environ["HAM_VERCEL_PROJECT_MAP_JSON"] = (
        '{"mappings": [{"repo": "x/y", "project_id": "prj_map", "team_id": "tm_1", "deploy_hook_env": "HOOK_X"}]}'
    )
    os.environ["HAM_VERCEL_API_TOKEN"] = "tok"
    os.environ["HAM_VERCEL_PROJECT_ID"] = "prj_global"
    os.environ["HOOK_X"] = "https://h.example/xx"
    reset_vercel_project_map_for_tests()
    try:
        agent = {"source": {"repository": "https://github.com/x/y"}}
        r = resolve_vercel_list_for_agent(agent)
        assert r.project_id == "prj_map"
        assert r.team_id == "tm_1"
        assert r.mapping_tier == "mapped"
        assert r.repo_key == "x/y"
        ld = vercel_list_resolution_to_dict(r)
        assert ld.get("project_id_used") == "prj_map"
        assert "x/y" in (ld.get("message") or "")

        h = resolve_vercel_hook_for_agent(agent)
        assert h.hook_url == "https://h.example/xx"
        assert h.mapping_tier == "mapped"
        assert h.deploy_hook_env_name == "HOOK_X"
        assert not h.used_global_hook_fallback
        hd = vercel_hook_resolution_to_dict(h)
        assert "https://" not in str(hd)
        assert "HOOK_X" in str(hd)
    finally:
        os.environ.pop("HAM_VERCEL_PROJECT_MAP_JSON", None)
        os.environ.pop("HOOK_X", None)
        reset_vercel_project_map_for_tests()


def test_list_falls_back_global_when_no_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_VERCEL_PROJECT_MAP_JSON", raising=False)
    os.environ["HAM_VERCEL_API_TOKEN"] = "t"
    os.environ["HAM_VERCEL_PROJECT_ID"] = "GLOB"
    reset_vercel_project_map_for_tests()
    try:
        agent = {"source": {"repository": "https://github.com/unknown/zzz"}}
        r = resolve_vercel_list_for_agent(agent)
        assert r.project_id == "GLOB"
        assert r.mapping_tier == "global"
        assert r.use_global_project_fallback is True
    finally:
        reset_vercel_project_map_for_tests()


def test_hook_fail_closed_missing_env_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.environ["HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK"] = "false"
    os.environ["HAM_VERCEL_DEPLOY_HOOK_URL"] = "https://global.hook/ok"
    os.environ["HAM_VERCEL_PROJECT_MAP_JSON"] = (
        '{"mappings": [{"repo": "a/b", "project_id": "p1", "deploy_hook_env": "MISSING_HOOK_ENV"}]}'
    )
    reset_vercel_project_map_for_tests()
    monkeypatch.delenv("MISSING_HOOK_ENV", raising=False)
    try:
        agent = {"source": {"repository": "https://github.com/a/b"}}
        h = resolve_vercel_hook_for_agent(agent)
        assert h.hook_url is None
        assert h.hook_configured is False
        assert h.fail_closed is True
    finally:
        os.environ.pop("HAM_VERCEL_PROJECT_MAP_JSON", None)
        os.environ.pop("HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK", None)
        reset_vercel_project_map_for_tests()


def test_hook_allows_global_when_fallback_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.environ["HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK"] = "true"
    os.environ["HAM_VERCEL_DEPLOY_HOOK_URL"] = "https://global.hook/ok"
    os.environ["HAM_VERCEL_PROJECT_MAP_JSON"] = (
        '{"mappings": [{"repo": "a/b", "project_id": "p1", "deploy_hook_env": "MISSING_HOOK"}]}'
    )
    reset_vercel_project_map_for_tests()
    monkeypatch.delenv("MISSING_HOOK", raising=False)
    try:
        agent = {"source": {"repository": "https://github.com/a/b"}}
        h = resolve_vercel_hook_for_agent(agent)
        assert h.hook_url == "https://global.hook/ok"
        assert h.used_global_hook_fallback is True
    finally:
        os.environ.pop("HAM_VERCEL_PROJECT_MAP_JSON", None)
        os.environ.pop("HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK", None)
        reset_vercel_project_map_for_tests()
