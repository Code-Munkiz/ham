from __future__ import annotations

from typing import Any

from src.persistence.cursor_credentials import get_effective_cursor_api_key
from src.registry.droids import DEFAULT_DROID_REGISTRY


def _card(
    *,
    id_: str,
    label: str,
    description: str,
    availability: str,
    capabilities: list[str],
    status: str,
    requires_auth: bool,
    requires_tty: bool,
    configured: bool,
    last_seen: str | None,
    actions_supported: list[str],
    source: str,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "description": description,
        "availability": availability,
        "capabilities": capabilities,
        "status": status,
        "requires_auth": requires_auth,
        "requires_tty": requires_tty,
        "configured": configured,
        "last_seen": last_seen,
        "actions_supported": actions_supported,
        "source": source,
        "warnings": warnings,
    }


def build_external_runner_cards(*, droid_count: int) -> list[dict[str, Any]]:
    """Normalized adapter cards; honest about stubs vs HAM-native integrations."""
    cursor_key = bool(get_effective_cursor_api_key())
    cards: list[dict[str, Any]] = []

    cards.append(
        _card(
            id_="cursor_cloud_agent",
            label="Cursor Cloud Agents",
            description="Launch and observe Cursor cloud agent runs via HAM control-plane APIs (when configured).",
            availability="ham_native" if cursor_key else "not_configured",
            capabilities=["control_plane_runs", "cursor_api_models_list"],
            status="ready" if cursor_key else "needs_cursor_api_key",
            requires_auth=True,
            requires_tty=False,
            configured=cursor_key,
            last_seen=None,
            actions_supported=["read_control_plane_runs", "launch_via_existing_api"],
            source="ham_cursor_integration",
            warnings=[]
            if cursor_key
            else ["Set Cursor API credentials on the HAM API host to enable Cloud Agents."],
        ),
    )

    cards.append(
        _card(
            id_="factory_droid",
            label="Factory Droids",
            description="HAM registry droids for bridge execution (builder, reviewer).",
            availability="ham_native",
            capabilities=["registry_profiles", "droid_launch_via_chat_workflows"],
            status="ready",
            requires_auth=False,
            requires_tty=False,
            configured=droid_count > 0,
            last_seen=None,
            actions_supported=["read_registry"],
            source="ham_droid_registry",
            warnings=[],
        ),
    )

    for stub_id, label, desc in (
        (
            "opencode",
            "OpenCode",
            "No HAM adapter shipped yet; CLI/host integration only if you run it outside HAM.",
        ),
        (
            "claude_code",
            "Claude Code",
            "No HAM adapter shipped yet; use vendor CLI on the operator machine.",
        ),
        (
            "codex",
            "Codex",
            "No HAM adapter shipped yet; use vendor CLI or IDE integration outside HAM.",
        ),
    ):
        cards.append(
            _card(
                id_=stub_id,
                label=label,
                description=desc,
                availability="stub",
                capabilities=[],
                status="not_implemented",
                requires_auth=False,
                requires_tty=True,
                configured=False,
                last_seen=None,
                actions_supported=[],
                source="placeholder",
                warnings=["Stub only — no HAM execution bridge for this runner yet."],
            ),
        )

    return cards
