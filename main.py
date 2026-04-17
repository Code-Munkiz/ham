#!/usr/bin/env python3
"""
Entry point: load env, assemble a minimal Ham run context, accept a CLI prompt.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.bridge.contracts import CommandSpec, ExecutionIntent, LimitSpec, ScopeSpec
from src.bridge.runtime import run_bridge_v0
from src.hermes_feedback import HermesReviewer
from src.llm_client import configure_litellm_env
from src.swarm_agency import assemble_ham_run

INTENT_PROFILE_CATALOG: dict[str, list[str]] = {
    "inspect.cwd": ["python", "-c", "import os; print(os.getcwd())"],
    "inspect.git_status": ["git", "status", "--short"],
    "inspect.git_diff": ["git", "diff", "--name-only"],
}
MAX_REVIEW_CONTEXT_CHARS = 1_000


def _select_intent_profile(prompt: str) -> str:
    tokens = set(re.findall(r"[a-z0-9_]+", prompt.lower()))
    # Precedence is deliberate: status before diff. Do not reorder without updating tests.
    if "status" in tokens:
        return "inspect.git_status"
    if "diff" in tokens:
        return "inspect.git_diff"
    return "inspect.cwd"


def _build_runtime_intent(prompt: str, profile_id: str) -> ExecutionIntent:
    root = Path.cwd().resolve()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()[:12]
    argv = INTENT_PROFILE_CATALOG[profile_id]
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
    review: dict[str, object],
) -> dict[str, object]:
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


def _dump_json(data: object) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    elif hasattr(data, "dict"):
        payload = data.dict()
    else:
        payload = data
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_litellm_env()

    parser = argparse.ArgumentParser(description="ham — autonomous developer swarm")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Hello, swarm.",
        help="User instruction for this run (default: short demo prompt).",
    )
    args = parser.parse_args(argv)

    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
        print("Prompt (would be used for this run):", args.prompt)
        return 0

    assembly = assemble_ham_run(args.prompt)
    profile_id = _select_intent_profile(assembly.user_prompt)
    intent = _build_runtime_intent(assembly.user_prompt, profile_id)
    bridge_result = run_bridge_v0(assembly, intent)
    review_assembly = assembly
    if bridge_result.mutation_detected is True:
        review_assembly = assemble_ham_run(assembly.user_prompt)
    review_context = review_assembly.critic_backstory[:MAX_REVIEW_CONTEXT_CHARS]
    bridge_json = _dump_json(bridge_result)

    try:
        review = HermesReviewer().evaluate(bridge_json, review_context)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        review = {
            "ok": False,
            "notes": [f"Hermes review handoff failed ({type(exc).__name__})."],
            "code": bridge_json[:1000],
            "context": review_context[:1000],
        }

    envelope = _build_runtime_envelope(
        prompt=assembly.user_prompt,
        profile_id=profile_id,
        bridge_result=bridge_result,
        review=review,
    )
    print("RUNTIME_RESULT:", _dump_json(envelope))
    return 0


if __name__ == "__main__":
    sys.exit(main())
