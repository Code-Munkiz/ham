"""Telegram adapter for GoHAM Social autonomy ticks.

The autonomy tick service owns profile/channel/action/cap/content gates. This
adapter only composes the existing Telegram autopilot run-once controller and
normalizes its dry-run lane-selection result into the small shape consumed by
``SocialAutonomyTickResult`` aggregation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.ham import social_telegram_autopilot
from src.ham.social_telegram_autopilot import HamgomoonAutopilotConfig

__all__ = ["AdapterUnavailable", "SocialAutonomyTelegramAdapter"]

_REACTIVE_ACTIONS = {"message", "reply"}
_LANE_TO_ACTIONS = {
    "reactive": _REACTIVE_ACTIONS,
    "activity": {"activity"},
}


class AdapterUnavailable(RuntimeError):  # noqa: N818 - contract requires this typed name.
    """Raised when Telegram autopilot lane selection cannot be performed."""


class SocialAutonomyTelegramAdapter:
    """Compose Telegram autopilot and return a tick-result-shaped slice."""

    def dispatch(
        self,
        action: Mapping[str, Any],
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Dispatch a single Telegram action through autopilot dry-run selection.

        Live dispatch is deliberately unavailable for Mission 13. The autopilot
        remains the only lane selector; this method only checks whether the
        selected lane corresponds to the tick service's already-eligible action.
        """

        if not dry_run:
            raise AdapterUnavailable("Telegram autopilot live dispatch is unavailable")

        action_name = str(action.get("action") or "").strip()
        try:
            result = social_telegram_autopilot.run_hamgomoon_autopilot_once(
                HamgomoonAutopilotConfig(dry_run=True),
            )
        except AssertionError:
            raise
        except Exception as exc:  # noqa: BLE001 - expose a typed adapter boundary.
            raise AdapterUnavailable(
                "Telegram autopilot lane selection unavailable",
            ) from exc

        if not getattr(result, "lane_order", []):
            raise AdapterUnavailable("Telegram autopilot lane selection unavailable")

        blocked_reasons = _blocked_reasons(result)
        actions_taken = _actions_taken_for_selection(
            requested_action=action_name,
            selected_lane=result.selected_lane,
            blocked_reasons=blocked_reasons,
        )
        return {
            "actions_taken": actions_taken,
            "blocked_reasons": blocked_reasons,
            "dry_run": bool(result.dry_run),
        }


def _actions_taken_for_selection(
    *,
    requested_action: str,
    selected_lane: str | None,
    blocked_reasons: list[str],
) -> list[str]:
    if blocked_reasons or selected_lane is None:
        return []
    if requested_action not in _LANE_TO_ACTIONS.get(selected_lane, set()):
        return []
    return [f"telegram:{requested_action}"]


def _blocked_reasons(result: Any) -> list[str]:
    blocking = _as_string_list(getattr(result, "blocking_reasons", []))
    if blocking:
        return _dedupe(blocking)
    status = str(getattr(result, "status", "") or "")
    selected_lane = getattr(result, "selected_lane", None)
    if selected_lane is not None and status in {"completed", "partial", "sent"}:
        return []
    if status in {"blocked", "failed"} or selected_lane is None:
        return _dedupe(_as_string_list(getattr(result, "reasons", [])))
    return []


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
