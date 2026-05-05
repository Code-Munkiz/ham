"""Pure advisory helpers for the persisted :class:`SocialPolicy`.

This module is **read-only and side-effect free**. It computes stable
``policy_*`` reason codes that frontends and snapshot routes can render
alongside (never replacing) the existing apply-gate ``reasons`` lists.

Hard contract:

* No file I/O. Callers pass in a :class:`SocialPolicy` (or ``None`` when
  the caller already knows the document is missing or malformed).
* No imports from live transports, schedulers, runners, or the ``goham_*``
  modules. Imports limited to :mod:`src.ham.social_policy.schema` and
  the standard library.
* All public functions are total — they never raise on bad input. They
  return ``[POLICY_DOCUMENT_MISSING]`` (or similar) instead.
* Output is always **sorted + deduped**, so callers can compare lists
  byte-for-byte in assertions.

These helpers are *advisory only*: they intentionally never trigger an
apply block. The existing ``_*_apply_reasons`` helpers in
:mod:`src.api.social` continue to be the sole source of enforcement.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from src.ham.social_policy.schema import ProviderPolicy, SocialPolicy

ProviderId = Literal["x", "telegram", "discord"]
LaneKind = Literal["broadcast", "reactive"]
ActionKind = Literal["post", "quote", "reply"]

# ---------------------------------------------------------------------------
# Stable advisory reason codes.
# ---------------------------------------------------------------------------

POLICY_DOCUMENT_MISSING = "policy_document_missing"
POLICY_PROVIDER_UNMAPPED = "policy_provider_unmapped"
POLICY_POSTING_MODE_OFF = "policy_posting_mode_off"
POLICY_REPLY_MODE_OFF = "policy_reply_mode_off"
POLICY_TARGET_LABEL_DISABLED = "policy_target_label_disabled"
POLICY_LIVE_AUTONOMY_NOT_ARMED = "policy_live_autonomy_not_armed"
POLICY_ACTION_NOT_ALLOWED = "policy_action_not_allowed"

ADVISORY_REASON_CODES: tuple[str, ...] = (
    POLICY_ACTION_NOT_ALLOWED,
    POLICY_DOCUMENT_MISSING,
    POLICY_LIVE_AUTONOMY_NOT_ARMED,
    POLICY_POSTING_MODE_OFF,
    POLICY_PROVIDER_UNMAPPED,
    POLICY_REPLY_MODE_OFF,
    POLICY_TARGET_LABEL_DISABLED,
)


def _sorted_unique(items: Iterable[str]) -> list[str]:
    return sorted({item for item in items if isinstance(item, str)})


def policy_for_provider(
    policy: SocialPolicy | None,
    provider_id: ProviderId,
) -> ProviderPolicy | None:
    """Return the per-provider sub-policy, or ``None`` if absent."""
    if policy is None:
        return None
    providers = getattr(policy, "providers", {}) or {}
    return providers.get(provider_id)


def _target_enabled(provider: ProviderPolicy, target_label: str) -> bool:
    for target in provider.targets:
        if target.label == target_label:
            return bool(target.enabled)
    return False


def policy_advisory_reasons_for_lane(
    policy: SocialPolicy | None,
    *,
    provider_id: ProviderId,
    lane: LaneKind,
    target_label: str | None = None,
) -> list[str]:
    """Compute advisory codes for a *read* of a lane status surface.

    ``policy_live_autonomy_not_armed`` is intentionally *never* emitted at
    the lane level; it is reserved for apply-action contexts where the
    armed flag would actually matter.
    """
    if policy is None:
        return [POLICY_DOCUMENT_MISSING]
    provider = policy_for_provider(policy, provider_id)
    if provider is None:
        return [POLICY_PROVIDER_UNMAPPED]
    out: list[str] = []
    if lane == "broadcast" and provider.posting_mode == "off":
        out.append(POLICY_POSTING_MODE_OFF)
    if lane == "reactive" and provider.reply_mode == "off":
        out.append(POLICY_REPLY_MODE_OFF)
    if target_label is not None and not _target_enabled(provider, target_label):
        out.append(POLICY_TARGET_LABEL_DISABLED)
    return _sorted_unique(out)


def policy_advisory_reasons_for_apply(
    policy: SocialPolicy | None,
    *,
    provider_id: ProviderId,
    action: ActionKind,
    target_label: str | None = None,
) -> list[str]:
    """Compute advisory codes for a hypothetical apply action.

    Always advisory — the result must never feed the apply gate. The
    enforcement code paths in :mod:`src.api.social` remain the sole
    decider of whether an apply executes.
    """
    if policy is None:
        return [POLICY_DOCUMENT_MISSING]
    provider = policy_for_provider(policy, provider_id)
    if provider is None:
        return [POLICY_PROVIDER_UNMAPPED]
    out: list[str] = []
    if action == "reply" and provider.reply_mode == "off":
        out.append(POLICY_REPLY_MODE_OFF)
    if action in {"post", "quote"} and provider.posting_mode == "off":
        out.append(POLICY_POSTING_MODE_OFF)
    if action not in set(provider.posting_actions_allowed):
        out.append(POLICY_ACTION_NOT_ALLOWED)
    if target_label is not None and not _target_enabled(provider, target_label):
        out.append(POLICY_TARGET_LABEL_DISABLED)
    if not policy.live_autonomy_armed or policy.autopilot_mode != "armed":
        out.append(POLICY_LIVE_AUTONOMY_NOT_ARMED)
    return _sorted_unique(out)


def policy_revision_summary(policy: SocialPolicy | None) -> dict[str, Any]:
    """Return a small read-only summary block suitable for response embedding.

    Never includes raw policy contents — only the metadata flags a UI
    layer needs to gate its own copy. ``policy_to_safe_dict`` from the
    schema module is the canonical full-policy serialiser.
    """
    if policy is None:
        return {
            "autopilot_mode": "off",
            "live_autonomy_armed": False,
            "policy_present": False,
        }
    return {
        "autopilot_mode": policy.autopilot_mode,
        "live_autonomy_armed": bool(policy.live_autonomy_armed),
        "policy_present": True,
    }


__all__ = [
    "ADVISORY_REASON_CODES",
    "ActionKind",
    "LaneKind",
    "POLICY_ACTION_NOT_ALLOWED",
    "POLICY_DOCUMENT_MISSING",
    "POLICY_LIVE_AUTONOMY_NOT_ARMED",
    "POLICY_POSTING_MODE_OFF",
    "POLICY_PROVIDER_UNMAPPED",
    "POLICY_REPLY_MODE_OFF",
    "POLICY_TARGET_LABEL_DISABLED",
    "ProviderId",
    "policy_advisory_reasons_for_apply",
    "policy_advisory_reasons_for_lane",
    "policy_for_provider",
    "policy_revision_summary",
]
