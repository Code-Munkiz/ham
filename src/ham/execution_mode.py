from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

ExecutionMode = Literal["browser", "machine", "chat"]
ExecutionModePreference = Literal["auto", "browser", "machine", "chat"]
ExecutionEnvironment = Literal["web", "desktop", "unknown"]

_WEB_HINTS_RE = re.compile(
    r"(https?://|www\.|website|web page|browser|click|navigate|open\s+site|fill\s+form|submit\s+form|search\s+for)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExecutionModeDecision:
    requested_mode: ExecutionModePreference
    selected_mode: ExecutionMode
    auto_selected: bool
    environment: ExecutionEnvironment
    browser_available: bool
    local_machine_available: bool
    reason: str


def browser_runtime_available() -> bool:
    raw = (os.environ.get("HAM_ENABLE_BROWSER_RUNTIME") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def looks_like_web_task(user_text: str) -> bool:
    return bool(_WEB_HINTS_RE.search((user_text or "").strip()))


def resolve_execution_mode(
    *,
    preference: ExecutionModePreference,
    environment: ExecutionEnvironment,
    user_text: str,
    browser_available: bool,
    local_machine_available: bool,
) -> ExecutionModeDecision:
    web_like = looks_like_web_task(user_text)
    requested = preference

    if requested == "browser":
        if browser_available:
            return ExecutionModeDecision(
                requested_mode=requested,
                selected_mode="browser",
                auto_selected=False,
                environment=environment,
                browser_available=browser_available,
                local_machine_available=local_machine_available,
                reason="User preference requested browser control.",
            )
        return ExecutionModeDecision(
            requested_mode=requested,
            selected_mode="chat",
            auto_selected=False,
            environment=environment,
            browser_available=browser_available,
            local_machine_available=local_machine_available,
            reason="Browser runtime is unavailable; fell back to chat.",
        )

    if requested == "machine":
        if local_machine_available:
            return ExecutionModeDecision(
                requested_mode=requested,
                selected_mode="machine",
                auto_selected=False,
                environment=environment,
                browser_available=browser_available,
                local_machine_available=local_machine_available,
                reason="User preference requested local machine control.",
            )
        if browser_available and web_like:
            return ExecutionModeDecision(
                requested_mode=requested,
                selected_mode="browser",
                auto_selected=False,
                environment=environment,
                browser_available=browser_available,
                local_machine_available=local_machine_available,
                reason="Machine control unavailable in this environment; using browser control for web task.",
            )
        return ExecutionModeDecision(
            requested_mode=requested,
            selected_mode="chat",
            auto_selected=False,
            environment=environment,
            browser_available=browser_available,
            local_machine_available=local_machine_available,
            reason="Machine control unavailable in this environment; fell back to chat.",
        )

    if requested == "chat":
        return ExecutionModeDecision(
            requested_mode=requested,
            selected_mode="chat",
            auto_selected=False,
            environment=environment,
            browser_available=browser_available,
            local_machine_available=local_machine_available,
            reason="User preference requested chat-only mode.",
        )

    # auto
    if browser_available and web_like:
        return ExecutionModeDecision(
            requested_mode=requested,
            selected_mode="browser",
            auto_selected=True,
            environment=environment,
            browser_available=browser_available,
            local_machine_available=local_machine_available,
            reason="Auto-selected browser control for web task.",
        )
    return ExecutionModeDecision(
        requested_mode=requested,
        selected_mode="chat",
        auto_selected=True,
        environment=environment,
        browser_available=browser_available,
        local_machine_available=local_machine_available,
        reason="Auto-selected chat mode.",
    )
