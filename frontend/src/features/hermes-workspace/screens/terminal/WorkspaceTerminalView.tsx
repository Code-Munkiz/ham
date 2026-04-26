import * as React from "react";
import { Link } from "react-router-dom";
import { Pencil, PanelLeft, SquareArrowOutUpRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { workspaceTerminalAdapter } from "../../adapters/terminalAdapter";
import { MobileTerminalInputBar } from "./MobileTerminalInputBar";
import { type XtermControl, WorkspaceXtermHost } from "./WorkspaceXtermHost";

const BG = "#0d0d0d";

export type TabModel = {
  id: string;
  title: string;
  sessionId: string | null;
};

type WorkspaceTerminalViewProps = {
  mode: "page" | "panel";
  onMinimize?: () => void;
  onClosePanel?: () => void;
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
  const [tabs, setTabs] = React.useState<TabModel[]>([{ id: newTabId(), title: "Shell", sessionId: null }]);
  const [activeId, setActiveId] = React.useState(() => tabs[0]!.id);
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number; tabId: string } | null>(null);
  const [bridgeLine, setBridgeLine] = React.useState<string | null>(null);
  const [isMobile, setIsMobile] = React.useState(false);
  const terminalAreaRef = React.useRef<HTMLDivElement | null>(null);
  const termCtlByTabIdRef = React.useRef<Record<string, XtermControl | null>>({});
  const activeSessionIdRef = React.useRef<string | null>(null);
  const outputCursorBySessionRef = React.useRef<Record<string, number>>({});
  const lastResizeBySessionRef = React.useRef<Record<string, { cols: number; rows: number }>>({});
  const activeWsRef = React.useRef<WebSocket | null>(null);
  const wsStopsPollRef = React.useRef(false);
  const sessionAttempted = React.useRef<Set<string>>(new Set());
  const resizeDebounce = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const tabsRef = React.useRef(tabs);
  tabsRef.current = tabs;

  const active = tabs.find((t) => t.id === activeId) ?? tabs[0]!;

  const sendToPty = React.useCallback((sessionId: string, data: string) => {
    if (!sessionId) return;
    const w = activeWsRef.current;
    if (w && w.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: "in", data }));
        return;
      } catch {
        /* fall back */
      }
    }
    void workspaceTerminalAdapter.sendInput(sessionId, data);
  }, []);

  const onPtyData = React.useCallback(
    (tabId: string, data: string) => {
      const t = tabsRef.current.find((x) => x.id === tabId);
      if (t?.sessionId) {
        sendToPty(t.sessionId, data);
      }
    },
    [sendToPty],
  );

  const onTermReady = React.useCallback(
    (tabId: string, ctrl: XtermControl | null) => {
      termCtlByTabIdRef.current[tabId] = ctrl;
      if (ctrl && tabId === activeId) {
        requestAnimationFrame(() => {
          ctrl.focus();
        });
      }
    },
    [activeId],
  );

  const measureAndPushResize = React.useCallback(() => {
    const sid = activeSessionIdRef.current;
    const id = activeId;
    if (!sid || !id) return;
    const ctl = termCtlByTabIdRef.current[id];
    if (!ctl) return;
    ctl.fit();
    const { cols, rows } = ctl.getDimensions();
    const prev = lastResizeBySessionRef.current[sid];
    if (prev && prev.cols === cols && prev.rows === rows) return;
    lastResizeBySessionRef.current[sid] = { cols, rows };
    const w = activeWsRef.current;
    if (w && w.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: "resize", cols, rows }));
      } catch {
        void workspaceTerminalAdapter.resize(sid, cols, rows);
      }
    } else {
      void workspaceTerminalAdapter.resize(sid, cols, rows);
    }
  }, [activeId]);

  activeSessionIdRef.current = active.sessionId;

  React.useLayoutEffect(() => {
    const el = terminalAreaRef.current;
    if (typeof window === "undefined" || !el || typeof ResizeObserver === "undefined") return;
    const schedule = () => {
      if (resizeDebounce.current) clearTimeout(resizeDebounce.current);
      resizeDebounce.current = setTimeout(() => {
        measureAndPushResize();
        resizeDebounce.current = null;
      }, 100);
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
  }, [measureAndPushResize]);

  React.useLayoutEffect(() => {
    const ctl = termCtlByTabIdRef.current[activeId];
    if (!active.sessionId) return;
    const t = setTimeout(() => {
      lastResizeBySessionRef.current[active.sessionId!] = { cols: 0, rows: 0 };
      measureAndPushResize();
    }, 0);
    if (ctl) {
      requestAnimationFrame(() => {
        ctl.focus();
      });
    }
    return () => clearTimeout(t);
  }, [active.sessionId, activeId, measureAndPushResize]);

  React.useEffect(() => {
    const m = window.matchMedia("(max-width: 767px)");
    const u = () => setIsMobile(m.matches);
    u();
    m.addEventListener("change", u);
    return () => m.removeEventListener("change", u);
  }, []);

  React.useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [contextMenu]);

  const activeSessionId = active.sessionId;

  // Bootstrap session for active tab
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
        return;
      }
      setBridgeLine(null);
      outputCursorBySessionRef.current[sessionId] = 0;
      setTabs((prev) => prev.map((t) => (t.id === tabId ? { ...t, sessionId } : t)));
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId, activeSessionId]);

  // When switching to a tab or session, catch up on PTY output that arrived while the tab was hidden.
  React.useEffect(() => {
    const sid = activeSessionId;
    if (!sid) return;
    const tabId = activeId;
    let cancelled = false;
    const run = (attempt: number) => {
      if (cancelled) return;
      const ctl = termCtlByTabIdRef.current[tabId];
      if (!ctl) {
        if (attempt < 8) {
          requestAnimationFrame(() => run(attempt + 1));
        }
        return;
      }
      void (async () => {
        if (cancelled) return;
        const after = outputCursorBySessionRef.current[sid] ?? 0;
        const { text, next, bridge } = await workspaceTerminalAdapter.pollOutput(sid, after);
        if (cancelled) return;
        if (bridge.status === "ready" && text) {
          ctl.write(text);
        }
        if (typeof next === "number") {
          outputCursorBySessionRef.current[sid] = next;
        }
      })();
    };
    run(0);
    return () => {
      cancelled = true;
    };
  }, [activeId, activeSessionId]);

  // WebSocket: output + in-band resize/recv; primary path when open.
  React.useEffect(() => {
    wsStopsPollRef.current = false;
    const sid = active.sessionId;
    if (!sid) {
      return;
    }
    const url = workspaceTerminalAdapter.webSocketStreamUrl(sid);
    if (!url) {
      return;
    }
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      return;
    }
    const tabId = activeId;
    const onMessage = (ev: MessageEvent<string>) => {
      try {
        const j = JSON.parse(ev.data) as { type?: string; text?: string };
        if (j.type === "out" && typeof j.text === "string" && j.text) {
          const ctl = termCtlByTabIdRef.current[tabId];
          if (ctl) {
            ctl.write(j.text);
          }
          outputCursorBySessionRef.current[sid] =
            (outputCursorBySessionRef.current[sid] ?? 0) + j.text.length;
        }
      } catch {
        /* ignore */
      }
    };
    activeWsRef.current = ws;
    ws.addEventListener("message", onMessage);
    ws.onopen = () => {
      wsStopsPollRef.current = true;
      requestAnimationFrame(() => {
        measureAndPushResize();
      });
    };
    ws.onerror = () => {
      wsStopsPollRef.current = false;
    };
    ws.onclose = () => {
      if (activeWsRef.current === ws) {
        activeWsRef.current = null;
      }
      wsStopsPollRef.current = false;
    };
    return () => {
      ws.onclose = null;
      ws.removeEventListener("message", onMessage);
      if (activeWsRef.current === ws) {
        activeWsRef.current = null;
      }
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      wsStopsPollRef.current = false;
    };
  }, [active.sessionId, activeId, measureAndPushResize]);

  // HTTP poll fallback
  React.useEffect(() => {
    const sid = active.sessionId;
    if (!sid) {
      return;
    }
    const tabId = activeId;
    const tid = setInterval(() => {
      void (async () => {
        if (wsStopsPollRef.current) {
          return;
        }
        const after = outputCursorBySessionRef.current[sid] ?? 0;
        const { text, next, bridge } = await workspaceTerminalAdapter.pollOutput(sid, after);
        if (bridge.status === "ready" && text) {
          const ctl = termCtlByTabIdRef.current[tabId];
          if (ctl) {
            ctl.write(text);
          }
        }
        if (typeof next === "number") {
          outputCursorBySessionRef.current[sid] = next;
        }
      })();
    }, 500);
    return () => {
      clearInterval(tid);
    };
  }, [active.sessionId, activeId]);

  const createTab = () => {
    const id = newTabId();
    setTabs((p) => [...p, { id, title: `Shell ${p.length + 1}`, sessionId: null }]);
    setActiveId(id);
  };

  const closeTab = (tabId: string) => {
    const target = tabs.find((t) => t.id === tabId);
    if (target?.sessionId) {
      void workspaceTerminalAdapter.closeSession(target.sessionId);
      delete outputCursorBySessionRef.current[target.sessionId];
    }
    delete termCtlByTabIdRef.current[tabId];
    if (tabs.length <= 1) {
      const nid = newTabId();
      setActiveId(nid);
      setTabs([{ id: nid, title: "Shell", sessionId: null }]);
      return;
    }
    setTabs((prev) => {
      const next = prev.filter((t) => t.id !== tabId);
      if (tabId === activeId) {
        setActiveId(next[0]!.id);
      }
      return next;
    });
  };

  const sendMobileLine = (line: string) => {
    const tab = active;
    if (!tab.sessionId) {
      return;
    }
    sendToPty(tab.sessionId, line);
  };

  return (
    <div className={cn("flex h-full min-h-0 min-w-0 flex-col", className)} style={{ background: BG }}>
      <div
        className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-0.5"
        style={{ background: "#141414" }}
      >
        <div className="flex min-w-0 flex-1 items-end gap-0 overflow-x-auto">
          {tabs.map((t) => {
            const isAct = t.id === activeId;
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
                    isAct ? "border-b-0 border-white/10 bg-[#0d0d0d] text-white/95" : "hover:bg-white/[0.04]",
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
                {isAct ? (
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

      <div ref={terminalAreaRef} className="relative min-h-0 flex-1 overflow-hidden" data-ham-term-viewport>
        {tabs.map((t) => {
          const isThisActive = t.id === activeId;
          return (
            <div
              key={t.id}
              className={cn(
                "absolute inset-0 min-h-0 min-w-0 p-0",
                isThisActive ? "z-10" : "z-0 opacity-0 pointer-events-none",
              )}
            >
              <WorkspaceXtermHost
                tabId={t.id}
                isActive={isThisActive}
                isMobile={isMobile}
                onReady={onTermReady}
                onPtyData={onPtyData}
              />
            </div>
          );
        })}
      </div>

      {isMobile ? (
        <MobileTerminalInputBar
          onSend={(data) => sendMobileLine(data.replace(/\r$/, ""))}
          onCtrlC={() => {
            if (active.sessionId) {
              sendToPty(active.sessionId, "\x03");
            }
          }}
        />
      ) : null}

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
