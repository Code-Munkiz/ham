from __future__ import annotations

from src.ham.build_registry.user_copy_sanitize import (
    contains_build_registry_v2_forbidden_token,
    sanitize_normal_user_copy,
)


def test_does_not_redact_common_filename_mentions() -> None:
    assert not contains_build_registry_v2_forbidden_token("Updated game.js with timer logic")
    assert not contains_build_registry_v2_forbidden_token("Tweaked config.yaml defaults")
    assert not contains_build_registry_v2_forbidden_token("Refactored dashboard_layout.tsx")


def test_redacts_registry_module_ids_and_playbook_headers() -> None:
    assert contains_build_registry_v2_forbidden_token(
        "Build Registry v2 playbook context: site.dashboard-ui-core"
    )
    assert contains_build_registry_v2_forbidden_token("Routed to game.idle-incremental")
    assert contains_build_registry_v2_forbidden_token("app.saas-dashboard-core selected")


def test_redacts_scaffold_quality_codes_not_layout_names() -> None:
    assert contains_build_registry_v2_forbidden_token(
        "gate report: dashboard_missing_requested_filter"
    )
    assert not contains_build_registry_v2_forbidden_token("Renamed dashboard_layout component")


def test_sanitize_preserves_legitimate_provider_copy() -> None:
    msg = "Patched game.js and config.yaml"
    assert sanitize_normal_user_copy(msg, fallback="redacted") == msg


def test_sanitize_replaces_internal_leaks() -> None:
    leaked = "Build Registry v2 playbook context: site.landing-page-core"
    assert sanitize_normal_user_copy(leaked, fallback="safe") == "safe"
