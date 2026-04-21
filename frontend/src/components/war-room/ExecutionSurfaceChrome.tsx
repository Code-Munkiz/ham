import { Activity, Layout, Monitor, Radar, X } from "lucide-react";

import { cn } from "@/lib/utils";

export type ExecutionChromeMode = "split" | "war_room" | "preview";

export interface ExecutionSurfaceChromeProps {
  mode: ExecutionChromeMode;
  onClose: () => void;
  warRoomSignal?: boolean;
  reduceMotion?: boolean;
  warBlink?: boolean;
  browserOnly?: boolean;
  children: React.ReactNode;
}

export function ExecutionSurfaceChrome({
  mode,
  onClose,
  warRoomSignal,
  reduceMotion,
  warBlink,
  browserOnly,
  children,
}: ExecutionSurfaceChromeProps) {
  const title = browserOnly
    ? "BROWSER"
    : mode === "preview"
      ? "PREVIEW_LENS"
      : mode === "war_room"
        ? "WAR_ROOM_SURFACE"
        : "EXECUTION_CONTEXT";
  const sub = browserOnly
    ? "ham.browser"
    : mode === "war_room"
      ? "operational.execution.ham"
      : mode === "preview"
        ? "preview.ham"
        : "ham.workbench";

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-[#0d0d0d] border-l border-white/10">
      <div className="h-12 flex items-center px-6 bg-black/40 border-b border-white/5 justify-between shrink-0">
        <div className="flex items-center gap-3">
          {browserOnly ? (
            <Monitor className="h-3.5 w-3.5 text-[#00E5FF]" />
          ) : mode === "preview" ? (
            <Monitor className="h-3.5 w-3.5 text-[#FF6B00]" />
          ) : mode === "war_room" ? (
            <Radar className="h-3.5 w-3.5 text-[#FF6B00]" />
          ) : (
            <Layout className="h-3.5 w-3.5 text-[#FF6B00]" />
          )}
          <div className="flex flex-col">
            <span className="text-[10px] font-black uppercase tracking-widest text-white/80 italic">{title}</span>
            <span className="text-[8px] font-bold text-white/20 uppercase tracking-widest">{sub}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 hover:bg-white/5 rounded text-white/20 hover:text-white transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {warRoomSignal && mode === "war_room" && !browserOnly ? (
        <div className="h-10 flex items-center px-4 gap-2 bg-black/50 border-b border-white/5 shrink-0">
          <Activity className="h-3 w-3 text-[#FF6B00]" />
          <span className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/90">WAR_ROOM_SIGNAL</span>
          <span
            className={cn(
              "ml-auto h-2 w-2 rounded-full bg-[#00E5FF]",
              !reduceMotion && warBlink ? "opacity-100" : "opacity-40",
            )}
            aria-hidden
          />
        </div>
      ) : null}

      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}
