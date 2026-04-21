import * as React from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import {
  captureBrowserScreenshot,
  clickBrowserSessionXY,
  closeBrowserSession,
  createBrowserSession,
  getBrowserLiveStreamState,
  getBrowserSessionState,
  navigateBrowserSession,
  resetBrowserSession,
  scrollBrowserSession,
  sendBrowserSessionKey,
  startBrowserLiveStream,
  stopBrowserLiveStream,
  type BrowserStreamState,
  type BrowserRuntimeState,
} from "@/lib/ham/api";
import { cn } from "@/lib/utils";

export interface BrowserTabPanelProps {
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  autoStart?: boolean;
}

function normalizeBrowserUrl(raw: string): string {
  const t = raw.trim();
  if (!t) return "";
  if (/^https?:\/\//i.test(t)) return t;
  if (/^[a-z0-9.-]+\.[a-z]{2,}(\/.*)?$/i.test(t)) return `https://${t}`;
  return t;
}

const LIVE_POLL_FAST_MS = 450;
const LIVE_POLL_RECOVER_MS = 900;
const LIVE_POLL_DEGRADED_MS = 1400;
const MAX_RECONNECT_ATTEMPTS = 4;

function readErrorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Browser runtime action failed.";
}

function isSessionMissingError(message: string): boolean {
  return /unknown session_id|404/i.test(message);
}

function isOwnerMismatchError(message: string): boolean {
  return /owner mismatch|403/i.test(message);
}

