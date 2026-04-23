import * as React from "react";
import { ExternalLink, Loader2, Maximize2, Minimize2, PictureInPicture2, Shrink } from "lucide-react";

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

export type BrowserViewMode = "normal" | "expanded" | "minimized";

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
  // Playwright errors: show API detail verbatim (install `playwright`, `playwright install chromium`, etc.).
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

/* ------------------------------------------------------------------ */
/*  Compact toolbar button                                            */
/* ------------------------------------------------------------------ */
function ToolbarBtn({
  children,
  disabled,
  onClick,
  title,
  accent,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  title?: string;
  accent?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={title}
      className={cn(
        "inline-flex items-center justify-center h-6 w-6 rounded border border-white/10 transition-colors",
        disabled
          ? "text-white/15 cursor-not-allowed"
          : accent
            ? "text-[#00E5FF] hover:bg-[#00E5FF]/10 hover:border-[#00E5FF]/30"
            : "text-white/50 hover:bg-white/5 hover:text-white/80",
      )}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Pop-out overlay (portal-free, fixed overlay)                       */
/* ------------------------------------------------------------------ */
function BrowserPopout({
  screenshotUrl,
  imageRef,
  session,
  onClose,
  onViewportClick,
  onViewportWheel,
  onViewportKeyDown,
}: {
  screenshotUrl: string;
  imageRef: React.RefObject<HTMLImageElement | null>;
  session: BrowserRuntimeState;
  onClose: () => void;
  onViewportClick: (e: React.MouseEvent<HTMLImageElement>) => void;
  onViewportWheel: (e: React.WheelEvent<HTMLImageElement>) => void;
  onViewportKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
}) {
  const frameRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    frameRef.current?.focus();
  }, []);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative flex flex-col w-[92vw] h-[88vh] max-w-[1400px] bg-[#0d0d0d] border border-white/15 rounded-lg overflow-hidden shadow-2xl">
        {/* header */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-black/60 border-b border-white/10 shrink-0">
          <span className="text-[10px] font-black uppercase tracking-widest text-[#00E5FF]/80">
            HAM Browser — Pop-out View
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-white/30 font-mono">
              {session.viewport.width}×{session.viewport.height}
            </span>
            <button
              type="button"
              onClick={onClose}
              className="text-white/40 hover:text-white transition-colors p-1"
              title="Close pop-out (Esc)"
            >
              <Shrink className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* viewport */}
        <div
          ref={frameRef}
          tabIndex={0}
          onKeyDown={onViewportKeyDown}
          className="flex-1 min-h-0 flex items-center justify-center bg-black outline-none focus:ring-1 focus:ring-[#00E5FF]/30 focus:ring-inset"
        >
          <img
            ref={imageRef}
            src={screenshotUrl}
            alt="Live in-pane browser viewport (pop-out)"
            onClick={onViewportClick}
            onWheel={onViewportWheel}
            className="max-w-full max-h-full object-contain cursor-crosshair select-none"
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function BrowserTabPanel({ embedUrl, onEmbedUrlChange, autoStart = false }: BrowserTabPanelProps) {
  const ownerKeyRef = React.useRef<string>(`pane_${crypto.randomUUID()}`);
  const autoStartedRef = React.useRef(false);
  const imageRef = React.useRef<HTMLImageElement | null>(null);
  const popoutImageRef = React.useRef<HTMLImageElement | null>(null);
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

  /* ---- view mode state ---- */
  const [viewMode, setViewMode] = React.useState<BrowserViewMode>("normal");
  const [popoutOpen, setPopoutOpen] = React.useState(false);

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
    if (!session) return;
    // Use whichever image ref is currently active
    const activeImg = popoutOpen ? popoutImageRef.current : imageRef.current;
    if (!activeImg) return;
    const mapped = mapViewportClick(event, activeImg, session.viewport);
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

  /* ---- Minimized state: collapsed strip ---- */
  if (hasSession && viewMode === "minimized") {
    return (
      <div className="flex flex-col min-h-0 flex-1">
        <div className="flex items-center gap-2 px-2 py-1.5 bg-black/40 border border-white/10 rounded">
          <span className="text-[9px] font-black uppercase tracking-widest text-[#00E5FF]/70 truncate flex-1">
            Browser — {session!.current_url || "session active"}
          </span>
          <span className={cn(
            "text-[8px] font-mono uppercase px-1.5 py-0.5 rounded",
            streamState.status === "live" ? "text-emerald-400/90 bg-emerald-400/10" : "text-white/40 bg-white/5",
          )}>
            {streamState.status}
          </span>
          <ToolbarBtn onClick={() => setViewMode("normal")} title="Restore browser view" accent>
            <Maximize2 className="h-3 w-3" />
          </ToolbarBtn>
          <ToolbarBtn onClick={() => setPopoutOpen(true)} title="Pop out browser">
            <PictureInPicture2 className="h-3 w-3" />
          </ToolbarBtn>
        </div>

        {/* Pop-out overlay even in minimized */}
        {popoutOpen && screenshotUrl && session ? (
          <BrowserPopout
            screenshotUrl={screenshotUrl}
            imageRef={popoutImageRef}
            session={session}
            onClose={() => setPopoutOpen(false)}
            onViewportClick={(e) => void handleViewportClick(e)}
            onViewportWheel={(e) => void handleViewportWheel(e)}
            onViewportKeyDown={(e) => void handleViewportKeyDown(e)}
          />
        ) : null}
      </div>
    );
  }

  const isExpanded = viewMode === "expanded";

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-0">
      {!hasSession ? (
        /* ── No session: start prompt (compact) ── */
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center border border-dashed border-white/10 rounded bg-black/20 p-4 gap-3">
          {/* View-mode controls (top-right) */}
          <p className="text-[10px] text-white/40 leading-relaxed text-center">
            Start a browser session to open a live viewport.
          </p>
          <button
            type="button"
            onClick={handleCreateSession}
            disabled={busy}
            className={cn(
              "inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest px-4 py-2.5 rounded border border-[#00E5FF]/35",
              busy ? "text-white/30 border-white/20" : "text-[#00E5FF] hover:bg-[#00E5FF]/5",
            )}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            Create Browser Session
          </button>
          {error ? (
            <p className="text-[10px] text-amber-500/90 font-mono leading-relaxed text-center" role="alert">
              {error}
            </p>
          ) : null}
          {streamState.last_error && !error ? (
            <p className="text-[10px] text-amber-400/90 font-mono leading-relaxed text-center">
              {streamState.last_error}
            </p>
          ) : null}
          <p className="text-[8px] text-white/25 leading-relaxed text-center max-w-xs">
            Requires Ham API with Playwright. Check{" "}
            <span className="font-mono text-white/40">/api/browser/sessions</span> if this fails.
          </p>
        </div>
      ) : (
        <div className={cn("flex flex-col min-h-0 flex-1 gap-0", isExpanded && "relative")}>
          {/* ── Compact URL bar + view controls (single tight row) ── */}
          {!isExpanded ? (
            <div className="flex items-center gap-0.5 shrink-0">
              <input
                value={embedUrl}
                onChange={(e) => onEmbedUrlChange(e.target.value)}
                placeholder="https://…"
                className="flex-1 min-w-0 bg-black/50 border border-white/10 font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40 px-1.5 py-0.5 text-[9px] rounded-sm"
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
                  "text-[8px] font-black uppercase tracking-widest border border-white/15 px-1.5 py-0.5 rounded-sm shrink-0",
                  busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
                )}
              >
                Go
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={refreshStateAndScreenshot}
                className={cn(
                  "text-[8px] font-black uppercase tracking-widest border border-white/15 px-1.5 py-0.5 rounded-sm shrink-0",
                  busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
                )}
              >
                ⟳
              </button>
              <span className="w-px h-4 bg-white/10 shrink-0 mx-0.5" />
              <ToolbarBtn
                onClick={() => setViewMode("expanded")}
                title="Expand browser"
              >
                <Maximize2 className="h-3 w-3" />
              </ToolbarBtn>
              <ToolbarBtn onClick={() => setViewMode("minimized")} title="Minimize browser">
                <Minimize2 className="h-3 w-3" />
              </ToolbarBtn>
              <ToolbarBtn onClick={() => setPopoutOpen(true)} title="Pop out browser">
                <PictureInPicture2 className="h-3 w-3" />
              </ToolbarBtn>
            </div>
          ) : null}

          {/* ── Errors (compact, only when needed) ── */}
          {error ? <p className="text-[9px] text-amber-500/90 font-mono shrink-0 truncate px-0.5">{error}</p> : null}

          {/* ── Viewport: fills ALL remaining space ── */}
          {screenshotUrl ? (
            <div className="relative flex-1 min-h-0 flex flex-col">
              <div
                ref={viewportFrameRef}
                tabIndex={0}
                onKeyDown={(e) => {
                  void handleViewportKeyDown(e);
                }}
                className="flex-1 min-h-0 outline-none focus:ring-1 focus:ring-[#00E5FF]/30 rounded-sm flex items-center justify-center bg-black/40"
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
                  className="w-full h-full border border-[#00E5FF]/15 bg-black object-contain cursor-crosshair select-none"
                />
              </div>

              {/* ── Expanded mode: floating overlay toolbar ── */}
              {isExpanded ? (
                <div className="absolute top-1 left-1 right-1 z-10 flex items-center gap-0.5 bg-black/70 backdrop-blur-sm border border-white/10 rounded px-1 py-0.5 opacity-40 hover:opacity-100 transition-opacity">
                  <span className={cn(
                    "h-1.5 w-1.5 rounded-full shrink-0",
                    streamState.status === "live" ? "bg-emerald-400" : streamState.status === "connecting" ? "bg-amber-400 animate-pulse" : "bg-white/20",
                  )} />
                  <input
                    value={embedUrl}
                    onChange={(e) => onEmbedUrlChange(e.target.value)}
                    placeholder="https://…"
                    className="flex-1 min-w-0 bg-transparent font-mono text-white/70 placeholder:text-white/20 outline-none px-1 py-0 text-[9px]"
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
                      "text-[8px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded-sm shrink-0",
                      busy ? "text-white/20" : "text-white/60 hover:text-white/90",
                    )}
                  >
                    Go
                  </button>
                  <span className="w-px h-3 bg-white/10 shrink-0" />
                  <ToolbarBtn
                    onClick={() => setViewMode("normal")}
                    title="Normal view"
                    accent
                  >
                    <Shrink className="h-3 w-3" />
                  </ToolbarBtn>
                  <ToolbarBtn onClick={() => setViewMode("minimized")} title="Minimize browser">
                    <Minimize2 className="h-3 w-3" />
                  </ToolbarBtn>
                  <ToolbarBtn onClick={() => setPopoutOpen(true)} title="Pop out browser">
                    <PictureInPicture2 className="h-3 w-3" />
                  </ToolbarBtn>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="flex-1 min-h-0 border border-dashed border-white/10 rounded-sm flex items-center justify-center bg-black/20">
              <span className="text-[9px] text-white/25 text-center uppercase tracking-widest">
                Connecting to browser viewport
              </span>
            </div>
          )}

          {/* ── Session controls: single compact row ── */}
          <div className={cn(
            "flex items-center gap-1 shrink-0",
            isExpanded ? "absolute bottom-1 left-1 right-1 z-10 bg-black/70 backdrop-blur-sm border border-white/10 rounded px-1 py-0.5 opacity-30 hover:opacity-100 transition-opacity" : "",
          )}>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => resetBrowserSession(session.session_id, ownerKeyRef.current))}
              className={cn(
                "text-[8px] font-black uppercase tracking-widest border border-white/10 px-2 py-0.5 rounded-sm",
                busy ? "text-white/20" : "text-white/50 hover:bg-white/5 hover:text-white/70",
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
                "text-[8px] font-black uppercase tracking-widest border border-white/10 px-2 py-0.5 rounded-sm",
                busy ? "text-white/20" : "text-white/50 hover:bg-white/5 hover:text-white/70",
              )}
            >
              Reconnect
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleCloseSession}
              className={cn(
                "text-[8px] font-black uppercase tracking-widest border border-white/10 px-2 py-0.5 rounded-sm",
                busy ? "text-white/20" : "text-white/50 hover:bg-white/5 hover:text-white/70",
              )}
            >
              Close
            </button>
            <div className="flex-1" />
            <span className={cn(
              "text-[7px] font-mono px-1 py-0.5 rounded",
              streamState.status === "live" ? "text-emerald-400/70" : "text-white/25",
            )}>
              {streamState.status}
            </span>
            <a
              href={canOpen ? normalizedUrl : "#"}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "inline-flex items-center gap-1 text-[8px] font-black uppercase tracking-widest",
                canOpen ? "text-[#00E5FF]/70 hover:text-[#00E5FF]" : "text-white/15 pointer-events-none",
              )}
              title="Open in new tab"
            >
              <ExternalLink className="h-2.5 w-2.5" />
              <span className="hidden sm:inline">External</span>
            </a>
          </div>
        </div>
      )}

      {/* ── Pop-out overlay ── */}
      {popoutOpen && screenshotUrl && session ? (
        <BrowserPopout
          screenshotUrl={screenshotUrl}
          imageRef={popoutImageRef}
          session={session}
          onClose={() => setPopoutOpen(false)}
          onViewportClick={(e) => void handleViewportClick(e)}
          onViewportWheel={(e) => void handleViewportWheel(e)}
          onViewportKeyDown={(e) => void handleViewportKeyDown(e)}
        />
      ) : null}
    </div>
  );
}
