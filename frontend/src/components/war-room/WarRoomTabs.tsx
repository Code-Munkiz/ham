import { cn } from "@/lib/utils";

import type { WarRoomTabDef, WarRoomTabId } from "./uplinkConfig";

export interface WarRoomTabsProps {
  tabs: WarRoomTabDef[];
  activeId: WarRoomTabId;
  onSelect: (id: WarRoomTabId) => void;
  /**
   * `chrome` = single row in the execution-surface top bar, horizontal scroll on narrow viewports.
   * `panel` = legacy in-pane tab strip (most callers now use `chrome` only via `WarRoomPane`).
   */
  variant?: "chrome" | "panel";
}

export function WarRoomTabs({ tabs, activeId, onSelect, variant = "panel" }: WarRoomTabsProps) {
  return (
    <div
      className={cn(
        "flex gap-1 shrink-0",
        variant === "chrome"
          ? "inline-flex w-max min-w-0 max-w-full items-stretch pr-0 py-0.5"
          : "flex-wrap border-b border-white/10 bg-black/30 px-2 pt-2 pb-0",
      )}
    >
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onSelect(t.id)}
          className={cn(
            "shrink-0 whitespace-nowrap px-3 py-2 text-[13px] font-black uppercase tracking-widest border-b-2 transition-colors -mb-px",
            activeId === t.id
              ? "border-[#FF6B00] text-[#FF6B00]"
              : "border-transparent text-white/35 hover:text-white/60",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
