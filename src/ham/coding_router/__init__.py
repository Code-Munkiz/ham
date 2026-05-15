"""HAM Coding Router — backend decision layer for chat-first orchestration.

Phase 1: pure, read-only primitives only.

- :mod:`types` — shared dataclasses + Literal aliases (no behaviour).
- :mod:`classify` — deterministic, regex-driven task classifier.
- :mod:`readiness` — boolean collation of provider readiness (no secret values).
- :mod:`recommend` — pure ranker that turns a task + readiness into Candidates.

The conductor preview/launch endpoints are **not** part of this phase. Each
provider keeps its own launch route (Cursor missions, ``/api/droid/preview``,
``/api/droid/build/preview``) and its own safety gates. The Coding Router is
allowed to read env presence and project flags, but **never** echoes secret
values, internal workflow ids (``safe_edit_low``), argv, runner URLs, or env
names like ``HAM_DROID_EXEC_TOKEN`` to non-operator surfaces.
"""

from src.ham.coding_router.classify import classify_task
from src.ham.coding_router.readiness import collate_readiness
from src.ham.coding_router.recommend import recommend
from src.ham.coding_router.types import (
    Candidate,
    CodingTask,
    ModelSourcePreference,
    PreferenceMode,
    ProjectFlags,
    ProviderKind,
    ProviderReadiness,
    TaskKind,
    WorkspaceAgentPolicy,
    WorkspaceReadiness,
)

__all__ = [
    "Candidate",
    "CodingTask",
    "ModelSourcePreference",
    "PreferenceMode",
    "ProjectFlags",
    "ProviderKind",
    "ProviderReadiness",
    "TaskKind",
    "WorkspaceAgentPolicy",
    "WorkspaceReadiness",
    "classify_task",
    "collate_readiness",
    "recommend",
]
