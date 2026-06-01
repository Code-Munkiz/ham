from __future__ import annotations

import json

from src.ham.builder_native_hermes import (
    _NATIVE_BUILD_MAX_ATTEMPTS,
    ham_native_builder_user_message,
    hermes_native_builder_ready,
    run_hermes_native_build,
)
from src.integrations.nous_gateway_client import GatewayCallError
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)


def test_hermes_native_build_creates_source_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        payload = {
            "status": "success",
            "summary": "Built.",
            "files": {
                "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
                "src/main.tsx": "import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App';\nReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n",
                "src/styles.css": "body { margin: 0; }\n",
            },
            "checks": ["renders"],
        }

        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(payload),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"
    source_rows = store.list_project_sources(workspace_id="ws_native", project_id="proj_native")
    assert source_rows[0].kind == "ham_native_builder"
    snapshots = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")
    assert snapshots[0].manifest["kind"] == "inline_text_bundle"
    assert "src/App.tsx" in snapshots[0].manifest["inline_files"]
    assert "package.json" in snapshots[0].manifest["inline_files"]


def test_hermes_native_build_rejects_internal_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        payload = {
            "status": "success",
            "files": {
                "src/App.tsx": "export const x = 'proposal_digest';\n",
            },
        }
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(payload),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "failed"
    assert result["ham_native_builder"]["failure_reason"] == "bundle"


def test_hermes_native_builder_ready_requires_http_base_url(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.delenv("HERMES_GATEWAY_BASE_URL", raising=False)
    assert hermes_native_builder_ready() is False


def test_hermes_native_build_gateway_error_returns_gateway_reason(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:

        def _boom(_messages: object) -> str:
            raise GatewayCallError("UPSTREAM_UNAVAILABLE", "connection refused")

        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=_boom,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"] == {"status": "failed", "failure_reason": "gateway"}
    assert result.get("import_job_id")
    assert ham_native_builder_user_message(result["ham_native_builder"]).startswith(
        "HAM Native Builder could not reach the Hermes runtime."
    )


def test_ham_native_builder_user_messages_are_non_internal() -> None:
    assert "registry" not in ham_native_builder_user_message({"status": "failed", "failure_reason": "bundle"}).lower()
    assert ham_native_builder_user_message({"status": "unavailable", "failure_reason": "unconfigured"}).startswith(
        "HAM Native Builder is still being configured."
    )


_VALID_BUNDLE = {
    "status": "success",
    "summary": "Built.",
    "files": {
        "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
        "src/main.tsx": "import App from './App';\nexport default App;\n",
        "src/styles.css": "body { margin: 0; }\n",
    },
    "checks": ["renders"],
}


def _native_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")


def test_hermes_native_build_repairs_prose_then_succeeds(tmp_path, monkeypatch) -> None:
    """Hermes first replies conversationally; the bounded repair turn recovers a build."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    calls: list[int] = []

    def _turn(messages: list[dict[str, object]]) -> str:
        calls.append(len(messages))
        if len(calls) == 1:
            return "Sure! I'd love to help you build that. What framework do you prefer?"
        return json.dumps(_VALID_BUNDLE)

    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert len(calls) == 2  # initial prose turn + one repair turn
    assert calls[1] > calls[0]  # repair turn feeds prior reply + correction back
    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"


def test_hermes_native_build_accepts_prose_wrapped_json_without_status(tmp_path, monkeypatch) -> None:
    """A valid files map embedded in prose (and missing status) is recovered on the first turn."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    no_status = {"summary": "here", "files": dict(_VALID_BUNDLE["files"])}
    wrapped = f"Absolutely, here is the project:\n```json\n{json.dumps(no_status)}\n```\nEnjoy!"
    calls: list[int] = []

    def _turn(messages: list[dict[str, object]]) -> str:
        calls.append(1)
        return wrapped

    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert len(calls) == 1  # no repair needed: extraction + lenient status succeed
    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"


def test_hermes_native_build_prose_only_returns_bundle_reason_no_internals(tmp_path, monkeypatch) -> None:
    """Prose on both turns ends in a safe, non-internal bundle failure (no faked success)."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    calls: list[int] = []

    def _turn(_messages: list[dict[str, object]]) -> str:
        calls.append(1)
        return "I think a calculator would be great! Tell me more about what you want."

    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert len(calls) == _NATIVE_BUILD_MAX_ATTEMPTS  # initial + repair both attempted
    assert result["scaffolded"] is False
    assert result["ham_native_builder"] == {"status": "failed", "failure_reason": "bundle"}
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert msg.startswith("HAM Native Builder could not prepare the project files.")
    haystack = (msg + json.dumps(result, default=str)).lower()
    for token in ("registry_v2", "proposal_digest", "base_revision", "hermes_native_build", "inline_files"):
        assert token not in haystack


def test_hermes_native_build_repair_gateway_error_reports_gateway(tmp_path, monkeypatch) -> None:
    """If the repair turn loses the gateway, surface the gateway reason honestly."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    calls: list[int] = []

    def _turn(_messages: list[dict[str, object]]) -> str:
        calls.append(1)
        if len(calls) == 1:
            return "Happy to help! What styling do you want?"
        raise GatewayCallError("UPSTREAM_UNAVAILABLE", "connection refused")

    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert len(calls) == 2
    assert result["ham_native_builder"] == {"status": "failed", "failure_reason": "gateway"}


def test_native_build_default_path_uses_artifact_channel(tmp_path, monkeypatch) -> None:
    """With no injected turn, the native build uses the private artifact channel."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    seen: dict[str, object] = {}

    def _fake_artifact(messages, *, timeout_sec=None, diag=None):
        seen["called"] = True
        if diag is not None:
            diag["artifact_mode"] = "json_mode"
            diag["gateway_capability_detected"] = "response_format_supported"
            diag["model_channel"] = "default"
        return json.dumps(_VALID_BUNDLE)

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.complete_artifact_turn",
        _fake_artifact,
    )
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert seen.get("called") is True
    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"


def test_native_build_default_path_artifact_unavailable_is_safe(tmp_path, monkeypatch) -> None:
    """If the artifact channel raises a gateway error, surface gateway reason (no fake success)."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _fake_artifact(messages, *, timeout_sec=None, diag=None):
        raise GatewayCallError("UPSTREAM_UNAVAILABLE", "connection refused")

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.complete_artifact_turn",
        _fake_artifact,
    )
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"] == {"status": "failed", "failure_reason": "gateway"}


def test_native_module_does_not_use_conversational_chat_turn() -> None:
    """The native builder must drive the private artifact channel, not user chat."""
    import src.ham.builder_native_hermes as native

    assert hasattr(native, "complete_artifact_turn")
    assert not hasattr(native, "complete_chat_turn")
