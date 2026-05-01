import * as React from "react";
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  ChevronsUp,
  Menu,
  MessageSquare,
  PanelLeft,
  PanelLeftClose,
  Plus,
  Search,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { Button } from "@/components/ui/button";
import { knowledgeNavItems, mainNavItems, workspacePathTitle } from "./workspaceNavConfig";
import { workspaceSessionAdapter } from "./workspaceAdapters";
import type { ChatSessionSummary } from "./workspaceTypes";
import { sessionCardSubtitle, sessionCardTitle } from "./utils/sessionListFormat";
import { WorkspaceMobileTabBar } from "./WorkspaceMobileTabBar";
import { WorkspaceChatFloatingToggle } from "./components/WorkspaceChatFloatingToggle";
import { WorkspaceChatPanel } from "./components/WorkspaceChatPanel";
import { WorkspaceTerminalView } from "./screens/terminal/WorkspaceTerminalView";
import { toast } from "sonner";

/** Keep in sync with `HWW_LAST_SESSION_KEY` in `WorkspaceChatScreen.tsx`. */
const HWW_SIDEBAR_LAST_SESSION_KEY = "hww.chat.lastSessionId";

const HWW_SIDEBAR_COLLAPSE_KEY = "hww.sidebar.collapsed";

/** SPA home / marketing landing. Default `/` uses the current deployment origin. Set `VITE_HAM_LANDING_URL` for a fixed URL (e.g. future marketing site). */
function hamLandingHref(): string {
  const v = (import.meta.env.VITE_HAM_LANDING_URL as string | undefined)?.trim();
  return v || "/";
}

function isAbsoluteHttpUrl(s: string): boolean {
  return /^https?:\/\//i.test(s);
}

type WorkspaceShellProps = {
  children: React.ReactNode;
};

type SideNavOptions = {
  onNavigate?: () => void;
  showClose?: boolean;
  onClose?: () => void;
  /** Desktop only: icon rail; mobile drawer always expanded. */
  layoutCollapsed: boolean;
  onToggleLayoutCollapse?: () => void;
  onExpandFromCollapsed?: () => void;
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  onSessionsRetry: () => void;
  sessionFilter: string;
  onSessionFilterChange: (q: string) => void;
  activeSessionId: string | null;
  /** When on `/workspace/chat`, sessions lead the rail (upstream ChatSidebar pattern). */
  isChatRoute: boolean;
  deletingSessionId: string | null;
  onDeleteSession?: (sessionId: string) => void;
};

function sideNavClass(isActive: boolean, iconOnly: boolean) {
  return cn(
    "flex font-medium text-[13px] transition-colors",
    iconOnly
      ? "w-full items-center justify-center rounded-lg p-2.5"
      : "items-center gap-2.5 rounded-lg px-2.5 py-2.5",
    isActive
      ? "bg-white/[0.1] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
      : "text-white/45 hover:bg-white/[0.05] hover:text-white/88",
  );
}

