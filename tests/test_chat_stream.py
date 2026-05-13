"""POST /api/chat/stream NDJSON streaming."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.integrations.nous_gateway_client import GatewayCallError

client = TestClient(app)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")


def _parse_ndjson(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def test_chat_stream_rejects_multiple_messages_in_one_request(mock_mode: None) -> None:
    """Data minimization: each turn sends one user message; prior context is session-backed."""
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
            ],
        },
    )
    assert res.status_code == 422


def test_chat_stream_rejects_non_user_single_message(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "assistant", "content": "hello"}]},
    )
    assert res.status_code == 422


def test_chat_stream_mock_yields_session_delta_done(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "hello stream"}]},
    )
    assert res.status_code == 200, res.text
    assert "ndjson" in res.headers.get("content-type", "").lower()
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    assert events[0]["session_id"]
    deltas = [e for e in events if e["type"] == "delta"]
    assert deltas
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["session_id"] == events[0]["session_id"]
    msgs = done[0]["messages"]
    assert msgs[-1]["role"] == "assistant"
    assert "Mock assistant reply" in msgs[-1]["content"]


@pytest.mark.parametrize(
    ("prompt", "expected_intent", "expected_reason_code"),
    [
        (
            "Launch a Cursor Cloud Agent for repo Unmapped-Org/unmapped-repo on branch main. Task: update docs only.",
            "cursor_agent_launch",
            "missing_project_mapping",
        ),
        (
            "have Cursor implement the SDK adapter fix",
            "cursor_agent_launch",
            "missing_project_context",
        ),
        (
            "fire up an agent to update the SDK adapter",
            "cursor_agent_launch",
            "missing_project_context",
        ),
    ],
)
def test_chat_stream_routes_agent_intents_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    expected_intent: str,
    expected_reason_code: str,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": prompt}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    # Routed intents should short-circuit before model streaming.
    assert [e for e in events if e["type"] == "delta"] == []
    done = [e for e in events if e["type"] == "done"][0]
    operator_result = done.get("operator_result")
    assert isinstance(operator_result, dict)
    assert operator_result.get("intent") == expected_intent
    assert operator_result.get("handled") is True
    assert operator_result.get("data", {}).get("reason_code") == expected_reason_code


@pytest.mark.parametrize(
    "prompt",
    [
        "send this to Factory Droid to update the SDK adapter",
        "use Claude to implement this change",
        "launch Claude Cloud Agent to edit this repo",
    ],
)
def test_chat_stream_non_cursor_agent_mention_streams_without_operator_block(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": prompt}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert any(e.get("type") == "delta" for e in events)
    done = [e for e in events if e["type"] == "done"][0]
    assert not done.get("operator_result")


def test_chat_stream_non_cursor_turn_persists_streamed_assistant_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "send this to Factory Droid to update the SDK adapter"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    done = [e for e in _parse_ndjson(res.text) if e["type"] == "done"][0]
    sid = str(done["session_id"])
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert msgs[-1]["role"] == "assistant"
    assert "provider_not_implemented" not in msgs[-1]["content"]
    assert "Blocked:" not in msgs[-1]["content"]


def test_chat_stream_build_intent_bypasses_operator_fallback(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _builder_hook(**_kwargs):  # type: ignore[no-untyped-def]
        return (
            "I'll create the initial project source and prepare the Workbench.\n\n",
            {"builder_intent": "build_or_create", "scaffolded": True},
        )

    def _unexpected_operator(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("operator fallback must not run for build_or_create intent")

    monkeypatch.setattr("src.api.chat.run_builder_happy_path_hook", _builder_hook)
    monkeypatch.setattr("src.api.chat.process_operator_turn", _unexpected_operator)
    monkeypatch.setattr("src.api.chat.process_agent_router_turn", _unexpected_operator)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "build me a game like Tetris"}], "enable_operator": True},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e.get("type") == "done"][0]
    assert done.get("operator_result") is None
    assert done.get("builder", {}).get("builder_intent") == "build_or_create"
    assert "prepare the Workbench" in done["messages"][-1]["content"]


def test_chat_stream_local_repo_ops_not_forced_into_mission_route_when_operator_disabled(
    mock_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_CHAT_OPERATOR", "false")
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "gh auth status"}]},
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    assert any(e.get("type") == "delta" for e in events), "should remain normal chat stream"
    done = [e for e in events if e["type"] == "done"][0]
    operator_result = done.get("operator_result")
    assert not operator_result


def test_chat_stream_gateway_failure_done_with_safe_assistant_and_signal(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_stream(*_a, **_k):
        raise GatewayCallError(
            "UPSTREAM_REJECTED",
            "secret-upstream-body-do-not-show-users",
            http_status=503,
        )

    monkeypatch.setattr("src.api.chat.stream_chat_turn", failing_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    assert events[0]["type"] == "session"
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done.get("gateway_error") == {"code": "UPSTREAM_REJECTED", "upstream_http_status": 503}
    msgs = done["messages"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert msgs[-1]["role"] == "assistant"
    body = msgs[-1]["content"]
    assert "secret-upstream" not in body.lower()
    assert "rejected" in body.lower() or "gateway" in body.lower()


def test_chat_stream_openrouter_model_rejected_done_with_safe_assistant_and_signal(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_stream(*_a, **_k):
        raise GatewayCallError(
            "OPENROUTER_MODEL_REJECTED",
            "secret-provider-body-do-not-show-users",
            http_status=400,
        )

    monkeypatch.setattr("src.api.chat.stream_chat_turn", failing_stream)

    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    assert events[-1]["type"] == "done"
    done = events[-1]
    assert done.get("gateway_error") == {"code": "OPENROUTER_MODEL_REJECTED", "upstream_http_status": 400}
    msgs = done["messages"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    body = msgs[-1]["content"]
    assert "secret-provider" not in body.lower()


def test_chat_stream_done_includes_active_agent_meta(
    mock_mode: None, isolated_home: Path, tmp_path: Path,
) -> None:
    root = tmp_path / "proj_stream"
    root.mkdir()
    (root / ".ham").mkdir()
    (root / ".ham" / "settings.json").write_text(
        json.dumps(
            {
                "agents": {
                    "profiles": [
                        {
                            "id": "ham.default",
                            "name": "StreamAgent",
                            "description": "",
                            "skills": [],
                            "enabled": True,
                        },
                    ],
                    "primary_agent_id": "ham.default",
                },
            },
        ),
        encoding="utf-8",
    )
    reg = client.post(
        "/api/projects",
        json={"name": "stproj", "root": str(root), "description": ""},
    )
    assert reg.status_code == 201
    pid = reg.json()["id"]
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [{"role": "user", "content": "hello stream"}],
            "project_id": pid,
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    assert done.get("active_agent") is not None
    assert done["active_agent"]["profile_name"] == "StreamAgent"


def test_chat_stream_custom_chunks(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(_msgs: list, **_kwargs):
        yield "a"
        yield "b"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", fake_stream)
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    texts = [e["text"] for e in events if e["type"] == "delta"]
    assert "".join(texts) == "ab"
    done = [e for e in events if e["type"] == "done"][0]
    assistants = [m["content"] for m in done["messages"] if m["role"] == "assistant"]
    assert assistants == ["ab"]


def test_chat_stream_disconnect_checkpoint_persists_partial(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_stream(_msgs: list, **_kwargs):
        yield "partial "
        yield "more"
        # Deterministically simulate an interrupted stream before normal completion.
        raise GeneratorExit()

    monkeypatch.setattr("src.api.chat.stream_chat_turn", slow_stream)

    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    with tolerant_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "keep going"}]},
    ) as res:
        assert res.status_code == 200
        # Consume one line if present then disconnect.
        _ = list(res.iter_lines())

    # Allow generator cleanup/finally to flush a best-effort final checkpoint.
    time.sleep(0.05)
    detail = client.get(f"/api/chat/sessions/{sid}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assistants = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert "partial" in assistants[0]
    assert "Connection interrupted. Ask me to continue." in assistants[0]


def test_chat_stream_after_disconnect_allows_new_stream(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing the client mid-stream must release the per-session lock (no stuck 409)."""

    def slow_stream(_msgs: list, **_kwargs):
        yield "hold "
        yield "more"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", slow_stream)

    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]
    tolerant_client = TestClient(app, raise_server_exceptions=False)
    with tolerant_client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "first"}]},
    ) as res:
        assert res.status_code == 200
        _ = list(res.iter_lines())

    time.sleep(0.05)
    follow = client.post(
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "second"}]},
    )
    assert follow.status_code == 200, follow.text
    events = _parse_ndjson(follow.text)
    assert any(e.get("type") == "done" for e in events)


