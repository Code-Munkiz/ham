"""
Server-side, deployment-derived HTTP probe for post-deploy validation (managed missions).

No arbitrary URLs, no browser automation. URL + redirect allowlist from Vercel deployment only.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx

from src.ham.vercel_deploy_status import (
    MatchConfidence,
    allowed_hosts_for_deployment,
    _deployment_state_fields,
    _resolve_deployment_url,
)

ValidationState = Literal["not_attempted", "pending", "passed", "failed", "inconclusive"]


def _content_marker() -> str | None:
    m = (os.environ.get("HAM_POST_DEPLOY_VALIDATION_SUBSTRING") or os.environ.get("HAM_POST_DEPLOY_SUBSTRING") or "").strip()
    return m or None


def _read_timeout_s() -> float:
    try:
        return float((os.environ.get("HAM_POST_DEPLOY_TIMEOUT_S") or "15").strip() or "15")
    except ValueError:
        return 15.0


def _max_body_bytes() -> int:
    try:
        return int((os.environ.get("HAM_POST_DEPLOY_MAX_BODY_BYTES") or "262144").strip() or "262144")
    except ValueError:
        return 262_144


def _max_redirects() -> int:
    try:
        r = int((os.environ.get("HAM_POST_DEPLOY_MAX_REDIRECTS") or "8").strip() or "8")
        return max(1, min(r, 32))
    except ValueError:
        return 8


def _title_from_html_head(snippet: str) -> str | None:
    m = re.search(
        r"<title[^>]*>([^<]{1,500})</title>",
        snippet,
        flags=re.I | re.DOTALL,
    )
    if not m:
        return None
    t = m.group(1)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _body_marker_match(text: str, marker: str) -> bool:
    if marker.lower() in text.lower():
        return True
    t = _title_from_html_head(text)
    return t is not None and marker.lower() in t.lower()


def _probe_url_allowlisted(
    start_url: str,
    allowed_hosts: frozenset[str],
) -> tuple[str, int | None, bytes, str | None, str | None]:
    """
    Returns (final_url, last_http_status, body_head, reason_code, detail).
    `reason_code` is None on success of HTTP + redirect path (caller checks status).
    """
    p = urlparse(start_url)
    if p.scheme not in ("http", "https"):
        return start_url, None, b"", "invalid_url_scheme", f"Refusing non-HTTP(S) scheme: {p.scheme!r}"
    if not p.netloc:
        return start_url, None, b"", "invalid_url", "URL has no host"

    timeout = _read_timeout_s()
    max_b = _max_body_bytes()
    max_h = _max_redirects()
    current = start_url

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _hop in range(max_h + 1):
            try:
                with client.stream("GET", current) as r:
                    if 300 <= r.status_code < 400:
                        loc = r.headers.get("location")
                        if not loc:
                            r.read()
                            return current, r.status_code, b"", "redirect_no_location", "Redirect without Location"
                        nxt = urljoin(current, loc.strip())
                        np = urlparse(nxt)
                        if np.scheme not in ("http", "https"):
                            r.read()
                            return nxt, r.status_code, b"", "redirect_invalid_scheme", "Redirect to non-HTTP(S)"
                        host = (np.hostname or "").lower()
                        if not host or host not in allowed_hosts:
                            r.read()
                            return nxt, r.status_code, b"", "redirect_disallowed", f"Host {host!r} not in deployment allowlist"
                        current = nxt
                        continue
                    # Terminal response: read capped body
                    chunks: list[bytes] = []
                    total = 0
                    for c in r.iter_bytes():
                        if not c:
                            break
                        chunks.append(c)
                        total += len(c)
                        if total >= max_b:
                            break
                    body = b"".join(chunks)[:max_b]
                    return current, r.status_code, body, None, None
            except httpx.TimeoutException as exc:
                return current, None, b"", "timeout_error", str(exc)
            except httpx.ConnectError as exc:
                return current, None, b"", "network_error", str(exc)
            except httpx.RequestError as exc:
                return current, None, b"", "network_error", str(exc)
        return current, None, b"", "too_many_redirects", f"More than {max_h} redirects"

    return start_url, None, b"", "internal", "unreachable"  # pragma: no cover


def run_post_deploy_probe(
    *,
    dep: dict[str, Any],
    match_confidence: MatchConfidence | None,
    force_attempt: bool,
) -> dict[str, Any]:
    """
    Returns normalized validation payload. URL is derived only from Vercel `dep` (same as deploy truth).
    """
    checked = datetime.now(timezone.utc).isoformat()
    ui, vraw = _deployment_state_fields(dep)
    durl = _resolve_deployment_url(dep, ui)

    if ui != "ready":
        return {
            "state": "not_attempted",
            "checked_at": checked,
            "url_probed": durl,
            "http_status": None,
            "match_confidence": match_confidence,
            "reason_code": "deploy_not_ready",
            "message": f"Validation runs only when Vercel deployment is ready (current: {vraw or 'unknown'}).",
        }

    if not durl or not durl.strip():
        return {
            "state": "not_attempted",
            "checked_at": checked,
            "url_probed": None,
            "http_status": None,
            "match_confidence": match_confidence,
            "reason_code": "no_url",
            "message": "No deployment URL resolved from the matched Vercel deployment for probing.",
        }

    durl = durl.strip()
    if (match_confidence or "") != "high" and not force_attempt:
        return {
            "state": "not_attempted",
            "checked_at": checked,
            "url_probed": durl,
            "http_status": None,
            "match_confidence": match_confidence,
            "reason_code": "confidence_skip",
            "message": "Automatic validation runs only for high-confidence deploy matches, or with force=1 (manual re-check).",
        }

    allowed = allowed_hosts_for_deployment(dep, durl)
    if not allowed:
        return {
            "state": "inconclusive",
            "checked_at": checked,
            "url_probed": durl,
            "http_status": None,
            "match_confidence": match_confidence,
            "reason_code": "no_allowed_hosts",
            "message": "Could not build a host allowlist from the Vercel deployment; cannot redirect safely.",
        }

    return _run_with_retries(
        durl=durl,
        allowed=allowed,
        match_confidence=match_confidence,
        checked=checked,
    )


def _run_with_retries(
    *,
    durl: str,
    allowed: frozenset[str],
    match_confidence: MatchConfidence | None,
    checked: str,
) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    for attempt in range(3):
        out = _run_once(durl, allowed, match_confidence, checked)
        last = out
        rc = out.get("reason_code")
        st = out.get("state")
        if st != "inconclusive" or rc not in ("network_error", "timeout_error"):
            return out
        if attempt < 2:
            time.sleep(0.2 * (2**attempt))
    assert last is not None
    return last


def _run_once(
    durl: str,
    allowed: frozenset[str],
    match_confidence: MatchConfidence | None,
    checked: str,
) -> dict[str, Any]:
    marker = _content_marker()
    final_url, last_status, body, rcode, detail = _probe_url_allowlisted(durl, allowed)

    if rcode is not None:
        st2: ValidationState
        st2 = "inconclusive" if rcode in ("timeout_error", "network_error", "too_many_redirects", "redirect_disallowed") else "failed"
        return {
            "state": st2,
            "checked_at": checked,
            "url_probed": durl,
            "final_url": final_url,
            "http_status": str(last_status) if last_status is not None else None,
            "match_confidence": match_confidence,
            "reason_code": rcode,
            "message": f"Server-side check did not complete ({detail or rcode}). May be transient. Not a user-browser test.",
        }

    assert last_status is not None
    code = last_status
    if not (200 <= code < 300):
        return {
            "state": "failed",
            "checked_at": checked,
            "url_probed": durl,
            "final_url": final_url,
            "http_status": str(code),
            "match_confidence": match_confidence,
            "reason_code": "http_not_success",
            "message": f"URL responded with HTTP {code}. Server-side only; not full E2E validation.",
        }

    text = body.decode("utf-8", errors="replace")
    if marker and not _body_marker_match(text, marker):
        return {
            "state": "failed",
            "checked_at": checked,
            "url_probed": durl,
            "final_url": final_url,
            "http_status": str(code),
            "match_confidence": match_confidence,
            "reason_code": "marker_missing",
            "message": "HAM_POST_DEPLOY_VALIDATION_SUBSTRING was not found in the bounded response. Server-side check only.",
        }

    return {
        "state": "passed",
        "checked_at": checked,
        "url_probed": durl,
        "final_url": final_url,
        "http_status": str(code),
        "match_confidence": match_confidence,
        "reason_code": "success",
        "message": "Server-side check passed (HTTP 2xx"
        + (f", substring match against HAM_POST_DEPLOY_VALIDATION_SUBSTRING)." if marker else ", no content marker configured).")
        + " This does not prove a logged-in user experience or business correctness.",
    }
