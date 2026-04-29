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
