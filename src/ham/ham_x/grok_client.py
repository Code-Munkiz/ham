"""Stub adapter shape for future xAI/Grok-backed drafting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.ham.ham_x.action_envelope import SocialActionEnvelope
from src.ham.ham_x.audit import append_audit_event
from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.safety_policy import check_social_action

XAI_BASE_URL = "https://api.x.ai/v1"
XAI_RESPONSES_ENDPOINT = f"{XAI_BASE_URL}/responses"
XAI_SMOKE_PROMPT = "Return exactly: HAM_XAI_SMOKE_OK"
XAI_SMOKE_EXPECTED = "HAM_XAI_SMOKE_OK"
XAI_SMOKE_MAX_OUTPUT_TOKENS = 8
XAI_SMOKE_TIMEOUT_SECONDS = 10

XaiHttpPost = Callable[..., Any]


@dataclass(frozen=True)
class XaiSmokeResult:
    ok: bool
    blocked: bool
    network_attempted: bool
    status_code: int | None
    reason: str
    model: str
    response_text: str = ""
    error: str = ""
    endpoint: str = XAI_RESPONSES_ENDPOINT
    max_output_tokens: int = XAI_SMOKE_MAX_OUTPUT_TOKENS
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def as_dict(self) -> dict[str, object]:
        return redact(
            {
                "ok": self.ok,
                "blocked": self.blocked,
                "network_attempted": self.network_attempted,
                "status_code": self.status_code,
                "reason": self.reason,
                "model": self.model,
                "response_text": self.response_text,
                "error": self.error,
                "endpoint": self.endpoint,
                "max_output_tokens": self.max_output_tokens,
                "execution_allowed": False,
                "mutation_attempted": False,
            }
        )


def run_xai_tiny_smoke(
    *,
    config: HamXConfig | None = None,
    http_post: XaiHttpPost | None = None,
    timeout_seconds: int = XAI_SMOKE_TIMEOUT_SECONDS,
) -> XaiSmokeResult:
    """Run one tiny xAI smoke request; never use the output for drafting."""
    cfg = config or load_ham_x_config()
    if not cfg.xai_api_key:
        return XaiSmokeResult(
            ok=False,
            blocked=True,
            network_attempted=False,
            status_code=None,
            reason="xai_api_key_missing",
            model=cfg.model,
        )

    payload = {
        "model": cfg.model,
        "input": [{"role": "user", "content": XAI_SMOKE_PROMPT}],
        "max_output_tokens": XAI_SMOKE_MAX_OUTPUT_TOKENS,
        "store": False,
    }
    headers = {
        "Authorization": f"Bearer {cfg.xai_api_key}",
        "Content-Type": "application/json",
    }
    post = http_post or _httpx_post
    try:
        response = post(
            XAI_RESPONSES_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - concrete errors vary by http client
        return XaiSmokeResult(
            ok=False,
            blocked=False,
            network_attempted=True,
            status_code=None,
            reason="xai_smoke_request_error",
            model=cfg.model,
            error=redact(str(exc)),
        )

    status_code = int(getattr(response, "status_code", 0) or 0)
    body = _response_json(response)
    text = _extract_response_text(body)
    if status_code < 200 or status_code >= 300:
        return XaiSmokeResult(
            ok=False,
            blocked=False,
            network_attempted=True,
            status_code=status_code,
            reason="xai_smoke_nonzero_status",
            model=cfg.model,
            response_text=redact(text),
            error=redact(_response_error_text(response, body)),
        )

    ok = text.strip() == XAI_SMOKE_EXPECTED
    return XaiSmokeResult(
        ok=ok,
        blocked=False,
        network_attempted=True,
        status_code=status_code,
        reason="xai_smoke_ok" if ok else "xai_smoke_unexpected_response",
        model=cfg.model,
        response_text=redact(text),
    )


def _httpx_post(*args: Any, **kwargs: Any) -> Any:
    import httpx

    return httpx.post(*args, **kwargs)


def _response_json(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _response_error_text(response: Any, body: dict[str, Any]) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return str(message)
    if isinstance(error, str):
        return error
    return str(getattr(response, "text", "") or "")


def _extract_response_text(body: dict[str, Any]) -> str:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = body.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str):
                            chunks.append(text)
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        if chunks:
            return "".join(chunks)
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return str(message["content"])
    return ""


def draft_social_action(
    *,
    target_summary: str,
    commentary_goal: str,
    input_ref: str | None = None,
    target_url: str | None = None,
    target_post_id: str | None = None,
    config: HamXConfig | None = None,
) -> SocialActionEnvelope:
    """Return a deterministic placeholder draft; no network calls in Phase 1A."""
    cfg = config or load_ham_x_config()
    text = (
        "Draft placeholder: add concise, relevant commentary after human review. "
        f"Target: {target_summary[:180]}. Goal: {commentary_goal[:180]}."
    )
    policy = check_social_action(text, action_type="draft")
    envelope = SocialActionEnvelope(
        action_type="draft",
        tenant_id=cfg.tenant_id,
        agent_id=cfg.agent_id,
        campaign_id=cfg.campaign_id,
        account_id=cfg.account_id,
        profile_id=cfg.profile_id,
        autonomy_mode=cfg.autonomy_mode,  # type: ignore[arg-type]
        policy_profile_id=cfg.policy_profile_id,
        brand_voice_id=cfg.brand_voice_id,
        catalog_skill_id=cfg.catalog_skill_id,
        dry_run=cfg.dry_run,
        autonomy_enabled=cfg.autonomy_enabled,
        input_ref=input_ref,
        target_url=target_url,
        target_post_id=target_post_id,
        text=text,
        model=cfg.model,
        policy_result=policy.model_dump(mode="json"),
        status="proposed" if policy.allowed else "rejected",
        reason="phase_1a_deterministic_placeholder",
        metadata={"network_calls": 0},
    )
    append_audit_event("draft_attempt", envelope.redacted_dump(), config=cfg)
    return envelope
