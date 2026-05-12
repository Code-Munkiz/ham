from __future__ import annotations

import subprocess
import sys
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


def test_managed_mission_feed_live_stream_hook_uses_fetch_sse_not_event_source() -> None:
    hook = Path("frontend/src/features/hermes-workspace/hooks/useManagedMissionFeedLiveStream.ts").read_text(encoding="utf-8")
    assert "setInterval" not in hook
    assert "/feed/stream" in hook
    assert "text/event-stream" in hook
    assert "EventSource" not in hook
    assert "fetchManagedMissionFeed" in hook


def test_builder_activity_stream_subscription_uses_fetch_sse_not_event_source() -> None:
    api_ts = Path("frontend/src/lib/ham/api.ts").read_text(encoding="utf-8")
    assert "export function subscribeBuilderActivityStream" in api_ts
    assert "builder/activity/stream" in api_ts
    assert "text/event-stream" in api_ts
    assert "mergeClerkAuthBearerIfNeeded" in api_ts
    assert "new EventSource" not in api_ts


def test_managed_mission_feed_surfaces_use_live_stream_hook_not_direct_feed_fetch() -> None:
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "useManagedMissionFeedLiveStream" in chat
    assert "fetchManagedMissionFeed" not in chat
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "useManagedMissionFeedLiveStream" in panel
    assert "fetchManagedMissionFeed" not in panel


def test_mission_feed_transcript_helper_contract() -> None:
    util = Path("frontend/src/features/hermes-workspace/utils/missionFeedTranscript.ts").read_text(encoding="utf-8")
    assert 'export type MissionTranscriptItem' in util
    assert "export function buildMissionFeedTranscript" in util
    assert "export function joinTranscriptChunk" in util
    assert "export function collapseAdjacentDuplicateTranscriptNoise" in util
    assert "export function missionFeedTranscriptFromEvents" in util
    assert "provider_status" in util
    assert "ManagedMissionFeedEvent" in util
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "missionFeedTranscriptFromEvents" in chat
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "missionFeedTranscriptFromEvents" in panel
    assert "latestAssistantPreviewFromTranscript" in panel


def test_no_raw_bounded_event_cards_for_managed_mission_live_feed_panel() -> None:
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    needle = "(selectedFeed?.events || []).slice(-8).map("
    assert needle not in panel
    needle_events = "(missionFeed?.events || []).slice(-3).map("
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert needle_events not in chat


def test_rest_refresh_disclaimer_copy_still_present() -> None:
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "REST refresh" in chat
    assert 'provider_projection?.mode === "rest_projection"' in chat
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "REST refresh" in panel
    assert 'provider_projection?.mode === "rest_projection"' in panel


def test_operations_outputs_latest_agent_wiring() -> None:
    ops = Path("frontend/src/features/hermes-workspace/screens/operations/WorkspaceOperationsScreen.tsx").read_text(
        encoding="utf-8"
    )
    assert "Latest agent output" in ops
    assert "onMissionTranscriptDigest={setLatestManagedAssistantPreview}" in ops
    assert "latestManagedAssistantPreview" in ops


def test_open_in_cursor_navigation_only() -> None:
    cursor_util = Path("frontend/src/features/hermes-workspace/utils/cursorCloudAgentWeb.ts").read_text(encoding="utf-8")
    assert "export function isBcCursorAgentId" in cursor_util
    assert "export function cursorCloudAgentWebHref" in cursor_util
    assert "https://cursor.com/agents/" in cursor_util
    assert "api.cursor.com" not in cursor_util
    panel = Path("frontend/src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "Open in Cursor" in panel
    assert "isBcCursorAgentId" in panel
    assert "cursorCloudAgentWebHref" in panel
    chat = Path("frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx").read_text(encoding="utf-8")
    assert "Open in Cursor" in chat


def test_mission_feed_transcript_runtime_verify_script() -> None:
    frontend = Path("frontend")
    script = frontend / "scripts" / "verify-mission-feed-transcript.ts"
    assert script.is_file()
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    proc = subprocess.run(
        [npx, "tsx", "scripts/verify-mission-feed-transcript.ts"],
        cwd=str(frontend),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


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
