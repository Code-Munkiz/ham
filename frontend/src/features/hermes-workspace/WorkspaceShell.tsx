import * as React from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Menu, PanelLeft, PanelLeftClose, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { Button } from "@/components/ui/button";
import {
  libraryNavItems,
  libraryRailMeta,
  pathMatchesLibraryRoute,
  pathMatchesSettingsRail,
  primaryRailItems,
  settingsRailItem,
  workspacePathTitle,
} from "./workspaceNavConfig";
import {
  WorkspaceLibraryFlyoutContext,
  useWorkspaceLibraryFlyout,
} from "./workspaceLibraryFlyoutContext";
import { WorkspaceMobileTabBar } from "./WorkspaceMobileTabBar";
import { WorkspaceChatFloatingToggle } from "./components/WorkspaceChatFloatingToggle";
import { WorkspaceChatPanel } from "./components/WorkspaceChatPanel";
import { WorkspaceSidebarUserTrigger } from "./components/WorkspaceSidebarUserTrigger";
import { HamWorkspaceTopbarPill } from "@/components/layout/HamWorkspaceTopbarPill";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

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
  canUseWorkspaceSidebar: boolean;
  workspaces: HamWorkspaceSummary[];
  activeWorkspaceId: string | null;
  workspaceFilter: string;
  onWorkspaceFilterChange: (q: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  isChatRoute: boolean;
};

