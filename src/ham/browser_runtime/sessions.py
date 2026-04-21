from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
from math import isfinite
from typing import Any
from urllib.parse import urlparse


class BrowserPolicyError(ValueError):
    """Raised when a URL fails Browser Runtime policy checks."""


class BrowserSessionError(RuntimeError):
    """Raised when a Browser Runtime session operation fails."""


class BrowserSessionNotFoundError(BrowserSessionError):
    """Raised when session id does not exist or has expired/closed."""


class BrowserSessionOwnerMismatchError(BrowserSessionError):
    """Raised when a caller does not own the session."""


class BrowserSessionConflictError(BrowserSessionError):
    """Raised when session state disallows an operation."""


class BrowserScreenshotTooLargeError(BrowserSessionError):
    """Raised when screenshot bytes exceed configured v1 limit."""


@dataclass
class BrowserSessionRecord:
    session_id: str
    owner_key: str
    created_at_ms: int
    touched_at_ms: int
    page: Any
    context: Any
    viewport_width: int
    viewport_height: int
    status: str = "ready"
    last_error: str | None = None
    stream_status: str = "disconnected"
    stream_mode: str = "none"
    stream_requested_transport: str = "none"
    stream_last_error: str | None = None


def _utc_now_ms() -> int:
    return int(time.time() * 1000)


def _utc_iso_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def _split_csv_env(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _is_private_or_local_host(host: str) -> bool:
    h = host.strip().lower()
    if not h:
        return True
    if h in {"localhost", "::1", "[::1]"}:
        return True
    if h.endswith(".local"):
        return True
    try:
        parsed = ip_address(h)
    except ValueError:
        return False
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
    )


