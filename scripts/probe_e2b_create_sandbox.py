from __future__ import annotations

import json
import os
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ham.builder_sandbox_provider import classify_sandbox_provider_error


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _sdk_version() -> str | None:
    try:
        return version("e2b")
    except PackageNotFoundError:
        return None


def main() -> int:
    started = time.monotonic()
    api_key = str(os.environ.get("HAM_BUILDER_SANDBOX_API_KEY") or "").strip()
    template = str(os.environ.get("HAM_BUILDER_SANDBOX_E2B_TEMPLATE") or "").strip()
    payload: dict[str, Any] = {
        "sdk_import_ok": False,
        "sdk_version": _sdk_version(),
        "api_key_present": bool(api_key),
        "template_configured": bool(template),
        "lifecycle_stage": "create_sandbox",
        "exception_class": None,
        "normalized_error_code": None,
        "normalized_error_message": None,
        "elapsed_ms": 0,
        "cleanup_attempted": False,
        "cleanup_succeeded": False,
    }
    if not api_key:
        payload["exception_class"] = "RuntimeError"
        payload["normalized_error_code"] = "SANDBOX_AUTH_FAILED"
        payload["normalized_error_message"] = "Sandbox provider authentication failed."
        payload["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        _print(payload)
        return 2
    sandbox = None
    try:
        from e2b import Sandbox  # type: ignore

        payload["sdk_import_ok"] = True
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": 120,
            "secure": False,
            "allow_internet_access": True,
        }
        if template:
            kwargs["template"] = template
        sandbox = Sandbox.create(**kwargs)
        payload["lifecycle_stage"] = "create_sandbox"
    except Exception as exc:  # noqa: BLE001
        classified = classify_sandbox_provider_error(error=exc, lifecycle_stage="create_sandbox")
        payload["exception_class"] = type(exc).__name__
        payload["normalized_error_code"] = classified.error_code
        payload["normalized_error_message"] = classified.error_message
        payload["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        _print(payload)
        return 1
    finally:
        if sandbox is not None:
            payload["cleanup_attempted"] = True
            try:
                sandbox.kill()
                payload["cleanup_succeeded"] = True
                payload["lifecycle_stage"] = "cleanup"
            except Exception:
                payload["cleanup_succeeded"] = False
    payload["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
