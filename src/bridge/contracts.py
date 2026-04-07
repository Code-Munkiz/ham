from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BridgeStatus(str, Enum):
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"


class CommandState(str, Enum):
    EXECUTED = "executed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class CommandSpec(BaseModel):
    command_id: str = Field(min_length=1)
    argv: list[str] = Field(min_length=1)
    working_dir: str = Field(min_length=1)
    env_overrides: dict[str, str] = Field(default_factory=dict)


class ScopeSpec(BaseModel):
    allowed_roots: list[str] = Field(min_length=1)
    allow_network: bool = False
    allow_write: bool = False


class LimitSpec(BaseModel):
    max_commands: int = Field(ge=1, le=100)
    timeout_sec_per_command: int = Field(ge=1, le=300)
    max_stdout_chars: int = Field(ge=1, le=200_000)
    max_stderr_chars: int = Field(ge=1, le=200_000)
    max_total_output_chars: int = Field(ge=1, le=400_000)


class ExecutionIntent(BaseModel):
    intent_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    issued_by: Literal["hermes"] = "hermes"
    task_class: Literal["inspect", "validate"]
    commands: list[CommandSpec] = Field(min_length=1)
    scope: ScopeSpec
    limits: LimitSpec
    reason: str = Field(min_length=1)
    priority: Literal["normal", "high"] = "normal"
    tags: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    policy_version: str = Field(min_length=1)


class CommandEvidence(BaseModel):
    command_id: str = Field(min_length=1)
    argv: list[str] = Field(min_length=1)
    working_dir: str = Field(min_length=1)
    status: CommandState
    exit_code: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)


class BridgeResult(BaseModel):
    intent_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: BridgeStatus
    policy_decision: PolicyDecision
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    commands: list[CommandEvidence] = Field(default_factory=list)
    summary: str = ""
    pre_exec_git_status: str | None = None
    post_exec_git_status: str | None = None
    mutation_detected: bool | None = None
    artifacts: list[str] = Field(default_factory=list)