def test_chat_stream_rejects_concurrent_same_session_streams(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream_started = threading.Event()
    allow_finish = threading.Event()

    def blocked_stream(_msgs: list, **_kwargs):
        yield "locked "
        stream_started.set()
        assert allow_finish.wait(timeout=2.0)
        yield "done"

    monkeypatch.setattr("src.api.chat.stream_chat_turn", blocked_stream)
    create = client.post("/api/chat/sessions")
    assert create.status_code == 200
    sid = create.json()["session_id"]

    first: dict[str, object] = {}

    def run_first() -> None:
        res = client.post(
            "/api/chat/stream",
            json={"session_id": sid, "messages": [{"role": "user", "content": "first"}]},
        )
        first["status_code"] = res.status_code
        first["events"] = _parse_ndjson(res.text)

    t = threading.Thread(target=run_first, daemon=True)
    t.start()
    assert stream_started.wait(timeout=1.0)

    second = client.post(
        "/api/chat/stream",
        json={"session_id": sid, "messages": [{"role": "user", "content": "second"}]},
    )
    assert second.status_code == 409
    detail = second.json().get("detail", {})
    assert detail.get("error", {}).get("code") == "STREAM_ALREADY_ACTIVE"

    allow_finish.set()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert first["status_code"] == 200


_MAX_TRANSCRIBE = 15 * 1024 * 1024


def test_transcribe_not_configured(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "CONNECT_STT_PROVIDER_REQUIRED"


def test_transcribe_openai_without_key(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 503


def test_transcribe_openai_placeholder_key_not_configured(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "PLACEHOLDER")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 503
    j = r.json()
    assert j["detail"]["error"]["code"] == "CONNECT_STT_PROVIDER_REQUIRED"


def test_transcribe_upload_too_large(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    big = b"z" * (_MAX_TRANSCRIBE + 1)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", big, "audio/webm")})
    assert r.status_code == 413


def test_transcribe_content_length_rejected(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post(
        "/api/chat/transcribe",
        headers={"Content-Length": str(_MAX_TRANSCRIBE + 1)},
        files={"file": ("d.webm", b"tiny", "audio/webm")},
    )
    assert r.status_code == 413


def test_transcribe_empty_file(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_transcribe_success_mocks_openai(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")

    async def fake(**_kwargs: object) -> str:
        return "hello from speech"

    import src.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_transcribe_with_openai", fake)

    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"fake-audio", "audio/webm")})
    assert r.status_code == 200
    assert r.json() == {"text": "hello from speech"}


def test_transcribe_upstream_auth_error_sanitized(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-real-looking")

    async def fake(**_kwargs: object) -> str:
        req = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
        resp = httpx.Response(
            status_code=401,
            request=req,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": "Incorrect API key provided: PLACEHOL********",
                }
            },
        )
        raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)

    import src.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_transcribe_with_openai", fake)

    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"fake-audio", "audio/webm")})
    assert r.status_code == 503
    j = r.json()
    assert j["detail"]["error"]["code"] == "TRANSCRIPTION_PROVIDER_REJECTED"
    assert "PLACEHOL" not in j["detail"]["error"]["message"]


