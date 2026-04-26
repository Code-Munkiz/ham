import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { UPSTREAM_SETTINGS_NAV_ITEMS } from "./workspaceSettingsNavData";
import type { UpstreamSettingsNavId } from "./workspaceSettingsNavData";

type WorkspaceSettingsSideNavProps = {
  activeSection: UpstreamSettingsNavId;
  className?: string;
};

export function WorkspaceSettingsSideNav({ activeSection, className }: WorkspaceSettingsSideNavProps) {
  const { pathname } = useLocation();
  const onMcp = pathname === "/workspace/settings/mcp" || pathname.endsWith("/workspace/settings/mcp");
  const onProviders = pathname === "/workspace/settings/providers" || pathname.endsWith("/workspace/settings/providers");

  return (
    <div className={cn("flex min-h-0 min-w-0 flex-col gap-4", className)}>
      <div className="hidden flex-col gap-1 border-b border-white/[0.06] pb-3 md:flex">
        <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">Settings</p>
        <p className="px-1 text-[11px] text-white/45">Same order and labels as upstream Hermes Workspace settings.</p>
      </div>

      <nav
        className="hww-settings-pills scrollbar-none flex gap-1.5 overflow-x-auto pb-1 md:hidden"
        aria-label="Settings sections"
      >
        {UPSTREAM_SETTINGS_NAV_ITEMS.map((item) => {
          if (item.id === "mcp") {
            const active = onMcp;
            return (
              <Link
                key={item.id}
                to="/workspace/settings/mcp"
                replace
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors",
                  active
                    ? "border-white/20 bg-white/[0.08] text-[#e8eef8]"
                    : "border-white/[0.08] bg-black/20 text-white/45 hover:border-white/15 hover:text-white/75",
                )}
              >
                {item.label}
              </Link>
            );
          }
          const active = !onMcp && !onProviders && activeSection === item.id;
          return (
            <Link
              key={item.id}
              to={`/workspace/settings?section=${encodeURIComponent(item.id)}`}
              replace
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors",
                active
                  ? "border-white/20 bg-white/[0.08] text-[#e8eef8]"
                  : "border-white/[0.08] bg-black/20 text-white/45 hover:border-white/15 hover:text-white/75",
              )}
            >
              {item.label}
            </Link>
          );
        })}
        <Link
          to="/workspace/settings/providers"
          replace
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors",
            onProviders
              ? "border-white/20 bg-white/[0.08] text-[#e8eef8]"
              : "border-white/[0.08] bg-black/20 text-white/45 hover:border-white/15 hover:text-white/75",
          )}
        >
          Provider setup
        </Link>
      </nav>

      <nav
        className="hidden min-h-0 w-56 shrink-0 flex-col gap-0.5 overflow-y-auto pr-1 md:flex"
        aria-label="Settings sections"
      >
        {UPSTREAM_SETTINGS_NAV_ITEMS.map((item) => {
          if (item.id === "mcp") {
            const active = onMcp;
            return (
              <Link
                key={item.id}
                to="/workspace/settings/mcp"
                replace
                className={cn(
                  "relative rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  active
                    ? "bg-[color-mix(in_srgb,#10b981_12%,transparent)] font-semibold text-[#34d399]"
                    : "text-white/45 hover:bg-white/[0.05] hover:text-white/85",
                )}
              >
                {active ? (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-[#34d399]"
                  />
                ) : null}
                <span className="pl-1">{item.label}</span>
              </Link>
            );
          }
          const active = !onMcp && !onProviders && activeSection === item.id;
          return (
            <Link
              key={item.id}
              to={`/workspace/settings?section=${encodeURIComponent(item.id)}`}
              replace
              className={cn(
                "relative rounded-lg px-3 py-2 text-left text-sm transition-colors",
                active
                  ? "bg-[color-mix(in_srgb,#10b981_12%,transparent)] font-semibold text-[#34d399]"
                  : "text-white/45 hover:bg-white/[0.05] hover:text-white/85",
              )}
            >
              {active ? (
                <span
                  aria-hidden
                  className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-[#34d399]"
                />
              ) : null}
              <span className="pl-1">{item.label}</span>
            </Link>
          );
        })}
        <Link
          to="/workspace/settings/providers"
          replace
          className={cn(
            "relative mt-2 rounded-lg border border-white/[0.06] px-3 py-2 text-left text-sm transition-colors",
            onProviders
              ? "border-[#34d399]/40 bg-[color-mix(in_srgb,#10b981_10%,transparent)] font-semibold text-[#a7f3d0]"
              : "text-white/45 hover:border-white/12 hover:bg-white/[0.04] hover:text-white/80",
          )}
        >
          Provider setup
          <span className="mt-0.5 block text-[10px] font-normal text-white/30">Dedicated route (upstream /settings/providers)</span>
        </Link>
      </nav>
    </div>
  );
}
