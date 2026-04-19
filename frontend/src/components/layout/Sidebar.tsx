import { ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { Link, useSearchParams } from "react-router-dom";
import {
  settingsStructure,
  normalizeSettingsTabParam,
} from "@/components/workspace/UnifiedSettings";

/**
 * Secondary column: **settings only** — full settings section links.
 * Other routes do not mount this component (see `AppLayout`).
 */
export function Sidebar({
  isVisible,
  onToggle,
  className,
  hideHeader = false,
}: {
  isVisible: boolean;
  onToggle?: () => void;
  className?: string;
  hideHeader?: boolean;
}) {
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeSubSegment = normalizeSettingsTabParam(tabParam);

  if (!isVisible) return null;

  return (
    <div
      className={cn(
        "flex h-screen flex-col bg-[#0d0d0d] transition-all duration-300 z-40 font-sans relative shrink-0",
        !className && "w-60 border-r border-white/5",
        className,
      )}
    >
      {!hideHeader && (
        <div className="flex h-12 items-center px-8 border-b border-white/5 bg-black/40 justify-between">
          <span className="text-[10px] font-black tracking-[0.3em] text-white/40 uppercase italic truncate">
            SETTINGS
          </span>
          {onToggle && (
            <button
              type="button"
              onClick={onToggle}
              className="text-white/20 hover:text-white transition-colors shrink-0"
              aria-label="Collapse settings sidebar"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-hide p-8 flex flex-col gap-10">
        {settingsStructure.map((group) => (
          <div key={group.group} className="space-y-4">
            <h4 className="px-3 text-[9px] font-black text-white/20 uppercase tracking-[0.4em] italic leading-none">
              {group.group}
            </h4>
            <nav className="space-y-1">
              {group.items.map((item) => (
                <Link
                  key={item.id}
                  to={`/settings?tab=${encodeURIComponent(item.id)}`}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left group",
                    activeSubSegment === item.id
                      ? "bg-[#FF6B00]/10 text-[#FF6B00]"
                      : "text-white/30 hover:text-white hover:bg-white/[0.03]",
                  )}
                >
                  <item.icon
                    className={cn(
                      "h-3.5 w-3.5 shrink-0",
                      activeSubSegment === item.id
                        ? "text-[#FF6B00]"
                        : "text-white/20",
                    )}
                  />
                  <span className="text-[10px] font-black uppercase tracking-widest whitespace-nowrap">
                    {item.label}
                  </span>
                </Link>
              ))}
            </nav>
          </div>
        ))}
      </div>
    </div>
  );
}
