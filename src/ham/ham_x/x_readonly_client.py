"""Direct read-only X API client for HAM-on-X smoke tests."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact

X_RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
DEFAULT_DIRECT_TIMEOUT_SECONDS = 15

XHttpGet = Callable[..., Any]


@dataclass(frozen=True)
class XDirectSearchResult:
    action_type: str
    transport: str
    blocked: bool
    executed: bool
    status_code: int | None
    reason: str
    status: str
    diagnostic: str = ""
    endpoint: str = X_RECENT_SEARCH_URL
    query: str = ""
    max_results: int = 10
    response: dict[str, Any] | None = None
    error: str = ""
    catalog_skill_id: str = ""
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def as_dict(self) -> dict[str, object]:
        return redact(
            {
                "action_type": self.action_type,
                "transport": self.transport,
                "blocked": self.blocked,
                "executed": self.executed,
                "status_code": self.status_code,
                "reason": self.reason,
                "status": self.status,
                "diagnostic": self.diagnostic,
                "endpoint": self.endpoint,
                "query": self.query,
                "max_results": self.max_results,
                "response": self.response or {},
                "error": self.error,
                "catalog_skill_id": self.catalog_skill_id,
                "execution_allowed": False,
                "mutation_attempted": False,
            }
        )


class XDirectReadonlyClient:
    def __init__(
        self,
        *,
        config: HamXConfig | None = None,
        http_get: XHttpGet | None = None,
    ) -> None:
        self.config = config or load_ham_x_config()
        self.http_get = http_get or _httpx_get

    def search_recent(
        self,
        query: str,
        *,
        max_results: int = 10,
        timeout_seconds: int = DEFAULT_DIRECT_TIMEOUT_SECONDS,
        tweet_fields: str | None = None,
        expansions: str | None = None,
        user_fields: str | None = None,
    ) -> XDirectSearchResult:
        limited = max(10, min(int(max_results), 100))
        if not self.config.x_bearer_token:
            return XDirectSearchResult(
                action_type="search",
                transport="direct_bearer",
                blocked=True,
                executed=False,
                status_code=None,
                reason="x_bearer_token_missing",
                status="blocked",
                diagnostic="X_BEARER_TOKEN is required for direct read-only X smoke.",
                query=query,
                max_results=limited,
                catalog_skill_id=self.config.catalog_skill_id,
            )

        headers = {"Authorization": f"Bearer {self.config.x_bearer_token}"}
        params = {"query": query, "max_results": limited}
        if tweet_fields:
            params["tweet.fields"] = tweet_fields
        if expansions:
            params["expansions"] = expansions
        if user_fields:
            params["user.fields"] = user_fields
        try:
            response = self.http_get(
                X_RECENT_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - concrete errors vary by http client
            return XDirectSearchResult(
                action_type="search",
                transport="direct_bearer",
                blocked=False,
                executed=True,
                status_code=None,
                reason="x_direct_search_request_error",
                status="failed",
                diagnostic="Direct X read-only search request failed before receiving a response.",
                query=query,
                max_results=limited,
                error=redact(str(exc)),
                catalog_skill_id=self.config.catalog_skill_id,
            )

        status_code = int(getattr(response, "status_code", 0) or 0)
        body = _response_json(response)
        if status_code < 200 or status_code >= 300:
            reason, diagnostic = _normalize_direct_failure(status_code=status_code, body=body)
            return XDirectSearchResult(
                action_type="search",
                transport="direct_bearer",
                blocked=False,
                executed=True,
                status_code=status_code,
                reason=reason,
                status="failed",
                diagnostic=diagnostic,
                query=query,
                max_results=limited,
                response=_bounded_response(body),
                error=redact(str(getattr(response, "text", "") or "")),
                catalog_skill_id=self.config.catalog_skill_id,
            )

        return XDirectSearchResult(
            action_type="search",
            transport="direct_bearer",
            blocked=False,
            executed=True,
            status_code=status_code,
            reason="x_direct_search_ok",
            status="ok",
            query=query,
            max_results=limited,
            response=_bounded_response(body),
            catalog_skill_id=self.config.catalog_skill_id,
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


def _httpx_get(url: str, **kwargs: Any) -> Any:
    headers = kwargs.get("headers") or {}
    params = kwargs.get("params") or {}
    timeout = kwargs.get("timeout")
    full_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(full_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return _UrlLibResponse(status_code=int(response.status), text=text)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return _UrlLibResponse(status_code=int(exc.code), text=text)


def _response_json(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _bounded_response(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    bounded: dict[str, Any] = {}
    if isinstance(data, list):
        bounded["data"] = data[:10]
    meta = body.get("meta")
    if isinstance(meta, dict):
        bounded["meta"] = meta
    errors = body.get("errors")
    if isinstance(errors, list):
        bounded["errors"] = errors[:5]
    includes = body.get("includes")
    if isinstance(includes, dict):
        bounded["includes"] = {
            "users": includes.get("users", [])[:10] if isinstance(includes.get("users"), list) else [],
            "tweets": includes.get("tweets", [])[:10] if isinstance(includes.get("tweets"), list) else [],
        }
    return bounded or body


def _normalize_direct_failure(*, status_code: int, body: dict[str, Any]) -> tuple[str, str]:
    title = str(body.get("title") or "").lower()
    detail = str(body.get("detail") or "").lower()
    if status_code == 401 or "unauthorized" in {title, detail}:
        return (
            "x_direct_search_401_unauthorized",
            "X returned 401 Unauthorized for direct Bearer search. Check bearer token "
            "freshness and X app/project read permissions.",
        )
    return (
        f"x_direct_search_http_{status_code}",
        "Direct X read-only search returned a non-success HTTP status.",
    )
