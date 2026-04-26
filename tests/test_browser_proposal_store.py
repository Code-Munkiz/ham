"""Tests for BrowserProposalStore (file-backed) and BrowserActionProposal redaction/caps."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.persistence.browser_proposal import (
    ALLOWED_ACTION_TYPES,
    MAX_TEXT,
    MAX_URL,
    BrowserActionPayload,
    BrowserActionProposal,
    BrowserProposalStore,
    ProposerActor,
    new_proposal_id,
    redact_url,
    utc_now_iso,
)


def _make_proposal(
    *,
    session_id: str = "brs_test123",
    owner_key: str = "pane_a",
    action_type: str = "browser.navigate",
    url: str | None = "https://example.com/path?secret=abc#frag",
    state: str = "proposed",
    text: str | None = None,
) -> BrowserActionProposal:
    return BrowserActionProposal(
        proposal_id=new_proposal_id(),
        session_id=session_id,
        owner_key=owner_key,
        state=state,  # type: ignore[arg-type]
        action=BrowserActionPayload(
            action_type=action_type,  # type: ignore[arg-type]
            url=url,
            text=text,
        ),
        proposer=ProposerActor(kind="operator", label="ui"),
        created_at=utc_now_iso(),
        expires_at=utc_now_iso(),
    )


def test_redact_url_drops_query_and_fragment() -> None:
    out = redact_url("https://example.com/foo?secret=abc#x")
    assert "secret" not in out
    assert "#" not in out
    assert out.startswith("https://example.com/foo")


def test_redact_url_caps_length() -> None:
    long = "https://example.com/" + ("a" * (MAX_URL + 100))
    out = redact_url(long)
    assert len(out) <= MAX_URL


def test_action_payload_caps_text() -> None:
    big = "x" * (MAX_TEXT + 1000)
    p = BrowserActionPayload(action_type="browser.type", selector="input", text=big, clear_first=True)
    assert p.text is not None
    assert len(p.text) <= MAX_TEXT


def test_allowed_action_types_constant() -> None:
    assert "browser.navigate" in ALLOWED_ACTION_TYPES
    assert "browser.click_xy" in ALLOWED_ACTION_TYPES
    assert "browser.type" in ALLOWED_ACTION_TYPES
    assert "browser.scroll" in ALLOWED_ACTION_TYPES
    assert "browser.key" in ALLOWED_ACTION_TYPES
    assert "browser.reset" in ALLOWED_ACTION_TYPES
    # Excluded in v1.
    assert "browser.click_selector" not in ALLOWED_ACTION_TYPES
    assert "shell.run" not in ALLOWED_ACTION_TYPES


def test_store_save_and_get_round_trip(tmp_path: Path) -> None:
    store = BrowserProposalStore(base_dir=tmp_path)
    proposal = _make_proposal()
    store.save(proposal)
    fetched = store.get(proposal.proposal_id)
    assert fetched is not None
    assert fetched.proposal_id == proposal.proposal_id
    assert fetched.session_id == "brs_test123"
    assert fetched.owner_key == "pane_a"
    # URL was redacted on construction.
    assert fetched.action.url is not None
    assert "secret" not in fetched.action.url
    assert "#" not in fetched.action.url


def test_store_get_invalid_id_raises(tmp_path: Path) -> None:
    store = BrowserProposalStore(base_dir=tmp_path)
    with pytest.raises(ValueError):
        store.get("not-a-uuid")


def test_store_list_for_session_filters_by_owner(tmp_path: Path) -> None:
    store = BrowserProposalStore(base_dir=tmp_path)
    p_a1 = _make_proposal(session_id="brs_x", owner_key="pane_a")
    p_a2 = _make_proposal(session_id="brs_x", owner_key="pane_a")
    p_b = _make_proposal(session_id="brs_x", owner_key="pane_b")
    p_y = _make_proposal(session_id="brs_y", owner_key="pane_a")
    for p in (p_a1, p_a2, p_b, p_y):
        store.save(p)

    rows = store.list_for_session(session_id="brs_x", owner_key="pane_a")
    ids = {r.proposal_id for r in rows}
    assert ids == {p_a1.proposal_id, p_a2.proposal_id}


def test_store_count_pending(tmp_path: Path) -> None:
    store = BrowserProposalStore(base_dir=tmp_path)
    p1 = _make_proposal(state="proposed")
    p2 = _make_proposal(state="proposed")
    p3 = _make_proposal(state="denied")
    p4 = _make_proposal(state="executed")
    for p in (p1, p2, p3, p4):
        store.save(p)
    assert store.count_pending_for_session(session_id="brs_test123", owner_key="pane_a") == 2


def test_proposal_does_not_persist_unknown_extra_fields() -> None:
    """Pydantic ConfigDict(extra="forbid") prevents accidental secrets sneaking in."""
    with pytest.raises(Exception):
        BrowserActionProposal.model_validate(
            {
                "proposal_id": new_proposal_id(),
                "session_id": "brs_a",
                "owner_key": "pane_a",
                "state": "proposed",
                "action": {"action_type": "browser.reset"},
                "proposer": {"kind": "operator"},
                "created_at": utc_now_iso(),
                "expires_at": utc_now_iso(),
                "auth_header": "Bearer secret-token",  # forbidden extra
            }
        )
