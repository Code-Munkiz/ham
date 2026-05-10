/**
 * Context pressure: Turn · Workspace · Thread.
 * Detailed copy lives in `ContextDiagnosticsHudPanel` (dark HUD — no native `title` tooltips).
 */
import * as React from "react";
import { createPortal } from "react-dom";
import type {
  ChatContextMetersPayload,
  ChatContextMeterColor,
  ChatContextThreadMeter,
  ChatContextThisTurnMeter,
  ChatContextWorkspaceMeter,
} from "@/lib/ham/types";
import { cn } from "@/lib/utils";
import { ContextDiagnosticsHudPanel, pctFromFillRatio } from "./ContextDiagnosticsHud";

/** Drives ring sizes / spacing in `WorkspaceChatComposer` narrow layouts. */
export type ContextMeterClusterDensity = "comfortable" | "compact" | "tight";

const DIMS: Record<
  ContextMeterClusterDensity,
  { ring: number; stroke: number; labelClass: string; gapClass: string }
> = {
  comfortable: {
    ring: 36,
    stroke: 3,
    labelClass: "mt-0.5 text-[8px] font-semibold uppercase tracking-wide text-white/35",
    gapClass: "gap-0.5 md:gap-1",
  },
  compact: {
    ring: 28,
    stroke: 2.5,
    labelClass: "mt-0.5 text-[7px] font-semibold uppercase tracking-wide text-white/35",
    gapClass: "gap-0.5",
  },
  tight: {
    ring: 22,
    stroke: 2,
    labelClass: "mt-px text-[6px] font-semibold uppercase tracking-wide text-white/35",
    gapClass: "gap-0",
  },
};

function mapApiColor(c: string | undefined): ChatContextMeterColor {
  if (c === "green" || c === "amber" || c === "red") return c;
  return "gray";
}

function ringProgressClass(
  kind: "turn" | "ws" | "thr",
  pct: number,
  api: ChatContextMeterColor | undefined,
): string {
  if (kind === "turn") {
    if (api === "red" || pct >= 95) return "stroke-red-400";
    return "stroke-emerald-400";
  }
  if (kind === "ws") {
    if (pct >= 100 || api === "red") return "stroke-rose-400";
    if (pct >= 90) return "stroke-rose-400/80";
    if (pct >= 70) return "stroke-amber-400/70";
    return "stroke-slate-300/55";
  }
  if (pct >= 100 || api === "red") return "stroke-rose-400";
  if (pct >= 90) return "stroke-amber-400";
  if (pct >= 70) return "stroke-amber-400/65";
  return "stroke-slate-300/55";
}

