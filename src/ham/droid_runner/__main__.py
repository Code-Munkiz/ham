"""`python -m src.ham.droid_runner` — development entry (uvicorn)."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    host = (os.environ.get("HAM_DROID_RUNNER_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("HAM_DROID_RUNNER_PORT") or "8791").strip())
    uvicorn.run(
        "src.ham.droid_runner.service:app",
        host=host,
        port=port,
        factory=False,
    )
