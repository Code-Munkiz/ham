from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"\bcrsr_[a-zA-Z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-[a-zA-Z0-9_\-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-\._~\+\/=]{8,}\b", re.I),
]

_LOG = logging.getLogger(__name__)


def cursor_sdk_bridge_enabled() -> bool:
    return str(os.environ.get("HAM_CURSOR_SDK_BRIDGE_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_text(raw: Any, *, limit: int = 260) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    for p in _SECRET_PATTERNS:
        s = p.sub("[REDACTED]", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _bridge_script_path() -> Path:
    return Path(__file__).resolve().parent / "cursor_sdk_bridge" / "bridge.mjs"


def _parse_jsonl(stdout_text: str) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    malformed = 0
    for ln in stdout_text.splitlines():
        line = ln.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            malformed += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            malformed += 1
    return rows, malformed


def stream_cursor_sdk_bridge_events(
    *,
    api_key: str,
    agent_id: str,
    run_id: str | None = None,
    max_seconds: int = 30,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Invoke Node @cursor/sdk bridge and return parsed JSONL rows.
    Returns (rows, error_code). rows may be empty when error_code is set.
    """
    script = _bridge_script_path()
    node_exec = shutil.which("node")
    has_run_id = bool(str(run_id or "").strip())
    diagnostics: dict[str, Any] = {
        "bridge_path_exists": script.exists(),
        "node_resolved": bool(node_exec),
        "has_agent_id": False,
        "has_run_id": has_run_id,
        "subprocess_exit_code": None,
        "timeout": False,
        "stderr_preview": "",
        "stdout_row_count": 0,
        "malformed_row_count": 0,
    }
    if not script.exists():
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_missing_script"
    aid = str(agent_id or "").strip()
    diagnostics["has_agent_id"] = bool(aid)
    if not aid:
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_missing_agent"
    key = str(api_key or "").strip()
    if not key:
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_missing_key"

    payload = {
        "agent_id": aid,
        "run_id": str(run_id).strip() if run_id else None,
        "mode": "stream_existing_run",
        "max_seconds": max(5, int(max_seconds)),
    }
    env = os.environ.copy()
    env["CURSOR_API_KEY"] = key
    cmd = ["node", str(script)]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=max(10, int(max_seconds) + 5),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        diagnostics["timeout"] = True
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_timeout"
    except (OSError, subprocess.SubprocessError):
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_exec_error"

    rows, malformed_count = _parse_jsonl(proc.stdout or "")
    diagnostics["subprocess_exit_code"] = proc.returncode
    diagnostics["stdout_row_count"] = len(rows)
    diagnostics["malformed_row_count"] = malformed_count
    diagnostics["stderr_preview"] = _safe_text(proc.stderr or "", limit=500)
    if proc.returncode != 0:
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        err = _safe_text(proc.stderr or proc.stdout or "", limit=120)
        if "CURSOR_API_KEY" in err:
            return rows, "provider_sdk_bridge_auth_error"
        return rows, "provider_sdk_bridge_error"
    if not rows:
        _LOG.warning("cursor.sdk_bridge.invoke", extra=diagnostics)
        return [], "provider_sdk_bridge_empty_output"
    _LOG.info("cursor.sdk_bridge.invoke", extra=diagnostics)
    return rows, None


async def iter_cursor_sdk_bridge_stdout_rows(
    *,
    api_key: str,
    agent_id: str,
    run_id: str | None = None,
    max_seconds: int = 30,
) -> AsyncIterator[dict[str, Any]]:
    """
    Async generator: yield each JSON object as the bridge prints one JSON line to stdout.

    Subprocess deadline is bounded (``max_seconds`` + headroom); the bridge itself also bounds
    per-chunk work so long missions stream across repeated iterator runs.
    """
    script = _bridge_script_path()
    node_exec = shutil.which("node")
    has_run_id = bool(str(run_id or "").strip())
    diagnostics: dict[str, Any] = {
        "bridge_path_exists": script.exists(),
        "node_resolved": bool(node_exec),
        "has_agent_id": False,
        "has_run_id": has_run_id,
        "subprocess_exit_code": None,
        "timeout": False,
        "stderr_preview": "",
        "stdout_row_count": 0,
        "malformed_row_count": 0,
    }
    if not script.exists() or not node_exec:
        _LOG.warning("cursor.sdk_bridge.iter_async", extra=diagnostics)
        return
    aid = str(agent_id or "").strip()
    diagnostics["has_agent_id"] = bool(aid)
    key = str(api_key or "").strip()
    if not aid or not key:
        _LOG.warning("cursor.sdk_bridge.iter_async", extra=diagnostics)
        return

    payload = {
        "agent_id": aid,
        "run_id": str(run_id).strip() if run_id else None,
        "mode": "stream_existing_run",
        "max_seconds": max(5, int(max_seconds)),
    }
    env = os.environ.copy()
    env["CURSOR_API_KEY"] = key
    wall_deadline = asyncio.get_running_loop().time() + float(max(10, int(max_seconds) + 5))

    malformed = 0
    row_count = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            node_exec,
            str(script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        _LOG.warning("cursor.sdk_bridge.iter_async", extra=diagnostics)
        return

    assert proc.stdin and proc.stdout and proc.stderr

    async def _slurp_stderr() -> bytes:
        return await proc.stderr.read() if proc.stderr else b""

    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()
    stderr_task = asyncio.create_task(_slurp_stderr())

    timed_out_killed = False
    loop_tm = asyncio.get_running_loop()
    stderr_buf = b""
    try:
        while True:
            remaining = wall_deadline - loop_tm.time()
            if remaining <= 0:
                diagnostics["timeout"] = True
                timed_out_killed = True
                proc.kill()
                break
            try:
                line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=min(30.0, max(0.05, remaining)))
            except asyncio.TimeoutError:
                if proc.returncode is not None:
                    break
                continue
            if not line_b:
                break
            row_count += 1
            text = line_b.decode(errors="ignore").strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                malformed += 1
                continue
            if isinstance(obj, dict):
                yield obj
            else:
                malformed += 1
        if not timed_out_killed:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=30.0)
    except asyncio.CancelledError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=12.0)
        if stderr_task.done() and not stderr_task.cancelled():
            with contextlib.suppress(Exception):
                stderr_buf = stderr_task.result() or b""

    diagnostics["subprocess_exit_code"] = proc.returncode
    diagnostics["stdout_row_count"] = row_count
    diagnostics["malformed_row_count"] = malformed
    diagnostics["stderr_preview"] = _safe_text(stderr_buf.decode(errors="ignore"), limit=500)
    status = (
        "iter_timeout_kill"
        if timed_out_killed
        else ("iter_ok" if proc.returncode == 0 else "iter_bad_exit")
    )
    fn = _LOG.warning if proc.returncode not in (0, None) and not timed_out_killed else _LOG.debug
    fn("cursor.sdk_bridge.iter_async", extra={**diagnostics, "finish": status})
