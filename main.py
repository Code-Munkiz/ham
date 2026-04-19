#!/usr/bin/env python3
"""
Entry point: load env, assemble a minimal Ham run context, accept a CLI prompt.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.bridge.contracts import CommandSpec, ExecutionIntent, LimitSpec, ScopeSpec
from src.bridge.runtime import run_bridge_v0
from src.hermes_feedback import HermesReviewer
from src.llm_client import configure_litellm_env
from src.registry.backends import DEFAULT_BACKEND_ID, DEFAULT_BACKEND_REGISTRY
from src.registry.profiles import DEFAULT_PROFILE_REGISTRY, KeywordSelector
from src.swarm_agency import assemble_ham_run

MAX_REVIEW_CONTEXT_CHARS = 1_000
# Hermes review echoes bridge JSON + context; huge strings break terminal wrap/reflow.
MAX_STDOUT_HERMES_CODE_CHARS = 1_200
MAX_STDOUT_HERMES_CONTEXT_CHARS = 900
_SELECTOR = KeywordSelector()


def _resolve_author() -> str:
    for var in ("HAM_AUTHOR", "USER", "USERNAME"):
        value = os.environ.get(var)
        if value and value.strip():
            return value.strip()
    return "unknown"


def _select_intent_profile(prompt: str) -> str:
    return _SELECTOR.select(prompt)


def _build_runtime_intent(prompt: str, profile_id: str) -> ExecutionIntent:
    root = Path.cwd().resolve()
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


def _truncate_envelope_for_stdout(envelope: dict[str, object]) -> dict[str, object]:
    """Shorten review strings for human stdout; full envelope is still written under .ham/runs/."""
    out = copy.deepcopy(envelope)
    hr = out.get("hermes_review")
    if not isinstance(hr, dict):
        return out
    for key, limit in (
        ("code", MAX_STDOUT_HERMES_CODE_CHARS),
        ("context", MAX_STDOUT_HERMES_CONTEXT_CHARS),
    ):
        val = hr.get(key)
        if isinstance(val, str) and len(val) > limit:
            omitted = len(val) - limit
            hr[key] = (
                val[:limit]
                + f"... [truncated {omitted} chars; full JSON in .ham/runs/]"
            )
    return out


def _dump_json(data: object, *, indent: int | None = None) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    elif hasattr(data, "dict"):
        payload = data.dict()
    else:
        payload = data
    if indent is not None:
        return json.dumps(payload, sort_keys=True, ensure_ascii=True, indent=indent)
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _persist_run_record(
    *,
    prompt: str,
    profile_id: str,
    bridge_result: object,
    review: dict[str, object],
) -> Path | None:
    try:
        now = datetime.now(timezone.utc)
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        created_at_for_filename = now.strftime("%Y%m%dT%H%M%SZ")

        if hasattr(bridge_result, "model_dump"):
            bridge_payload = bridge_result.model_dump()
        elif hasattr(bridge_result, "dict"):
            bridge_payload = bridge_result.dict()
        else:
            bridge_payload = bridge_result

        run_id = str(getattr(bridge_result, "run_id", "")) or str(bridge_payload.get("run_id", ""))
        profile_version = DEFAULT_PROFILE_REGISTRY.get(profile_id).version
        backend_version = DEFAULT_BACKEND_REGISTRY.get_record(DEFAULT_BACKEND_ID).version

        record = {
            "run_id": run_id,
            "created_at": created_at,
            "profile_id": profile_id,
            "profile_version": profile_version,
            "backend_id": DEFAULT_BACKEND_ID,
            "backend_version": backend_version,
            "prompt_summary": prompt[:200],
            "author": _resolve_author(),
            "bridge_result": bridge_payload,
            "hermes_review": review,
        }

        runs_dir = Path.cwd().resolve() / ".ham" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        final_path = runs_dir / f"{created_at_for_filename}-{run_id}.json"
        tmp_path = runs_dir / f"{created_at_for_filename}-{run_id}.json.tmp"
        payload = json.dumps(record, sort_keys=True, ensure_ascii=True, indent=2)
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, final_path)
        return final_path
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Warning: run persistence failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_litellm_env()

    parser = argparse.ArgumentParser(description="ham — autonomous developer swarm")
    parser.add_argument(
        "--compact-json",
        action="store_true",
        help="Emit RUNTIME_RESULT as a single line (for scripts). Default is indented JSON for readability in terminals.",
    )
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
    _persist_run_record(
        prompt=assembly.user_prompt,
        profile_id=profile_id,
        bridge_result=bridge_result,
        review=review,
    )
    to_print = (
        envelope
        if args.compact_json
        else _truncate_envelope_for_stdout(envelope)
    )
    dumped = _dump_json(to_print, indent=None if args.compact_json else 2)
    if args.compact_json:
        print("RUNTIME_RESULT:", dumped)
    else:
        print("RUNTIME_RESULT:\n" + dumped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