function userFacingError(message: string): string {
  if (isSessionMissingError(message)) return "Session ended. Start a new browser session.";
  if (isOwnerMismatchError(message)) return "Session ownership changed. Open a new browser session.";
  if (/blocked|allow_private_network|allowed_domains|422/i.test(message)) {
    return "Target URL is blocked by browser policy.";
  }
  if (/only http:\/\/ and https:\/\//i.test(message)) return "Only http(s) URLs are supported.";
  if (/playwright runtime failed to start|playwright is not installed/i.test(message)) {
    return "Browser runtime is unavailable on this API host.";
  }
  return message;
}

function pollDelayForStatus(status: BrowserStreamState["status"]): number {
  if (status === "live") return LIVE_POLL_FAST_MS;
  if (status === "reconnecting") return LIVE_POLL_RECOVER_MS;
  return LIVE_POLL_DEGRADED_MS;
}

function mapViewportClick(
  event: React.MouseEvent<HTMLImageElement>,
  imageEl: HTMLImageElement,
  viewport: { width: number; height: number },
): { x: number; y: number } | null {
  const rect = imageEl.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return null;
  const sourceAspect = viewport.width / viewport.height;
  const boxAspect = rect.width / rect.height;
  const drawWidth = sourceAspect >= boxAspect ? rect.width : rect.height * sourceAspect;
  const drawHeight = sourceAspect >= boxAspect ? rect.width / sourceAspect : rect.height;
  const offsetX = (rect.width - drawWidth) / 2;
  const offsetY = (rect.height - drawHeight) / 2;
  const localX = event.clientX - rect.left - offsetX;
  const localY = event.clientY - rect.top - offsetY;
  if (localX < 0 || localY < 0 || localX > drawWidth || localY > drawHeight) return null;
  const nx = localX / drawWidth;
  const ny = localY / drawHeight;
  // Playwright mouse coordinates use CSS pixels in page viewport space.
  return { x: nx * viewport.width, y: ny * viewport.height };
}

export function BrowserTabPanel({ embedUrl, onEmbedUrlChange, autoStart = false }: BrowserTabPanelProps) {
  const ownerKeyRef = React.useRef<string>(`pane_${crypto.randomUUID()}`);
  const autoStartedRef = React.useRef(false);
  const imageRef = React.useRef<HTMLImageElement | null>(null);
  const viewportFrameRef = React.useRef<HTMLDivElement | null>(null);
  const pollInFlightRef = React.useRef(false);
  const reconnectCountRef = React.useRef(0);
  const [session, setSession] = React.useState<BrowserRuntimeState | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [streamState, setStreamState] = React.useState<BrowserStreamState>({
    status: "disconnected",
    mode: "none",
    requested_transport: "none",
    last_error: null,
  });
  const [error, setError] = React.useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = React.useState<string | null>(null);
  const normalizedUrl = normalizeBrowserUrl(embedUrl);
  const canOpen = normalizedUrl.startsWith("http");
  const hasSession = session !== null;

  function replaceScreenshot(next: Blob) {
    setScreenshotUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(next);
    });
  }

  async function capture(sessionId: string) {
    const png = await captureBrowserScreenshot(sessionId, ownerKeyRef.current);
    replaceScreenshot(png);
  }


  React.useEffect(() => {
    return () => {
      if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
    };
  }, [screenshotUrl]);

  async function run(action: () => Promise<BrowserRuntimeState>) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setSession(next);
      setStreamState(next.stream_state);
      if (next.current_url && next.current_url !== "about:blank") {
        onEmbedUrlChange(next.current_url);
      }
    } catch (e: unknown) {
      const message = readErrorMessage(e);
      if (isSessionMissingError(message)) {
        setSession(null);
        setStreamState({
          status: "disconnected",
          mode: "none",
          requested_transport: "none",
          last_error: message,
        });
      }
      setError(userFacingError(message));
    } finally {
      setBusy(false);
    }
  }

  async function refreshStateAndScreenshot() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const [state, live, png] = await Promise.all([
        getBrowserSessionState(session.session_id, ownerKeyRef.current),
        getBrowserLiveStreamState(session.session_id, ownerKeyRef.current),
        captureBrowserScreenshot(session.session_id, ownerKeyRef.current),
      ]);
      setSession(state);
      setStreamState(live);
      replaceScreenshot(png);
    } catch (e: unknown) {
      const message = readErrorMessage(e);
      if (isSessionMissingError(message)) {
        setSession(null);
        setStreamState({
          status: "disconnected",
          mode: "none",
          requested_transport: "none",
          last_error: message,
        });
      }
      setError(userFacingError(message));
    } finally {
      setBusy(false);
    }
  }

  async function startLiveStream(sessionId: string) {
    setStreamState({
      status: "connecting",
      mode: "negotiating",
      requested_transport: "screenshot_loop",
      last_error: null,
    });
    const started = await startBrowserLiveStream(
      sessionId,
      ownerKeyRef.current,
      "screenshot_loop",
    );
    setStreamState(started);
  }

  async function handleCreateSession() {
    setBusy(true);
    setError(null);
    try {
      const created = await createBrowserSession({
        owner_key: ownerKeyRef.current,
        viewport_width: 1280,
        viewport_height: 720,
      });
      const bootUrl = normalizedUrl || "https://www.google.com";
      const next = await navigateBrowserSession(created.session_id, ownerKeyRef.current, bootUrl);
      setSession(next);
      onEmbedUrlChange(bootUrl);
      await startLiveStream(created.session_id);
      await capture(created.session_id);
    } catch (e: unknown) {
      const message = readErrorMessage(e);
      setError(userFacingError(message));
      setStreamState({
        status: "error",
        mode: "none",
        requested_transport: "screenshot_loop",
        last_error: message,
      });
    } finally {
      setBusy(false);
    }
  }

  React.useEffect(() => {
    if (!autoStart || autoStartedRef.current || hasSession || busy) return;
    autoStartedRef.current = true;
    void handleCreateSession();
  }, [autoStart, hasSession, busy]);

  async function handleCloseSession() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await stopBrowserLiveStream(session.session_id, ownerKeyRef.current);
      await closeBrowserSession(session.session_id, ownerKeyRef.current);
      setSession(null);
      if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
      setScreenshotUrl(null);
      setStreamState({
        status: "disconnected",
        mode: "none",
        requested_transport: "none",
        last_error: null,
      });
    } catch (e: unknown) {
      setError(userFacingError(readErrorMessage(e)));
    } finally {
      setBusy(false);
    }
  }

  React.useEffect(() => {
    if (!session) return;
    if (!["live", "degraded", "reconnecting", "connecting"].includes(streamState.status)) return;
    let cancelled = false;
    let timeoutId: number | null = null;

    const poll = () => {
      if (cancelled || pollInFlightRef.current || busy) {
        const wait = pollDelayForStatus(streamState.status);
        timeoutId = window.setTimeout(poll, wait);
        return;
      }
      pollInFlightRef.current = true;
      Promise.all([
        captureBrowserScreenshot(session.session_id, ownerKeyRef.current),
        getBrowserLiveStreamState(session.session_id, ownerKeyRef.current),
      ])
        .then(([png, live]) => {
          replaceScreenshot(png);
          setStreamState(live);
          reconnectCountRef.current = 0;
        })
        .catch((e: unknown) => {
          const message = readErrorMessage(e);
          if (isSessionMissingError(message) || isOwnerMismatchError(message)) {
            setSession(null);
            setStreamState({
              status: "disconnected",
              mode: "none",
              requested_transport: "none",
              last_error: message,
            });
            setError(userFacingError(message));
            return;
          }
          reconnectCountRef.current += 1;
          if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
            setStreamState((prev) => ({
              ...prev,
              status: "reconnecting",
              last_error: message,
            }));
            return;
          }
          setStreamState((prev) => ({
            ...prev,
            status: "degraded",
            last_error: message,
          }));
          setError("Live updates degraded. Use Navigate/Capture/Reset while reconnecting.");
        })
        .finally(() => {
          pollInFlightRef.current = false;
          if (!cancelled) {
            const wait = pollDelayForStatus(streamState.status);
            timeoutId = window.setTimeout(poll, wait);
          }
        });
    };

    poll();

    return () => {
      cancelled = true;
      if (timeoutId != null) window.clearTimeout(timeoutId);
    };
  }, [busy, session, streamState.status]);

  async function handleViewportClick(event: React.MouseEvent<HTMLImageElement>) {
    if (!session || !imageRef.current) return;
    const mapped = mapViewportClick(event, imageRef.current, session.viewport);
    if (!mapped) return;
    await run(() =>
      clickBrowserSessionXY(session.session_id, ownerKeyRef.current, mapped.x, mapped.y),
    );
    await capture(session.session_id);
  }

  async function handleViewportWheel(event: React.WheelEvent<HTMLImageElement>) {
    if (!session) return;
    event.preventDefault();
    await run(() =>
      scrollBrowserSession(
        session.session_id,
        ownerKeyRef.current,
        Math.max(-2000, Math.min(2000, event.deltaX)),
        Math.max(-2000, Math.min(2000, event.deltaY)),
      ),
    );
  }

  async function handleViewportKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!session) return;
    let key = event.key;
    if (key === " ") key = "Space";
    if (key.length > 1 && !/^F\d{1,2}$/.test(key) && !key.startsWith("Arrow")) {
      const allowed = new Set(["Enter", "Backspace", "Tab", "Escape", "Delete", "Home", "End", "PageUp", "PageDown"]);
      if (!allowed.has(key)) return;
    }
    event.preventDefault();
    viewportFrameRef.current?.focus();
    await run(() => sendBrowserSessionKey(session.session_id, ownerKeyRef.current, key));
  }

  return (
    <div className="space-y-3 flex flex-col min-h-0 flex-1">
      <p className="text-[9px] font-bold text-white/35 uppercase tracking-widest">
        HAM Browser Surface (in-pane live transport)
      </p>
      {!hasSession ? (
        <div className="space-y-3 border border-dashed border-white/15 rounded p-4">
          <p className="text-[10px] text-white/45 leading-relaxed">
            Start a browser session to open a live in-pane viewport.
          </p>
          <button
            type="button"
            onClick={handleCreateSession}
            disabled={busy}
            className={cn(
              "inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest px-3 py-2 border border-[#00E5FF]/35",
              busy ? "text-white/30 border-white/20" : "text-[#00E5FF] hover:bg-white/5",
            )}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            Create Browser Session
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-2 md:grid-cols-[1fr_auto_auto]">
            <input
              value={embedUrl}
              onChange={(e) => onEmbedUrlChange(e.target.value)}
              placeholder="https://example.com"
              className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40"
            />
            <button
              type="button"
              disabled={busy || !embedUrl.trim()}
              onClick={() =>
                run(() =>
                  navigateBrowserSession(
                    session.session_id,
                    ownerKeyRef.current,
                    normalizeBrowserUrl(embedUrl),
                  ),
                )
              }
              className={cn(
                "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
              )}
            >
              Navigate
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={refreshStateAndScreenshot}
              className={cn(
                "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
              )}
            >
              Capture
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[9px] text-white/50 font-mono">
            <span>status={session.status}</span>
            <span>host={session.runtime_host}</span>
            <span>transport={streamState.mode}</span>
            <span>stream={streamState.status}</span>
          </div>

          {error ? <p className="text-[10px] text-amber-500/90 font-mono">{error}</p> : null}
          {streamState.last_error ? (
            <p className="text-[10px] text-amber-400/90 font-mono">{streamState.last_error}</p>
          ) : null}

          {screenshotUrl ? (
            <div
              ref={viewportFrameRef}
              tabIndex={0}
              onKeyDown={(e) => {
                void handleViewportKeyDown(e);
              }}
              className="outline-none focus:ring-1 focus:ring-[#00E5FF]/40 rounded"
            >
              <img
                ref={imageRef}
                src={screenshotUrl}
                alt="Live in-pane browser viewport"
                onClick={(e) => {
                  viewportFrameRef.current?.focus();
                  void handleViewportClick(e);
                }}
                onWheel={(e) => {
                  void handleViewportWheel(e);
                }}
                className="w-full border border-[#00E5FF]/20 bg-black object-contain max-h-[480px] cursor-crosshair select-none"
              />
            </div>
          ) : (
            <div className="border border-dashed border-white/15 rounded p-5 text-[10px] text-white/30 text-center uppercase tracking-widest">
              Connecting to browser viewport
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => resetBrowserSession(session.session_id, ownerKeyRef.current))}
              className={cn(
                "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
              )}
            >
              Reset
            </button>
            <button
              type="button"
              disabled={busy || !session}
              onClick={() => {
                if (!session) return;
                void startLiveStream(session.session_id);
              }}
              className={cn(
                "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
              )}
            >
              Reconnect
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleCloseSession}
              className={cn(
                "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
              )}
            >
              Close Session
            </button>
          </div>
        </div>
      )}
      <a
        href={canOpen ? normalizedUrl : "#"}
        target="_blank"
        rel="noreferrer"
        className={cn(
          "inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15 w-fit",
          canOpen ? "text-[#00E5FF] hover:bg-white/5" : "text-white/20 pointer-events-none",
        )}
      >
        <ExternalLink className="h-3 w-3" />
        Open externally
      </a>
    </div>
  );
}
