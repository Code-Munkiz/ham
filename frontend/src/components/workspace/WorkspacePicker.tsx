/**
 * Phase 1c: workspace picker dropdown.
 *
 * Lightweight self-contained menu (no radix dropdown wrapper) so the topbar
 * pill stays a single component. Closes on outside click, escape, or
 * selection.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

export interface WorkspacePickerProps {
  workspaces: HamWorkspaceSummary[];
  activeWorkspaceId: string | null;
  open: boolean;
  onSelect: (workspaceId: string) => void;
  onCreate: () => void;
  onClose: () => void;
}

function roleBadgeClass(role: string): string {
  switch (role) {
    case "owner":
      return "bg-amber-400/20 text-amber-100";
    case "admin":
      return "bg-sky-400/20 text-sky-100";
    case "member":
      return "bg-emerald-400/20 text-emerald-100";
    default:
      return "bg-white/10 text-foreground/80";
  }
}

export function WorkspacePicker({
  workspaces,
  activeWorkspaceId,
  open,
  onSelect,
  onCreate,
  onClose,
}: WorkspacePickerProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    function onDocClick(ev: MouseEvent) {
      const el = containerRef.current;
      if (el && ev.target instanceof Node && !el.contains(ev.target)) {
        onClose();
      }
    }
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const visible = workspaces.filter((w) => w.status === "active");

  return (
    <div
      ref={containerRef}
      role="menu"
      aria-label="Workspace picker"
      data-testid="workspace-picker"
      className="absolute right-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-xl border border-white/10 bg-black/85 text-sm text-foreground shadow-2xl backdrop-blur"
    >
      <ul className="max-h-72 overflow-y-auto py-1">
        {visible.length === 0 ? (
          <li className="px-3 py-2 text-foreground/60">No workspaces yet.</li>
        ) : (
          visible.map((w) => {
            const isActive = w.workspace_id === activeWorkspaceId;
            return (
              <li key={w.workspace_id}>
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={isActive}
                  data-active={isActive ? "true" : "false"}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5",
                    isActive ? "bg-white/[0.06]" : undefined,
                  )}
                  onClick={() => {
                    onSelect(w.workspace_id);
                    onClose();
                  }}
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate font-medium">{w.name}</span>
                    <span className="truncate text-xs text-foreground/60">
                      {w.slug}
                      {w.org_id ? ` · ${w.org_id}` : ""}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
                      roleBadgeClass(w.role),
                    )}
                  >
                    {w.role}
                  </span>
                </button>
              </li>
            );
          })
        )}
      </ul>
      <div className="border-t border-white/10">
        <button
          type="button"
          role="menuitem"
          data-testid="workspace-picker-create"
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-foreground/80 transition-colors hover:bg-white/5"
          onClick={() => {
            onCreate();
            onClose();
          }}
        >
          <span className="text-base leading-none">＋</span>
          <span>Create workspace</span>
        </button>
      </div>
    </div>
  );
}
