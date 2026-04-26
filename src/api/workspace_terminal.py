"""
HAM-owned workspace terminal session bridge (subprocess + stdin/stdout).

Uses COMSPEC/cmd.exe on Windows and /bin/bash on Unix. Output is captured to a
buffer; clients poll for new data. Hardening (isolation, audit, pty) is follow-up.
"""

from __future__ import annotations

import os
import subprocess
import threading
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor

router = APIRouter(prefix="/api/workspace/terminal", tags=["workspace-terminal"])

_sessions_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


def _spawn() -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603
            [os.environ.get("COMSPEC", "cmd.exe")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
        )
    shell = os.environ.get("SHELL", "/bin/bash")
    return subprocess.Popen(  # noqa: S603
        [shell, "-i"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
    )


def _reader_thread(sid: str, proc: subprocess.Popen[bytes], done: threading.Event) -> None:
    if proc.stdout is None:
        return
    while not done.is_set():
        try:
            chunk = proc.stdout.read(1024)
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


@router.post("/sessions")
def create_session(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, str]:
    global _sessions
    sid = str(uuid.uuid4())
    try:
        proc = _spawn()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to start shell: {e}") from e
    done = threading.Event()
    out_buf: list[str] = []
    th = threading.Thread(
        target=_reader_thread,
        args=(sid, proc, done),
        name=f"ham-term-{sid[:8]}",
        daemon=True,
    )
    with _sessions_lock:
        _sessions[sid] = {
            "proc": proc,
            "out": out_buf,
            "reader": th,
            "done": done,
        }
    th.start()
    return {"sessionId": sid}


class InputBody(BaseModel):
    data: str = Field(..., description="Raw bytes as string (e.g. lines with \\n, or \\x03 for Ctrl+C)")


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
    proc: subprocess.Popen[bytes] = s["proc"]
    if proc.stdin is None:
        return {"ok": False}
    try:
        data = body.data
        b = data.encode("utf-8", errors="surrogateescape")
        proc.stdin.write(b)
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return {"ok": False}
    return {"ok": True}


class ResizeBody(BaseModel):
    cols: int = 80
    rows: int = 24


@router.post("/sessions/{session_id}/resize")
def resize_(
    session_id: str,
    _body: ResizeBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, bool]:
    """Resize: accepted for future TTY/pty; no-op for plain pipes."""
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Unknown session")
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
    with _sessions_lock:
        s = _sessions.pop(session_id, None)
    if s is None:
        return
    s["done"].set()
    proc: subprocess.Popen[bytes] = s["proc"]
    try:
        proc.terminate()
    except OSError:
        pass
    s["reader"].join(timeout=2.0)
