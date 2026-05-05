/**
 * Phase 1c: workspace picker dropdown.
 *
 * Lightweight self-contained menu (no radix dropdown wrapper) so the topbar
 * pill stays a single component. Closes on outside click, escape, or
 * selection.
 *
 * When `anchorRef` is set, the menu is portaled to `document.body` with
 * `position: fixed` under the anchor. That avoids clipping from
 * `overflow-hidden` ancestors (e.g. workspace shell) when the menu is wider
 * than the sidebar and was previously `right`-aligned off the left edge.
 */
import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

const PICKER_WIDTH_PX = 288;
const PICKER_MARGIN_PX = 8;

export interface WorkspacePickerProps {
  workspaces: HamWorkspaceSummary[];
  activeWorkspaceId: string | null;
  open: boolean;
  onSelect: (workspaceId: string) => void;
  onCreate: () => void;
  onClose: () => void;
  /** When provided, menu is portaled and fixed-positioned below this element. */
  anchorRef?: React.RefObject<HTMLElement | null>;
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
  anchorRef,
}: WorkspacePickerProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [fixedPos, setFixedPos] = React.useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  React.useEffect(() => {
    if (!open) setFixedPos(null);
  }, [open]);

  const updateFixedPosition = React.useCallback(() => {
    const anchor = anchorRef?.current;
    if (!anchor) return;
    const r = anchor.getBoundingClientRect();
    const w = Math.min(PICKER_WIDTH_PX, window.innerWidth - PICKER_MARGIN_PX * 2);
    let left = r.left;
    if (left + w + PICKER_MARGIN_PX > window.innerWidth) {
      left = window.innerWidth - w - PICKER_MARGIN_PX;
    }
    if (left < PICKER_MARGIN_PX) left = PICKER_MARGIN_PX;
    setFixedPos({
      top: r.bottom + PICKER_MARGIN_PX,
      left,
      width: w,
    });
  }, [anchorRef]);

  React.useLayoutEffect(() => {
    if (!open || !anchorRef) return;
    updateFixedPosition();
  }, [open, anchorRef, updateFixedPosition, workspaces.length]);

  React.useEffect(() => {
    if (!open || !anchorRef) return;
    function onDocClick(ev: MouseEvent) {
      const menu = containerRef.current;
      const anchor = anchorRef.current;
      const t = ev.target;
      if (!(t instanceof Node)) return;
      if (menu?.contains(t) || anchor?.contains(t)) return;
      onClose();
    }
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    function onViewportChange() {
      updateFixedPosition();
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [open, onClose, anchorRef, updateFixedPosition]);

  React.useEffect(() => {
    if (!open || anchorRef) return;
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
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const visible = workspaces.filter((w) => w.status === "active");

  // Wait one layout pass so the anchor has bounds before portaling (avoids a stray 0,0 flash).
  if (anchorRef && fixedPos === null) return null;

  const menuClassName = cn(
    "overflow-hidden rounded-xl border border-white/10 bg-black/85 text-sm text-foreground shadow-2xl backdrop-blur",
    anchorRef ? "fixed z-[300]" : "absolute left-0 top-full z-[300] mt-2 w-[min(18rem,calc(100vw-1rem))]",
  );

  const menuInner = (
    <div
      ref={containerRef}
      role="menu"
      aria-label="Workspace picker"
      data-testid="workspace-picker"
      className={menuClassName}
      style={
        anchorRef && fixedPos
          ? {
              top: fixedPos.top,
              left: fixedPos.left,
              width: fixedPos.width,
            }
          : undefined
      }
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

  if (anchorRef) {
    return typeof document !== "undefined" ? createPortal(menuInner, document.body) : null;
  }
  return menuInner;
}
