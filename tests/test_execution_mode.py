from __future__ import annotations

from src.ham.execution_mode import resolve_execution_mode


def test_auto_prefers_browser_for_web_task():
    d = resolve_execution_mode(
        preference="auto",
        environment="web",
        user_text="Open https://example.com and click sign in",
        browser_available=True,
        local_machine_available=False,
    )
    assert d.selected_mode == "browser"
    assert d.auto_selected is True


def test_auto_falls_back_to_chat_for_non_web_task():
    d = resolve_execution_mode(
        preference="auto",
        environment="web",
        user_text="Explain this architecture document",
        browser_available=True,
        local_machine_available=False,
    )
    assert d.selected_mode == "chat"


def test_machine_pref_in_web_falls_back_to_browser_for_web_task():
    d = resolve_execution_mode(
        preference="machine",
        environment="web",
        user_text="Navigate to docs site and search for API endpoint",
        browser_available=True,
        local_machine_available=False,
    )
    assert d.selected_mode == "browser"
    assert d.auto_selected is False


def test_machine_pref_in_desktop_keeps_machine():
    d = resolve_execution_mode(
        preference="machine",
        environment="desktop",
        user_text="Open terminal and check process",
        browser_available=True,
        local_machine_available=True,
    )
    assert d.selected_mode == "machine"
