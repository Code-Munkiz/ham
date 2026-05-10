/**
 * Three compact SVG rings for chat context pressure (Turn · Workspace · Thread).
 * Tooltips via native `title` (max ~4 short lines); colors include pattern fill for a11y.
 */
import * as React from "react";
import { useNavigate } from "react-router-dom";
import type {
  ChatContextMetersPayload,
  ChatContextMeterColor,
  ChatContextThreadMeter,
  ChatContextThisTurnMeter,
  ChatContextWorkspaceMeter,
} from "@/lib/ham/types";
import { cn } from "@/lib/utils";

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

function strokeForColor(c: ChatContextMeterColor | undefined): string {
  switch (c) {
    case "green":
      return "stroke-emerald-400";
    case "amber":
      return "stroke-amber-400";
    case "red":
      return "stroke-red-400";
    default:
      return "stroke-white/25";
  }
}

function MeterRing({
  label,
  pct,
  color,
  unavailable,
  ringSize,
  strokeWidth,
  labelClass,
}: {
  label: string;
  pct: number | null;
  color: ChatContextMeterColor | undefined;
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
  return (
    <div className="relative flex flex-col items-center">
      <svg
        width={ringSize}
        height={ringSize}
        viewBox={`0 0 ${ringSize} ${ringSize}`}
        className="shrink-0"
        aria-hidden
      >
        <circle
          cx={ringSize / 2}
          cy={ringSize / 2}
          r={R}
          fill="none"
          className="stroke-white/[0.12]"
          strokeWidth={strokeWidth}
        />
        {!u ? (
          <circle
            cx={ringSize / 2}
            cy={ringSize / 2}
            r={R}
            fill="none"
            className={`${strokeForColor(color)} transition-[stroke-dashoffset]`}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={`${C} ${C}`}
            strokeDashoffset={dash}
            transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`}
          />
        ) : null}
        {u ? (
          <circle
            cx={ringSize / 2}
            cy={ringSize / 2}
            r={R - Math.max(2, strokeWidth)}
            fill="currentColor"
            className="text-white/[0.06]"
          />
        ) : null}
      </svg>
      <span className={labelClass}>{label}</span>
    </div>
  );
}

function pctFromRatio(ratio: number | undefined): number | null {
  if (ratio === undefined || ratio === null || Number.isNaN(ratio)) return null;
  return Math.round(Math.min(1, Math.max(0, ratio)) * 100);
}

function mapApiColor(c: string | undefined): ChatContextMeterColor {
  if (c === "green" || c === "amber" || c === "red") return c;
  return "gray";
}

function buildThisTurnTooltip(m: ChatContextThisTurnMeter | null): string {
  if (!m) return "This turn — unavailable\nEstimates update after you send.";
  const pct = pctFromRatio(m.fill_ratio);
  const lines = [
    `This turn · ${pct}% full`,
    `About ${m.used.toLocaleString()} / ${m.limit.toLocaleString()} est. tokens`,
    "Uses persisted thread plus a fixed routing overhead estimate.",
    "Shorten the message, remove attachments, narrow the ask, or pick a larger-context model.",
  ];
  return lines.join("\n");
}

function buildWorkspaceTooltip(m: ChatContextWorkspaceMeter | null): string {
  if (!m) return "Workspace — unavailable\nOpen Context & memory when connected.";
  const pct = pctFromRatio(m.fill_ratio);
  const role = m.bottleneck_role
    ? `${m.bottleneck_role} role is tightest`
    : "Instruction assembly vs budget";
  const lines = [
    `Workspace · ${pct}% full (${m.source})`,
    `${m.used.toLocaleString()} / ${m.limit.toLocaleString()} chars`,
    role,
    "Open Context & memory to reduce instruction surface or check Routing first.",
  ];
  return lines.join("\n");
}

function buildThreadTooltip(m: ChatContextThreadMeter | null): string {
  if (!m) return "Thread — unavailable";
  const pct = pctFromRatio(m.fill_ratio);
  const lines = [
    `Thread · ${pct}% full`,
    `${m.approx_transcript_chars.toLocaleString()} / ${m.thread_budget_chars.toLocaleString()} chars (estimate)`,
    "Persisted transcript size vs session compaction budget.",
    "Start a new chat session or export this one if needed.",
  ];
  return lines.join("\n");
}

export type ContextMeterClusterProps = {
  payload: ChatContextMetersPayload | null;
  enabled: boolean;
  density?: ContextMeterClusterDensity;
  /** `rings`: three separate meters. `pulse`: compact System Pulse chip with combined tooltip. */
  layout?: "rings" | "pulse";
};

function dotClassForColor(c: ChatContextMeterColor | undefined): string {
  switch (c) {
    case "green":
      return "bg-emerald-400/90 shadow-[0_0_10px_rgba(52,211,153,0.35)]";
    case "amber":
      return "bg-amber-400/90 shadow-[0_0_10px_rgba(251,191,36,0.28)]";
    case "red":
      return "bg-red-400/90 shadow-[0_0_12px_rgba(248,113,113,0.38)]";
    default:
      return "bg-white/25";
  }
}

function SystemPulseChip({
  payload,
  turn,
  ws,
  th,
  turnPct,
}: {
  payload: ChatContextMetersPayload | null;
  turn: ChatContextThisTurnMeter | null;
  ws: ChatContextWorkspaceMeter | null;
  th: ChatContextThreadMeter | null;
  turnPct: number | null;
}) {
  const combinedTitle = [
    buildThisTurnTooltip(turn),
    "",
    buildWorkspaceTooltip(ws),
    "",
    buildThreadTooltip(th),
    "",
    "Tip: open Workspace → Settings → Model / provider to adjust routing surfaces.",
  ].join("\n");

  const turnC = turn ? mapApiColor(turn.color) : "gray";
  const wsC = ws ? mapApiColor(ws.color) : "gray";
  const thC = th ? mapApiColor(th.color) : "gray";

  return (
    <button
      type="button"
      data-hww-system-pulse="true"
      title={combinedTitle}
      aria-label={combinedTitle.replace(/\n/g, ". ")}
      className={cn(
        "hww-system-pulse flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-white/[0.1] bg-black/35 px-2 text-[10px] font-mono uppercase tracking-wide text-white/75",
        "outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40",
      )}
    >
      <span className="select-none text-white/40">Sys</span>
      <span className="flex items-center gap-0.5" aria-hidden>
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            dotClassForColor(turnC),
            !payload?.enabled || !turn ? "opacity-40" : null,
          )}
        />
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            dotClassForColor(wsC),
            !payload?.enabled || !ws ? "opacity-40" : null,
          )}
        />
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            dotClassForColor(thC),
            !payload?.enabled || !th ? "opacity-40" : null,
          )}
        />
      </span>
      <span className="tabular-nums text-white/55" aria-hidden>
        {payload?.enabled && turnPct != null ? `${turnPct}%` : "—"}
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
  const navigate = useNavigate();
  if (!enabled) return null;

  const turn = payload?.this_turn ?? null;
  const ws = payload?.workspace ?? null;
  const th = payload?.thread ?? null;

  const turnPct = turn ? pctFromRatio(turn.fill_ratio) : null;
  const wsPct = ws ? pctFromRatio(ws.fill_ratio) : null;
  const thPct = th ? pctFromRatio(th.fill_ratio) : null;

  if (layout === "pulse") {
    return (
      <div className="flex shrink-0 items-center" data-hww-meter-cluster="pulse">
        <SystemPulseChip
          payload={payload}
          turn={turn}
          ws={ws}
          th={th}
          turnPct={payload?.enabled ? turnPct : null}
        />
      </div>
    );
  }

  const dim = DIMS[density];

  return (
    <div
      className={cn("flex shrink-0 items-center", dim.gapClass)}
      role="group"
      aria-label="Context meters"
      data-hww-meter-cluster="rings"
    >
      <button
        type="button"
        title={buildThisTurnTooltip(turn)}
        aria-label={buildThisTurnTooltip(turn).replace(/\n/g, ". ")}
        className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
      >
        <MeterRing
          label="Turn"
          pct={payload?.enabled ? turnPct : null}
          color={turn ? mapApiColor(turn.color) : "gray"}
          unavailable={!payload?.enabled || !turn}
          ringSize={dim.ring}
          strokeWidth={dim.stroke}
          labelClass={dim.labelClass}
        />
      </button>
      <button
        type="button"
        title={buildWorkspaceTooltip(ws)}
        aria-label={buildWorkspaceTooltip(ws).replace(/\n/g, ". ")}
        onClick={() => navigate("/workspace/settings?section=hermes")}
        className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
      >
        <MeterRing
          label="Ws"
          pct={payload?.enabled ? wsPct : null}
          color={ws ? mapApiColor(ws.color) : "gray"}
          unavailable={!payload?.enabled || !ws}
          ringSize={dim.ring}
          strokeWidth={dim.stroke}
          labelClass={dim.labelClass}
        />
      </button>
      <button
        type="button"
        title={buildThreadTooltip(th)}
        aria-label={buildThreadTooltip(th).replace(/\n/g, ". ")}
        className="rounded-lg p-0.5 text-white/80 outline-none ring-offset-2 ring-offset-[#030a10] hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-emerald-400/40"
      >
        <MeterRing
          label="Thr"
          pct={payload?.enabled ? thPct : null}
          color={th ? mapApiColor(th.color) : "gray"}
          unavailable={!payload?.enabled || !th}
          ringSize={dim.ring}
          strokeWidth={dim.stroke}
          labelClass={dim.labelClass}
        />
      </button>
    </div>
  );
}