function MeterRing({
  label,
  pct,
  kind,
  apiColor,
  unavailable,
  ringSize,
  strokeWidth,
  labelClass,
}: {
  label: string;
  pct: number | null;
  kind: "turn" | "ws" | "thr";
  apiColor: ChatContextMeterColor | undefined;
  unavailable?: boolean;
  ringSize: number;
  strokeWidth: number;
  labelClass: string;
}) {
  const u = unavailable || pct === null;
  const p = u ? 0 : Math.max(0, Math.min(100, pct));
  const R = (ringSize - strokeWidth) / 2 - 1;
  const C = 2 * Math.PI * R;
  const dash = C * (1 - p / 100);
  const progressClass = !u ? ringProgressClass(kind, p, apiColor) : "";

  return (
    <div className="relative flex flex-col items-center">
      <svg
        width={ringSize}
        height={ringSize}
        viewBox={`0 0 ${ringSize} ${ringSize}`}
        className="shrink-0"
        aria-hidden
      >
        {u ? (
          <circle
            cx={ringSize / 2}
            cy={ringSize / 2}
            r={R}
            fill="none"
            className="stroke-white/[0.14]"
            strokeWidth={strokeWidth}
            strokeDasharray="3.5 3.2"
            strokeLinecap="round"
          />
        ) : (
          <>
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={R}
              fill="none"
              className="stroke-white/[0.12]"
              strokeWidth={strokeWidth}
            />
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={R}
              fill="none"
              className={`${progressClass} transition-[stroke-dashoffset]`}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={`${C} ${C}`}
              strokeDashoffset={dash}
              transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`}
            />
          </>
        )}
      </svg>
      <span className={labelClass}>{label}</span>
    </div>
  );
}

function pulseDotClass(
  kind: "turn" | "ws" | "thr",
  pct: number | null,
  enabled: boolean,
  hasData: boolean,
): string {
  if (!enabled || !hasData || pct == null) return "bg-white/18 opacity-60";
  if (kind === "turn") {
    if (pct >= 95) return "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.35)]";
    return "bg-emerald-400/90 shadow-[0_0_8px_rgba(52,211,153,0.22)]";
  }
  if (kind === "ws") {
    if (pct >= 100) return "bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.38)]";
    if (pct >= 90) return "bg-rose-400/90";
    if (pct >= 70) return "bg-amber-400/80";
    return "bg-slate-300/60";
  }
  if (pct >= 100) return "bg-rose-500";
  if (pct >= 90) return "bg-amber-400";
  if (pct >= 70) return "bg-amber-400/75";
  return "bg-slate-300/60";
}

export type ContextMeterClusterProps = {
  payload: ChatContextMetersPayload | null;
  enabled: boolean;
  density?: ContextMeterClusterDensity;
  /** `rings`: three separate meters. `pulse`: compact System Pulse chip. */
  layout?: "rings" | "pulse";
};

function SystemPulseChip({
  payload,
  turn,
  ws,
  th,
  turnPct,
  wsPct,
  thPct,
  onOpenDiagnostics,
}: {
  payload: ChatContextMetersPayload | null;
  turn: ChatContextThisTurnMeter | null;
  ws: ChatContextWorkspaceMeter | null;
  th: ChatContextThreadMeter | null;
  turnPct: number | null;
  wsPct: number | null;
  thPct: number | null;
  onOpenDiagnostics: (anchor: HTMLElement) => void;
}) {
  const worst = React.useMemo(() => {
    const vals = [turnPct, wsPct, thPct].filter((x): x is number => typeof x === "number");
    if (!vals.length) return null;
    return Math.max(...vals);
  }, [turnPct, wsPct, thPct]);

  const critical =
    (wsPct != null && wsPct >= 90) ||
    (thPct != null && thPct >= 90) ||
    (turnPct != null && turnPct >= 95);

  return (
    <button
      type="button"
      data-hww-system-pulse="true"
      aria-label="Open system diagnostics"
      aria-haspopup="dialog"
      onClick={(e) => onOpenDiagnostics(e.currentTarget)}
      className={cn(
        "hww-system-pulse flex h-8 shrink-0 items-center gap-1.5 rounded-full border bg-black/35 px-2 text-[10px] font-mono uppercase tracking-wide text-white/75",
        "outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40",
        critical ? "border-rose-500/35" : "border-white/[0.1]",
      )}
    >
      <span className="select-none text-white/40">Sys</span>
      <span className="flex items-center gap-0.5" aria-hidden>
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full transition-opacity",
            pulseDotClass(
              "turn",
              payload?.enabled ? turnPct : null,
              Boolean(payload?.enabled),
              Boolean(turn),
            ),
          )}
        />
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full transition-opacity",
            pulseDotClass(
              "ws",
              payload?.enabled ? wsPct : null,
              Boolean(payload?.enabled),
              Boolean(ws),
            ),
          )}
        />
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full transition-opacity",
            pulseDotClass(
              "thr",
              payload?.enabled ? thPct : null,
              Boolean(payload?.enabled),
              Boolean(th),
            ),
          )}
        />
      </span>
      <span className="tabular-nums text-white/55" aria-hidden>
        {payload?.enabled && worst != null ? `${worst}%` : "—"}
      </span>
    </button>
  );
}

export function ContextMeterCluster({
  payload,
  enabled,
  density = "comfortable",
  layout = "rings",
}: ContextMeterClusterProps) {
  const [diagOpen, setDiagOpen] = React.useState(false);
  const [diagPos, setDiagPos] = React.useState({ top: 0, left: 0 });
  const openFromRef = React.useRef<HTMLElement | null>(null);
  const diagOpenRef = React.useRef(false);

  React.useEffect(() => {
    diagOpenRef.current = diagOpen;
  }, [diagOpen]);

  const closeDiagnostics = React.useCallback(() => {
    diagOpenRef.current = false;
    setDiagOpen(false);
    openFromRef.current = null;
  }, []);

  const openDiagnostics = React.useCallback(
    (anchor: HTMLElement) => {
      if (diagOpenRef.current && openFromRef.current === anchor) {
        closeDiagnostics();
        return;
      }
      openFromRef.current = anchor;
      const r = anchor.getBoundingClientRect();
      const panelW = 308;
      setDiagPos({
        top: r.bottom + 8,
        left: Math.max(8, Math.min(r.left, window.innerWidth - panelW - 8)),
      });
      diagOpenRef.current = true;
      setDiagOpen(true);
    },
    [closeDiagnostics],
  );

  React.useEffect(() => {
    if (!diagOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDiagnostics();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [diagOpen, closeDiagnostics]);

  React.useEffect(() => {
    if (!diagOpen) return;
    let onDoc: ((e: MouseEvent) => void) | undefined;
    let detached = false;
    const id = window.setTimeout(() => {
      if (detached) return;
      onDoc = (e: MouseEvent) => {
        const t = e.target as Node | null;
        if (!t) return;
        const panel = document.querySelector('[data-hww-diagnostics-hud="panel"]');
        if (panel?.contains(t)) return;
        closeDiagnostics();
      };
      document.addEventListener("mousedown", onDoc);
    }, 0);
    return () => {
      detached = true;
      window.clearTimeout(id);
      if (onDoc) document.removeEventListener("mousedown", onDoc);
    };
  }, [diagOpen, closeDiagnostics]);

  if (!enabled) return null;

  const turn = payload?.this_turn ?? null;
  const ws = payload?.workspace ?? null;
  const th = payload?.thread ?? null;

  const turnPct = turn ? pctFromFillRatio(turn.fill_ratio) : null;
  const wsPct = ws ? pctFromFillRatio(ws.fill_ratio) : null;
  const thPct = th ? pctFromFillRatio(th.fill_ratio) : null;

  const diagPortal =
    diagOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            data-hww-diagnostics-hud="floating"
            className="pointer-events-auto z-[250]"
            style={{ position: "fixed", top: diagPos.top, left: diagPos.left }}
            role="presentation"
          >
            <ContextDiagnosticsHudPanel payload={payload} enabled={Boolean(payload?.enabled)} />
          </div>,
          document.body,
        )
      : null;

  if (layout === "pulse") {
    return (
      <>
        <div className="flex shrink-0 items-center" data-hww-meter-cluster="pulse">
          <SystemPulseChip
            payload={payload}
            turn={turn}
            ws={ws}
            th={th}
            turnPct={payload?.enabled ? turnPct : null}
            wsPct={payload?.enabled ? wsPct : null}
            thPct={payload?.enabled ? thPct : null}
            onOpenDiagnostics={openDiagnostics}
          />
        </div>
        {diagPortal}
      </>
    );
  }

  const dim = DIMS[density];

  return (
    <>
      <div
        className={cn("flex shrink-0 items-center", dim.gapClass)}
        role="group"
        aria-label="Context meters"
        data-hww-meter-cluster="rings"
      >
        <button
          type="button"
          aria-label="Open system diagnostics — this turn"
          aria-haspopup="dialog"
          onClick={(e) => openDiagnostics(e.currentTarget)}
          className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
        >
          <MeterRing
            label="Turn"
            kind="turn"
            pct={payload?.enabled ? turnPct : null}
            apiColor={turn ? mapApiColor(turn.color) : "gray"}
            unavailable={!payload?.enabled || !turn}
            ringSize={dim.ring}
            strokeWidth={dim.stroke}
            labelClass={dim.labelClass}
          />
        </button>
        <button
          type="button"
          aria-label="Open system diagnostics — workspace"
          aria-haspopup="dialog"
          onClick={(e) => openDiagnostics(e.currentTarget)}
          className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
        >
          <MeterRing
            label="Ws"
            kind="ws"
            pct={payload?.enabled ? wsPct : null}
            apiColor={ws ? mapApiColor(ws.color) : "gray"}
            unavailable={!payload?.enabled || !ws}
            ringSize={dim.ring}
            strokeWidth={dim.stroke}
            labelClass={dim.labelClass}
          />
        </button>
        <button
          type="button"
          aria-label="Open system diagnostics — thread"
          aria-haspopup="dialog"
          onClick={(e) => openDiagnostics(e.currentTarget)}
          className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
        >
          <MeterRing
            label="Thr"
            kind="thr"
            pct={payload?.enabled ? thPct : null}
            apiColor={th ? mapApiColor(th.color) : "gray"}
            unavailable={!payload?.enabled || !th}
            ringSize={dim.ring}
            strokeWidth={dim.stroke}
            labelClass={dim.labelClass}
          />
        </button>
      </div>
      {diagPortal}
    </>
  );
}
