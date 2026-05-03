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

const RING_SIZE = 36;
const STROKE = 3;
const R = (RING_SIZE - STROKE) / 2 - 1;
const C = 2 * Math.PI * R;

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
}: {
  label: string;
  pct: number | null;
  color: ChatContextMeterColor | undefined;
  unavailable?: boolean;
}) {
  const u = unavailable || pct === null;
  const p = u ? 0 : Math.max(0, Math.min(100, pct));
  const dash = C * (1 - p / 100);
  return (
    <div className="relative flex flex-col items-center">
      <svg
        width={RING_SIZE}
        height={RING_SIZE}
        viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
        className="shrink-0"
        aria-hidden
      >
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={R}
          fill="none"
          className="stroke-white/[0.12]"
          strokeWidth={STROKE}
        />
        {!u ? (
          <circle
            cx={RING_SIZE / 2}
            cy={RING_SIZE / 2}
            r={R}
            fill="none"
            className={`${strokeForColor(color)} transition-[stroke-dashoffset]`}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${C} ${C}`}
            strokeDashoffset={dash}
            transform={`rotate(-90 ${RING_SIZE / 2} ${RING_SIZE / 2})`}
          />
        ) : null}
        {u ? (
          <circle
            cx={RING_SIZE / 2}
            cy={RING_SIZE / 2}
            r={R - 4}
            fill="currentColor"
            className="text-white/[0.06]"
          />
        ) : null}
      </svg>
      <span className="mt-0.5 text-[8px] font-semibold uppercase tracking-wide text-white/35">{label}</span>
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
  const role = m.bottleneck_role ? `${m.bottleneck_role} role is tightest` : "Instruction assembly vs budget";
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
};

export function ContextMeterCluster({ payload, enabled }: ContextMeterClusterProps) {
  const navigate = useNavigate();
  if (!enabled) return null;

  const turn = payload?.this_turn ?? null;
  const ws = payload?.workspace ?? null;
  const th = payload?.thread ?? null;

  const turnPct = turn ? pctFromRatio(turn.fill_ratio) : null;
  const wsPct = ws ? pctFromRatio(ws.fill_ratio) : null;
  const thPct = th ? pctFromRatio(th.fill_ratio) : null;

  return (
    <div className="flex shrink-0 items-center gap-0.5 md:gap-1" role="group" aria-label="Context meters">
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
        />
      </button>
    </div>
  );
}
