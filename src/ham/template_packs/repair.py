"""One-shot visual quality repair for native Hermes workspace builds."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from src.ham.hermes_workspace_execution import (
    WorkspaceExecutionOutcome,
    run_hermes_cli_workspace_build,
)
from src.ham.template_packs.quality import visual_quality_repair_instruction
from src.ham.template_packs.schema import TemplatePack

_LOG = logging.getLogger(__name__)
_REPAIR_ENV = "HAM_TEMPLATE_PACK_QUALITY_REPAIR_ENABLED"


def template_pack_quality_repair_enabled() -> bool:
    raw = (os.environ.get(_REPAIR_ENV) or "").strip().lower()
    if not raw:
        return True
    return raw in ("1", "true", "yes", "on")


def attempt_visual_quality_repair(
    *,
    workspace_dir: Path,
    user_prompt: str,
    import_job_id: str,
    pack: TemplatePack,
    files_provider: Callable[..., dict[str, str] | None] | None = None,
) -> dict[str, str] | None:
    """Run at most one repair pass; returns updated files or None."""
    if not template_pack_quality_repair_enabled():
        return None

    repair_prompt = (
        f"{user_prompt.strip()}\n\n{visual_quality_repair_instruction()}\n"
        f"Template pack baseline id (internal): {pack.id}"
    )
    _LOG.warning(
        "template_pack_quality_repair_start import_job_id=%s pack_id=%s",
        import_job_id,
        pack.id,
    )

    if files_provider is not None:
        collected = files_provider(
            workspace_id="",
            project_id="",
            import_job_id=import_job_id,
            user_prompt=repair_prompt,
            workspace_dir=workspace_dir,
            repair_pass=True,
        )
        if isinstance(collected, dict) and collected:
            return collected
        return None

    outcome = run_hermes_cli_workspace_build(
        workspace_dir=workspace_dir,
        user_prompt=repair_prompt,
        import_job_id=import_job_id,
        template_pack=pack,
        skip_seed=True,
    )
    if outcome.ok and outcome.files:
        return outcome.files
    return None


__all__ = [
    "attempt_visual_quality_repair",
    "template_pack_quality_repair_enabled",
]
