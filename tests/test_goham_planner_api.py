from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def _payload(overrides: dict | None = None) -> dict:
    base = {
        "goal": "research MiniMax M2.5 OpenRouter free tier context window",
        "currentUrl": "https://duckduckgo.com/",
        "title": "DuckDuckGo results",
        "requiredEvidenceTerms": ["minimax", "m2 5", "free tier", "context window"],
        "observedEvidenceTerms": [],
        "missingEvidenceTerms": ["minimax", "m2 5"],
        "candidates": [
            {
                "id": "ham_cand_1_0",
                "text": "MiniMax M2.5 (free) - API Pricing & Providers | OpenRouter",
                "tag": "a",
                "role": None,
                "risk": "low",
                "score": 21,
                "safety": "safe",
            },
            {
                "id": "ham_cand_1_1",
                "text": "Sign in",
                "tag": "a",
                "role": None,
                "risk": "low",
                "score": -5,
                "safety": "login or sign-up area",
            },
            {
                "id": "ham_cand_1_2",
                "text": "Unknown risky",
                "tag": "button",
                "role": None,
                "risk": "high",
                "score": 3,
                "safety": "safe",
            },
        ],
        "stepNumber": 1,
        "remainingBudget": 5,
    }
    if overrides:
        base.update(overrides)
    return base


def test_disabled_planner_returns_fallback(monkeypatch):
    monkeypatch.delenv("GOHAM_LLM_PLANNER_ENABLED", raising=False)
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "goham_planner_next_action"
    assert body["status"] == "fallback"
    assert body["planner_mode"] == "fallback"
    assert body["action"]["type"] == "done"


def test_valid_model_output_returns_llm_action(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr(
        "src.api.goham_planner._call_planner_model",
        lambda _prompt: '{"type":"click_candidate","candidate_id":"ham_cand_1_0","reason":"Open the result that matches MiniMax M2.5 pricing.","confidence":0.82}',
    )
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["planner_mode"] == "llm"
    assert body["action"]["type"] == "click_candidate"
    assert body["action"]["candidate_id"] == "ham_cand_1_0"


def test_malformed_model_output_returns_error(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr("src.api.goham_planner._call_planner_model", lambda _prompt: "not json")
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert body["planner_mode"] == "fallback"
    assert "malformed" in body["warnings"][0]


def test_unknown_action_rejected(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr(
        "src.api.goham_planner._call_planner_model",
        lambda _prompt: '{"type":"type","reason":"Type in a search box.","confidence":0.9}',
    )
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert "unknown_action" in body["warnings"][0]


def test_unknown_candidate_rejected(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr(
        "src.api.goham_planner._call_planner_model",
        lambda _prompt: '{"type":"click_candidate","candidate_id":"missing","reason":"Click missing result.","confidence":0.9}',
    )
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert "unknown_candidate" in body["warnings"][0]


def test_risky_candidate_rejected(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr(
        "src.api.goham_planner._call_planner_model",
        lambda _prompt: '{"type":"click_candidate","candidate_id":"ham_cand_1_2","reason":"Click risky result.","confidence":0.9}',
    )
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert "candidate_risk_not_low" in body["warnings"][0]


def test_sensitive_candidate_rejected(monkeypatch):
    monkeypatch.setenv("GOHAM_LLM_PLANNER_ENABLED", "true")
    monkeypatch.setattr(
        "src.api.goham_planner._call_planner_model",
        lambda _prompt: '{"type":"click_candidate","candidate_id":"ham_cand_1_1","reason":"Click sign in.","confidence":0.9}',
    )
    res = client.post("/api/goham/planner/next-action", json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "error"
    assert "candidate_not_safe" in body["warnings"][0]
