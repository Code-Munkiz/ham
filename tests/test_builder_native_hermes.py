from __future__ import annotations

import json

import pytest

from src.ham.builder_native_hermes import (
    _NATIVE_BUILD_MAX_ATTEMPTS,
    ham_native_builder_user_message,
    hermes_native_builder_ready,
    run_hermes_native_build,
)
from src.ham.builder_preview_typecheck import user_safe_typecheck_failure_message
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
        "src/main.tsx": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom/client';\n"
            "import App from './App';\n"
            "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ");\n"
        ),
        "src/styles.css": "body { margin: 0; }\n",
    },
    "checks": ["renders"],
}


@pytest.fixture(autouse=True)
def _skip_npm_typecheck_unless_typecheck_test(request: pytest.FixtureRequest, monkeypatch) -> None:
    """Keep native Hermes tests fast; typecheck-named tests exercise the real gate."""
    if "typecheck" in request.node.name:
        return

    def _passthrough(files: dict[str, str]):
        from src.ham.builder_preview_typecheck import (
            PreviewTypecheckResult,
            ensure_preview_tsconfig,
            ensure_tailwind_config_for_preview,
        )

        prepared = ensure_tailwind_config_for_preview(ensure_preview_tsconfig(dict(files)))
        return PreviewTypecheckResult(
            ok=True,
            files=prepared,
            repair_summary=None,
            user_message="",
            compiler_output="",
            deterministic_repair_attempted=False,
        )

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.validate_preview_app_files",
        _passthrough,
    )


def _native_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    # Native builds require a dedicated fast artifact model/profile to be configured.
    monkeypatch.setenv("HERMES_BUILDER_MODEL", "hermes-builder-fast")


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


def test_hermes_native_build_bootstraps_main_when_hermes_omits_entry(tmp_path, monkeypatch) -> None:
    """Hermes may return App without main; preview bootstrap must supply src/main.tsx."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    payload = {
        "status": "success",
        "summary": "Built.",
        "files": {
            "src/App.tsx": "export default function App() { return <main>Hello</main>; }\n",
            "src/styles.css": "body { margin: 0; }\n",
        },
    }
    try:
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
    inline = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")[0].manifest[
        "inline_files"
    ]
    assert "src/main.tsx" in inline
    assert "package.json" in inline


def test_hermes_native_build_accepts_object_wrapped_file_entries(tmp_path, monkeypatch) -> None:
    """Hermes repair turns may return JSON objects instead of raw UTF-8 strings per file."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    payload = {
        "status": "success",
        "summary": "Built.",
        "files": {
            "package.json": {
                "name": "ham-native-demo",
                "private": True,
                "type": "module",
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
            },
            "src/App.tsx": {
                "content": "export default function App() { return <main>Hello</main>; }\n",
            },
            "src/main.tsx": {
                "text": (
                    "import React from 'react';\n"
                    "import ReactDOM from 'react-dom/client';\n"
                    "import App from './App';\n"
                    "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
                ),
            },
            "src/styles.css": "body { margin: 0; }\n",
        },
    }
    try:
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
    snapshots = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")
    inline = snapshots[0].manifest["inline_files"]
    assert '"ham-native-demo"' in inline["package.json"]
    assert "Hello" in inline["src/App.tsx"]


def test_hermes_native_build_skips_disallowed_paths_and_succeeds(tmp_path, monkeypatch) -> None:
    """Hermes may include README or eslint paths; keep runnable src/ files for preview."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    payload = {
        "status": "success",
        "summary": "Built.",
        "files": {
            **dict(_VALID_BUNDLE["files"]),
            "README.md": "# Demo\n",
            "eslint.config.js": "export default {};\n",
            "components/App.tsx": "export default function App() { return null; }\n",
        },
    }
    try:
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
    snapshots = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")
    inline = snapshots[0].manifest["inline_files"]
    assert "README.md" not in inline
    assert "components/App.tsx" not in inline


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


def test_hermes_native_build_stream_max_duration_maps_to_gateway(tmp_path, monkeypatch) -> None:
    """An artifact STREAM_MAX_DURATION timeout surfaces as a safe gateway failure (no internals)."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _fake_artifact(messages, *, timeout_sec=None, diag=None):
        if diag is not None:
            diag["artifact_mode"] = "json_mode"
            diag["artifact_transport"] = "non_streaming"
            diag["model_channel"] = "default"
        raise GatewayCallError("STREAM_MAX_DURATION", "No completion within 300s wall clock")

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
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert msg.startswith("HAM Native Builder could not reach the Hermes runtime.")
    haystack = (msg + json.dumps(result, default=str)).lower()
    for token in ("registry_v2", "proposal_digest", "stream_max_duration", "inline_files"):
        assert token not in haystack


