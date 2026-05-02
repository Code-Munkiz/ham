#!/usr/bin/env python3
"""
Run Ham FastAPI locally with defaults that match desktop + Vite smoke testing.

- Loads optional repo-root ``.env`` (does not override variables already set in the shell).
- Sets ``HERMES_GATEWAY_MODE=mock`` when unset (avoids broken upstream gateway during UI work).
- Uses in-memory chat sessions when unset (no SQLite path issues).
- **Always** forces API-side Clerk enforcement **off** for this entrypoint so a SPA that sends
  ``Authorization: Bearer`` (e.g. ``VITE_CLERK_PUBLISHABLE_KEY``) never hits
  ``CLERK_JWT_ISSUER`` / JWT verification HTTP 500 on routes like ``GET /api/chat/sessions`` or
  ``GET /api/chat/capabilities``.

Usage (from repo root)::

    .venv/bin/python scripts/run_local_api.py

Override port::

    PORT=8000 .venv/bin/python scripts/run_local_api.py

Full Clerk-enforced local testing (not this script)::

    HAM_CLERK_REQUIRE_AUTH=true HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS=… CLERK_JWT_ISSUER=… \\
      .venv/bin/python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import sys

    # Ensure ``import src`` works in this interpreter (``PYTHONPATH`` alone does not update ``sys.path`` mid-process).
    os.chdir(_ROOT)
    root_s = str(_ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ["PYTHONPATH"] = root_s

    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)

    os.environ.setdefault("HERMES_GATEWAY_MODE", "mock")
    os.environ.setdefault("HAM_CHAT_SESSION_STORE", "memory")

    # Local dashboard/dev: never verify Clerk JWTs here (.env may set REQUIRE_AUTH / email gate).
    os.environ["HAM_CLERK_REQUIRE_AUTH"] = "false"
    os.environ["HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS"] = "false"

    host = (os.environ.get("HAM_API_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("PORT") or os.environ.get("HAM_API_PORT") or "8000").strip())
    # ``uvicorn --reload`` spawns a child that does not reliably inherit in-process ``sys.path`` fixes;
    # subprocess with explicit ``PYTHONPATH`` avoids ``ModuleNotFoundError: No module named 'src'``.
    reload = (os.environ.get("HAM_API_RELOAD") or "0").strip().lower() in ("1", "true", "yes", "on")

    if reload:
        import subprocess
        import sys

        env = {**os.environ, "PYTHONPATH": str(_ROOT)}
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "src.api.server:app",
            "--host",
            host,
            "--port",
            str(port),
            "--reload",
        ]
        raise SystemExit(subprocess.call(cmd, env=env, cwd=_ROOT))

    import uvicorn

    uvicorn.run("src.api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
