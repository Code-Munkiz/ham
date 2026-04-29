"""Direct OAuth1 canary executor for HAM-on-X manual actions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact

X_CREATE_TWEET_URL = "https://api.x.com/2/tweets"
XWritePost = Callable[..., Any]


@dataclass(frozen=True)
class XProviderResult:
    status: str
    status_code: int | None
    provider_post_id: str | None
    response: dict[str, Any]
    diagnostic: str = ""

    def as_dict(self) -> dict[str, object]:
        return redact(
            {
                "status": self.status,
                "status_code": self.status_code,
                "provider_post_id": self.provider_post_id,
                "response": self.response,
                "diagnostic": self.diagnostic,
            }
        )


class XCanaryExecutor:
    def __init__(
        self,
        *,
        config: HamXConfig | None = None,
        http_post: XWritePost | None = None,
    ) -> None:
        self.config = config or load_ham_x_config()
        self.http_post = http_post or _urllib_post

    def execute(self, request: Any) -> XProviderResult:
        body: dict[str, Any] = {"text": request.text}
        if request.action_type == "quote":
            body["quote_tweet_id"] = request.quote_target_id
        headers = {
            "Content-Type": "application/json",
            "Authorization": _oauth1_header(
                method="POST",
                url=X_CREATE_TWEET_URL,
                consumer_key=self.config.x_api_key,
                consumer_secret=self.config.x_api_secret,
                access_token=self.config.x_access_token,
                token_secret=self.config.x_access_token_secret,
            ),
        }
        try:
            response = self.http_post(
                X_CREATE_TWEET_URL,
                headers=headers,
                json=body,
                timeout=15,
            )
        except Exception as exc:  # pragma: no cover - concrete errors vary by http client
            return XProviderResult(
                status="failed",
                status_code=None,
                provider_post_id=None,
                response={},
                diagnostic=redact(str(exc)),
            )
        status_code = int(getattr(response, "status_code", 0) or 0)
        payload = _response_json(response)
        provider_post_id = _provider_post_id(payload)
        if 200 <= status_code < 300 and provider_post_id:
            return XProviderResult(
                status="executed",
                status_code=status_code,
                provider_post_id=provider_post_id,
                response=_bounded_response(payload),
            )
        return XProviderResult(
            status="failed",
            status_code=status_code,
            provider_post_id=provider_post_id,
            response=_bounded_response(payload),
            diagnostic="X create tweet returned a non-success response.",
        )


class _UrlLibResponse:
    def __init__(self, *, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict[str, Any]:
        try:
            body = json.loads(self.text)
        except json.JSONDecodeError:
            return {}
        return body if isinstance(body, dict) else {}


def _urllib_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> Any:
    data = __import__("json").dumps(json).encode("utf-8")
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return _UrlLibResponse(status_code=int(response.status), text=text)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return _UrlLibResponse(status_code=int(exc.code), text=text)


def _oauth1_header(
    *,
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    token_secret: str,
) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    base_params = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), _enc(url), _enc(base_params)])
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    signature = base64.b64encode(
        hmac.new(key.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    params["oauth_signature"] = signature
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(params.items()))


def _enc(value: str) -> str:
    return quote(str(value), safe="")


def _response_json(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _provider_post_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return None


def _bounded_response(payload: dict[str, Any]) -> dict[str, Any]:
    return redact(payload)