class BrowserSessionManager:
    """
    HAM-owned local Browser Runtime session manager (Playwright).

    Locked v1 decisions:
    - Runtime host: local HAM API process.
    - Session ownership: owner-key scoped to one in-pane client.
    - Domain policy: block local/private targets unless explicit env override.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, BrowserSessionRecord] = {}
        self._playwright = None
        self._browser = None

        self._ttl_seconds = max(60, int((os.environ.get("HAM_BROWSER_SESSION_TTL_SECONDS") or "900").strip()))
        self._max_actions_per_minute = max(
            5, int((os.environ.get("HAM_BROWSER_MAX_ACTIONS_PER_MINUTE") or "120").strip())
        )
        self._allow_private_network = (os.environ.get("HAM_BROWSER_ALLOW_PRIVATE_NETWORK") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self._allowed_domains = _split_csv_env("HAM_BROWSER_ALLOWED_DOMAINS")
        self._blocked_domains = _split_csv_env("HAM_BROWSER_BLOCKED_DOMAINS")
        self._max_screenshot_bytes = max(
            32_768, int((os.environ.get("HAM_BROWSER_MAX_SCREENSHOT_BYTES") or "5000000").strip())
        )
        self._action_hits: dict[tuple[str, int], int] = {}
        self._webrtc_enabled = (os.environ.get("HAM_BROWSER_ENABLE_WEBRTC") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise BrowserSessionError(
                "Playwright is not installed on this HAM API host. Install dependency `playwright` and run `playwright install chromium`."
            ) from exc
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise BrowserSessionError(
                f"Playwright runtime failed to start: {exc}"
            ) from exc
        return self._browser

    def _check_owner(self, session: BrowserSessionRecord, owner_key: str) -> None:
        if session.owner_key != owner_key:
            raise BrowserSessionOwnerMismatchError("Session owner mismatch.")

    def _touch(self, session: BrowserSessionRecord) -> None:
        session.touched_at_ms = _utc_now_ms()

    def _evict_expired_locked(self) -> None:
        now = _utc_now_ms()
        ttl_ms = self._ttl_seconds * 1000
        expired = [
            sid for sid, rec in self._sessions.items() if (now - rec.touched_at_ms) > ttl_ms
        ]
        for sid in expired:
            rec = self._sessions.pop(sid, None)
            if rec is None:
                continue
            try:
                rec.context.close()
            except Exception:
                pass

    def _check_rate_limit(self, session_id: str) -> None:
        minute_bucket = int(time.time() // 60)
        key = (session_id, minute_bucket)
        hits = self._action_hits.get(key, 0) + 1
        self._action_hits[key] = hits
        if hits > self._max_actions_per_minute:
            raise BrowserSessionConflictError("Action rate limit exceeded for this session.")

    @staticmethod
    def _host_matches_domain(host: str, domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    def _enforce_domain_policy(self, url: str) -> None:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().strip()
        if scheme not in {"http", "https"}:
            raise BrowserPolicyError("Only http:// and https:// URLs are allowed.")
        if not host:
            raise BrowserPolicyError("URL host is required.")
        if any(self._host_matches_domain(host, blocked) for blocked in self._blocked_domains):
            raise BrowserPolicyError("Target domain is blocked by HAM_BROWSER_BLOCKED_DOMAINS.")
        if self._allowed_domains:
            if not any(self._host_matches_domain(host, allowed) for allowed in self._allowed_domains):
                raise BrowserPolicyError("Target domain is not allowed by HAM_BROWSER_ALLOWED_DOMAINS.")
        if not self._allow_private_network and _is_private_or_local_host(host):
            raise BrowserPolicyError(
                "Local/private network targets are blocked. Set HAM_BROWSER_ALLOW_PRIVATE_NETWORK=true to override."
            )

    @staticmethod
    def _ensure_actionable(rec: BrowserSessionRecord, action_name: str) -> None:
        blocked_while_error = {"click", "type", "click_xy", "scroll", "key_press"}
        if rec.status == "error" and action_name in blocked_while_error:
            raise BrowserSessionConflictError(
                "Session is in error state for interactive input. Use navigate/reset to recover."
            )

    def _get_session_locked(self, session_id: str) -> BrowserSessionRecord:
        rec = self._sessions.get(session_id)
        if rec is None:
            raise BrowserSessionNotFoundError(f"Unknown session_id: {session_id}")
        return rec

    def create_session(
        self,
        *,
        owner_key: str,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            browser = self._ensure_browser()
            context = browser.new_context(viewport={"width": viewport_width, "height": viewport_height})
            page = context.new_page()
            now = _utc_now_ms()
            session_id = f"brs_{uuid.uuid4().hex[:12]}"
            self._sessions[session_id] = BrowserSessionRecord(
                session_id=session_id,
                owner_key=owner_key,
                created_at_ms=now,
                touched_at_ms=now,
                page=page,
                context=context,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )
            return self._state_from_record(self._sessions[session_id])

    def close_session(self, *, session_id: str, owner_key: str) -> None:
        with self._lock:
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._sessions.pop(session_id, None)
            try:
                rec.context.close()
            except Exception:
                pass

    def navigate(self, *, session_id: str, owner_key: str, url: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "navigate")
            self._enforce_domain_policy(url)
            try:
                rec.status = "busy"
                rec.page.goto(url.strip(), wait_until="domcontentloaded", timeout=30000)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Navigate failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def click(self, *, session_id: str, owner_key: str, selector: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "click")
            try:
                rec.status = "busy"
                rec.page.click(selector, timeout=15000)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Click failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def type_text(
        self, *, session_id: str, owner_key: str, selector: str, text: str, clear_first: bool
    ) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "type")
            try:
                rec.status = "busy"
                if clear_first:
                    rec.page.fill(selector, text, timeout=15000)
                else:
                    rec.page.type(selector, text, timeout=15000)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Type failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def screenshot_png(self, *, session_id: str, owner_key: str) -> bytes:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "screenshot")
            try:
                rec.status = "busy"
                image = rec.page.screenshot(type="png", full_page=False)
                if len(image) > self._max_screenshot_bytes:
                    raise BrowserScreenshotTooLargeError(
                        "Screenshot exceeds HAM_BROWSER_MAX_SCREENSHOT_BYTES."
                    )
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                if isinstance(exc, BrowserScreenshotTooLargeError):
                    raise exc
                raise BrowserSessionError(f"Screenshot failed: {exc}") from exc
            finally:
                self._touch(rec)
            return image

    def reset(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            try:
                rec.status = "busy"
                rec.page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Reset failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def get_state(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._touch(rec)
            return self._state_from_record(rec)

    def _state_from_record(self, rec: BrowserSessionRecord) -> dict[str, Any]:
        current_url = rec.page.url if rec.page is not None else ""
        title = ""
        if rec.page is not None:
            try:
                title = rec.page.title() or ""
            except Exception:
                title = ""
        return {
            "session_id": rec.session_id,
            "status": rec.status,
            "last_error": rec.last_error,
            "current_url": current_url,
            "title": title,
            "viewport": {
                "width": rec.viewport_width,
                "height": rec.viewport_height,
            },
            "created_at": _utc_iso_from_ms(rec.created_at_ms),
            "updated_at": _utc_iso_from_ms(rec.touched_at_ms),
            "ownership": "pane_owner_key",
            "runtime_host": "ham_api_local",
            "screenshot_transport": "binary_png_endpoint",
            "streaming_supported": False,
            "cursor_embedding_supported": False,
            "stream_state": self._stream_payload(rec),
        }

    @staticmethod
    def _stream_payload(rec: BrowserSessionRecord) -> dict[str, Any]:
        return {
            "status": rec.stream_status,
            "mode": rec.stream_mode,
            "requested_transport": rec.stream_requested_transport,
            "last_error": rec.stream_last_error,
        }

    def policy_snapshot(self) -> dict[str, Any]:
        return {
            "runtime_host": "ham_api_local",
            "session_ownership": "pane_owner_key",
            "screenshot_transport": "binary_png_endpoint",
            "streaming_supported": True,
            "cursor_embedding_supported": False,
            "supported_live_transports": ["screenshot_loop"],
            "webrtc_enabled": self._webrtc_enabled,
            "allow_private_network": self._allow_private_network,
            "allowed_domains": list(self._allowed_domains),
            "blocked_domains": list(self._blocked_domains),
            "session_ttl_seconds": self._ttl_seconds,
            "max_actions_per_minute": self._max_actions_per_minute,
            "max_screenshot_bytes": self._max_screenshot_bytes,
        }

    def start_stream(self, *, session_id: str, owner_key: str, requested_transport: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            transport = (requested_transport or "").strip().lower() or "screenshot_loop"
            rec.stream_requested_transport = transport
            if rec.status == "error":
                rec.stream_status = "degraded"
                rec.stream_mode = "screenshot_loop"
                rec.stream_last_error = "Session is in error state. Use navigate/reset to recover live updates."
                self._touch(rec)
                return self._stream_payload(rec)
            if transport == "webrtc" and not self._webrtc_enabled:
                rec.stream_status = "degraded"
                rec.stream_mode = "screenshot_loop"
                rec.stream_last_error = (
                    "WebRTC transport is not enabled on this HAM host. Falling back to screenshot_loop live transport."
                )
            else:
                rec.stream_status = "live"
                rec.stream_mode = "screenshot_loop"
                rec.stream_last_error = None
            self._touch(rec)
            return self._stream_payload(rec)

    def stop_stream(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            rec.stream_status = "disconnected"
            rec.stream_mode = "none"
            rec.stream_last_error = None
            self._touch(rec)
            return self._stream_payload(rec)

    def get_stream_state(self, *, session_id: str, owner_key: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._touch(rec)
            return self._stream_payload(rec)

    def handle_webrtc_offer(
        self, *, session_id: str, owner_key: str, sdp: str, offer_type: str
    ) -> dict[str, Any]:
        _ = (sdp, offer_type)
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            if not self._webrtc_enabled:
                raise BrowserSessionConflictError(
                    "WebRTC handshake is not enabled on this HAM host."
                )
            raise BrowserSessionConflictError("WebRTC handshake path is reserved but not active in this build.")

    def handle_webrtc_candidate(
        self, *, session_id: str, owner_key: str, candidate: str
    ) -> dict[str, Any]:
        _ = candidate
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            if not self._webrtc_enabled:
                raise BrowserSessionConflictError(
                    "WebRTC candidate handling is not enabled on this HAM host."
                )
            raise BrowserSessionConflictError("WebRTC candidate path is reserved but not active in this build.")

    def click_xy(
        self, *, session_id: str, owner_key: str, x: float, y: float, button: str = "left"
    ) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "click_xy")
            if not isfinite(x) or not isfinite(y):
                raise BrowserPolicyError("Click coordinates must be finite numbers.")
            if x < 0 or y < 0 or x > rec.viewport_width or y > rec.viewport_height:
                raise BrowserPolicyError(
                    f"Click coordinates out of viewport bounds (0..{rec.viewport_width}, 0..{rec.viewport_height})."
                )
            try:
                rec.status = "busy"
                rec.page.mouse.click(x, y, button=button)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Coordinate click failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def scroll(
        self, *, session_id: str, owner_key: str, delta_x: float = 0.0, delta_y: float = 0.0
    ) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "scroll")
            if not isfinite(delta_x) or not isfinite(delta_y):
                raise BrowserPolicyError("Scroll deltas must be finite numbers.")
            delta_x = max(-2000.0, min(2000.0, delta_x))
            delta_y = max(-2000.0, min(2000.0, delta_y))
            try:
                rec.status = "busy"
                rec.page.mouse.wheel(delta_x, delta_y)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Scroll failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

    def key_press(self, *, session_id: str, owner_key: str, key: str) -> dict[str, Any]:
        with self._lock:
            self._evict_expired_locked()
            rec = self._get_session_locked(session_id)
            self._check_owner(rec, owner_key)
            self._check_rate_limit(session_id)
            self._ensure_actionable(rec, "key_press")
            try:
                rec.status = "busy"
                rec.page.keyboard.press(key)
                rec.last_error = None
                rec.status = "ready"
            except Exception as exc:
                rec.status = "error"
                rec.last_error = str(exc)
                raise BrowserSessionError(f"Key press failed: {exc}") from exc
            finally:
                self._touch(rec)
            return self._state_from_record(rec)

