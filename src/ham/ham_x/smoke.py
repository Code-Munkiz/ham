"""Safe smoke harness for HAM-on-X Phase 1D.

Smoke modes are non-mutating. Live-capable modes are opt-in only and still do
not execute posting in Phase 1D.
"""
from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.action_envelope import platform_context_from_config
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.pipeline import PipelineRunResult, run_supervised_opportunity_loop
from src.ham.ham_x.redaction import redact

SmokeMode = Literal["local", "env", "x-readonly", "xai", "e2e-dry-run"]

SECRET_ENV_NAMES = (
    "XAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_BEARER_TOKEN",
)


class SmokeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SmokeMode
    ok: bool
    live_enabled: bool
    network_attempted: bool = False
    mutation_attempted: bool = False
    execution_allowed: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    tenant_id: str
    agent_id: str
    campaign_id: str
    account_id: str
    profile_id: str
    policy_profile_id: str
    brand_voice_id: str
    autonomy_mode: str
    catalog_skill_id: str
    audit_path: str | None = None
    review_queue_path: str | None = None
    exception_queue_path: str | None = None

    def redacted_dump(self) -> dict[str, Any]:
        return redact(self.model_dump(mode="json"))


def run_smoke(mode: str, config: HamXConfig | None = None) -> SmokeResult:
    """Run one HAM-on-X smoke mode without mutating X."""
    cfg = config or load_ham_x_config()
    normalized = _normalize_mode(mode)
    if normalized == "env":
        return _env_smoke(cfg)
    if normalized == "local":
        return _pipeline_smoke(normalized, cfg)
    if normalized == "e2e-dry-run":
        if not cfg.enable_live_smoke:
            return _pipeline_smoke(
                normalized,
                cfg,
                warnings=["live smoke disabled; using fixture candidate data"],
            )
        return _pipeline_smoke(
            normalized,
            cfg,
            warnings=["live e2e smoke not implemented; fixture candidate data used"],
        )
    if normalized == "x-readonly":
        return _readonly_x_smoke(cfg)
    if normalized == "xai":
        return _xai_smoke(cfg)
    raise AssertionError("unreachable")


def _normalize_mode(mode: str) -> SmokeMode:
    value = (mode or "").strip().lower()
    allowed = {"local", "env", "x-readonly", "xai", "e2e-dry-run"}
    if value not in allowed:
        raise ValueError(f"unsupported HAM-on-X smoke mode: {mode!r}")
    return value  # type: ignore[return-value]


def _base_result(
    *,
    mode: SmokeMode,
    config: HamXConfig,
    ok: bool,
    summary: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    network_attempted: bool = False,
) -> SmokeResult:
    ctx = platform_context_from_config(config)
    return SmokeResult(
        mode=mode,
        ok=ok,
        live_enabled=config.enable_live_smoke,
        network_attempted=network_attempted,
        mutation_attempted=False,
        execution_allowed=False,
        summary=redact(summary or {}),
        warnings=list(warnings or []),
        audit_path=str(config.audit_log_path),
        review_queue_path=str(config.review_queue_path),
        exception_queue_path=str(config.exception_queue_path),
        **ctx,
    )


def _pipeline_smoke(
    mode: SmokeMode,
    config: HamXConfig,
    *,
    warnings: list[str] | None = None,
) -> SmokeResult:
    run = run_supervised_opportunity_loop(_fixture_candidates(), config=config)
    return _base_result(
        mode=mode,
        config=config,
        ok=True,
        warnings=warnings,
        summary=_pipeline_summary(run),
    )


def _env_smoke(config: HamXConfig) -> SmokeResult:
    env_status = {
        name: {
            "present": bool((os.environ.get(name) or "").strip()),
            "value": "[REDACTED]" if (os.environ.get(name) or "").strip() else "",
        }
        for name in SECRET_ENV_NAMES
    }
    safe_defaults = {
        "HAM_X_AUTONOMY_ENABLED": config.autonomy_enabled is False,
        "HAM_X_DRY_RUN": config.dry_run is True,
        "HAM_X_ENABLE_LIVE_SMOKE": config.enable_live_smoke is False,
    }
    return _base_result(
        mode="env",
        config=config,
        ok=all(safe_defaults.values()),
        summary={
            "secret_env": env_status,
            "safe_defaults": safe_defaults,
            "emergency_stop": config.emergency_stop,
        },
    )


def _readonly_x_smoke(config: HamXConfig) -> SmokeResult:
    planned = [config.xurl_bin, "search", "base ecosystem builders", "--max-results", "5"]
    if not config.enable_live_smoke:
        return _base_result(
            mode="x-readonly",
            config=config,
            ok=True,
            warnings=["live smoke disabled; read-only xurl execution not attempted"],
            summary={
                "status": "disabled",
                "planned_command": planned,
                "catalog_skill_id": config.catalog_skill_id,
                "safety_status": "not_executed",
                "execution_allowed": False,
            },
        )
    return _base_result(
        mode="x-readonly",
        config=config,
        ok=True,
        warnings=["live read-only xurl smoke not implemented in Phase 1D"],
        summary={
            "status": "not_implemented",
            "planned_command": planned,
            "catalog_skill_id": config.catalog_skill_id,
            "safety_status": "not_executed",
            "execution_allowed": False,
        },
    )


def _xai_smoke(config: HamXConfig) -> SmokeResult:
    if not config.enable_live_smoke:
        return _base_result(
            mode="xai",
            config=config,
            ok=True,
            warnings=["live smoke disabled; xAI request not attempted"],
            summary={
                "status": "disabled",
                "model": config.model,
                "prompt_budget": "tiny_future_smoke",
                "execution_allowed": False,
            },
        )
    return _base_result(
        mode="xai",
        config=config,
        ok=True,
        warnings=["live xAI smoke not implemented in Phase 1D"],
        summary={
            "status": "not_implemented",
            "model": config.model,
            "prompt_budget": "tiny_future_smoke",
            "execution_allowed": False,
        },
    )


def _pipeline_summary(run: PipelineRunResult) -> dict[str, Any]:
    return {
        "candidate_count": len(run.candidates),
        "queued_count": run.queued_count,
        "exception_count": run.exception_count,
        "auto_approved_candidate_count": run.auto_approved_candidate_count,
        "ignored_count": run.ignored_count,
        "statuses": [item.status for item in run.candidates],
        "decisions": [
            item.autonomy_decision.decision if item.autonomy_decision is not None else None
            for item in run.candidates
        ],
    }


def _fixture_candidates() -> list[dict[str, Any]]:
    return [
        {
            "source": "phase_1d_smoke_fixture",
            "source_post_id": "smoke-base-1",
            "source_url": "https://x.example/smoke-base-1",
            "author_handle": "builderalice",
            "text_excerpt": (
                "Base ecosystem builders are shipping open source autonomous "
                "agent tooling for developer workflows."
            ),
            "matched_keywords": ["base", "builders", "autonomous agents"],
        }
    ]