def test_native_build_upstream_timeout_maps_to_gateway(tmp_path, monkeypatch) -> None:
    """The production UPSTREAM_TIMEOUT surfaces as a safe gateway failure (no internals, no fake success)."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _fake_artifact(messages, *, timeout_sec=None, diag=None):
        if diag is not None:
            diag["artifact_mode"] = "json_mode"
            diag["artifact_transport"] = "non_streaming"
            diag["model_channel"] = "builder"
            diag["elapsed_ms"] = 300082.6
        raise GatewayCallError("UPSTREAM_TIMEOUT", "Gateway request timed out")

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
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert msg.startswith("HAM Native Builder could not reach the Hermes runtime.")
    haystack = (msg + json.dumps(result, default=str)).lower()
    for token in ("registry_v2", "proposal_digest", "upstream_timeout", "inline_files", "hermes-builder"):
        assert token not in haystack


def test_native_build_fails_clearly_when_builder_model_unconfigured(tmp_path, monkeypatch) -> None:
    """Without HERMES_BUILDER_MODEL the native build fails fast with safe copy, not a 300s timeout."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    monkeypatch.delenv("HERMES_BUILDER_MODEL", raising=False)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    called = {"n": 0}

    def _fake_artifact(messages, *, timeout_sec=None, diag=None):
        called["n"] += 1
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

    assert called["n"] == 0  # the slow gateway model is never invoked -> no 300s burn
    assert result["scaffolded"] is False
    assert result["ham_native_builder"] == {"status": "unavailable", "failure_reason": "unconfigured"}
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert msg.startswith("HAM Native Builder is still being configured.")


_TEAM_MISMATCH_BUNDLE = {
    "status": "success",
    "summary": "Built.",
    "files": {
        "src/App.tsx": (
            "export default function App() {\n"
            "  const TEAM = [{ id: 1, name: 'A' }];\n"
            "  return <div>{team.map((t) => t.id)}</div>;\n"
            "}\n"
        ),
        "src/main.tsx": _VALID_BUNDLE["files"]["src/main.tsx"],
        "src/styles.css": _VALID_BUNDLE["files"]["src/styles.css"],
        "package.json": json.dumps(
            {
                "name": "team-mismatch",
                "private": True,
                "type": "module",
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                    "tailwindcss": "^3.4.0",
                },
            },
            indent=2,
        )
        + "\n",
        "postcss.config.js": (
            "export default { plugins: { tailwindcss: {}, autoprefixer: {} } };\n"
        ),
    },
    "checks": ["renders"],
}


def test_hermes_native_build_fails_typecheck_without_marking_preview_ready(
    tmp_path, monkeypatch
) -> None:
    """A TEAM/team mismatch must fail the build and must not enqueue cloud preview."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    preview_calls: list[str] = []

    def _no_preview(**kwargs: object) -> dict[str, object]:
        preview_calls.append(str(kwargs.get("source_snapshot_id")))
        return {"cloud_runtime_job_id": "should-not-run"}

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.maybe_enqueue_chat_scaffold_cloud_runtime_job",
        _no_preview,
    )
    monkeypatch.setattr(
        "src.ham.builder_preview_typecheck.try_repair_identifier_case_mismatch",
        lambda _files, _output: None,
    )
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a dashboard",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(_TEAM_MISMATCH_BUNDLE),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "failed"
    assert preview_calls == []
    jobs = store.list_import_jobs(workspace_id="ws_native", project_id="proj_native")
    assert jobs[0].status == "failed"
    assert "cloud_runtime_job_id" not in result


def test_hermes_native_build_typecheck_failure_user_message_is_safe(
    tmp_path, monkeypatch
) -> None:
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _always_fail_typecheck(files: dict[str, str]):
        from src.ham.builder_preview_typecheck import PreviewTypecheckResult

        return PreviewTypecheckResult(
            ok=False,
            files=files,
            repair_summary="Compiler summary:\nerror TS2304: Cannot find name 'team'.",
            user_message=user_safe_typecheck_failure_message(),
            compiler_output="error TS2304: Cannot find name 'team'.",
            deterministic_repair_attempted=False,
        )

    monkeypatch.setattr(
        "src.ham.builder_native_hermes.validate_preview_app_files",
        _always_fail_typecheck,
    )
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(_VALID_BUNDLE),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    haystack = (msg + json.dumps(result, default=str)).lower()
    for token in ("ts2304", "team", "stack", "traceback", "inline_files"):
        assert token not in haystack
    assert "could not prepare" in haystack


def test_hermes_native_build_repairs_typecheck_via_second_hermes_turn(
    tmp_path, monkeypatch
) -> None:
    """When deterministic repair is insufficient, a repair turn can fix the bundle."""
    _native_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    calls: list[int] = []

    def _turn(messages: list[dict[str, object]]) -> str:
        calls.append(1)
        if len(calls) == 1:
            return json.dumps(_TEAM_MISMATCH_BUNDLE)
        fixed = dict(_TEAM_MISMATCH_BUNDLE)
        fixed["files"] = dict(_TEAM_MISMATCH_BUNDLE["files"])
        fixed["files"]["src/App.tsx"] = (
            "export default function App() {\n"
            "  const TEAM = [{ id: 1, name: 'A' }];\n"
            "  return <div>{TEAM.map((t) => t.id)}</div>;\n"
            "}\n"
        )
        return json.dumps(fixed)

    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a dashboard",
            created_by="user_native",
            complete_turn=_turn,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert len(calls) == 1
    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"
