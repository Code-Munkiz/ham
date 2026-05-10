/**
 * Dark operator Diagnostics HUD for context meters (replaces native `title` tooltips).
 */
import { Link } from "react-router-dom";
import type { ChatContextMetersPayload } from "@/lib/ham/types";
import { cn } from "@/lib/utils";

export function pctFromFillRatio(ratio: number | undefined): number | null {
  if (ratio === undefined || ratio === null || Number.isNaN(ratio)) return null;
  return Math.round(Math.min(1, Math.max(0, ratio)) * 100);
}

function MiniMeterBar({
  label,
  pct,
  variant,
}: {
  label: string;
  pct: number | null;
  variant: "neutral" | "amber" | "rose";
}) {
  const u = pct == null;
  const p = u ? 0 : Math.max(0, Math.min(100, pct));
  const fill =
    variant === "rose"
      ? "bg-gradient-to-r from-rose-500/80 to-rose-400/70"
      : variant === "amber"
        ? "bg-gradient-to-r from-amber-500/75 to-amber-400/65"
        : "bg-gradient-to-r from-slate-200/45 to-slate-300/35";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-wide text-white/45">
        <span>{label}</span>
        <span className="tabular-nums text-white/70">{u ? "—" : `${p}%`}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/50 ring-1 ring-white/[0.08]">
        <div
          className={cn("h-full rounded-full transition-[width] duration-200", !u && fill)}
          style={{ width: u ? 0 : `${p}%` }}
        />
      </div>
    </div>
  );
}

function sectionVariant(
  pct: number | null,
  criticalThreshold: number,
): "neutral" | "amber" | "rose" {
  if (pct == null) return "neutral";
  if (pct >= criticalThreshold) return "rose";
  if (pct >= criticalThreshold - 10) return "amber";
  return "neutral";
}

export type ContextDiagnosticsHudPanelProps = {
  payload: ChatContextMetersPayload | null;
  enabled: boolean;
  className?: string;
};

export function ContextDiagnosticsHudPanel({
  payload,
  enabled,
  className,
}: ContextDiagnosticsHudPanelProps) {
  const turn = payload?.this_turn ?? null;
  const ws = payload?.workspace ?? null;
  const th = payload?.thread ?? null;

  const turnPct = turn ? pctFromFillRatio(turn.fill_ratio) : null;
  const wsPct = ws ? pctFromFillRatio(ws.fill_ratio) : null;
  const thPct = th ? pctFromFillRatio(th.fill_ratio) : null;

  const turnBody = !enabled
    ? "Context meters are offline for this session."
    : !turn
      ? "Estimates update after you send a message."
      : `About ${turn.used.toLocaleString()} / ${turn.limit.toLocaleString()} est. tokens. Uses persisted thread plus routing overhead.`;

  const wsBody = !enabled
    ? "Workspace meter unavailable."
    : !ws
      ? "Open Context & memory when connected."
      : `${ws.used.toLocaleString()} / ${ws.limit.toLocaleString()} chars (${ws.source}). ${
          ws.bottleneck_role
            ? `${ws.bottleneck_role} role is tightest.`
            : "Instruction assembly vs budget."
        }`;

  const thBody = !enabled
    ? "Thread meter unavailable."
    : !th
      ? "No thread estimate yet."
      : `${th.approx_transcript_chars.toLocaleString()} / ${th.thread_budget_chars.toLocaleString()} chars (estimate). Persisted transcript vs session compaction budget. Start a new chat session or export this one if needed.`;

  const critical =
    (wsPct != null && wsPct >= 90) ||
    (thPct != null && thPct >= 90) ||
    (turnPct != null && turnPct >= 95);

  return (
    <div
      data-hww-diagnostics-hud="panel"
      className={cn(
        "max-w-[min(20rem,calc(100vw-1.25rem))] rounded-lg border bg-[#070f14]/96 p-3 text-[11px] leading-snug text-white/88 shadow-[0_12px_48px_rgba(0,0,0,0.55)] backdrop-blur-md",
        critical ? "border-rose-500/35 shadow-rose-900/20" : "border-white/10",
        className,
      )}
    >
      <p className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-white/50">
        System diagnostics
      </p>

      <div className="mt-3 space-y-3">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-wide text-emerald-200/85">
            This turn
          </p>
          <p className="mt-1 text-white/72">{turnBody}</p>
        </div>

        <MiniMeterBar
          label="This turn (est.)"
          pct={enabled ? turnPct : null}
          variant={sectionVariant(turnPct, 95)}
        />

        <MiniMeterBar
          label="Workspace"
          pct={enabled ? wsPct : null}
          variant={sectionVariant(wsPct, 90)}
        />

        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-wide text-white/70">
            Workspace detail
          </p>
          <p className="mt-1 text-white/65">{wsBody}</p>
        </div>

        <MiniMeterBar
          label="Thread"
          pct={enabled ? thPct : null}
          variant={sectionVariant(thPct, 90)}
        />

        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-wide text-white/70">
            Thread
          </p>
          <p className="mt-1 text-white/65">{thBody}</p>
        </div>
      </div>

      <p className="mt-3 border-t border-white/[0.07] pt-2 font-mono text-[10px] text-white/45">
        Tip: adjust routing and provider surfaces in{" "}
        <Link
          to="/workspace/settings?section=hermes"
          className="font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
        >
          Workspace → Settings → Model / provider
        </Link>
        .
      </p>
    </div>
  );
}
