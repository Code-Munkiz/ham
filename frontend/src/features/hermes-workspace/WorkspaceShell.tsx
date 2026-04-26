import * as React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Menu, Plus, Search, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { publicAssetUrl } from "@/lib/ham/publicAssets";
import { knowledgeNavItems, mainNavItems, workspacePathTitle } from "./workspaceNavConfig";

type WorkspaceShellProps = {
  children: React.ReactNode;
};

type SideNavOptions = {
  onNavigate?: () => void;
  showClose?: boolean;
  onClose?: () => void;
};

function sideNavClass(isActive: boolean) {
  return cn(
    "flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[13px] font-medium transition-colors",
    isActive
      ? "bg-white/[0.1] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
      : "text-white/45 hover:bg-white/[0.05] hover:text-white/88",
  );
}

function WorkspaceSideNav({ onNavigate, showClose, onClose }: SideNavOptions) {
  const logoSrc = publicAssetUrl("ham-logo.png");

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src={logoSrc}
            alt=""
            className="h-7 w-7 shrink-0 object-contain brightness-0 invert opacity-90"
          />
          <div className="min-w-0">
            <p className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-white/80">
              Hermes workspace
            </p>
            <p className="hww-pill mt-0.5 w-fit">Lift preview</p>
          </div>
        </div>
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

      <div className="mb-2">
        <label className="sr-only" htmlFor="hww-workspace-search">
          Search
        </label>
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30"
            strokeWidth={1.5}
          />
          <input
            id="hww-workspace-search"
            type="search"
            readOnly
            placeholder="Search…"
            className="hww-input w-full cursor-default rounded-lg pl-8"
            title="Global workspace search — wires with a later HAM/adapter slice"
          />
        </div>
      </div>

      <div className="mb-3">
        <Link
          to="/workspace/chat"
          onClick={onNavigate}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#c45c12]/35 bg-gradient-to-b from-white/[0.08] to-black/25 py-2.5 text-[12px] font-semibold text-white/90 shadow-[inset_0_0_0_1px_rgba(255,120,50,0.12)] transition hover:border-[#c45c12]/55 hover:from-white/[0.1]"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2} />
          New session
        </Link>
        <p className="mt-1 px-0.5 text-[9px] leading-snug text-white/28">Starts in workspace chat; HAM session model in a follow-up</p>
      </div>

      <div className="hww-side-section">Main</div>
      <nav className="mb-4 flex flex-col gap-0.5" aria-label="Main">
        {mainNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end ?? false}
            onClick={onNavigate}
            className={({ isActive }) => sideNavClass(isActive)}
          >
            <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="hww-side-section">Knowledge</div>
      <nav className="mb-4 flex flex-col gap-0.5" aria-label="Knowledge">
        {knowledgeNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) => sideNavClass(isActive)}
          >
            <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="hww-side-section">Sessions</div>
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
      <p className="mb-3 px-0.5 text-[9px] text-white/28">List + search bind to the HAM session API in a later commit.</p>

      <div className="hww-side-section mt-1">Ham</div>
      <p className="mb-2 px-0.5 text-[10px] leading-relaxed text-white/32">
        Main product routes stay until this lift is promoted. Runtime unchanged: same HAM API and backend.
      </p>
      <Link
        to="/chat"
        onClick={onNavigate}
        className="mb-1 flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-2.5 py-2.5 text-[11px] text-[#ffb27a]/90 transition-colors hover:border-white/15 hover:bg-white/[0.04]"
      >
        <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
        Open /chat
      </Link>
    </>
  );
}

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  const pageTitle = workspacePathTitle(location.pathname);

  React.useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

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
      <aside className="hww-sidebar hww-scroll hidden min-h-0 min-w-0 flex-col px-3 py-4 md:flex">
        <div className="flex min-h-0 flex-1 flex-col">
          <WorkspaceSideNav />
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
            />
          </aside>
        </>
      ) : null}

      <div className="hww-main min-h-0 min-w-0 flex-1 border-[color:var(--ham-workspace-line)] bg-[#030a10]/40 md:border-l">
        {children}
      </div>
    </div>
  );
}
