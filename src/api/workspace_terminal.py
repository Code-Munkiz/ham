"""
HAM workspace terminal: ConPTY on Windows (pywinpty), pipe+read1 fallback.

- **Output:** ``GET /sessions/{id}/output?after=`` and ``WebSocket /sessions/{id}/stream``
- **Input:** ``POST .../input`` or WebSocket ``{"type":"in","data":...}``
- **Resize:** ConPTY: ``setwinsize``; pipe: no-op

``HAM_TERMINAL_PTY=0`` forces pipe mode on Windows. ``HAM_TERMINAL_IDLE_SECONDS`` (default 3600)
reaps idle sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.ham import terminal_runtime as tr

router = APIRouter(prefix="/api/workspace/terminal", tags=["workspace-terminal"])

_sessions_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}

_reaper_lock = threading.Lock()
_reaper_started = False
_IDLE_SECS = max(60.0, float((os.environ.get("HAM_TERMINAL_IDLE_SECONDS") or "3600").strip()))


def _terminal_cwd() -> str | None:
    for key in ("HAM_WORKSPACE_ROOT", "HAM_WORKSPACE_FILES_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if raw and os.path.isdir(raw):
            return raw
    return None


def _touch(s: dict[str, Any]) -> None:
    s["last_touched"] = time.monotonic()


def _pipe_spawn() -> subprocess.Popen[bytes]:
    cwd = _terminal_cwd() or os.getcwd()
    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603
            [os.environ.get("COMSPEC", "cmd.exe")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )
    shell = os.environ.get("SHELL", "/bin/bash")
    return subprocess.Popen(  # noqa: S603
        [shell, "-i"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
    )


def _reader_thread_pipe(sid: str, proc: subprocess.Popen[bytes], done: threading.Event) -> None:
    if proc.stdout is None:
        return
    while not done.is_set():
        try:
            chunk = proc.stdout.read1(4096)
        except (ValueError, OSError):
            break
        if not chunk:
            break
        t = chunk.decode("utf-8", errors="replace")
        with _sessions_lock:
            s = _sessions.get(sid)
            if s is None:
                break
            s["out"].append(t)
            _touch(s)


def _reader_thread_pty(sid: str, pty: Any, done: threading.Event) -> None:
    while not done.is_set():
        try:
            chunk = pty.read(32 * 1024)
        except (EOFError, OSError) as e:
            if not done.is_set():
                with _sessions_lock:
                    s = _sessions.get(sid)
                    if s is not None:
                        s["out"].append(f"\n[pty closed: {e!r}]\n")
            break
        except Exception as e:  # noqa: BLE001
            with _sessions_lock:
                s = _sessions.get(sid)
                if s is not None:
                    s["out"].append(f"\n[pty read error: {e!r}]\n")
            break
        if not chunk:
            time.sleep(0.01)
            continue
        with _sessions_lock:
            s = _sessions.get(sid)
            if s is None:
                break
            s["out"].append(chunk)
            _touch(s)


def _reaper_loop() -> None:
    while True:
        time.sleep(30.0)
        now = time.monotonic()
        victims: list[str] = []
        with _sessions_lock:
            for sid, s in _sessions.items():
                if now - float(s.get("last_touched", 0.0)) > _IDLE_SECS:
                    victims.append(sid)
        for sid in victims:
            _shutdown_session(sid, reason="idle_timeout")


def _ensure_reaper() -> None:
    global _reaper_started
    with _reaper_lock:
        if _reaper_started:
            return
        t = threading.Thread(
            target=_reaper_loop,
            name="ham-terminal-reaper",
            daemon=True,
        )
        t.start()
        _reaper_started = True


def _shutdown_session(session_id: str, *, reason: str = "closed") -> None:  # noqa: ARG001
    with _sessions_lock:
        s = _sessions.pop(session_id, None)
    if s is None:
        return
    s["done"].set()
    if s.get("kind") == "pty" and s.get("pty") is not None:
        pty = s["pty"]
        try:
            pty.terminate()
        except (OSError, Exception):  # noqa: BLE001
            pass
        try:
            pty.close()
        except (OSError, Exception):  # noqa: BLE001
            pass
    else:
        proc: subprocess.Popen[bytes] | None = s.get("proc")
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
    th: threading.Thread = s["reader"]
    th.join(timeout=2.0)


class CreateSessionBody(BaseModel):
    cols: int = Field(default=80, ge=20, le=200)
    rows: int = Field(default=24, ge=4, le=200)


@router.post("/sessions")
def create_session(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    body: Annotated[CreateSessionBody | None, Body()] = None,
) -> dict[str, str]:
    b = body or CreateSessionBody()
    _ensure_reaper()
    sid = str(uuid.uuid4())
    cwd = _terminal_cwd() or os.getcwd()
    done = threading.Event()
    out_buf: list[str] = []
    rows, cols = int(b.rows), int(b.cols)
    pty: Any | None = tr.try_winpty(cwd, rows, cols)
    proc: subprocess.Popen[bytes] | None = None
    if pty is not None:
        kind = "pty"
        th = threading.Thread(
            target=_reader_thread_pty,
            args=(sid, pty, done),
            name=f"ham-term-pty-{sid[:8]}",
            daemon=True,
        )
    else:
        try:
            proc = _pipe_spawn()
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to start shell: {e}") from e
        kind = "pipe"
        th = threading.Thread(
            target=_reader_thread_pipe,
            args=(sid, proc, done),
            name=f"ham-term-pipe-{sid[:8]}",
            daemon=True,
        )
    now = time.monotonic()
    with _sessions_lock:
        _sessions[sid] = {
            "kind": kind,
            "out": out_buf,
            "reader": th,
            "done": done,
            "pty": pty,
            "proc": proc,
            "last_touched": now,
        }
    th.start()
    with _sessions_lock:
        if sid in _sessions:
            _touch(_sessions[sid])
    return {
        "sessionId": sid,
        "transport": kind,
        "streamPath": f"/api/workspace/terminal/sessions/{sid}/stream",
    }


class InputBody(BaseModel):
    data: str = Field(..., description="Raw string (e.g. lines, or \\x03 for Ctrl+C)")


def _apply_input(s: dict[str, Any], data: str) -> bool:
    _touch(s)
    if s.get("kind") == "pty" and s.get("pty") is not None:
        pty: Any = s["pty"]
        try:
            pty.write(data)
            return True
        except (BrokenPipeError, OSError, EOFError):
            return False
    proc: subprocess.Popen[bytes] | None = s.get("proc")
    if proc is None or proc.stdin is None:
        return False
    try:
        b = data.encode("utf-8", errors="surrogateescape")
        proc.stdin.write(b)
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return False
    return True


@router.post("/sessions/{session_id}/input")
def post_input(
    session_id: str,
    body: InputBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, bool]:
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return {"ok": _apply_input(s, body.data)}


class ResizeBody(BaseModel):
    cols: int = 80
    rows: int = 24


@router.post("/sessions/{session_id}/resize")
def resize_(
    session_id: str,
    body: ResizeBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, bool]:
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    _touch(s)
    if s.get("kind") == "pty" and s.get("pty") is not None:
        pty: Any = s["pty"]
        r = max(1, int(body.rows))
        c = max(1, int(body.cols))
        try:
            pty.setwinsize(r, c)
        except (OSError, Exception):  # noqa: BLE001
            return {"ok": False}
        return {"ok": True}
    return {"ok": True}


@router.get("/sessions/{session_id}/output")
def get_output(
    session_id: str,
    after: int = 0,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> dict[str, Any]:
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    _touch(s)
    text = "".join(s["out"])
    if after < 0:
        after = 0
    if after > len(text):
        after = len(text)
    return {
        "text": text[after:],
        "len": len(text),
        "next": len(text),
    }


@router.delete("/sessions/{session_id}", status_code=204)
def close_session(
    session_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)] = None,
) -> None:
    _shutdown_session(session_id, reason="client_delete")


@router.websocket("/sessions/{session_id}/stream")
async def terminal_stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        await websocket.close(code=4404)
        return
    _touch(s)
    with _sessions_lock:
        s0 = _sessions.get(session_id)
    text_offset = len("".join(s0["out"])) if s0 is not None else 0
    send_lock = asyncio.Lock()

    async def send_out_delta() -> None:
        nonlocal text_offset
        while True:
            await asyncio.sleep(0.04)
            with _sessions_lock:
                s2 = _sessions.get(session_id)
            if s2 is None:
                return
            text = "".join(s2["out"])
            if len(text) > text_offset:
                chunk = text[text_offset:]
                text_offset = len(text)
                async with send_lock:
                    try:
                        await websocket.send_text(
                            json.dumps({"type": "out", "text": chunk}, ensure_ascii=False),
                        )
                    except (RuntimeError, OSError) as e:
                        if "not connected" in str(e).lower() or "closed" in str(e).lower():
                            return
                _touch(s2)

    async def recv_msgs() -> None:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            except (RuntimeError, OSError) as e:
                if "not connected" in str(e).lower() or "closed" in str(e).lower():
                    return
                raise
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            with _sessions_lock:
                s2 = _sessions.get(session_id)
            if s2 is None:
                return
            mtype = msg.get("type")
            if mtype == "in" and "data" in msg:
                _apply_input(s2, str(msg["data"]))
            elif mtype == "ping":
                with _sessions_lock:
                    s3 = _sessions.get(session_id)
                if s3 is not None:
                    _touch(s3)
            elif mtype == "resize":
                c = int(msg.get("cols") or 80)
                r = int(msg.get("rows") or 24)
                with _sessions_lock:
                    s2b = _sessions.get(session_id)
                if s2b is not None and s2b.get("kind") == "pty" and s2b.get("pty") is not None:
                    try:
                        s2b["pty"].setwinsize(max(1, r), max(1, c))
                    except (OSError, Exception):  # noqa: BLE001
                        pass
                    _touch(s2b)

    push = asyncio.create_task(send_out_delta())
    try:
        await recv_msgs()
    finally:
        push.cancel()
        try:
            await push
        except asyncio.CancelledError:
            pass
        with _sessions_lock:
            s0 = _sessions.get(session_id)
        if s0 is not None:
            _touch(s0)