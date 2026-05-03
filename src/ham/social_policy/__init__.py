"""Persisted Social Policy Store (D.1).

This package owns ``.ham/social_policy.json`` with a preview / apply /
rollback contract that mirrors :mod:`src.ham.settings_write`. It does
**not** call providers, start schedulers, mutate ``.env``, or replace any
existing live-apply gate. It only persists user *intent* for HAMgomoon /
Ham social behavior.

Re-exports the public names used by the API router.
"""
from __future__ import annotations

from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    SOCIAL_POLICY_REL_PATH,
    ChannelTarget,
    ContentStyle,
    PersonaRef,
    PostingCaps,
    ProviderPolicy,
    ReplyCaps,
    SafetyRules,
    SocialPolicy,
    SocialPolicyChanges,
    redact_string_field,
)
from src.ham.social_policy.store import (
    APPLY_CONFIRMATION_PHRASE,
    LIVE_AUTONOMY_CONFIRMATION_PHRASE,
    ROLLBACK_CONFIRMATION_PHRASE,
    ApplyResult,
    PreviewResult,
    RollbackResult,
    SocialPolicyApplyError,
    SocialPolicyWriteConflictError,
    apply_social_policy,
    list_audit_envelopes,
    list_backups,
    preview_social_policy,
    read_social_policy_document,
    revision_for_document,
    rollback_social_policy,
    social_policy_path,
    social_policy_writes_enabled,
)

__all__ = [
    "APPLY_CONFIRMATION_PHRASE",
    "ApplyResult",
    "ChannelTarget",
    "ContentStyle",
    "DEFAULT_SOCIAL_POLICY",
    "LIVE_AUTONOMY_CONFIRMATION_PHRASE",
    "PersonaRef",
    "PostingCaps",
    "PreviewResult",
    "ProviderPolicy",
    "ReplyCaps",
    "ROLLBACK_CONFIRMATION_PHRASE",
    "RollbackResult",
    "SOCIAL_POLICY_REL_PATH",
    "SafetyRules",
    "SocialPolicy",
    "SocialPolicyApplyError",
    "SocialPolicyChanges",
    "SocialPolicyWriteConflictError",
    "apply_social_policy",
    "list_audit_envelopes",
    "list_backups",
    "preview_social_policy",
    "read_social_policy_document",
    "redact_string_field",
    "revision_for_document",
    "rollback_social_policy",
    "social_policy_path",
    "social_policy_writes_enabled",
]