def test_transcribe_clerk_required_without_session(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-live-demo-key-12345")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)


def test_chat_stream_accepts_ham_chat_user_v1(mock_mode: None) -> None:
    """1×1 PNG data URL — stored as ham_chat_user_v1; mock stream still completes."""
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "describe this",
                        "images": [
                            {"name": "pixel.png", "mime": "image/png", "data_url": tiny_png},
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert user_msgs, "user turn should be persisted"
    assert '"h":"ham_chat_user_v1"' in user_msgs[-1]["content"] or "ham_chat_user_v1" in user_msgs[-1]["content"]


def test_chat_stream_rejects_bad_image_mime(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "x",
                        "images": [
                            {
                                "name": "x.gif",
                                "mime": "image/gif",
                                "data_url": "data:image/gif;base64,R0lGODdhAQABAIABAP///wAAACwAAAAAAQABAAACAkQBADs=",
                            },
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 422


def test_chat_stream_rejects_oversized_image_data_url(
    mock_mode: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server enforces HAM_CHAT_IMAGE_MAX_BYTES on embedded data URLs."""
    monkeypatch.setenv("HAM_CHAT_IMAGE_MAX_BYTES", "20")
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v1",
                        "text": "x",
                        "images": [
                            {"name": "big.png", "mime": "image/png", "data_url": tiny_png},
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 422
    detail = res.json().get("detail") if res.headers.get("content-type", "").startswith("application/json") else {}
    msg = str(detail).lower()
    assert "too large" in msg or "image" in msg


def test_chat_stream_text_only_unchanged(mock_mode: None) -> None:
    res = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "plain text only"}]},
    )
    assert res.status_code == 200
    events = _parse_ndjson(res.text)
    done = [e for e in events if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert user_msgs[-1]["content"] == "plain text only"


def test_chat_stream_accepts_ham_chat_user_v2(
    mock_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.chat_attachment_store import LocalDiskAttachmentStore, set_chat_attachment_store_for_tests

    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_DIR", str(tmp_path))
    set_chat_attachment_store_for_tests(LocalDiskAttachmentStore(tmp_path))
    tiny_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )
    up = client.post(
        "/api/chat/attachments",
        files={"file": ("a.png", tiny_png, "image/png")},
    )
    assert up.status_code == 200, up.text
    aid = up.json()["attachment_id"]
    res = client.post(
        "/api/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "h": "ham_chat_user_v2",
                        "text": "what is this",
                        "attachments": [
                            {
                                "id": aid,
                                "name": "a.png",
                                "mime": "image/png",
                                "kind": "image",
                            },
                        ],
                    },
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    done = [e for e in _parse_ndjson(res.text) if e["type"] == "done"][0]
    user_msgs = [m for m in done["messages"] if m["role"] == "user"]
    assert "ham_chat_user_v2" in user_msgs[-1]["content"]
