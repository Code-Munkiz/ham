import { cn } from "@/lib/utils";

import type { WarRoomTabDef, WarRoomTabId } from "./uplinkConfig";

export interface WarRoomTabsProps {
  tabs: WarRoomTabDef[];
  activeId: WarRoomTabId;
  onSelect: (id: WarRoomTabId) => void;
}

export function WarRoomTabs({ tabs, activeId, onSelect }: WarRoomTabsProps) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-white/10 px-2 pt-2 pb-0 shrink-0 bg-black/30">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onSelect(t.id)}
          className={cn(
            "px-3 py-2.5 text-[13px] font-black uppercase tracking-widest border-b-2 transition-colors -mb-px",
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
