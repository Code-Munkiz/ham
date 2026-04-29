"""Deterministic Phase 1B budget guardrails."""
from __future__ import annotations

from dataclasses import dataclass

from src.ham.ham_x.config import HamXConfig, load_ham_x_config


@dataclass(frozen=True)
class BudgetGuardrailResult:
    allowed: bool
    estimated_spend_usd: float
    daily_limit_usd: float
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "estimated_spend_usd": self.estimated_spend_usd,
            "daily_limit_usd": self.daily_limit_usd,
            "reason": self.reason,
        }


def check_budget_guardrail(
    *,
    estimated_spend_usd: float = 0.0,
    config: HamXConfig | None = None,
) -> BudgetGuardrailResult:
    """Placeholder spend guardrail; Phase 1B defaults to zero estimated spend."""
    cfg = config or load_ham_x_config()
    estimate = max(0.0, float(estimated_spend_usd))
    allowed = estimate <= cfg.daily_spend_limit_usd
    return BudgetGuardrailResult(
        allowed=allowed,
        estimated_spend_usd=estimate,
        daily_limit_usd=cfg.daily_spend_limit_usd,
        reason="" if allowed else "daily_spend_limit_exceeded",
    )
