"""
Hermes self-learning critic: wraps local hermes-agent for code review and FTS5-backed learning.
"""
import json
from typing import Any

MAX_CODE_ECHO_CHARS = 1_000
MAX_CONTEXT_ECHO_CHARS = 1_000
MAX_LLM_OUTPUT_CHARS = 4_000

class HermesReviewer:
    """
    Placeholder: will call the local hermes-agent API to evaluate code and
    drive the self-learning / persistence loop.
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    def evaluate(self, code: str, context: str | None = None) -> dict[str, Any]:
        """Run a minimal LLM-backed code critique with conservative fallback."""
        safe_code = code[:MAX_CODE_ECHO_CHARS]
        safe_context = context[:MAX_CONTEXT_ECHO_CHARS] if context else None

        try:
            payload = self._run_review(code=code, context=context)
            return self._normalize_result(payload, safe_code, safe_context)
        except Exception as exc:  # deterministic conservative fallback
            note = (
                "Review confidence is limited: automated critique failed "
                f"({type(exc).__name__})."
            )
            return {
                "ok": False,
                "notes": [note],
                "code": safe_code,
                "context": safe_context,
            }

    def _run_review(self, *, code: str, context: str | None) -> Any:
        if self._client is None:
            from src.llm_client import get_crew_llm

            self._client = get_crew_llm()

        prompt = self._build_prompt(code=code, context=context)
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str) -> Any:
        client = self._client
        if client is None:
            raise RuntimeError("LLM client unavailable")

        # Prefer explicit method names; fall back to callable object.
        if hasattr(client, "call"):
            return client.call(prompt)
        if hasattr(client, "invoke"):
            return client.invoke(prompt)
        if callable(client):
            return client(prompt)

        raise TypeError("Unsupported LLM client interface")

    @staticmethod
    def _build_prompt(*, code: str, context: str | None) -> str:
        context_block = context or "(none)"
        return (
            "You are a strict software code reviewer.\n"
            "Return JSON ONLY with keys: ok (bool), confidence (high|limited), notes (array of strings).\n"
            "Use ok=true only if there are no blocking issues.\n"
            "Use ok=false if there is any blocking issue or confidence is limited.\n"
            f"Context:\n{context_block}\n\n"
            f"Code:\n{code}\n"
        )

    @staticmethod
    def _extract_json_object(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        if not raw:
            raise ValueError("Empty model response")

        # Accept plain JSON or JSON wrapped in markdown fences.
        if raw.startswith("```"):
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                raw = raw[start:end + 1]

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON must be an object")
        return parsed

    def _normalize_result(
        self,
        payload: Any,
        safe_code: str,
        safe_context: str | None,
    ) -> dict[str, Any]:
        if isinstance(payload, dict):
            obj = payload
        else:
            text = str(payload)[:MAX_LLM_OUTPUT_CHARS]
            obj = self._extract_json_object(text)

        raw_notes = obj.get("notes", [])
        if isinstance(raw_notes, str):
            notes = [raw_notes.strip()] if raw_notes.strip() else []
        elif isinstance(raw_notes, list):
            notes = [str(n).strip() for n in raw_notes if str(n).strip()]
        else:
            notes = [str(raw_notes).strip()] if str(raw_notes).strip() else []

        confidence = str(obj.get("confidence", "limited")).strip().lower()
        normalized_ok = self._normalize_ok_value(obj.get("ok"))
        blocking = normalized_ok is False
        limited = confidence != "high"
        ok = (not blocking) and (not limited) and not notes

        if limited and not any("confidence" in n.lower() for n in notes):
            notes.append("Review confidence is limited.")

        return {
            "ok": ok,
            "notes": notes,
            "code": safe_code,
            "context": safe_context,
        }

    @staticmethod
    def _normalize_ok_value(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return None
