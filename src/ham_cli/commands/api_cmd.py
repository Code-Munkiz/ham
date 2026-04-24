"""ham api — thin HTTP helpers."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from src.ham_cli.util import emit_json, get_api_base


def run_api_status(*, json_out: bool, base: str | None) -> None:
    resolved = (base or "").strip().rstrip("/") or get_api_base()
    if not resolved:
        msg = "Set HAM_API_BASE or pass --base URL (origin only, no /api suffix)."
        if json_out:
            emit_json({"ok": False, "error": msg})
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(code=1)

    url = f"{resolved}/api/status"
    try:
        r = httpx.get(url, timeout=15.0)
    except Exception as exc:  # noqa: BLE001
        if json_out:
            emit_json({"ok": False, "ham_api_base": resolved, "error": str(exc)})
        else:
            typer.echo(f"Request failed: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_out:
        body: Any
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = r.text
        emit_json(
            {
                "ok": r.is_success,
                "ham_api_base": resolved,
                "http_status": r.status_code,
                "body": body,
            }
        )
        if not r.is_success:
            raise typer.Exit(code=1)
        return

    if r.is_success:
        try:
            data = r.json()
            import json as _json

            print(_json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True))
        except Exception:  # noqa: BLE001
            print(r.text)
    else:
        typer.echo(f"HTTP {r.status_code} from {url}", err=True)
        typer.echo(r.text[:800], err=True)
        raise typer.Exit(code=1)
