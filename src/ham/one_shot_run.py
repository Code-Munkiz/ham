"""Single Ham bridge + review + persist cycle at an explicit project root (CLI + operator API)."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.bridge.contracts import CommandSpec, ExecutionIntent, LimitSpec, ScopeSpec
from src.bridge.runtime import run_bridge_v0
from src.hermes_feedback import HermesReviewer
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY, KeywordSelector
from src.swarm_agency import assemble_ham_run

from src.ham.run_persist import persist_ham_run_record

_MAX_REVIEW_CONTEXT_CHARS = 1_000
_SELECTOR = KeywordSelector()


def select_intent_profile(prompt: str) -> str:
    return _SELECTOR.select(prompt)


def build_runtime_intent(prompt: str, profile_id: str, project_root: Path) -> ExecutionIntent:
    root = project_root.resolve()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()[:12]
    argv = DEFAULT_PROFILE_REGISTRY.get(profile_id).argv
    return ExecutionIntent(
        intent_id=f"intent-{prompt_hash}",
        request_id=f"request-{prompt_hash}",
        run_id=f"run-{prompt_hash}",
        task_class="inspect",
        commands=[
            CommandSpec(
                command_id="inspect-1",
                argv=argv,
                working_dir=str(root),
            )
        ],
        scope=ScopeSpec(allowed_roots=[str(root)], allow_network=False, allow_write=False),
        limits=LimitSpec(
            max_commands=1,
            timeout_sec_per_command=5,
            max_stdout_chars=2000,
            max_stderr_chars=2000,
            max_total_output_chars=4000,
        ),
        reason=f"supervisory runtime intent ({profile_id}) for prompt hash {prompt_hash}",
    )


def _build_runtime_envelope(
    prompt: str,
    profile_id: str,
    bridge_result: object,
    review: dict[str, Any],
) -> dict[str, Any]:
    if hasattr(bridge_result, "model_dump"):
        bridge_payload = bridge_result.model_dump()
    elif hasattr(bridge_result, "dict"):
        bridge_payload = bridge_result.dict()
    else:
        bridge_payload = bridge_result
    return {
        "prompt_summary": prompt[:200],
        "intent_profile_id": profile_id,
        "bridge_result": bridge_payload,
        "hermes_review": review,
    }


@dataclass(frozen=True)
class OneShotRunResult:
    ok: bool
    run_id: str
    profile_id: str
    persist_path: str | None
    bridge_status: str
    summary: str
    envelope: dict[str, Any] | None
    error: str | None = None


def run_ham_one_shot(
    project_root: Path,
    prompt: str,
    *,
    profile_id: str | None = None,
) -> OneShotRunResult:
    """
    Execute inspect-class bridge at ``project_root``, Hermes review, persist under ``.ham/runs/``.

    Requires ``OPENROUTER_API_KEY`` for reviewer (same as ``main.py``).
    """
    if not os.getenv("OPENROUTER_API_KEY"):
        return OneShotRunResult(
            ok=False,
            run_id="",
            profile_id="",
            persist_path=None,
            bridge_status="blocked",
            summary="",
            envelope=None,
            error="OPENROUTER_API_KEY is not set on the API host — bridge review cannot run.",
        )

    root = project_root.resolve()
    pid = profile_id or select_intent_profile(prompt)
    assembly = assemble_ham_run(prompt, project_root=root)
    intent = build_runtime_intent(prompt, pid, root)
    bridge_result = run_bridge_v0(assembly, intent)
    review_assembly = assembly
    if bridge_result.mutation_detected is True:
        review_assembly = assemble_ham_run(prompt, project_root=root)
    review_context = review_assembly.critic_backstory[:_MAX_REVIEW_CONTEXT_CHARS]

    if hasattr(bridge_result, "model_dump"):
        bridge_json = json.dumps(
            bridge_result.model_dump(),
            sort_keys=True,
            ensure_ascii=True,
        )
    elif hasattr(bridge_result, "dict"):
        bridge_json = json.dumps(
            bridge_result.dict(),
            sort_keys=True,
            ensure_ascii=True,
        )
    else:
        bridge_json = str(bridge_result)

    try:
        review: dict[str, Any] = HermesReviewer().evaluate(bridge_json, review_context)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        review = {
            "ok": False,
            "notes": [f"Hermes review handoff failed ({type(exc).__name__})."],
            "code": bridge_json[:1000],
            "context": review_context[:1000],
        }

    rid = str(getattr(bridge_result, "run_id", ""))
    path = persist_ham_run_record(
        root,
        prompt=prompt,
        profile_id=pid,
        bridge_result=bridge_result,
        review=review,
    )
    status = str(getattr(bridge_result, "status", ""))
    summ = str(getattr(bridge_result, "summary", "") or "")
    env = _build_runtime_envelope(prompt, pid, bridge_result, review)
    return OneShotRunResult(
        ok=True,
        run_id=rid,
        profile_id=pid,
        persist_path=str(path) if path else None,
        bridge_status=status,
        summary=summ[:500],
        envelope=env,
        error=None,
    )
