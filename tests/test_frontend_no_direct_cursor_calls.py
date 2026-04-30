from __future__ import annotations

from pathlib import Path


def test_frontend_has_no_direct_cursor_api_calls() -> None:
    frontend = Path("frontend/src")
    offenders: list[str] = []
    for p in frontend.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        txt = p.read_text(encoding="utf-8")
        if "api.cursor.com" in txt:
            offenders.append(str(p))
    assert offenders == []


def test_workspace_routes_are_defined_and_legacy_chat_redirects() -> None:
    app_tsx = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'path="/workspace/*" element={<WorkspaceApp />}' in app_tsx
    assert 'path="/chat" element={<Navigate to="/workspace/chat" replace />}' in app_tsx


def test_managed_mission_feed_poll_constants_and_delay_helper_present() -> None:
    adapter = Path("frontend/src/features/hermes-workspace/adapters/managedMissionsAdapter.ts").read_text(encoding="utf-8")
    assert "MANAGED_MISSION_FEED_POLL_MS_ACTIVE = 12_000" in adapter
    assert "MANAGED_MISSION_FEED_POLL_MS_HIDDEN = 60_000" in adapter
    assert "MANAGED_MISSION_FEED_POLL_MS_TERMINAL_VISIBLE = 120_000" in adapter
    assert "MANAGED_MISSION_FEED_POLL_MS_TERMINAL_HIDDEN = 300_000" in adapter
    assert "export function managedMissionFeedPollDelayMs" in adapter


def test_managed_mission_feed_bounded_poll_single_hook_no_interval() -> None:
    hook = Path("frontend/src/features/hermes-workspace/hooks/useManagedMissionFeedPoll.ts").read_text(encoding="utf-8")
    assert "setInterval" not in hook
    assert "setTimeout" in hook
    assert "fetchManagedMissionFeed" in hook
    assert "managedMissionFeedPollDelayMs" in hook


def test_managed_mission_feed_surfaces_use_shared_poll_hook_not_direct_feed_fetch() -> None:
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "useManagedMissionFeedPoll" in chat
    assert "fetchManagedMissionFeed" not in chat
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "useManagedMissionFeedPoll" in panel
    assert "fetchManagedMissionFeed" not in panel


def test_rest_refresh_disclaimer_copy_still_present() -> None:
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "REST refresh" in chat
    assert 'provider_projection?.mode === "rest_projection"' in chat
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "REST refresh" in panel
    assert 'provider_projection?.mode === "rest_projection"' in panel


def test_managed_mission_feed_poll_delay_contract() -> None:
    """Mirrors managedMissionFeedPollDelayMs (non-terminal active vs terminal slow)."""

    def delay_ms(lifecycle: str | None, hidden: bool) -> int:
        active, hidden_ms, term_vis, term_hid = 12_000, 60_000, 120_000, 300_000
        terminal = lifecycle in ("succeeded", "failed", "archived")
        if terminal:
            return term_hid if hidden else term_vis
        return hidden_ms if hidden else active

    assert delay_ms("open", False) == 12_000
    assert delay_ms("open", True) == 60_000
    assert delay_ms(None, False) == 12_000
    assert delay_ms("succeeded", False) == 120_000
    assert delay_ms("failed", True) == 300_000
