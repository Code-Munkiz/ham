/**
 * Sidebar avatar opens the upstream-style account dialog (desktop + drawer nav).
 */
import * as React from "react";

import { cn } from "@/lib/utils";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import type { HamMeUser } from "@/lib/ham/workspaceApi";

import { WorkspaceUserAccountDialog } from "./WorkspaceUserAccountDialog";

function initialsFromMe(user: HamMeUser): string {
  const raw = (user.display_name ?? user.email ?? "U").trim();
  const parts = raw.split(/\s+/).filter(Boolean);
  if (parts.length >= 2)
    return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase().slice(0, 3);
  return (parts[0]?.[0] ?? "U").toUpperCase();
}

export function WorkspaceSidebarUserTrigger({ layoutCollapsed }: { layoutCollapsed: boolean }) {
  const ham = useHamWorkspace();
  const [open, setOpen] = React.useState(false);

  const me =
    ham.state.status === "ready" || ham.state.status === "onboarding" ? ham.state.me : null;

  if (!me) return null;

  const initials = initialsFromMe(me.user);
  const title = layoutCollapsed ? "Account" : (me.user.display_name ?? me.user.email ?? "Account");

  return (
    <>
      <WorkspaceUserAccountDialog open={open} onOpenChange={setOpen} />
      <button
        type="button"
        data-testid="hww-sidebar-user-trigger"
        title={layoutCollapsed ? "Account and preferences" : undefined}
        aria-label="Open account and preferences"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className={cn(
          "box-border flex shrink-0 items-center rounded-xl border border-transparent text-left outline-none ring-offset-2 ring-offset-[#040d14] transition-colors focus-visible:ring-2 focus-visible:ring-emerald-400/35 hover:border-white/10 hover:bg-white/[0.06]",
          layoutCollapsed ? "size-9 justify-center p-0" : "min-w-0 flex-1 gap-2.5 px-2 py-1.5",
        )}
      >
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-bold text-white shadow-sm"
          aria-hidden
        >
          {initials}
        </span>
        {layoutCollapsed ? null : (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[11px] font-semibold text-white/88">{title}</span>
            <span className="mt-0.5 block truncate text-[10px] text-white/40">Account</span>
          </span>
        )}
      </button>
    </>
  );
}
