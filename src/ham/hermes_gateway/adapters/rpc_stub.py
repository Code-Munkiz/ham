from __future__ import annotations

from typing import Any


def hermes_rpc_placeholder() -> dict[str, Any]:
    """Path C seam — not a live client; documents future adapter hook."""
    return {
        "id": "hermes_json_rpc",
        "label": "JSON-RPC control (future adapter)",
        "status": "not_implemented_upstream",
        "note": (
            "No Hermes JSON-RPC server in audited v0.8.0 (REST + SSE only). "
            "See docs/HERMES_UPSTREAM_CONTRACT_AUDIT.md."
        ),
    }


def websocket_control_placeholder() -> dict[str, Any]:
    return {
        "id": "hermes_websocket_control",
        "label": "WebSocket control (future adapter)",
        "status": "not_implemented_upstream",
        "note": "Hermes API server (v0.8.0) does not expose WebSocket for menus/control.",
    }
