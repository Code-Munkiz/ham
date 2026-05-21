"""Dry-run X caller for GoHAM Social autonomy ticks.

The tick service owns profile/channel/action/cap/content gates. This module is
only a thin composition layer over the existing HAM-on-X reactive runners and
normalizes their dry-run result into the slice consumed by
``SocialAutonomyTickResult`` aggregation.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, Protocol

from src.ham.ham_x import goham_reactive_batch, goham_reactive_live
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.reactive_reply_executor import (
    ReactiveReplyRequest,
    ReactiveReplyResult,
)

__all__ = ["X_REACTIVE_RUNNER_ERROR", "dry_run"]

X_REACTIVE_RUNNER_ERROR: Final = "x_reactive_runner_error"

_DRY_RUN_ONLY_REASONS: Final[frozenset[str]] = frozenset(
    {
        "reactive_dry_run_enabled",
        "reactive_live_canary_required",
    }
)
_BATCH_ITEM_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset({"dry_run", "executed"})
_LIVE_ACTIONS: Final[frozenset[str]] = frozenset({"reply", "live_reply"})
_BATCH_ACTIONS: Final[frozenset[str]] = frozenset({"broadcast", "batch", "reply_batch"})


class _Runner(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Reactive runner callable boundary."""


def dry_run(
    action: Mapping[str, Any],
    *,
    config: HamXConfig | None = None,
) -> dict[str, Any]:
    """Invoke the HAM-on-X reactive dry-run path and normalize the result.

    ``dry_run`` never asks the runner to perform live transport. It passes a
    conservative config with dry-run flags enabled plus a provider-call guard
    for the lower-level ``run_reply`` hook.
    """

    action_name = _action_name(action)
    try:
        if _runner_kind(action) == "batch":
            result = _run_batch(action, action_name=action_name, config=config)
            return _normalize_batch_result(result, action_name)
        result = _run_live(action, action_name=action_name, config=config)
        return _normalize_live_result(result, action_name)
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001 - caller contract surfaces structured failures.
        return _failure_result(action_name, diagnostic=str(exc))


def _run_live(
    action: Mapping[str, Any],
    *,
    action_name: str,
    config: HamXConfig | None,
) -> Any:
    cfg = _dry_run_config(config, runner_kind="live")
    prepared = _prepared_inbound(action, action_name=action_name)
    return _invoke_runner(
        goham_reactive_live.run_reactive_live_once,
        prepared,
        config=cfg,
        run_reply=_blocked_live_transport,
    )


def _run_batch(
    action: Mapping[str, Any],
    *,
    action_name: str,
    config: HamXConfig | None,
) -> Any:
    cfg = _dry_run_config(config, runner_kind="batch")
    candidate = _prepared_inbound(action, action_name=action_name)
    return _invoke_runner(
        goham_reactive_batch.run_reactive_batch_once,
        [candidate],
        config=cfg,
        run_reply=_blocked_live_transport,
    )


def _invoke_runner(runner: _Runner, *args: Any, **kwargs: Any) -> Any:
    """Call a runner, passing ``dry_run=True`` when that surface supports it."""

    signature = inspect.signature(runner)
    parameters = signature.parameters
    if "dry_run" in parameters:
        kwargs["dry_run"] = True
    return runner(*args, **kwargs)


def _dry_run_config(
    config: HamXConfig | None,
    *,
    runner_kind: str,
) -> HamXConfig:
    base = config or _safe_default_config()
    updates: dict[str, Any] = {
        "enable_goham_reactive": True,
        "goham_reactive_dry_run": True,
        "goham_reactive_live_canary": False,
    }
    if runner_kind == "batch":
        updates.update(
            {
                "enable_goham_reactive_batch": True,
                "goham_reactive_batch_dry_run": True,
                "goham_reactive_batch_max_replies_per_run": max(
                    1,
                    base.goham_reactive_batch_max_replies_per_run,
                ),
            }
        )
    return replace(base, **updates)


def _safe_default_config() -> HamXConfig:
    cfg = load_ham_x_config()
    sink = Path(os.devnull)
    return replace(cfg, audit_log_path=sink, execution_journal_path=sink)


