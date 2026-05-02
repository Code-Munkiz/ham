"""HAMgomoon Telegram autopilot run-once orchestrator.

This module deliberately does not schedule, loop, or own provider transport.
It coordinates the existing bounded Telegram lane run_once controllers exactly
once per invocation.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import load_ham_x_config
from src.ham.social_telegram_activity import TelegramActivityKind
from src.ham.social_telegram_activity_runner import (
    TelegramActivityRunConfig,
    TelegramActivityRunResult,
    run_telegram_activity_once,
)
from src.ham.social_telegram_reactive_runner import (
    TelegramReactiveRunConfig,
    TelegramReactiveRunResult,
    run_telegram_reactive_once,
)
from src.ham.social_telegram_send import TelegramTransport

HamgomoonAutopilotStatus = Literal["completed", "blocked", "sent", "failed", "partial"]


class HamgomoonAutopilotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    allow_both_live_lanes: bool = False
    readiness: str = "setup_required"
    gateway_runtime_state: str = "unknown"
    emergency_stop: bool | None = None
    activity_kind: TelegramActivityKind = "test_activity"
    transcript_paths: list[Path] | None = None
    delivery_log_path: Path | None = None
    now: datetime | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    reactive_hourly_cap: int = Field(default=2, ge=0, le=24)
    reactive_daily_cap: int = Field(default=3, ge=0, le=100)


class HamgomoonAutopilotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_kind: Literal["hamgomoon_autopilot_run_once"] = "hamgomoon_autopilot_run_once"
    status: HamgomoonAutopilotStatus = "blocked"
    dry_run: bool = True
    execution_allowed: bool = False
    mutation_attempted: bool = False
    lane_order: list[str] = Field(default_factory=list)
    reactive: dict[str, object] | None = None
    activity: dict[str, object] | None = None
    skipped_lanes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, object] = Field(default_factory=dict)


def run_hamgomoon_autopilot_once(
    config: HamgomoonAutopilotConfig | None = None,
    *,
    reactive_transport: TelegramTransport | None = None,
    activity_transport: TelegramTransport | None = None,
) -> HamgomoonAutopilotResult:
    cfg = config or HamgomoonAutopilotConfig()
    emergency_stop = _resolve_emergency_stop(cfg.emergency_stop)

    if cfg.dry_run:
        reactive = run_telegram_reactive_once(
            _reactive_config(cfg, dry_run=True),
            transport=reactive_transport,
        )
        activity = run_telegram_activity_once(
            _activity_config(cfg, dry_run=True, emergency_stop=emergency_stop),
            transport=activity_transport,
        )
        return _compose_result(
            cfg=cfg,
            reactive=reactive,
            activity=activity,
            lane_order=["reactive", "activity"],
            skipped_lanes=[],
            extra_reasons=[],
            mode="dry_run",
        )

    gate_reasons = _global_live_gate_reasons(emergency_stop=emergency_stop)
    if gate_reasons:
        return HamgomoonAutopilotResult(
            status="blocked",
            dry_run=False,
            execution_allowed=False,
            mutation_attempted=False,
            lane_order=[],
            reasons=gate_reasons,
            result={"mode": "live_blocked"},
        )

    lane_order = ["reactive"]
    skipped_lanes: list[str] = []
    reactive = run_telegram_reactive_once(
        _reactive_config(cfg, dry_run=False),
        transport=reactive_transport,
    )
    activity: TelegramActivityRunResult | None = None
    if reactive.status == "sent" and not cfg.allow_both_live_lanes:
        skipped_lanes.append("activity")
    else:
        lane_order.append("activity")
        activity = run_telegram_activity_once(
            _activity_config(cfg, dry_run=False, emergency_stop=emergency_stop),
            transport=activity_transport,
        )

    reasons: list[str] = []
    if "activity" in skipped_lanes:
        reasons.append("activity_skipped_after_reactive_send")
    return _compose_result(
        cfg=cfg,
        reactive=reactive,
        activity=activity,
        lane_order=lane_order,
        skipped_lanes=skipped_lanes,
        extra_reasons=reasons,
        mode="live_once",
    )


def _reactive_config(cfg: HamgomoonAutopilotConfig, *, dry_run: bool) -> TelegramReactiveRunConfig:
    return TelegramReactiveRunConfig(
        dry_run=dry_run,
        readiness=cfg.readiness,
        gateway_runtime_state=cfg.gateway_runtime_state,
        transcript_paths=cfg.transcript_paths,
        delivery_log_path=cfg.delivery_log_path,
        now=cfg.now,
        timeout_seconds=cfg.timeout_seconds,
        hourly_cap=cfg.reactive_hourly_cap,
        daily_cap=cfg.reactive_daily_cap,
    )


def _activity_config(
    cfg: HamgomoonAutopilotConfig,
    *,
    dry_run: bool,
    emergency_stop: bool,
) -> TelegramActivityRunConfig:
    return TelegramActivityRunConfig(
        activity_kind=cfg.activity_kind,
        dry_run=dry_run,
        readiness=cfg.readiness,
        gateway_runtime_state=cfg.gateway_runtime_state,
        emergency_stop=emergency_stop,
        now=cfg.now,
        delivery_log_path=cfg.delivery_log_path,
        timeout_seconds=cfg.timeout_seconds,
    )


def _global_live_gate_reasons(*, emergency_stop: bool) -> list[str]:
    reasons: list[str] = []
    if (os.environ.get("HAMGOMOON_AUTOPILOT_ENABLED") or "").strip().lower() != "true":
        reasons.append("hamgomoon_autopilot_disabled")
    if (os.environ.get("HAMGOMOON_AUTOPILOT_DRY_RUN") or "true").strip().lower() != "false":
        reasons.append("hamgomoon_autopilot_dry_run_enabled")
    if emergency_stop:
        reasons.append("emergency_stop")
    return reasons


def _resolve_emergency_stop(explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    try:
        return bool(load_ham_x_config().emergency_stop)
    except Exception:
        return False


def _compose_result(
    *,
    cfg: HamgomoonAutopilotConfig,
    reactive: TelegramReactiveRunResult | None,
    activity: TelegramActivityRunResult | None,
    lane_order: list[str],
    skipped_lanes: list[str],
    extra_reasons: list[str],
    mode: str,
) -> HamgomoonAutopilotResult:
    lane_results = [item for item in (reactive, activity) if item is not None]
    reasons = _dedupe(
        [
            *extra_reasons,
            *(reactive.reasons if reactive is not None else []),
            *(activity.reasons if activity is not None else []),
        ]
    )
    warnings = _dedupe(
        [
            *(reactive.warnings if reactive is not None else []),
            *(activity.warnings if activity is not None else []),
        ]
    )
    mutation_attempted = any(bool(item.mutation_attempted) for item in lane_results)
    execution_allowed = any(bool(item.execution_allowed) for item in lane_results)
    return HamgomoonAutopilotResult(
        status=_status_for_lanes(lane_results=lane_results, reasons=reasons, skipped_lanes=skipped_lanes),
        dry_run=cfg.dry_run,
        execution_allowed=execution_allowed,
        mutation_attempted=mutation_attempted,
        lane_order=lane_order,
        reactive=reactive.model_dump(mode="json") if reactive is not None else None,
        activity=activity.model_dump(mode="json") if activity is not None else None,
        skipped_lanes=skipped_lanes,
        reasons=reasons,
        warnings=warnings,
        result={
            "mode": mode,
            "allow_both_live_lanes": bool(cfg.allow_both_live_lanes),
            "lanes_attempted": lane_order,
            "lanes_skipped": skipped_lanes,
        },
    )


def _status_for_lanes(
    *,
    lane_results: list[TelegramReactiveRunResult | TelegramActivityRunResult],
    reasons: list[str],
    skipped_lanes: list[str],
) -> HamgomoonAutopilotStatus:
    statuses = [str(item.status) for item in lane_results]
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "sent" for status in statuses):
        return "sent"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    if reasons and not skipped_lanes:
        return "blocked"
    return "completed"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _cli_summary(result: HamgomoonAutopilotResult) -> dict[str, object]:
    return {
        "run_kind": result.run_kind,
        "status": result.status,
        "dry_run": result.dry_run,
        "execution_allowed": result.execution_allowed,
        "mutation_attempted": result.mutation_attempted,
        "lane_order": result.lane_order,
        "skipped_lanes": result.skipped_lanes,
        "reasons": result.reasons[:12],
        "warnings": result.warnings[:12],
        "reactive_status": result.reactive.get("status") if isinstance(result.reactive, dict) else None,
        "activity_status": result.activity.get("status") if isinstance(result.activity, dict) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HAMgomoon Telegram autopilot once.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Preview both lanes without mutation (default).")
    group.add_argument("--live-once", action="store_true", help="Attempt one live autopilot pass if all env gates allow it.")
    parser.add_argument("--allow-both", action="store_true", help="Allow activity after a reactive live send.")
    args = parser.parse_args(argv)

    result = run_hamgomoon_autopilot_once(
        HamgomoonAutopilotConfig(
            dry_run=not bool(args.live_once),
            allow_both_live_lanes=bool(args.allow_both),
        )
    )
    print(json.dumps(_cli_summary(result), sort_keys=True))
    return 0 if result.status in {"completed", "sent"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
