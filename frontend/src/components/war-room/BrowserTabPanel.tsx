import * as React from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import {
  captureBrowserScreenshot,
  clickBrowserSession,
  closeBrowserSession,
  createBrowserSession,
  getBrowserSessionState,
  navigateBrowserSession,
  resetBrowserSession,
  type BrowserRuntimeState,
  typeBrowserSession,
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

export function BrowserTabPanel({ embedUrl, onEmbedUrlChange, autoStart = false }: BrowserTabPanelProps) {
  const ownerKeyRef = React.useRef<string>(`pane_${crypto.randomUUID()}`);
  const autoStartedRef = React.useRef(false);
  const [session, setSession] = React.useState<BrowserRuntimeState | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [selector, setSelector] = React.useState("");
  const [typeSelector, setTypeSelector] = React.useState("");
  const [typeText, setTypeText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = React.useState<string | null>(null);
  const normalizedUrl = normalizeBrowserUrl(embedUrl);
  const canOpen = normalizedUrl.startsWith("http");
  const hasSession = session !== null;
  async function capture(sessionId: string) {
    const png = await captureBrowserScreenshot(sessionId, ownerKeyRef.current);
    if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
    setScreenshotUrl(URL.createObjectURL(png));
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
      if (next.current_url && next.current_url !== "about:blank") {
        onEmbedUrlChange(next.current_url);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Browser runtime action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshStateAndScreenshot() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const [state, png] = await Promise.all([
        getBrowserSessionState(session.session_id, ownerKeyRef.current),
        captureBrowserScreenshot(session.session_id, ownerKeyRef.current),
      ]);
      setSession(state);
      if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
      setScreenshotUrl(URL.createObjectURL(png));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to refresh browser state.");
    } finally {
      setBusy(false);
    }
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
      await capture(created.session_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start browser session.");
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
      await closeBrowserSession(session.session_id, ownerKeyRef.current);
      setSession(null);
      if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
      setScreenshotUrl(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to close browser session.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 flex flex-col min-h-0 flex-1">
      <p className="text-[9px] font-bold text-white/35 uppercase tracking-widest">
        HAM-owned Browser Runtime (in-pane) — no live streaming and no Cursor embedding in v1.
      </p>
      {!hasSession ? (
        <div className="space-y-3 border border-dashed border-white/15 rounded p-4">
          <p className="text-[10px] text-white/45 leading-relaxed">
            Start a Browser Runtime session to enable real navigate/click/type/screenshot actions.
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

          <div className="grid gap-2 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-[8px] font-black uppercase tracking-widest text-white/40">
                Click selector
              </label>
              <div className="flex gap-2">
                <input
                  value={selector}
                  onChange={(e) => setSelector(e.target.value)}
                  placeholder="button[type=submit]"
                  className="flex-1 bg-black/50 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40"
                />
                <button
                  type="button"
                  disabled={busy || !selector.trim()}
                  onClick={() =>
                    run(() => clickBrowserSession(session.session_id, ownerKeyRef.current, selector.trim()))
                  }
                  className={cn(
                    "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                    busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
                  )}
                >
                  Click
                </button>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-[8px] font-black uppercase tracking-widest text-white/40">
                Type action
              </label>
              <div className="grid grid-cols-1 gap-2">
                <input
                  value={typeSelector}
                  onChange={(e) => setTypeSelector(e.target.value)}
                  placeholder="input[name=email]"
                  className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40"
                />
                <div className="flex gap-2">
                  <input
                    value={typeText}
                    onChange={(e) => setTypeText(e.target.value)}
                    placeholder="text to type"
                    className="flex-1 bg-black/50 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40"
                  />
                  <button
                    type="button"
                    disabled={busy || !typeSelector.trim()}
                    onClick={() =>
                      run(() =>
                        typeBrowserSession(
                          session.session_id,
                          ownerKeyRef.current,
                          typeSelector.trim(),
                          typeText,
                          true,
                        ),
                      )
                    }
                    className={cn(
                      "text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15",
                      busy ? "text-white/20" : "text-white/70 hover:bg-white/5",
                    )}
                  >
                    Type
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[9px] text-white/50 font-mono">
            <span>status={session.status}</span>
            <span>host={session.runtime_host}</span>
            <span>transport={session.screenshot_transport}</span>
          </div>

          {error ? <p className="text-[10px] text-amber-500/90 font-mono">{error}</p> : null}

          {screenshotUrl ? (
            <img
              src={screenshotUrl}
              alt="Latest browser screenshot"
              className="w-full border border-[#00E5FF]/20 bg-black object-contain max-h-[360px]"
            />
          ) : (
            <div className="border border-dashed border-white/15 rounded p-5 text-[10px] text-white/30 text-center uppercase tracking-widest">
              Capture a screenshot to view current page output
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
