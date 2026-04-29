"""Read-only inbound engagement abstraction for GoHAM reactive dry-runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.config import HamXConfig, load_ham_x_config
from src.ham.ham_x.redaction import redact
from src.ham.ham_x.review_queue import _cap

InboundKind = Literal["mention", "comment", "dm"]
InboundFetchStatus = Literal["blocked", "ok", "failed"]
InboundHttpGet = Callable[..., Any]


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
    """Read-only inbound client shell; live endpoint wiring is fail-closed."""

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
        return InboundClientCapability(
            mentions_search=self.http_get is not None,
            owned_post_replies=self.http_get is not None,
            reason="read_only_transport_ready" if self.http_get is not None else "http_get_not_configured",
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
        """Fail-closed live read placeholder; tests should inject prepared records."""
        capability = self.capability_probe()
        if not capability.mentions_search:
            return InboundFetchResult(
                status="blocked",
                blocked=True,
                source="mentions_search",
                reason=capability.reason or "mentions_search_unavailable",
                diagnostic="Reactive inbound live mentions search is not wired for Phase 4A.",
            )
        return InboundFetchResult(
            status="blocked",
            blocked=True,
            source="mentions_search",
            reason="phase_4a_live_ingestion_disabled",
            diagnostic=f"Phase 4A accepts prepared inbound records only; query={query[:80]} max_results={max_results}.",
        )
