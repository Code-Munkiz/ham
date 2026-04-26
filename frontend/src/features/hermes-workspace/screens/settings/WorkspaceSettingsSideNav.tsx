import * as React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { WORKSPACE_SETTINGS_NAV } from "./workspaceSettingsNavData";

type WorkspaceSettingsSideNavProps = {
  activeSlug: string;
  className?: string;
};

export function WorkspaceSettingsSideNav({ activeSlug, className }: WorkspaceSettingsSideNavProps) {
  const core = WORKSPACE_SETTINGS_NAV.filter((i) => i.group === "core");
  const system = WORKSPACE_SETTINGS_NAV.filter((i) => i.group === "system");

  return (
    <div className={cn("flex min-h-0 min-w-0 flex-col gap-4", className)}>
      <nav
        className="hww-settings-pills flex gap-1.5 overflow-x-auto pb-1 md:hidden"
        aria-label="Settings sections"
      >
        {WORKSPACE_SETTINGS_NAV.map((item) => {
          const active = activeSlug === item.id;
          return (
            <Link
              key={item.id}
              to={`/workspace/settings?tab=${encodeURIComponent(item.id)}`}
              replace
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors",
                active
                  ? "border-white/20 bg-white/[0.08] text-[#e8eef8]"
                  : "border-white/[0.08] bg-black/20 text-white/45 hover:border-white/15 hover:text-white/75",
              )}
            >
              <item.icon className="h-3.5 w-3.5 opacity-90" strokeWidth={1.75} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <nav
        className="hidden min-h-0 w-56 shrink-0 flex-col gap-6 overflow-y-auto border-r border-white/[0.06] pr-3 md:flex"
        aria-label="Settings sections"
      >
        <div>
          <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">Workspace</p>
          <ul className="space-y-0.5">
            {core.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/workspace/settings?tab=${encodeURIComponent(item.id)}`}
                  replace
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-2.5 py-2 text-[12px] font-medium transition-colors",
                    activeSlug === item.id
                      ? "bg-white/[0.1] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                      : "text-white/45 hover:bg-white/[0.05] hover:text-white/85",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
                  <span className="leading-tight">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">System</p>
          <ul className="space-y-0.5">
            {system.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/workspace/settings?tab=${encodeURIComponent(item.id)}`}
                  replace
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-2.5 py-2 text-[12px] font-medium transition-colors",
                    activeSlug === item.id
                      ? "bg-white/[0.1] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                      : "text-white/45 hover:bg-white/[0.05] hover:text-white/85",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
                  <span className="leading-tight">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </nav>
    </div>
  );
}
