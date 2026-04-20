import * as React from "react";

import { cn } from "@/lib/utils";

const STORAGE_KEY = "ham_workbench_split_left_pct_v1";
const MIN_LEFT = 28;
const MAX_LEFT = 72;
const DEFAULT_PCT = 50;

function loadPct(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PCT;
    const n = Number.parseFloat(raw);
    if (Number.isFinite(n) && n >= MIN_LEFT && n <= MAX_LEFT) return n;
  } catch {
    /* ignore */
  }
  return DEFAULT_PCT;
}

function savePct(n: number) {
  try {
    localStorage.setItem(STORAGE_KEY, String(Math.round(n)));
  } catch {
    /* ignore */
  }
}

export interface ResizableWorkbenchSplitProps {
  left: React.ReactNode;
  right: React.ReactNode;
  className?: string;
}

/**
 * Draggable vertical divider between transcript (left) and execution surface (right).
 */
export function ResizableWorkbenchSplit({ left, right, className }: ResizableWorkbenchSplitProps) {
  const [leftPct, setLeftPct] = React.useState(loadPct);
  const drag = React.useRef<{ startX: number; startPct: number } | null>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);

  const onMove = React.useCallback((e: MouseEvent) => {
    if (!drag.current || !containerRef.current) return;
    const w = containerRef.current.getBoundingClientRect().width;
    if (w <= 0) return;
    const dx = e.clientX - drag.current.startX;
    const deltaPct = (dx / w) * 100;
    const next = Math.min(MAX_LEFT, Math.max(MIN_LEFT, drag.current.startPct + deltaPct));
    setLeftPct(next);
  }, []);

  const onUp = React.useCallback(() => {
    drag.current = null;
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    setLeftPct((p) => {
      savePct(p);
      return p;
    });
  }, [onMove]);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    drag.current = { startX: e.clientX, startPct: leftPct };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  React.useEffect(() => {
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [onMove, onUp]);

  return (
    <div ref={containerRef} className={cn("flex h-full min-h-0 w-full flex-1", className)}>
      <div
        className="h-full min-h-0 overflow-hidden flex flex-col shrink-0"
        style={{ width: `${leftPct}%`, minWidth: 280 }}
      >
        {left}
      </div>
      <button
        type="button"
        aria-label="Resize workbench columns"
        onMouseDown={onMouseDown}
        className="h-full w-1.5 shrink-0 cursor-col-resize bg-white/10 hover:bg-[#FF6B00]/50 border-x border-white/5 z-10"
      />
      <div className="h-full min-h-0 overflow-hidden flex flex-col min-w-0 flex-1" style={{ minWidth: 280 }}>
        {right}
      </div>
    </div>
  );
}
