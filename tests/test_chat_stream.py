"""POST /api/chat/stream NDJSON streaming."""
from __future__ import annotations

import json
from pathlib import Path

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
    assert done.get("gateway_error") == {"code": "UPSTREAM_REJECTED"}
    msgs = done["messages"]
    assert msgs[-1]["role"] == "assistant"
    body = msgs[-1]["content"]
    assert "secret-upstream" not in body.lower()
    assert "rejected" in body.lower() or "gateway" in body.lower()


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
    texts = [e["text"] for e in _parse_ndjson(res.text) if e["type"] == "delta"]
    assert "".join(texts) == "ab"


_MAX_TRANSCRIBE = 15 * 1024 * 1024


def test_transcribe_not_configured(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 501
    assert r.json()["detail"]["error"]["code"] == "TRANSCRIPTION_NOT_CONFIGURED"


def test_transcribe_openai_without_key(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.delenv("HAM_TRANSCRIPTION_API_KEY", raising=False)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 501


def test_transcribe_upload_too_large(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-test-fake")
    big = b"z" * (_MAX_TRANSCRIBE + 1)
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", big, "audio/webm")})
    assert r.status_code == 413


def test_transcribe_content_length_rejected(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-test-fake")
    r = client.post(
        "/api/chat/transcribe",
        headers={"Content-Length": str(_MAX_TRANSCRIBE + 1)},
        files={"file": ("d.webm", b"tiny", "audio/webm")},
    )
    assert r.status_code == 413


def test_transcribe_empty_file(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-test-fake")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_transcribe_success_mocks_openai(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-test-fake")

    async def fake(**_kwargs: object) -> str:
        return "hello from speech"

    import src.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_transcribe_with_openai", fake)

    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"fake-audio", "audio/webm")})
    assert r.status_code == 200
    assert r.json() == {"text": "hello from speech"}


def test_transcribe_clerk_required_without_session(mock_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://clerk.example.com")
    monkeypatch.setenv("HAM_TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("HAM_TRANSCRIPTION_API_KEY", "sk-test-fake")
    r = client.post("/api/chat/transcribe", files={"file": ("d.webm", b"x", "audio/webm")})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"
    monkeypatch.delenv("HAM_CLERK_REQUIRE_AUTH", raising=False)
