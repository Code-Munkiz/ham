import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowUp, Pencil, PanelLeft, SquareArrowOutUpRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { workspaceTerminalAdapter } from "../../adapters/terminalAdapter";
import { MobileTerminalInputBar } from "./MobileTerminalInputBar";

const BG = "#0d0d0d";

export type TabModel = {
  id: string;
  title: string;
  sessionId: string | null;
  outputLines: string[];
};

type WorkspaceTerminalViewProps = {
  mode: "page" | "panel";
  onMinimize?: () => void;
  onClosePanel?: () => void;
  /** when panel opens, optional initial session hint */
  className?: string;
};

let tabSeq = 0;
function newTabId() {
  tabSeq += 1;
  return `tab-${tabSeq}`;
}

function short(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function WorkspaceTerminalView({ mode, onMinimize, onClosePanel, className }: WorkspaceTerminalViewProps) {
  const [tabs, setTabs] = React.useState<TabModel[]>([
    { id: newTabId(), title: "Shell", sessionId: null, outputLines: [] },
  ]);
  const [activeId, setActiveId] = React.useState(() => tabs[0]!.id);
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number; tabId: string } | null>(null);
  const [lineInput, setLineInput] = React.useState("");
  const [bridgeLine, setBridgeLine] = React.useState<string | null>(null);
  const [isMobile, setIsMobile] = React.useState(false);
  const outRef = React.useRef<HTMLPreElement | null>(null);
  /** Viewport for output (used to approximate TTY cols/rows for the resize endpoint). */
  const terminalAreaRef = React.useRef<HTMLDivElement | null>(null);
  const activeSessionIdRef = React.useRef<string | null>(null);
  const lastResizeRef = React.useRef<{
    sid: string;
    cols: number;
    rows: number;
  } | null>(null);
  const resizeDebounce = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionAttempted = React.useRef<Set<string>>(new Set());
  /** Byte offset per session for /output?after= */
  const pollCursor = React.useRef<Record<string, number>>({});
  /** When the WebSocket stream is open, skip HTTP polling to avoid duplicate output. */
  const wsStopsPollRef = React.useRef(false);
  const active = tabs.find((t) => t.id === activeId) ?? tabs[0]!;

  /**
   * Approximate grid from panel size (PTY resize on Windows ConPTY; pipe mode records dimensions only).
   * Uses 12px mono text: ~7.2px char width, ~16px line height, minus p-2 (8px) padding.
   */
  const measureAndResize = React.useCallback(() => {
    const el = terminalAreaRef.current;
    const sid = activeSessionIdRef.current;
    if (!el || !sid) return;
    if (typeof window === "undefined" || typeof window.ResizeObserver === "undefined") return;
    const { width, height } = el.getBoundingClientRect();
    const pad = 16;
    const w = Math.max(0, width - pad);
    const h = Math.max(0, height - pad);
    const charPx = 7.2;
    const linePx = 16;
    const cols = Math.max(20, Math.min(200, Math.floor(w / charPx)));
    const rows = Math.max(4, Math.min(200, Math.floor(h / linePx)));
    const prev = lastResizeRef.current;
    if (prev && prev.sid === sid && prev.cols === cols && prev.rows === rows) return;
    lastResizeRef.current = { sid, cols, rows };
    void workspaceTerminalAdapter.resize(sid, cols, rows);
  }, []);

  activeSessionIdRef.current = active.sessionId;

  React.useLayoutEffect(() => {
    const el = terminalAreaRef.current;
    if (typeof window === "undefined" || !el || typeof ResizeObserver === "undefined") return;
    const schedule = () => {
      if (resizeDebounce.current) clearTimeout(resizeDebounce.current);
      resizeDebounce.current = setTimeout(() => {
        measureAndResize();
        resizeDebounce.current = null;
      }, 120);
    };
    const ro = new ResizeObserver(() => {
      schedule();
    });
    ro.observe(el);
    schedule();
    return () => {
      ro.disconnect();
      if (resizeDebounce.current) clearTimeout(resizeDebounce.current);
    };
  }, [measureAndResize]);

  React.useLayoutEffect(() => {
    if (!active.sessionId) return;
    const t = setTimeout(() => {
      lastResizeRef.current = null;
      measureAndResize();
    }, 0);
    return () => clearTimeout(t);
  }, [active.sessionId, activeId, measureAndResize]);

  const append = React.useCallback((tabId: string, line: string) => {
    setTabs((prev) =>
      prev.map((t) => (t.id === tabId ? { ...t, outputLines: [...t.outputLines, line] } : t)),
    );
  }, []);

  const appendStream = React.useCallback((tabId: string, chunk: string) => {
    if (!chunk) return;
    setTabs((prev) =>
      prev.map((t) => (t.id === tabId ? { ...t, outputLines: [...t.outputLines, chunk] } : t)),
    );
  }, []);

  React.useEffect(() => {
    const m = window.matchMedia("(max-width: 767px)");
    const u = () => setIsMobile(m.matches);
    u();
    m.addEventListener("change", u);
    return () => m.removeEventListener("change", u);
  }, []);

  React.useEffect(() => {
    if (!outRef.current) return;
    outRef.current.scrollTop = outRef.current.scrollHeight;
  }, [active.outputLines, activeId]);

  React.useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [contextMenu]);

  const activeSessionId = active.sessionId;

  // Bootstrap session for active tab (best-effort; bridge pending is ok).
  React.useEffect(() => {
    if (activeSessionId) return;
    if (sessionAttempted.current.has(activeId)) return;
    sessionAttempted.current.add(activeId);
    const tabId = activeId;
    let cancelled = false;
    (async () => {
      setBridgeLine("Starting terminal session");
      const { sessionId, bridge } = await workspaceTerminalAdapter.createSession(tabId);
      if (cancelled) return;
      if (bridge.status === "pending" || !sessionId) {
        setBridgeLine("Runtime bridge pending");
        setTabs((prev) => prev.map((t) => (t.id === tabId ? { ...t, sessionId: null } : t)));
        append(
          tabId,
          "No terminal session active — when the server bridge is available, output will stream here.",
        );
        return;
      }
      setBridgeLine(null);
      setTabs((prev) => prev.map((t) => (t.id === tabId ? { ...t, sessionId } : t)));
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId, activeSessionId, append]);

  // WebSocket: primary output when available; HTTP poll below is a fallback.
  React.useEffect(() => {
    wsStopsPollRef.current = false;
    const sid = active.sessionId;
    if (!sid) return;
    const url = workspaceTerminalAdapter.webSocketStreamUrl(sid);
    if (!url) return;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      return;
    }
    const onMessage = (ev: MessageEvent<string>) => {
      try {
        const j = JSON.parse(ev.data) as { type?: string; text?: string };
        if (j.type === "out" && typeof j.text === "string" && j.text) {
          appendStream(activeId, j.text);
        }
      } catch {
        /* ignore */
      }
    };
    ws.addEventListener("message", onMessage);
    ws.onopen = () => {
      wsStopsPollRef.current = true;
    };
    ws.onerror = () => {
      wsStopsPollRef.current = false;
    };
    ws.onclose = () => {
      wsStopsPollRef.current = false;
    };
    return () => {
      ws.onclose = null;
      ws.removeEventListener("message", onMessage);
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      wsStopsPollRef.current = false;
    };
  }, [active.sessionId, activeId, appendStream]);

  // Poll server process output (fallback when WebSocket is unavailable)
  React.useEffect(() => {
    const sid = active.sessionId;
    if (!sid) return;
    const tid = setInterval(() => {
      void (async () => {
        if (wsStopsPollRef.current) {
          return;
        }
        const after = pollCursor.current[sid] ?? 0;
        const { text, next, bridge } = await workspaceTerminalAdapter.pollOutput(sid, after);
        if (bridge.status === "ready" && text) {
          appendStream(activeId, text);
        }
        pollCursor.current[sid] = next;
      })();
    }, 500);
    return () => {
      clearInterval(tid);
    };
  }, [active.sessionId, activeId, appendStream]);

  const createTab = () => {
    const id = newTabId();
    setTabs((p) => [...p, { id, title: `Shell ${p.length + 1}`, sessionId: null, outputLines: [] }]);
    setActiveId(id);
  };

  const closeTab = (tabId: string) => {
    const target = tabs.find((t) => t.id === tabId);
    if (target?.sessionId) {
      void workspaceTerminalAdapter.closeSession(target.sessionId);
      delete pollCursor.current[target.sessionId];
    }
    setTabs((prev) => {
      if (prev.length <= 1) {
        return [{ ...prev[0]!, outputLines: [], sessionId: null, title: "Shell" }];
      }
      const next = prev.filter((t) => t.id !== tabId);
      if (tabId === activeId) {
        setActiveId(next[0]!.id);
      }
      return next;
    });
  };

  const sendLine = (raw: string) => {
    const tab = active;
    const line = raw.endsWith("\n") || raw.length === 0 ? raw : raw + "\n";
    append(tab.id, `\n> ${raw}\n`);
    if (!tab.sessionId) {
      return;
    }
    void (async () => {
      const { ok, bridge } = await workspaceTerminalAdapter.sendInput(tab.sessionId, line);
      if (!ok && bridge.status === "pending") {
        setBridgeLine("Runtime bridge pending");
      }
    })();
  };

  return (
    <div className={cn("flex h-full min-h-0 min-w-0 flex-col", className)} style={{ background: BG }}>
      <div
        className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-0.5"
        style={{ background: "#141414" }}
      >
        <div className="flex min-w-0 flex-1 items-end gap-0 overflow-x-auto">
          {tabs.map((t) => {
            const isActive = t.id === activeId;
            return (
              <div key={t.id} className="group relative flex shrink-0">
                <button
                  type="button"
                  onClick={() => setActiveId(t.id)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setContextMenu({ x: e.clientX, y: e.clientY, tabId: t.id });
                  }}
                  className={cn(
                    "relative border border-transparent px-2.5 py-1.5 text-left text-[11px] text-white/70",
                    isActive
                      ? "border-b-0 border-white/10 bg-[#0d0d0d] text-white/95"
                      : "hover:bg-white/[0.04]",
                  )}
                >
                  {short(t.title, 20)}
                </button>
                {tabs.length > 1 ? (
                  <button
                    type="button"
                    className="ml-0.5 rounded p-0.5 text-white/30 opacity-0 hover:bg-white/10 hover:text-white/70 group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(t.id);
                    }}
                    aria-label="Close tab"
                  >
                    <X className="h-3 w-3" />
                  </button>
                ) : null}
                {isActive ? (
                  <span className="pointer-events-none absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-[#ea580c]/90" />
                ) : null}
              </div>
            );
          })}
        </div>
        <div className="flex shrink-0 items-center gap-0.5 pr-0.5">
          <span className="px-1 text-[10px] text-white/35" title="Status">
            {bridgeLine || (active.sessionId ? "Session active" : "No terminal session active")}
          </span>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-white/50"
            onClick={() => {
              const msg = window.prompt("Rename tab", active.title);
              if (!msg) return;
              setTabs((p) => p.map((t) => (t.id === activeId ? { ...t, title: msg } : t)));
            }}
            title="Rename tab"
            aria-label="Rename tab"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-base text-white/60"
            onClick={createTab}
            aria-label="New terminal tab"
            title="New tab"
          >
            +
          </Button>
          {mode === "panel" ? (
            <>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/55"
                onClick={onMinimize}
                aria-label="Minimize"
                title="Minimize"
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/55"
                asChild
                title="Maximize (open full page)"
              >
                <Link
                  to="/workspace/terminal"
                  aria-label="Maximize"
                  className="inline-flex h-7 w-7 items-center justify-center"
                >
                  <SquareArrowOutUpRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/55"
                onClick={onClosePanel}
                aria-label="Close"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <div
        ref={terminalAreaRef}
        className="relative min-h-0 flex-1 overflow-hidden"
        data-ham-term-viewport
      >
        <pre
          ref={outRef}
          className="h-full min-h-0 w-full overflow-auto p-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap"
          style={{ color: "#e6e6e6" }}
        >
          {active.outputLines.join("")}
        </pre>
      </div>

      {isMobile ? (
        <MobileTerminalInputBar
          onSend={(data) => sendLine(data.replace(/\r$/, ""))}
          onCtrlC={() => {
            if (active.sessionId) {
              void workspaceTerminalAdapter.sendInput(active.sessionId, "\x03");
            }
          }}
        />
      ) : (
        <div
          className="flex items-center gap-1 border-t border-white/10 px-2 py-1.5"
          style={{ background: "#1a1a1a" }}
        >
          <input
            value={lineInput}
            onChange={(e) => setLineInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                sendLine(lineInput);
                setLineInput("");
              }
            }}
            placeholder="Type command…"
            className="min-w-0 flex-1 rounded-md border border-white/10 bg-[#2a2a2a] px-2 py-1 font-mono text-[12px] text-[#e6e6e6] outline-none"
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="h-7 w-7 shrink-0"
            onClick={() => {
              if (active.sessionId) {
                void workspaceTerminalAdapter.sendInput(active.sessionId, "\x03");
              }
            }}
            title="Send Ctrl+C"
            aria-label="Send Ctrl+C"
          >
            <span className="text-[9px] font-mono">^C</span>
          </Button>
          <Button
            type="button"
            size="icon"
            className="h-7 w-7 shrink-0 bg-[#ea580c] text-white hover:bg-[#f97316]"
            onClick={() => {
              sendLine(lineInput);
              setLineInput("");
            }}
            title="Send"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      )}

      {contextMenu ? (
        <div
          className="fixed z-50 min-w-32 rounded-md border border-white/10 bg-[#1a1a1a] p-1 text-[11px] text-white/90"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          <button
            type="button"
            className="flex w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
            onClick={() => {
              const t = tabs.find((x) => x.id === contextMenu.tabId);
              const n = t ? window.prompt("Rename tab", t.title) : null;
              if (n) {
                setTabs((p) => p.map((x) => (x.id === contextMenu.tabId ? { ...x, title: n } : x)));
              }
              setContextMenu(null);
            }}
          >
            Rename
          </button>
          <button
            type="button"
            className="flex w-full rounded px-2 py-1.5 text-left hover:bg-white/10"
            onClick={() => {
              closeTab(contextMenu.tabId);
              setContextMenu(null);
            }}
          >
            Close
          </button>
        </div>
      ) : null}
    </div>
  );
}