def _prepared_inbound(action: Mapping[str, Any], *, action_name: str) -> dict[str, Any]:
    text = _action_text(action, action_name=action_name)
    digest = hashlib.sha256(f"{action_name}:{text}".encode()).hexdigest()[:16]
    inbound_id = str(action.get("inbound_id") or f"social-autonomy-{digest}")
    post_id = str(action.get("post_id") or f"social-autonomy-post-{digest}")
    thread_id = str(action.get("thread_id") or post_id)
    return {
        "inbound_id": inbound_id,
        "inbound_type": "mention",
        "text": text,
        "author_id": str(action.get("author_id") or "social-autonomy-dry-run-author"),
        "author_handle": str(action.get("author_handle") or "ham_operator"),
        "post_id": post_id,
        "thread_id": thread_id,
        "conversation_id": str(action.get("conversation_id") or thread_id),
        "in_reply_to_post_id": str(action.get("in_reply_to_post_id") or post_id),
        "relevance_score": float(action.get("relevance_score") or 1.0),
        "metadata": {
            "source": "social_autonomy_x_caller",
            "requested_action": action_name,
        },
    }


def _action_text(action: Mapping[str, Any], *, action_name: str) -> str:
    for key in ("payload", "summary", "text", "draft"):
        value = str(action.get(key) or "").strip()
        if value:
            return _reactive_batch_text(value) if action_name in _BATCH_ACTIONS else value
    fallback = "HAM social autonomy dry-run candidate"
    return _reactive_batch_text(fallback) if action_name in _BATCH_ACTIONS else fallback


def _reactive_batch_text(text: str) -> str:
    if "?" in text:
        return text
    return f"How should HAM operators think about {text.rstrip('.')}?"


def _action_name(action: Mapping[str, Any]) -> str:
    raw = str(action.get("action") or "reply").strip().lower()
    return raw or "reply"


def _runner_kind(action: Mapping[str, Any]) -> str:
    requested = str(action.get("runner") or action.get("mode") or "").strip().lower()
    if requested in {"batch", "reactive_batch"}:
        return "batch"
    if requested in {"live", "reactive_live"}:
        return "live"
    action_name = _action_name(action)
    if action_name in _BATCH_ACTIONS:
        return "batch"
    if action_name in _LIVE_ACTIONS:
        return "live"
    return "batch"


def _normalize_live_result(result: Any, action_name: str) -> dict[str, Any]:
    status = _status(result)
    reasons = _reasons(result)
    if status in {"dry_run", "completed", "executed"} or (
        status == "blocked" and reasons and set(reasons) <= _DRY_RUN_ONLY_REASONS
    ):
        return _success_result(action_name)
    return _blocked_result(action_name, reasons or [X_REACTIVE_RUNNER_ERROR])


def _normalize_batch_result(result: Any, action_name: str) -> dict[str, Any]:
    reasons = _reasons(result)
    items = list(getattr(result, "items", []) or [])
    item_reasons = _blocked_batch_item_reasons(items)
    has_successful_item = any(_is_successful_batch_item(item) for item in items)
    blocked = _dedupe([*reasons, *item_reasons])
    if _status(result) == "completed" and has_successful_item:
        return _success_result(action_name, blocked_reasons=blocked)
    return _blocked_result(action_name, blocked or [X_REACTIVE_RUNNER_ERROR])


def _is_successful_batch_item(item: Any) -> bool:
    status = _status(item)
    reasons = _reasons(item)
    return status in _BATCH_ITEM_SUCCESS_STATUSES or (
        status == "blocked" and reasons and set(reasons) <= _DRY_RUN_ONLY_REASONS
    )


def _blocked_batch_item_reasons(items: list[Any]) -> list[str]:
    reasons: list[str] = []
    for item in items:
        if item is None or _is_successful_batch_item(item):
            continue
        reasons.extend(f"x_reactive_item_blocked:{reason}" for reason in _reasons(item))
    return _dedupe(reasons)


def _success_result(
    action_name: str, *, blocked_reasons: list[str] | None = None
) -> dict[str, Any]:
    return {
        "channel": "x",
        "action": action_name,
        "actions_taken": [f"x:{action_name}"],
        "blocked_reasons": _dedupe(blocked_reasons or []),
        "dry_run": True,
        "execution_allowed": True,
    }


def _blocked_result(action_name: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "channel": "x",
        "action": action_name,
        "actions_taken": [],
        "blocked_reasons": _dedupe(reasons),
        "dry_run": True,
        "execution_allowed": False,
    }


def _failure_result(action_name: str, *, diagnostic: str) -> dict[str, Any]:
    result = _blocked_result(action_name, [X_REACTIVE_RUNNER_ERROR])
    if diagnostic:
        result["diagnostic"] = diagnostic
    return result


def _status(result: Any) -> str:
    return str(getattr(result, "status", "") or "").strip().lower()


def _reasons(result: Any) -> list[str]:
    value = getattr(result, "reasons", [])
    if not isinstance(value, list):
        return []
    return _dedupe([str(item) for item in value if str(item)])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _blocked_live_transport(_request: ReactiveReplyRequest) -> ReactiveReplyResult:
    raise AssertionError("live X transport attempted in x_caller dry_run")
