from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _input_line() -> str:
    """Cmd.exe and POSIX shells: send a line that can produce process output in the test."""
    if os.name == "nt":
        return "echo WSTPING\r\n"
    return "echo WSTPING\n"


def test_workspace_terminal_create_output_close(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    assert r.status_code == 200
    data = r.json()
    assert data.get("transport") in ("pty", "pipe")
    assert "streamPath" in data
    sid = data.get("sessionId")
    assert isinstance(sid, str) and sid

    out = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0")
    assert out.status_code == 200
    body = out.json()
    assert "text" in body
    assert "next" in body

    d = client.delete(f"/api/workspace/terminal/sessions/{sid}")
    assert d.status_code == 204


def test_workspace_terminal_input_ok(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    assert r.status_code == 200
    sid = r.json()["sessionId"]
    r_in = client.post(
        f"/api/workspace/terminal/sessions/{sid}/input",
        json={"data": _input_line()},
    )
    assert r_in.status_code == 200
    assert r_in.json() == {"ok": True}
    client.delete(f"/api/workspace/terminal/sessions/{sid}")


def test_workspace_terminal_resize_ok(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    sid = r.json()["sessionId"]
    r_sz = client.post(
        f"/api/workspace/terminal/sessions/{sid}/resize",
        json={"cols": 100, "rows": 40},
    )
    assert r_sz.status_code == 200
    assert r_sz.json() == {"ok": True}
    client.delete(f"/api/workspace/terminal/sessions/{sid}")


def test_workspace_terminal_input_then_poll_captures_text(client: TestClient) -> None:
    """Reader uses read1() so Windows pipe output is not stuck behind BufferedReader.read(n) fill behavior."""
    r = client.post("/api/workspace/terminal/sessions")
    sid = r.json()["sessionId"]
    n0 = 0
    if os.name == "nt":
        for _ in range(80):
            o0 = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0").json()
            t0 = (o0.get("text") or "") if isinstance(o0.get("text"), str) else ""
            n0 = int(o0.get("len") or 0)
            # ConPTY: short escape codes arrive before cmd's banner + prompt (~2s). Pipe: banner is faster.
            if n0 > 100 or "Microsoft" in t0 or "C:\\" in t0:
                break
            time.sleep(0.1)
        assert n0 > 0, "Expected shell startup text before first input (ConPTY or pipe)"
    else:
        o0 = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0").json()
        n0 = int(o0.get("len") or 0)
    assert client.post(
        f"/api/workspace/terminal/sessions/{sid}/input",
        json={"data": _input_line()},
    ).status_code == 200
    saw = False
    for _ in range(40):
        out = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0").json()
        t = (out.get("text") or "") if isinstance(out.get("text"), str) else ""
        n = int(out.get("len") or 0)
        if "WSTPING" in t or n > n0 + 2:
            saw = True
            break
        time.sleep(0.05)
    assert saw, "Expected command output (WSTPING) in polled buffer"
    out_end = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0").json()
    assert out_end.get("len") is not None
    client.delete(f"/api/workspace/terminal/sessions/{sid}")


def test_workspace_terminal_stream_ws_accepts_and_pushes_text(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    sid = r.json()["sessionId"]
    with client.websocket_connect(f"/api/workspace/terminal/sessions/{sid}/stream") as ws:
        for _ in range(80):
            msg = ws.receive_text()
            if json.loads(msg).get("type") == "out":
                break
            time.sleep(0.02)
    client.delete(f"/api/workspace/terminal/sessions/{sid}")


def test_workspace_terminal_output_404_after_close(client: TestClient) -> None:
    r = client.post("/api/workspace/terminal/sessions")
    sid = r.json()["sessionId"]
    assert client.delete(f"/api/workspace/terminal/sessions/{sid}").status_code == 204
    r_out = client.get(f"/api/workspace/terminal/sessions/{sid}/output?after=0")
    assert r_out.status_code == 404
    r_in = client.post(
        f"/api/workspace/terminal/sessions/{sid}/input",
        json={"data": "\n"},
    )
    assert r_in.status_code == 404
