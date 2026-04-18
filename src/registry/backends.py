from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.tools.droid_executor import DroidExecutionRecord


class ExecutionBackend(Protocol):
    def execute(
        self,
        argv: list[str],
        *,
        working_dir: str | None = None,
        timeout_sec: int = 30,
        max_stdout_chars: int = 8_000,
        max_stderr_chars: int = 8_000,
        env_overrides: dict[str, str] | None = None,
    ) -> DroidExecutionRecord: ...


class LocalDroidBackend:
    def execute(
        self,
        argv: list[str],
        *,
        working_dir: str | None = None,
        timeout_sec: int = 30,
        max_stdout_chars: int = 8_000,
        max_stderr_chars: int = 8_000,
        env_overrides: dict[str, str] | None = None,
    ) -> DroidExecutionRecord:
        from src.tools.droid_executor import droid_executor

        return droid_executor(
            argv,
            working_dir=working_dir,
            timeout_sec=timeout_sec,
            max_stdout_chars=max_stdout_chars,
            max_stderr_chars=max_stderr_chars,
            env_overrides=env_overrides,
        )


class BackendRecord(BaseModel):
    id: str
    version: str = "1.0.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackendRegistry:
    def __init__(self, backends: dict[str, tuple[BackendRecord, ExecutionBackend]]):
        self._backends = backends

    def get(self, backend_id: str) -> ExecutionBackend:
        try:
            return self._backends[backend_id][1]
        except KeyError as exc:
            raise KeyError(f"Unknown backend_id: {backend_id}") from exc

    def ids(self) -> list[str]:
        return sorted(self._backends.keys())


DEFAULT_BACKEND_ID = "local.droid"
DEFAULT_BACKEND_REGISTRY = BackendRegistry(
    {
        DEFAULT_BACKEND_ID: (
            BackendRecord(id=DEFAULT_BACKEND_ID, version="1.0.0", metadata={}),
            LocalDroidBackend(),
        )
    }
)
