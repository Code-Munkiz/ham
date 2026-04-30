from __future__ import annotations

import subprocess
from pathlib import Path

from src.integrations import cursor_sdk_bridge_client as bridge


def test_bridge_enabled_flag(monkeypatch) -> None:
    monkeypatch.setenv("HAM_CURSOR_SDK_BRIDGE_ENABLED", "true")
    assert bridge.cursor_sdk_bridge_enabled() is True
    monkeypatch.setenv("HAM_CURSOR_SDK_BRIDGE_ENABLED", "0")
    assert bridge.cursor_sdk_bridge_enabled() is False


def test_stream_returns_missing_script_when_bridge_absent(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_bridge_script_path", lambda: Path("z:/missing/bridge.mjs"))
    rows, err = bridge.stream_cursor_sdk_bridge_events(
        api_key="crsr_test",
        agent_id="bc-x",
    )
    assert rows == []
    assert err == "provider_sdk_bridge_missing_script"


def test_stream_timeout_maps_to_timeout_error(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "bridge.mjs"
    fake.write_text("// test", encoding="utf-8")
    monkeypatch.setattr(bridge, "_bridge_script_path", lambda: fake)

    def _timeout(*_args: object, **_kwargs: object):
        raise subprocess.TimeoutExpired(cmd=["node"], timeout=1)

    monkeypatch.setattr(bridge.subprocess, "run", _timeout)
    rows, err = bridge.stream_cursor_sdk_bridge_events(
        api_key="crsr_test",
        agent_id="bc-x",
    )
    assert rows == []
    assert err == "provider_sdk_bridge_timeout"


def test_stream_parses_jsonl(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "bridge.mjs"
    fake.write_text("// test", encoding="utf-8")
    monkeypatch.setattr(bridge, "_bridge_script_path", lambda: fake)

    class _Proc:
        returncode = 0
        stdout = '{"event_id":"e1","kind":"status"}\n{"event_id":"e2","kind":"completed"}\n'
        stderr = ""

    monkeypatch.setattr(bridge.subprocess, "run", lambda *_args, **_kwargs: _Proc())
    rows, err = bridge.stream_cursor_sdk_bridge_events(
        api_key="crsr_test",
        agent_id="bc-x",
    )
    assert err is None
    assert len(rows) == 2
    assert rows[0]["event_id"] == "e1"
