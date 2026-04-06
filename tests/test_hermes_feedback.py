from __future__ import annotations

from src.hermes_feedback import HermesReviewer


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def call(self, _prompt: str) -> str:
        return self.response


class _FailingLLM:
    def call(self, _prompt: str) -> str:
        raise RuntimeError("boom")


def test_evaluate_returns_stable_schema_and_ok_true():
    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM('{"ok": true, "confidence": "high", "notes": []}')

    result = reviewer.evaluate("print('ok')", "tiny context")

    assert set(result.keys()) == {"ok", "notes", "code", "context"}
    assert result["ok"] is True
    assert result["notes"] == []
    assert isinstance(result["code"], str)
    assert isinstance(result["context"], str)


def test_evaluate_semantics_ok_false_when_blocking_issue_present():
    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM(
        '{"ok": false, "confidence": "high", "notes": ["Blocking: syntax error"]}'
    )

    result = reviewer.evaluate("broken code", None)

    assert result["ok"] is False
    assert any("blocking" in n.lower() for n in result["notes"])


def test_evaluate_semantics_ok_false_when_confidence_limited_even_if_ok_true():
    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM('{"ok": true, "confidence": "limited", "notes": []}')

    result = reviewer.evaluate("code", "context")

    assert result["ok"] is False
    assert any("confidence" in n.lower() for n in result["notes"])


def test_evaluate_handles_markdown_fenced_json():
    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM(
        "```json\n"
        '{"ok": true, "confidence": "high", "notes": []}\n'
        "```"
    )

    result = reviewer.evaluate("code", None)
    assert set(result.keys()) == {"ok", "notes", "code", "context"}
    assert result["ok"] is True


def test_evaluate_handles_dict_payload_without_json_string_roundtrip():
    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM({
        "ok": True,
        "confidence": "high",
        "notes": [],
    })

    result = reviewer.evaluate("code", "context")
    assert set(result.keys()) == {"ok", "notes", "code", "context"}
    assert result["ok"] is True
    assert result["notes"] == []


def test_evaluate_normalizes_string_boolean_ok_values():
    reviewer_true = HermesReviewer()
    reviewer_true._client = _FakeLLM('{"ok": "TrUe", "confidence": "high", "notes": []}')
    result_true = reviewer_true.evaluate("code", None)
    assert result_true["ok"] is True

    reviewer_false = HermesReviewer()
    reviewer_false._client = _FakeLLM('{"ok": "FALSE", "confidence": "high", "notes": []}')
    result_false = reviewer_false.evaluate("code", None)
    assert result_false["ok"] is False


def test_evaluate_fallback_is_conservative_on_llm_failure():
    reviewer = HermesReviewer()
    reviewer._client = _FailingLLM()

    result = reviewer.evaluate("x" * 5000, "y" * 5000)

    assert set(result.keys()) == {"ok", "notes", "code", "context"}
    assert result["ok"] is False
    assert any("confidence is limited" in n.lower() for n in result["notes"])
    assert len(result["code"]) <= 1000
    assert len(result["context"]) <= 1000
