"""Read-only inbound engagement abstraction for GoHAM reactive dry-runs."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap
from src.ham.ham_x.x_readonly_client import XDirectReadonlyClient

InboundKind = Literal["mention", "comment", "dm"]
InboundFetchStatus = Literal["blocked", "ok", "failed"]
InboundHttpGet = Callable[..., Any]
_TWEET_FIELDS = "id,text,author_id,conversation_id,created_at,in_reply_to_user_id,referenced_tweets"
_EXPANSIONS = "author_id,referenced_tweets.id"
_USER_FIELDS = "username"
_REACTIVE_RELEVANCE_RE = re.compile(r"(?i)\b(ham|goham|hermes|base|agent|agents|automation|campaign|x)\b")


class ReactiveInboundItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound_id: str
    inbound_type: InboundKind = "mention"
    text: str
    author_id: str | None = None
    author_handle: str | None = None
    post_id: str | None = None
    thread_id: str | None = None
    conversation_id: str | None = None
    in_reply_to_post_id: str | None = None
    url: str | None = None
    created_at: str | None = None
    already_answered: bool = False
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


class InboundFetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: InboundFetchStatus
    ok: bool = False
    blocked: bool = False
    source: str
    items: list[ReactiveInboundItem] = Field(default_factory=list)
    status_code: int | None = None
    reason: str = ""
    diagnostic: str = ""
    execution_allowed: bool = False
    mutation_attempted: bool = False

    def redacted_dump(self) -> dict[str, Any]:
        return redact(_cap(self.model_dump(mode="json")))


@dataclass(frozen=True)
class InboundClientCapability:
    mentions_search: bool
    owned_post_replies: bool
    dms: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return redact(self.__dict__)


class InboundClient:
    """Read-only inbound client shell for prepared records or enabled discovery."""

    def __init__(
        self,
        *,
        config: HamXConfig | None = None,
        http_get: InboundHttpGet | None = None,
    ) -> None:
        self.config = config or load_ham_x_config()
        self.http_get = http_get

    def capability_probe(self) -> InboundClientCapability:
        if not self.config.x_bearer_token:
            return InboundClientCapability(
                mentions_search=False,
                owned_post_replies=False,
                reason="x_bearer_token_missing",
            )
        if not self.config.enable_reactive_inbox_discovery:
            return InboundClientCapability(
                mentions_search=False,
                owned_post_replies=False,
                reason="reactive_inbox_discovery_disabled",
            )
        return InboundClientCapability(
            mentions_search=True,
            owned_post_replies=True,
            reason="read_only_transport_ready",
        )

    def from_records(
        self,
        records: list[ReactiveInboundItem | dict[str, Any]],
        *,
        source: str = "prepared_inbound_records",
    ) -> InboundFetchResult:
        items = [record if isinstance(record, ReactiveInboundItem) else ReactiveInboundItem.model_validate(record) for record in records]
        return InboundFetchResult(
            status="ok",
            ok=True,
            source=source,
            items=items,
            reason="prepared_records_loaded",
        )

    def fetch_mentions(self, *, query: str, max_results: int = 25) -> InboundFetchResult:
        """Read mentions via direct Bearer search and normalize into inbound items."""
        capability = self.capability_probe()
        if not capability.mentions_search:
            return InboundFetchResult(
                status="blocked",
                blocked=True,
                source="mentions_search",
                reason=capability.reason or "mentions_search_unavailable",
                diagnostic="Reactive inbound discovery requires X_BEARER_TOKEN and HAM_X_ENABLE_REACTIVE_INBOX_DISCOVERY=true.",
            )
        client = XDirectReadonlyClient(config=self.config, http_get=self.http_get)
        result = client.search_recent(
            query,
            max_results=max_results,
            tweet_fields=_TWEET_FIELDS,
            expansions=_EXPANSIONS,
            user_fields=_USER_FIELDS,
        )
        if result.blocked:
            return InboundFetchResult(
                status="blocked",
                blocked=True,
                source="x_recent_search",
                reason=result.reason,
                diagnostic=result.diagnostic,
                status_code=result.status_code,
            )
        if result.status != "ok":
            return InboundFetchResult(
                status="failed",
                source="x_recent_search",
                reason=result.reason,
                diagnostic=result.diagnostic,
                status_code=result.status_code,
            )
        return InboundFetchResult(
            status="ok",
            ok=True,
            source="x_recent_search",
            items=normalize_x_recent_search_response(result.response or {}),
            status_code=result.status_code,
            reason="x_recent_search_normalized",
        )


def normalize_x_recent_search_response(body: dict[str, Any], *, source: str = "x_recent_search") -> list[ReactiveInboundItem]:
    users = _users_by_id(body)
    referenced = _tweets_by_id(body)
    data = body.get("data")
    if not isinstance(data, list):
        return []
    items: list[ReactiveInboundItem] = []
    for tweet in data:
        if not isinstance(tweet, dict):
            continue
        tweet_id = str(tweet.get("id") or "").strip()
        text = str(tweet.get("text") or "").strip()
        if not tweet_id or not text:
            continue
        author_id = str(tweet.get("author_id") or "").strip() or None
        conversation_id = str(tweet.get("conversation_id") or "").strip() or None
        reply_target = _reply_target(tweet, referenced)
        user = users.get(author_id or "")
        username = str(user.get("username") or "").strip() if user else ""
        items.append(
            ReactiveInboundItem(
                inbound_id=tweet_id,
                inbound_type="comment" if reply_target else "mention",
                text=text,
                author_id=author_id,
                author_handle=username or None,
                post_id=tweet_id,
                thread_id=conversation_id or tweet_id,
                conversation_id=conversation_id,
                in_reply_to_post_id=reply_target,
                created_at=str(tweet.get("created_at") or "").strip() or None,
                relevance_score=1.0 if _REACTIVE_RELEVANCE_RE.search(text) else 0.5,
                metadata={"source": source},
            )
        )
    return items


def _users_by_id(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    includes = body.get("includes")
    users = includes.get("users") if isinstance(includes, dict) else None
    if not isinstance(users, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for user in users:
        if isinstance(user, dict) and user.get("id"):
            out[str(user["id"])] = user
    return out


def _tweets_by_id(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    includes = body.get("includes")
    tweets = includes.get("tweets") if isinstance(includes, dict) else None
    if not isinstance(tweets, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for tweet in tweets:
        if isinstance(tweet, dict) and tweet.get("id"):
            out[str(tweet["id"])] = tweet
    return out


def _reply_target(tweet: dict[str, Any], referenced: dict[str, dict[str, Any]]) -> str | None:
    refs = tweet.get("referenced_tweets")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("type") != "replied_to":
            continue
        ref_id = str(ref.get("id") or "").strip()
        if ref_id:
            return ref_id
    for ref in refs:
        if isinstance(ref, dict) and str(ref.get("id") or "") in referenced:
            return str(ref.get("id"))
    return None