function sideNavClass(isActive: boolean, iconOnly: boolean) {
  return cn(
    "box-border flex font-medium text-[13px] transition-colors",
    iconOnly
      ? "size-9 shrink-0 items-center justify-center rounded-lg p-0"
      : "w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5",
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
  canUseWorkspaceSidebar,
  workspaces,
  activeWorkspaceId,
  workspaceFilter,
  onWorkspaceFilterChange,
  onSelectWorkspace,
  isChatRoute,
}: SideNavOptions) {
  const brandLogoSrc = hamWorkspaceLogoUrl();
  const landingHref = hamLandingHref();
  const landingIsExternal = isAbsoluteHttpUrl(landingHref);
  const c = layoutCollapsed;

  const q = workspaceFilter.trim().toLowerCase();
  const { pathname } = useLocation();
  const libFlyout = useWorkspaceLibraryFlyout();
  const LibraryIcon = libraryRailMeta.icon;

  const filteredWorkspaces = React.useMemo(() => {
    if (!q) return workspaces;
    return workspaces.filter((w) => {
      const id = w.workspace_id.toLowerCase();
      const name = (w.name || "").toLowerCase();
      const slug = (w.slug || "").toLowerCase();
      return id.includes(q) || name.includes(q) || slug.includes(q);
    });
  }, [workspaces, q]);

  const topPrimaryNav = (
    <nav
      className={cn(
        "flex shrink-0 flex-col",
        c ? "w-full max-w-full items-center gap-1.5" : "gap-0.5",
      )}
      aria-label="Workspace primary"
    >
      {primaryRailItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end ?? false}
          onClick={onNavigate}
          className={({ isActive }) => sideNavClass(isActive, c)}
          title={item.label}
        >
          <item.icon className="h-[18px] w-[18px] shrink-0 opacity-90" strokeWidth={1.5} />
          {c ? <span className="sr-only">{item.label}</span> : item.label}
        </NavLink>
      ))}
      <button
        type="button"
        onClick={() => libFlyout?.toggleLibrary()}
        className={sideNavClass(pathMatchesLibraryRoute(pathname), c)}
        aria-label={libraryRailMeta.label}
        title={libraryRailMeta.label}
        aria-expanded={Boolean(libFlyout?.libraryOpen)}
        aria-haspopup="dialog"
      >
        <LibraryIcon className="h-[18px] w-[18px] shrink-0 opacity-90" strokeWidth={1.5} />
        {c ? <span className="sr-only">{libraryRailMeta.label}</span> : libraryRailMeta.label}
      </button>
    </nav>
  );

  const settingsFooterControl = (
    <NavLink
      to={settingsRailItem.to}
      onClick={onNavigate}
      className={() =>
        cn(
          "box-border inline-flex shrink-0 items-center justify-center rounded-lg font-medium transition-colors",
          c ? "size-9 p-0" : "p-2.5",
          pathMatchesSettingsRail(pathname)
            ? "bg-white/[0.1] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
            : "text-white/45 hover:bg-white/[0.05] hover:text-white/88",
        )
      }
      title={settingsRailItem.label}
      aria-label={settingsRailItem.label}
    >
      <settingsRailItem.icon className="h-[18px] w-[18px] shrink-0 opacity-90" strokeWidth={1.5} />
      <span className="sr-only">{settingsRailItem.label}</span>
    </NavLink>
  );

  const expandedWorkspaceList = (ulClass: string) => {
    if (!workspaces.length) {
      return (
        <p className="mb-1 px-0.5 text-[11px] leading-relaxed text-white/45">
          No workspaces yet. Use the{" "}
          <span className="font-medium text-white/55">+ Create workspace</span> control next to your
          workspace name above.
        </p>
      );
    }
    if (!filteredWorkspaces.length) {
      return <p className="mb-1 px-0.5 text-[11px] text-white/40">No matching workspaces.</p>;
    }
    return (
      <ul className={ulClass} aria-label="Workspaces">
        {filteredWorkspaces.map((w) => {
          const active = activeWorkspaceId === w.workspace_id;
          return (
            <li key={w.workspace_id}>
              <button
                type="button"
                data-testid={`hww-workspace-row-${w.workspace_id}`}
                onClick={() => {
                  onSelectWorkspace(w.workspace_id);
                  onNavigate?.();
                }}
                className={cn(
                  "w-full rounded-lg border px-2 py-1.5 text-left transition",
                  active
                    ? "border-white/20 bg-white/[0.1] text-white/92"
                    : "border-white/[0.04] bg-black/20 text-white/70 hover:border-white/10 hover:bg-white/[0.04]",
                )}
              >
                <p className="truncate text-[11px] font-medium leading-snug text-white/85">
                  {w.name}
                </p>
                {w.slug ? (
                  <p className="mt-0.5 truncate text-[10px] text-white/45">{w.slug}</p>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <div
      className={cn("flex min-h-0 min-w-0 flex-1 flex-col", c && "max-w-full overflow-x-hidden")}
    >
      <div
        className={cn(
          "mb-4 flex max-w-full items-center justify-between gap-1 px-0.5",
          c && "mb-2 w-full max-w-full flex-col items-center gap-2",
        )}
      >
        <div
          className={cn(
            "flex min-w-0 items-center",
            c ? "w-full max-w-full flex-col items-center justify-center" : "gap-2",
          )}
        >
          <img
            src={brandLogoSrc}
            alt=""
            className="h-7 w-7 shrink-0 object-contain opacity-95"
            width={28}
            height={28}
          />
          <div className={cn("min-w-0", c && "hidden")}>
            <p className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-white/80">
              {isChatRoute ? "Chat" : "HAM's Workspace"}
            </p>
          </div>
        </div>
        <div
          className={cn(
            "flex shrink-0 items-center gap-0.5",
            c && "w-full max-w-full justify-center",
          )}
        >
          {!showClose && onToggleLayoutCollapse ? (
            <button
              type="button"
              onClick={onToggleLayoutCollapse}
              className="rounded-md p-1.5 text-white/50 transition-colors hover:bg-white/[0.08] hover:text-white"
              aria-label={c ? "Expand sidebar" : "Collapse sidebar"}
              title={c ? "Expand sidebar" : "Collapse sidebar"}
            >
              {c ? (
                <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
              ) : (
                <PanelLeftClose className="h-4 w-4" strokeWidth={1.5} />
              )}
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
        <div className="mb-4">
          <HamWorkspaceTopbarPill />
        </div>
      )}

      {/* Primary nav: fixed slot directly under header / pill on every route */}
      {topPrimaryNav}

      {/* Expanded sidebar: workspace search + list (hidden when collapsed) */}
      {c ? (
        <div className="min-h-0 flex-1 shrink-0" aria-hidden />
      ) : (
        <div className="mt-3 flex min-h-0 min-w-0 flex-1 flex-col gap-2 border-t border-white/[0.06] pt-3">
          <div className="hww-side-section shrink-0">Search</div>
          {canUseWorkspaceSidebar ? (
            <>
              <div className="shrink-0">
                <label className="sr-only" htmlFor="hww-workspace-search">
                  Search workspaces
                </label>
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                  <input
                    id="hww-workspace-search"
                    data-testid="hww-workspace-search"
                    type="search"
                    value={workspaceFilter}
                    onChange={(e) => onWorkspaceFilterChange(e.target.value)}
                    placeholder="Search workspaces…"
                    className="hww-input w-full rounded-lg"
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="hww-side-section shrink-0">Workspaces</div>
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                {expandedWorkspaceList(
                  "min-h-0 flex-1 space-y-1 overflow-y-auto pr-0.5 [scrollbar-gutter:stable]",
                )}
              </div>
            </>
          ) : (
            <p className="shrink-0 px-0.5 text-[11px] leading-relaxed text-white/45">
              Sign in and load a workspace to search and switch workspaces here. Use{" "}
              <span className="font-medium text-white/55">+ Create workspace</span> next to your
              workspace when signed in.
            </p>
          )}
        </div>
      )}

      <nav
        className={cn(
          "mt-auto flex w-full max-w-full shrink-0 border-t border-white/[0.06] pt-3",
          c
            ? "flex-col items-center gap-2 px-0"
            : "flex-row items-center justify-between gap-2 px-0.5",
        )}
        aria-label="Workspace utilities"
      >
        <div className={cn("flex min-w-0 items-center gap-2", c ? "w-full flex-col" : "flex-1")}>
          {settingsFooterControl}
          {canUseWorkspaceSidebar ? <WorkspaceSidebarUserTrigger layoutCollapsed={c} /> : null}
        </div>
        {landingIsExternal ? (
          <a
            href={landingHref}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onNavigate}
            className={cn(
              "box-border flex shrink-0 items-center rounded-lg text-white/50 transition-colors hover:bg-white/[0.05] hover:text-[#a5f3fc]/95",
              c ? "size-9 justify-center p-0" : "gap-2 px-1.5 py-1.5 justify-end",
            )}
            title="Go to HAM landing"
            aria-label="Go to HAM landing"
          >
            <img
              src={brandLogoSrc}
              alt=""
              className={cn("shrink-0 object-contain", c ? "h-7 w-7" : "h-8 w-8")}
              width={c ? 28 : 32}
              height={c ? 28 : 32}
              aria-hidden
            />
            <span
              className={cn(
                "max-w-[5.5rem] truncate text-[11px] font-medium text-white/40",
                c && "sr-only",
              )}
            >
              HAM
            </span>
          </a>
        ) : (
          <Link
            to={landingHref}
            onClick={onNavigate}
            className={cn(
              "box-border flex shrink-0 items-center rounded-lg text-white/50 transition-colors hover:bg-white/[0.05] hover:text-[#a5f3fc]/95",
              c ? "size-9 justify-center p-0" : "gap-2 px-1.5 py-1.5 justify-end",
            )}
            title="Go to HAM landing"
            aria-label="Go to HAM landing"
          >
            <img
              src={brandLogoSrc}
              alt=""
              className={cn("shrink-0 object-contain", c ? "h-7 w-7" : "h-8 w-8")}
              width={c ? 28 : 32}
              height={c ? 28 : 32}
              aria-hidden
            />
            <span
              className={cn(
                "max-w-[5.5rem] truncate text-[11px] font-medium text-white/40",
                c && "sr-only",
              )}
            >
              HAM
            </span>
          </Link>
        )}
      </nav>
    </div>
  );
}

function WorkspaceLibraryFlyout({
  open,
  onOpenChange,
  sidebarCollapsed,
  onItemNavigate,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sidebarCollapsed: boolean;
  onItemNavigate?: () => void;
}) {
  const navigate = useNavigate();
  if (!open) return null;

  const close = () => onOpenChange(false);

  const pick = (to: string) => {
    onItemNavigate?.();
    navigate(to);
    close();
  };

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-[55] bg-black/45 md:bg-black/25"
        aria-label="Close library menu"
        onClick={close}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={libraryRailMeta.label}
        className={cn(
          "fixed z-[60] overflow-hidden rounded-xl border border-white/[0.12] bg-[#050e14]/98 py-2 shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur-md",
          "max-md:left-3 max-md:right-3 max-md:top-14 max-md:w-auto",
          "md:w-[min(18rem,calc(100vw-2rem))]",
          sidebarCollapsed ? "md:left-[3.25rem] md:top-20" : "md:left-[260px] md:top-20",
        )}
      >
        <p className="mb-1.5 border-b border-white/[0.06] px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/45">
          Library
        </p>
        <nav className="flex flex-col gap-0.5 px-1.5" aria-label="Library tools">
          {libraryNavItems.map((item) => (
            <button
              key={item.to}
              type="button"
              onClick={() => pick(item.to)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-white/80 transition-colors hover:bg-white/[0.06]"
            >
              <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} aria-hidden />
              {item.label}
            </button>
          ))}
        </nav>
      </div>
    </>
  );
}

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  const hamWorkspace = useHamWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => {
    try {
      const v = localStorage.getItem(HWW_SIDEBAR_COLLAPSE_KEY);
      if (v === "0") return false;
      if (v === "1") return true;
      return true;
    } catch {
      return true;
    }
  });
  const [libraryFlyoutOpen, setLibraryFlyoutOpen] = React.useState(false);
  const libraryFlyoutCtx = React.useMemo(
    () => ({
      openLibrary: () => setLibraryFlyoutOpen(true),
      toggleLibrary: () => setLibraryFlyoutOpen((v) => !v),
      libraryOpen: libraryFlyoutOpen,
    }),
    [libraryFlyoutOpen],
  );
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [workspaceChatPanelOpen, setWorkspaceChatPanelOpen] = React.useState(false);
  const [workspaceFilter, setWorkspaceFilter] = React.useState("");

  const canUseWorkspaceSidebar =
    hamWorkspace.state.status === "ready" || hamWorkspace.state.status === "onboarding";
  const activeWorkspaceIdForNav =
    hamWorkspace.state.status === "ready" ? hamWorkspace.state.activeWorkspaceId : null;

  const pageTitle = workspacePathTitle(location.pathname);
  const isWorkspaceChat =
    location.pathname === "/workspace/chat" || location.pathname.startsWith("/workspace/chat/");

  React.useEffect(() => {
    setDrawerOpen(false);
    setLibraryFlyoutOpen(false);
  }, [location.pathname]);

  React.useEffect(() => {
    if (!libraryFlyoutOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLibraryFlyoutOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [libraryFlyoutOpen]);

  React.useEffect(() => {
    if (isWorkspaceChat) setWorkspaceChatPanelOpen(false);
  }, [isWorkspaceChat]);

  const workspaceNavProps = {
    canUseWorkspaceSidebar,
    workspaces: hamWorkspace.workspaces,
    activeWorkspaceId: activeWorkspaceIdForNav,
    workspaceFilter,
    onWorkspaceFilterChange: setWorkspaceFilter,
    onSelectWorkspace: (workspaceId: string) => {
      if (hamWorkspace.state.status === "ready") {
        hamWorkspace.selectWorkspace(workspaceId);
      }
      navigate("/workspace/chat");
    },
    isChatRoute: isWorkspaceChat,
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

  const showLocalUiQaBanner = hamWorkspace.authMode === "local_dev_bypass";

  return (
    <WorkspaceLibraryFlyoutContext.Provider value={libraryFlyoutCtx}>
      <div className="hww-root flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden">
        {showLocalUiQaBanner ? (
          <div
            role="status"
            data-hww-local-dev-workspace-banner
            className="flex h-7 shrink-0 items-center justify-center border-b border-amber-400/22 bg-amber-500/[0.08] px-3 text-[10px] font-medium tracking-wide text-amber-100/90"
          >
            Local dev workspace · UI QA only · not authenticated
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
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
              "hww-sidebar hww-scroll hidden min-h-0 min-w-0 flex-col py-4 md:flex",
              sidebarCollapsed ? "hww-sidebar--collapsed" : "px-3",
            )}
          >
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <WorkspaceSideNav
                {...workspaceNavProps}
                layoutCollapsed={sidebarCollapsed}
                onToggleLayoutCollapse={onToggleSidebar}
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
                  {...workspaceNavProps}
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
            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
          </div>
          <WorkspaceMobileTabBar />
          {!isWorkspaceChat && hamWorkspace.state.status === "ready" ? (
            <WorkspaceChatFloatingToggle onOpen={() => setWorkspaceChatPanelOpen(true)} />
          ) : null}
          <WorkspaceChatPanel
            open={workspaceChatPanelOpen && hamWorkspace.state.status === "ready"}
            onClose={() => setWorkspaceChatPanelOpen(false)}
          />
          <WorkspaceLibraryFlyout
            open={libraryFlyoutOpen}
            onOpenChange={setLibraryFlyoutOpen}
            sidebarCollapsed={sidebarCollapsed}
            onItemNavigate={() => setDrawerOpen(false)}
          />
        </div>
      </div>
    </WorkspaceLibraryFlyoutContext.Provider>
  );
}
