"""Pluggable Hermes-style social critic.

The default implementation is a deterministic stub. A future implementation
could route through :class:`src.hermes_feedback.HermesReviewer.evaluate(...)`
with a social-critic prompt variant (currently the reviewer prompt is
code-review oriented); leave that wiring for a follow-up — the contract here
is intentionally LLM-free so tests can inject a mock critic without touching
network.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol, runtime_checkable

from src.ham.hamgomoon_learning.models import (
    DeliveryOutcome,
    HermesSocialCritique,
    LearningRecord,
    ReviewOutcome,
    SocialDraftRecord,
)


@runtime_checkable
class SocialCritic(Protocol):
    def critique(
        self, draft: SocialDraftRecord
    ) -> HermesSocialCritique:  # pragma: no cover - protocol
        ...


class StubSocialCritic:
    """Deterministic, offline-safe critic. Returns conservative high scores."""

    def critique(self, draft: SocialDraftRecord) -> HermesSocialCritique:
        return HermesSocialCritique(
            draft_id=draft.draft_id,
            brand_fit_score=0.9,
            safety_score=0.95,
            clarity_score=0.85,
            engagement_hypothesis="Stub critic: no live model used.",
            risk_flags=[],
            suggested_improvement=None,
            reusable_lesson="Keep drafts brief and persona-consistent.",
            policy_suggestion=None,
            should_update_strategy=False,
        )

    def review(self, tick_result: Any) -> LearningRecord:
        """Convert a social-autonomy tick result into a deterministic record.

        This is deliberately offline-only: it summarizes the tick result and
        reuses the local stub critique. Redaction is performed again by the
        learning hook and JSONL store before persistence.
        """

        data = _to_mapping(tick_result)
        status = _string_field(data, tick_result, "profile_status_at_tick", "profile_status")
        actions_taken_raw = _list_field(data, tick_result, "actions_taken")
        blocked_reasons = [
            str(reason)
            for reason in _list_field(data, tick_result, "blocked_reasons")
            if str(reason).strip()
        ]
        action_labels = [_action_label(action) for action in actions_taken_raw]
        action_labels = [label for label in action_labels if label]
        action_details = [_action_detail(action) for action in actions_taken_raw]
        action_details = [detail for detail in action_details if detail]
        ran = bool(_field(data, tick_result, "ran", default=False))
        dry_run = bool(_field(data, tick_result, "dry_run", default=True))

        channel = _record_channel(actions_taken_raw)
        draft = SocialDraftRecord(
            channel=channel,
            proposed_action=_record_action(actions_taken_raw),
            prompt="GoHAM autonomy tick learning summary.",
            draft_text="\n".join(
                line
                for line in [
                    f"profile_status_at_tick={status or 'unknown'}",
                    f"actions_taken={', '.join(action_labels) if action_labels else 'none'}",
                    (
                        "blocked_reasons="
                        f"{', '.join(blocked_reasons) if blocked_reasons else 'none'}"
                    ),
                    (f"action_details={' | '.join(action_details) if action_details else 'none'}"),
                    _next_run_line(data, tick_result),
                ]
                if line
            ),
            safety_state="preview_blocked" if blocked_reasons else "preview_ok",
        )
        review = ReviewOutcome(
            draft_id=draft.draft_id,
            decision="approved" if ran and not blocked_reasons else "needs_changes",
            reviewer_note="Stub critic review: no live model used.",
            reason_tags=[
                tag
                for tag in [
                    f"profile_status_at_tick:{status or 'unknown'}",
                    *(f"blocked:{reason}" for reason in blocked_reasons),
                    *(f"action:{label}" for label in action_labels),
                ]
                if tag
            ],
        )
        return LearningRecord(
            workspace_id=None,
            project_id=None,
            channel=channel,
            draft=draft,
            review=review,
            delivery=DeliveryOutcome(
                draft_id=draft.draft_id,
                status="dry_run" if dry_run else "not_sent",
                external_platform_id=None,
            ),
            critique=self.critique(draft),
            safe_future_hint="Use tick summaries to tune future dry-run social autonomy behavior.",
        )


def get_default_social_critic() -> SocialCritic:
    """Return the default critic. Tests monkeypatch this to inject mocks."""
    return StubSocialCritic()


__all__ = ["SocialCritic", "StubSocialCritic", "get_default_social_critic"]


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {}


def _field(
    data: Mapping[str, Any],
    source: Any,
    *names: str,
    default: Any = None,
) -> Any:
    for name in names:
        if name in data:
            return data[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _string_field(data: Mapping[str, Any], source: Any, *names: str) -> str:
    value = _field(data, source, *names, default="")
    return str(value).strip() if value is not None else ""


def _list_field(data: Mapping[str, Any], source: Any, name: str) -> list[Any]:
    value = _field(data, source, name, default=[])
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _action_mapping(action: Any) -> Mapping[str, Any]:
    if isinstance(action, Mapping):
        return action
    data = _to_mapping(action)
    return data


def _split_action_id(action: Any) -> tuple[str, str]:
    if not isinstance(action, str) or ":" not in action:
        return "", ""

    raw_channel, raw_action = action.split(":", 1)
    channel = raw_channel.strip().lower()
    action_name = raw_action.strip().lower()
    if channel not in {"x", "telegram", "discord"}:
        return "", ""
    if action_name == "reply":
        return channel, "reply"
    if action_name in {"message", "activity"}:
        return channel, "message"
    if action_name in {"broadcast", "post"}:
        return channel, "post"
    return "", ""


def _action_label(action: Any) -> str:
    if isinstance(action, str):
        return action.strip()
    data = _action_mapping(action)
    channel = str(data.get("channel") or data.get("provider") or "").strip()
    action_name = str(
        data.get("action") or data.get("execution_kind") or data.get("type") or ""
    ).strip()
    if channel and action_name:
        return f"{channel}:{action_name}"
    return channel or action_name


def _action_detail(action: Any) -> str:
    if isinstance(action, str):
        return action.strip()
    data = _action_mapping(action)
    label = _action_label(action)
    fields = []
    for key in (
        "summary",
        "payload_summary",
        "provider_post_id",
        "target_ref",
        "external_user_id",
        "external_platform_id",
    ):
        value = data.get(key)
        if value is not None and str(value).strip():
            fields.append(f"{key}={value}")
    if not fields:
        return label
    return f"{label} ({'; '.join(fields)})" if label else "; ".join(fields)


def _record_channel(actions_taken: list[Any]) -> str:
    for action in actions_taken:
        channel, _ = _split_action_id(action)
        if channel:
            return channel
        data = _action_mapping(action)
        channel = str(data.get("channel") or data.get("provider") or "").strip()
        if channel in {"x", "telegram", "discord"}:
            return channel
    return "other"


def _record_action(actions_taken: list[Any]) -> str:
    for action in actions_taken:
        _, action_name = _split_action_id(action)
        if action_name:
            return action_name
        data = _action_mapping(action)
        action_name = str(data.get("action") or "").strip()
        if action_name == "reply":
            return "reply"
        if action_name in {"message", "activity"}:
            return "message"
        if action_name in {"broadcast", "post"}:
            return "post"
    return "message"


def _next_run_line(data: Mapping[str, Any], source: Any) -> str:
    next_run_summary = _string_field(data, source, "next_run_summary")
    if not next_run_summary:
        return ""
    return f"next_run_summary={next_run_summary}"