function WorkspaceSideNav({
  onNavigate,
  showClose,
  onClose,
  layoutCollapsed,
  onToggleLayoutCollapse,
  onExpandFromCollapsed,
  sessions,
  sessionsLoading,
  sessionsError,
  onSessionsRetry,
  sessionFilter,
  onSessionFilterChange,
  activeSessionId,
  isChatRoute,
  deletingSessionId,
  onDeleteSession,
}: SideNavOptions) {
  const brandLogoSrc = hamWorkspaceLogoUrl();
  const landingHref = hamLandingHref();
  const landingIsExternal = isAbsoluteHttpUrl(landingHref);
  const c = layoutCollapsed;
  const expand = onExpandFromCollapsed ?? (() => undefined);

  const q = sessionFilter.trim().toLowerCase();
  const [workspaceNavOpen, setWorkspaceNavOpen] = React.useState(true);
  const [knowledgeNavOpen, setKnowledgeNavOpen] = React.useState(true);

  const sectionToggle = (
    label: string,
    open: boolean,
    onToggle: () => void,
  ) =>
    c ? null : (
      <button
        type="button"
        onClick={onToggle}
        className="hww-side-section shrink-0 flex w-full items-center justify-between text-left"
        aria-expanded={open}
      >
        <span>{label}</span>
        {open ? <ChevronDown className="h-3.5 w-3.5 opacity-70" /> : <ChevronRight className="h-3.5 w-3.5 opacity-70" />}
      </button>
    );
  const filteredSessions = React.useMemo(() => {
    if (!q) return sessions;
    return sessions.filter((s) => {
      const id = s.session_id.toLowerCase();
      const preview = (s.preview || "").toLowerCase();
      const date = (s.created_at || "").toLowerCase();
      return (
        id.includes(q) || preview.includes(q) || date.includes(q) || String(s.turn_count).includes(q)
      );
    });
  }, [sessions, q]);

  const mainNav = (
    <nav
      className={cn("mb-4 flex flex-col", c ? "items-center gap-1" : "gap-0.5")}
      aria-label="Main"
    >
      {mainNavItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end ?? false}
          onClick={onNavigate}
          className={({ isActive }) => sideNavClass(isActive, c)}
          title={item.label}
        >
          <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
          {c ? <span className="sr-only">{item.label}</span> : item.label}
        </NavLink>
      ))}
    </nav>
  );

  const knowledgeNav = (
    <nav
      className={cn("mb-3 flex flex-col", c ? "items-center gap-1" : "gap-0.5")}
      aria-label="Knowledge"
    >
      {knowledgeNavItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          onClick={onNavigate}
          className={({ isActive }) => sideNavClass(isActive, c)}
          title={item.label}
        >
          <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
          {c ? <span className="sr-only">{item.label}</span> : item.label}
        </NavLink>
      ))}
    </nav>
  );

  const expandedSessionsContent = (ulClass: string) => {
    if (sessionsError) {
      return (
        <div className="mb-2 rounded-lg border border-amber-500/30 bg-amber-950/40 px-2 py-1.5 text-[10px] text-amber-100/90">
          <p className="break-words">{sessionsError}</p>
          <button
            type="button"
            onClick={() => {
              onSessionsRetry();
            }}
            className="mt-1.5 text-[10px] font-medium text-[#ffb27a]/90 underline"
          >
            Retry
          </button>
        </div>
      );
    }
    if (sessionsLoading) {
      return <p className="mb-2 px-0.5 text-[11px] text-white/40">Loading sessions…</p>;
    }
    if (!sessions.length) {
      return (
        <p className="mb-1 px-0.5 text-[11px] leading-relaxed text-white/40">
          No sessions yet.{" "}
          <Link
            to="/workspace/chat"
            onClick={onNavigate}
            className="text-[#ffb27a]/90 underline-offset-2 hover:underline"
          >
            Start a conversation →
          </Link>
        </p>
      );
    }
    if (!filteredSessions.length) {
      return <p className="mb-1 px-0.5 text-[11px] text-white/40">No matches for this filter.</p>;
    }
    return (
      <ul className={ulClass} aria-label="Chat sessions">
        {filteredSessions.map((s) => {
          const active = activeSessionId === s.session_id;
          const sub = sessionCardSubtitle(s.turn_count, s.created_at);
          return (
            <li key={s.session_id} className="flex min-w-0 items-stretch gap-1">
              <Link
                to={`/workspace/chat?session=${encodeURIComponent(s.session_id)}`}
                onClick={onNavigate}
                className={cn(
                  "block min-w-0 flex-1 rounded-lg border px-2 py-1.5 text-left transition",
                  active
                    ? "border-white/20 bg-white/[0.1] text-white/92"
                    : "border-white/[0.04] bg-black/20 text-white/70 hover:border-white/10 hover:bg-white/[0.04]",
                )}
              >
                <p className="line-clamp-2 text-[11px] leading-snug text-white/85">{sessionCardTitle(s.preview)}</p>
                {sub ? <p className="mt-0.5 truncate text-[10px] text-white/45">{sub}</p> : null}
              </Link>
              {onDeleteSession ? (
                <button
                  type="button"
                  disabled={deletingSessionId === s.session_id}
                  aria-label={`Delete chat session ${sessionCardTitle(s.preview)}`}
                  title="Delete thread"
                  onClick={(evt) => {
                    evt.preventDefault();
                    evt.stopPropagation();
                    onDeleteSession(s.session_id);
                  }}
                  className={cn(
                    "inline-flex shrink-0 items-center justify-center rounded-lg border px-2 text-white/40 transition hover:border-red-500/35 hover:bg-red-950/30 hover:text-red-100/95 disabled:opacity-40",
                    active ? "border-white/14" : "border-white/[0.06]",
                  )}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden strokeWidth={2} />
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div
        className={cn("mb-4 flex items-center justify-between gap-1 px-0.5", c && "mb-2 flex-col gap-2")}
      >
        <div
          className={cn("flex min-w-0 items-center", c ? "w-full flex-col justify-center" : "gap-2")}
        >
          <img
            src={brandLogoSrc}
            alt=""
            className="h-7 w-7 shrink-0 object-contain opacity-95"
            width={28}
            height={28}
          />
          <div
            className={cn("min-w-0", c && "hidden")}
          >
            <p className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-white/80">
              {isChatRoute ? "Chat" : "HAM's Workspace"}
            </p>
          </div>
        </div>
        <div className={cn("flex shrink-0 items-center gap-0.5", c && "w-full justify-center")}>
          {!showClose && onToggleLayoutCollapse ? (
            <button
              type="button"
              onClick={onToggleLayoutCollapse}
              className="rounded-md p-1.5 text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white"
              aria-label={c ? "Expand sidebar" : "Collapse sidebar"}
              title={c ? "Expand sidebar" : "Collapse sidebar"}
            >
              {c ? <PanelLeft className="h-4 w-4" strokeWidth={1.5} /> : <PanelLeftClose className="h-4 w-4" strokeWidth={1.5} />}
            </button>
          ) : null}
          {showClose && onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white"
              aria-label="Close menu"
            >
              <X className="h-4 w-4" strokeWidth={1.5} />
            </button>
          ) : null}
        </div>
      </div>

      {c ? null : (
        <>
          <div className="hww-side-section">{isChatRoute ? "Search" : "Find session"}</div>
          <div className="mb-2">
            <label className="sr-only" htmlFor="hww-workspace-search">
              Filter sessions
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30"
                strokeWidth={1.5}
                aria-hidden
              />
              <input
                id="hww-workspace-search"
                type="search"
                value={sessionFilter}
                onChange={(e) => onSessionFilterChange(e.target.value)}
                placeholder="Search sessions…"
                className="hww-input w-full rounded-lg"
                autoComplete="off"
              />
            </div>
          </div>
        </>
      )}

      {c ? (
        <div className="mb-2 flex flex-col items-center">
          <button
            type="button"
            onClick={expand}
            className="text-white/45 hover rounded-lg p-2.5 text-white/70 transition-colors hover:bg-white/[0.05]"
            aria-label="Expand sidebar to search sessions"
            title="Expand sidebar to search sessions"
          >
            <Search className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
      ) : null}

      <div className={c ? "mb-1 flex flex-col items-center" : "mb-3"}>
        {c ? (
          <Link
            to="/workspace/chat"
            onClick={onNavigate}
            className="flex w-full items-center justify-center rounded-lg border border-[#c45c12]/40 bg-gradient-to-b from-white/[0.08] to-black/25 p-2.5 text-white/90 shadow-[inset_0_0_0_1px_rgba(255,120,50,0.12)] transition hover:border-[#c45c12]/60"
            title="New session"
            aria-label="New session"
          >
            <Plus className="h-4 w-4" strokeWidth={2} />
          </Link>
        ) : (
          <>
            <Link
              to="/workspace/chat"
              onClick={onNavigate}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#c45c12]/35 bg-gradient-to-b from-white/[0.08] to-black/25 py-2.5 text-[12px] font-semibold text-white/90 shadow-[inset_0_0_0_1px_rgba(255,120,50,0.12)] transition hover:border-[#c45c12]/55 hover:from-white/[0.1]"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={2} />
              New session
            </Link>
          </>
        )}
      </div>

      {c ? (
        <>
          {mainNav}
          {knowledgeNav}
        </>
      ) : isChatRoute ? (
        <>
          <div className="hww-side-section">Sessions</div>
          <div className="mb-1 flex min-h-0 min-w-0 flex-1 flex-col">
            {expandedSessionsContent(
              "min-h-0 flex-1 space-y-1 overflow-y-auto pr-0.5 [scrollbar-gutter:stable]",
            )}
          </div>
          {sectionToggle("Workspace", workspaceNavOpen, () => setWorkspaceNavOpen((v) => !v))}
          {workspaceNavOpen ? mainNav : null}
          {sectionToggle("Knowledge", knowledgeNavOpen, () => setKnowledgeNavOpen((v) => !v))}
          {knowledgeNavOpen ? knowledgeNav : null}
        </>
      ) : (
        <>
          {sectionToggle("Workspace", workspaceNavOpen, () => setWorkspaceNavOpen((v) => !v))}
          {workspaceNavOpen ? mainNav : null}
          {sectionToggle("Knowledge", knowledgeNavOpen, () => setKnowledgeNavOpen((v) => !v))}
          {knowledgeNavOpen ? knowledgeNav : null}
          <div className="hww-side-section">Sessions</div>
          {expandedSessionsContent(
            "mb-2 max-h-44 min-h-0 space-y-1 overflow-y-auto pr-0.5",
          )}
        </>
      )}

      {c && !sessionsError ? (
        <div className="mb-2 flex flex-col items-center">
          <Link
            to="/workspace/chat"
            onClick={onNavigate}
            className="flex w-full items-center justify-center rounded-lg border border-white/[0.06] bg-black/20 p-2.5 text-white/50 transition hover:bg-white/[0.05] hover:text-white/85"
            title="Workspace chat and sessions (expand to browse the list)"
            aria-label="Workspace chat and sessions"
          >
            <MessageSquare className="h-4 w-4" strokeWidth={1.5} />
            <span className="sr-only">Browse sessions in expanded sidebar</span>
          </Link>
        </div>
      ) : null}
      {c && sessionsError ? (
        <div className="mb-2 w-full text-center text-[9px] text-amber-200/90">
          <button
            type="button"
            onClick={() => {
              onSessionsRetry();
            }}
            className="text-[#ffb27a]/90 underline"
          >
            Session error
          </button>
        </div>
      ) : null}

      <div className="mt-auto border-t border-white/[0.06] pt-3">
        {landingIsExternal ? (
          <a
            href={landingHref}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-2 rounded-lg px-2 py-2 text-white/50 transition-colors hover:bg-white/[0.05] hover:text-[#a5f3fc]/95",
              c ? "justify-center" : "md:justify-start",
            )}
            title="Go to HAM landing"
            aria-label="Go to HAM landing"
          >
            <img
              src={brandLogoSrc}
              alt=""
              className="h-8 w-8 shrink-0 object-contain"
              width={32}
              height={32}
              aria-hidden
            />
            <span
              className={cn("text-[11px] font-medium text-white/40", c && "sr-only")}
            >
              HAM
            </span>
          </a>
        ) : (
          <Link
            to={landingHref}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-2 rounded-lg px-2 py-2 text-white/50 transition-colors hover:bg-white/[0.05] hover:text-[#a5f3fc]/95",
              c ? "justify-center" : "md:justify-start",
            )}
            title="Go to HAM landing"
            aria-label="Go to HAM landing"
          >
            <img
              src={brandLogoSrc}
              alt=""
              className="h-8 w-8 shrink-0 object-contain"
              width={32}
              height={32}
              aria-hidden
            />
            <span
              className={cn("text-[11px] font-medium text-white/40", c && "sr-only")}
            >
              HAM
            </span>
          </Link>
        )}
      </div>
    </div>
  );
}

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => {
    try {
      return localStorage.getItem(HWW_SIDEBAR_COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  /** SHELL-015 — docked terminal strip on chat route */
  const [chatTerminalDockOpen, setChatTerminalDockOpen] = React.useState(false);
  const [workspaceChatPanelOpen, setWorkspaceChatPanelOpen] = React.useState(false);
  const [sessions, setSessions] = React.useState<ChatSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = React.useState(true);
  const [sessionsError, setSessionsError] = React.useState<string | null>(null);
  const [sessionFilter, setSessionFilter] = React.useState("");

  const activeSessionId =
    location.pathname === "/workspace/chat" || location.pathname.endsWith("/workspace/chat")
      ? searchParams.get("session")
      : null;

  const [deletingSessionId, setDeletingSessionId] = React.useState<string | null>(null);

  const loadSessions = React.useCallback(async () => {
    setSessionsLoading(true);
    setSessionsError(null);
    try {
      const { sessions: list } = await workspaceSessionAdapter.list();
      setSessions(list);
    } catch (e) {
      setSessionsError(e instanceof Error ? e.message : "Failed to load sessions");
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadSessions();
  }, [loadSessions, location.pathname, location.search]);

  const handleDeleteSession = React.useCallback(
    async (sid: string) => {
      if (!globalThis.confirm("Delete this chat thread? Server-stored messages for this session will be removed.")) {
        return;
      }
      setDeletingSessionId(sid);
      try {
        await workspaceSessionAdapter.delete(sid);
        toast.success("Chat deleted");
        if (activeSessionId === sid) {
          try {
            localStorage.removeItem(HWW_SIDEBAR_LAST_SESSION_KEY);
          } catch {
            /* ignore */
          }
          navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
        }
        await loadSessions();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not delete chat");
      } finally {
        setDeletingSessionId(null);
      }
    },
    [activeSessionId, loadSessions, navigate],
  );

  const pageTitle = workspacePathTitle(location.pathname);
  const isWorkspaceChat =
    location.pathname === "/workspace/chat" || location.pathname.startsWith("/workspace/chat/");

  React.useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  React.useEffect(() => {
    if (isWorkspaceChat) setWorkspaceChatPanelOpen(false);
  }, [isWorkspaceChat]);

  const sessionNavProps = {
    sessions,
    sessionsLoading,
    sessionsError,
    onSessionsRetry: () => {
      void loadSessions();
    },
    sessionFilter,
    onSessionFilterChange: setSessionFilter,
    activeSessionId,
    isChatRoute: isWorkspaceChat,
    deletingSessionId,
    onDeleteSession: handleDeleteSession,
  };

  const setSidebarPersist = React.useCallback((next: boolean) => {
    setSidebarCollapsed(next);
    try {
      localStorage.setItem(HWW_SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const onToggleSidebar = React.useCallback(() => {
    setSidebarPersist(!sidebarCollapsed);
  }, [sidebarCollapsed, setSidebarPersist]);

  return (
    <div className="hww-root flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden md:flex-row">
      {/* Mobile top bar (upstream-style compact header) */}
      <header className="hww-mobile-header z-20 flex h-12 shrink-0 items-center justify-between border-b border-[color:var(--ham-workspace-line)] bg-[#040d14]/90 px-3 backdrop-blur-sm md:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-white/75 transition-colors hover:bg-white/[0.06]"
          aria-label="Open workspace menu"
        >
          <Menu className="h-5 w-5" strokeWidth={1.5} />
        </button>
        <span className="text-[13px] font-medium text-white/88">{pageTitle}</span>
        <span className="w-9" aria-hidden />
      </header>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hww-sidebar hww-scroll hidden min-h-0 min-w-0 flex-col px-3 py-4 md:flex",
          sidebarCollapsed && "hww-sidebar--collapsed",
        )}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <WorkspaceSideNav
            {...sessionNavProps}
            layoutCollapsed={sidebarCollapsed}
            onToggleLayoutCollapse={onToggleSidebar}
            onExpandFromCollapsed={() => {
              setSidebarPersist(false);
            }}
          />
        </div>
      </aside>

      {/* Mobile drawer + backdrop */}
      {drawerOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm md:hidden"
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
          />
          <aside
            className="hww-drawer hww-scroll fixed left-0 top-0 z-50 flex h-full w-[min(88vw,290px)] min-w-0 flex-col overflow-y-auto border-r border-[color:var(--ham-workspace-line)] bg-[#040d14]/98 px-3 py-4 shadow-2xl md:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="Workspace navigation"
          >
            <WorkspaceSideNav
              showClose
              onClose={() => setDrawerOpen(false)}
              onNavigate={() => setDrawerOpen(false)}
              layoutCollapsed={false}
              {...sessionNavProps}
            />
          </aside>
        </>
      ) : null}

      <div
        className={cn(
          "hww-main flex min-h-0 min-w-0 flex-1 flex-col border-[color:var(--ham-workspace-line)] bg-[#030a10]/40 md:border-l",
          !isWorkspaceChat && "max-md:pb-[var(--hww-tabbar-h,3.5rem)]",
        )}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {children}
          {isWorkspaceChat ? (
            <div className="shrink-0 border-t border-white/[0.06] bg-[#030a0f]/90">
              {chatTerminalDockOpen ? (
                <div className="h-[min(14rem,38vh)] min-h-0 w-full">
                  <WorkspaceTerminalView
                    mode="panel"
                    onMinimize={() => {
                      setChatTerminalDockOpen(false);
                    }}
                    onClosePanel={() => {
                      setChatTerminalDockOpen(false);
                    }}
                  />
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2 px-3 py-1.5">
                  <div className="flex min-w-0 items-center gap-2 text-[11px] text-white/45">
                    <Terminal className="h-3.5 w-3.5 shrink-0 opacity-80" strokeWidth={1.5} />
                    <span className="truncate">Local terminal</span>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-7 gap-1.5 px-2.5 text-[11px] text-white/88"
                    onClick={() => {
                      setChatTerminalDockOpen(true);
                    }}
                  >
                    <ChevronsUp className="h-3.5 w-3.5 opacity-80" strokeWidth={2} />
                    Open
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
      <WorkspaceMobileTabBar />
      {!isWorkspaceChat ? (
        <WorkspaceChatFloatingToggle onOpen={() => setWorkspaceChatPanelOpen(true)} />
      ) : null}
      <WorkspaceChatPanel open={workspaceChatPanelOpen} onClose={() => setWorkspaceChatPanelOpen(false)} />
    </div>
  );
}
