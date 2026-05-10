/**
 * Command-deck context pressure: compact system pulse + Diagnostics HUD (no native tooltips).
 */
import * as React from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import type {
  ChatContextMetersPayload,
  ChatContextMeterColor,
  ChatContextThreadMeter,
  ChatContextThisTurnMeter,
  ChatContextWorkspaceMeter,
} from "@/lib/ham/types";

const MINI_RING = 14;
const STROKE = 2;
const R = (MINI_RING - STROKE) / 2 - 0.5;
const C = 2 * Math.PI * R;

function strokeClass(c: ChatContextMeterColor | undefined): string {
  switch (c) {
    case "green":
      return "stroke-emerald-400";
    case "amber":
      return "stroke-amber-400";
    case "red":
      return "stroke-red-400";
    default:
      return "stroke-white/30";
  }
}

function pctFromRatio(ratio: number | undefined): number | null {
  if (ratio === undefined || ratio === null || Number.isNaN(ratio)) return null;
  return Math.round(Math.min(1, Math.max(0, ratio)) * 100);
}

function mapApiColor(c: string | undefined): ChatContextMeterColor {
  if (c === "green" || c === "amber" || c === "red") return c;
  return "gray";
}

function hudBarClasses(unavailable: boolean, pct: number | null, color: ChatContextMeterColor): string {
  if (unavailable || pct === null) return "bg-white/[0.06]";
  const critical = pct >= 90 || color === "red";
  const warn = color === "amber" && pct < 90;
  if (critical) return "bg-rose-400/85";
  if (warn) return "bg-amber-400/75";
  if (pct >= 100) return "bg-emerald-400/90";
  return "bg-emerald-400/60";
}

function MiniRing({
  pct,
  color,
  unavailable,
}: {
  pct: number | null;
  color: ChatContextMeterColor;
  unavailable?: boolean;
}) {
  const u = unavailable === true || pct === null;
  const p = u ? 0 : Math.max(0, Math.min(100, pct));
  const dash = C * (1 - p / 100);
  return (
    <svg
      width={MINI_RING}
      height={MINI_RING}
      viewBox={`0 0 ${MINI_RING} ${MINI_RING}`}
      className="shrink-0"
      aria-hidden
    >
      <circle
        cx={MINI_RING / 2}
        cy={MINI_RING / 2}
        r={R}
        fill="none"
        className={u ? "stroke-white/[0.14] stroke-dasharray-[2_2]" : "stroke-white/[0.14]"}
        strokeWidth={STROKE}
      />
      {!u && p > 0 ? (
        <circle
          cx={MINI_RING / 2}
          cy={MINI_RING / 2}
          r={R}
          fill="none"
          className={cn(`${strokeClass(color)} transition-[stroke-dashoffset]`)}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={`${C} ${C}`}
          strokeDashoffset={dash}
          transform={`rotate(-90 ${MINI_RING / 2} ${MINI_RING / 2})`}
        />
      ) : null}
      {!u && p === 0 ? (
        <circle
          cx={MINI_RING / 2}
          cy={MINI_RING / 2}
          r={Math.max(1.25, R - 4)}
          fill="currentColor"
          className="text-white/[0.03]"
          aria-hidden
        />
      ) : null}
    </svg>
  );
}

function thisTurnHudLines(m: ChatContextThisTurnMeter | null, enabled: boolean): { pct: number | null; detail: string } {
  if (!enabled || !m) {
    return { pct: null, detail: enabled ? "Estimates update after you send." : "Context metering unavailable." };
  }
  const pct = pctFromRatio(m.fill_ratio);
  return {
    pct,
    detail: `About ${m.used.toLocaleString()} / ${m.limit.toLocaleString()} est. tokens · routing overhead included.`,
  };
}

function workspaceHudLines(m: ChatContextWorkspaceMeter | null, enabled: boolean): { pct: number | null; detail: string } {
  if (!enabled || !m) {
    return { pct: null, detail: enabled ? "Open Context & memory when connected." : "Workspace metering unavailable." };
  }
  const pct = pctFromRatio(m.fill_ratio);
  const role = m.bottleneck_role ? `${m.bottleneck_role} role is tightest` : "Instruction assembly vs budget.";
  return {
    pct,
    detail: `${m.used.toLocaleString()} / ${m.limit.toLocaleString()} chars · ${role} (${m.source}).`,
  };
}

function threadHudLines(m: ChatContextThreadMeter | null, enabled: boolean): { pct: number | null; detail: string } {
  if (!enabled || !m) {
    return { pct: null, detail: enabled ? "Thread sizing unavailable yet." : "Thread metering unavailable." };
  }
  const pct = pctFromRatio(m.fill_ratio);
  return {
    pct,
    detail: `${m.approx_transcript_chars.toLocaleString()} / ${m.thread_budget_chars.toLocaleString()} chars (estimate) · compaction budget.`,
  };
}

function buildTip(payload: ChatContextMetersPayload | null, enabled: boolean): string | null {
  const parts: string[] = [];
  if (!enabled || !payload) return null;
  const turn = payload.this_turn;
  const ws = payload.workspace;
  const th = payload.thread;
  const turnPct = turn ? pctFromRatio(turn.fill_ratio) : null;
  const wsPct = ws ? pctFromRatio(ws.fill_ratio) : null;
  const thPct = th ? pctFromRatio(th.fill_ratio) : null;
  const turnStress = Boolean(turn && (mapApiColor(turn.color) === "red" || (turnPct != null && turnPct >= 90)));
  const wsStress = Boolean(ws && (mapApiColor(ws.color) === "red" || (wsPct != null && wsPct >= 90)));
  const thStress = Boolean(th && (mapApiColor(th.color) === "red" || (thPct != null && thPct >= 90)));
  if (turnStress) parts.push("This turn context is tight—shorten the message or shrink attachments.");
  if (wsStress) parts.push("Workspace assembly is tight—trim instructions in Context & memory / Routing.");
  if (thStress) parts.push("Thread is large—start a new session or export if needed.");
  return parts.length ? parts.join(" ") : null;
}

function buildPulseAria(payload: ChatContextMetersPayload | null, enabled: boolean): string {
  if (!enabled) return "System context metering disabled.";
  if (!payload) return "System context telemetry loading.";
  const turn = payload.this_turn ? pctFromRatio(payload.this_turn.fill_ratio) : null;
  const ws = payload.workspace ? pctFromRatio(payload.workspace.fill_ratio) : null;
  const th = payload.thread ? pctFromRatio(payload.thread.fill_ratio) : null;
  return [
    "System diagnostics",
    turn != null ? `This turn fill ${turn}%.` : "This turn unavailable.",
    ws != null ? `Workspace fill ${ws}%.` : "Workspace unavailable.",
    th != null ? `Thread fill ${th}%.` : "Thread unavailable.",
    "Activate for full details.",
  ].join(" ");
}

export type ContextMeterClusterProps = {
  payload: ChatContextMetersPayload | null;
  enabled: boolean;
};

export function ContextMeterCluster({ payload, enabled }: ContextMeterClusterProps) {
  const navigate = useNavigate();

  if (!enabled) return null;

  const turnMet = payload?.this_turn ?? null;
  const wsMet = payload?.workspace ?? null;
  const thMet = payload?.thread ?? null;
  const turnPct = payload?.enabled && turnMet ? pctFromRatio(turnMet.fill_ratio) : null;
  const wsPct = payload?.enabled && wsMet ? pctFromRatio(wsMet.fill_ratio) : null;
  const thPct = payload?.enabled && thMet ? pctFromRatio(thMet.fill_ratio) : null;

  const turnColor = turnMet ? mapApiColor(turnMet.color) : "gray";
  const wsColor = wsMet ? mapApiColor(wsMet.color) : "gray";
  const thColor = thMet ? mapApiColor(thMet.color) : "gray";

  const turnU = !payload?.enabled || !turnMet;
  const wsU = !payload?.enabled || !wsMet;
  const thU = !payload?.enabled || !thMet;

  function stressPct(
    meter: ChatContextThisTurnMeter | ChatContextWorkspaceMeter | ChatContextThreadMeter | null,
    pct: number | null,
    color: ChatContextMeterColor,
  ): number | null {
    if (!meter || pct === null) return null;
    if (color === "red") return pct;
    if (color !== "green" && pct >= 90) return pct;
    return null;
  }

  const stressValues = [
    stressPct(turnMet, turnPct, turnColor),
    stressPct(wsMet, wsPct, wsColor),
    stressPct(thMet, thPct, thColor),
  ].filter((n): n is number => typeof n === "number");
  const criticalPulsePct = stressValues.length ? Math.max(...stressValues) : null;

  const showCriticalPulse = criticalPulsePct !== null;

  const [hudOpen, setHudOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);
  const [anchorRect, setAnchorRect] = React.useState<DOMRect | null>(null);
  const hoverOpenTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverCloseTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointerInPanelRef = React.useRef(false);

  const clearHoverTimers = React.useCallback(() => {
    if (hoverOpenTimerRef.current) {
      clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current) {
      clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
  }, []);

  const syncAnchorRect = React.useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    setAnchorRect(el.getBoundingClientRect());
  }, []);

  React.useLayoutEffect(() => {
    if (!hudOpen) return;
    syncAnchorRect();
    const onSr = () => syncAnchorRect();
    window.addEventListener("scroll", onSr, true);
    window.addEventListener("resize", onSr);
    return () => {
      window.removeEventListener("scroll", onSr, true);
      window.removeEventListener("resize", onSr);
    };
  }, [hudOpen, syncAnchorRect]);

  React.useEffect(() => {
    if (!hudOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        clearHoverTimers();
        setHudOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clearHoverTimers, hudOpen]);

  React.useEffect(() => {
    if (!hudOpen) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      if (pointerInPanelRef.current) return;
      setHudOpen(false);
    };
    document.addEventListener("mousedown", onDoc, true);
    return () => document.removeEventListener("mousedown", onDoc, true);
  }, [hudOpen]);

  const hudTip = React.useMemo(
    () => buildTip(payload, Boolean(payload?.enabled)),
    [payload],
  );

  const turnHud = React.useMemo(
    () => thisTurnHudLines(turnMet ?? null, Boolean(payload?.enabled)),
    [turnMet, payload?.enabled],
  );
  const wsHud = React.useMemo(
    () => workspaceHudLines(wsMet ?? null, Boolean(payload?.enabled)),
    [wsMet, payload?.enabled],
  );
  const thHud = React.useMemo(() => threadHudLines(thMet ?? null, Boolean(payload?.enabled)), [payload?.enabled, thMet]);

  const requestOpenHud = React.useCallback(() => {
    clearHoverTimers();
    syncAnchorRect();
    setHudOpen(true);
  }, [clearHoverTimers, syncAnchorRect]);

  const scheduleOpenFromHover = React.useCallback(() => {
    clearHoverTimers();
    hoverOpenTimerRef.current = setTimeout(requestOpenHud, 120);
  }, [clearHoverTimers, requestOpenHud]);

  const scheduleCloseFromHover = React.useCallback(() => {
    clearHoverTimers();
    hoverCloseTimerRef.current = setTimeout(() => {
      if (!pointerInPanelRef.current) setHudOpen(false);
    }, 220);
  }, [clearHoverTimers]);

  const toggleHud = React.useCallback(() => {
    clearHoverTimers();
    setHudOpen((o) => !o);
  }, [clearHoverTimers]);

  return (
    <div data-hww-system-pulse="cluster" className="relative flex shrink-0 items-center justify-center">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggleHud}
        onMouseEnter={() => {
          scheduleOpenFromHover();
        }}
        onMouseLeave={() => {
          scheduleCloseFromHover();
        }}
        onFocus={() => {
          clearHoverTimers();
          syncAnchorRect();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleHud();
          }
        }}
        className={cn(
          "inline-flex h-[32px] min-h-[32px] max-h-[32px] items-center gap-1.5 rounded-[10px] border px-2 outline-none ring-offset-2 ring-offset-[#030a10]",
          "border-white/[0.10] bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]",
          "hover:border-white/[0.16] hover:bg-white/[0.07]",
          "focus-visible:ring-2 focus-visible:ring-emerald-400/35",
          hudOpen && "border-emerald-400/25 bg-white/[0.07]",
        )}
        aria-label={buildPulseAria(payload, Boolean(payload?.enabled ?? true))}
        aria-expanded={hudOpen}
        aria-haspopup="dialog"
        data-hww-context-pulse="trigger"
      >
        <div className="flex items-center gap-1">
          <MiniRing pct={turnPct} color={turnColor} unavailable={turnU} />
          <MiniRing pct={wsPct} color={wsColor} unavailable={wsU} />
          <MiniRing pct={thPct} color={thColor} unavailable={thU} />
        </div>
        {showCriticalPulse && criticalPulsePct !== null ? (
          <span className="font-mono text-[10px] font-semibold tabular-nums tracking-tight text-rose-300/95">
            {criticalPulsePct}%
          </span>
        ) : null}
      </button>

      {hudOpen && anchorRect && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={panelRef}
              role="dialog"
              aria-labelledby="hww-diagnostics-heading"
              className={cn(
                "fixed z-[220] box-border w-[min(94vw,16.5rem)] overflow-hidden rounded-lg",
                "border border-white/[0.12]",
                "bg-[#050809]/93 shadow-[0_14px_40px_rgba(0,0,0,0.55)] backdrop-blur-md",
              )}
              style={{
                left: Math.min(window.innerWidth - 16 - 264, Math.max(8, anchorRect.right - 264)),
                bottom: window.innerHeight - anchorRect.top + 10,
              }}
              onMouseEnter={() => {
                pointerInPanelRef.current = true;
                clearHoverTimers();
              }}
              onMouseLeave={() => {
                pointerInPanelRef.current = false;
                scheduleCloseFromHover();
              }}
              data-hww-context-diagnostics="panel"
            >
              <div className="border-b border-white/[0.08] px-3 py-2">
                <div
                  id="hww-diagnostics-heading"
                  className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/42"
                >
                  System Diagnostics
                </div>
              </div>
              <div className="space-y-2.5 px-3 py-3 font-mono text-[11px] leading-snug text-white/78">
                <div>
                  <div className="mb-1 flex justify-between gap-2 text-white/72">
                    <span>This turn</span>
                    {!turnU && turnHud.pct != null ? (
                      <span className="tabular-nums text-white/45">{turnHud.pct}%</span>
                    ) : (
                      <span className="text-white/35">–</span>
                    )}
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-white/[0.08]" data-hww-diagnostics-bar="turn">
                    {!turnU && turnHud.pct != null ? (
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width]",
                          hudBarClasses(turnU, turnHud.pct, turnColor),
                        )}
                        style={{ width: `${turnHud.pct}%` }}
                      />
                    ) : null}
                  </div>
                  <p className="mt-1 text-[10px] font-sans leading-snug text-white/41">{turnHud.detail}</p>
                </div>

                <div>
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <span className="text-white/72">Workspace</span>
                    {!wsU && wsHud.pct != null ? (
                      <span className="tabular-nums text-white/45">{wsHud.pct}%</span>
                    ) : (
                      <span className="text-white/35">–</span>
                    )}
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-white/[0.08]" data-hww-diagnostics-bar="workspace">
                    {!wsU && wsHud.pct != null ? (
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width]",
                          hudBarClasses(wsU, wsHud.pct, wsColor),
                        )}
                        style={{ width: `${wsHud.pct}%` }}
                      />
                    ) : null}
                  </div>
                  <p className="mt-1 text-[10px] font-sans leading-snug text-white/41">{wsHud.detail}</p>
                  <button
                    type="button"
                    className="mt-1.5 rounded px-0 text-[10px] font-sans text-emerald-200/85 underline-offset-4 hover:text-emerald-100 hover:underline"
                    onClick={() => {
                      setHudOpen(false);
                      navigate("/workspace/settings?section=hermes");
                    }}
                  >
                    Open Routing & Hermes settings
                  </button>
                </div>

                <div>
                  <div className="mb-1 flex justify-between gap-2 text-white/72">
                    <span>Thread</span>
                    {!thU && thHud.pct != null ? (
                      <span className="tabular-nums text-white/45">{thHud.pct}%</span>
                    ) : (
                      <span className="text-white/35">–</span>
                    )}
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-white/[0.08]" data-hww-diagnostics-bar="thread">
                    {!thU && thHud.pct != null ? (
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width]",
                          hudBarClasses(thU, thHud.pct, thColor),
                        )}
                        style={{ width: `${thHud.pct}%` }}
                      />
                    ) : (
                      <div className="h-full w-[4%] rounded-full bg-white/[0.08]" aria-hidden />
                    )}
                  </div>
                  <p className="mt-1 text-[10px] font-sans leading-snug text-white/41">{thHud.detail}</p>
                  <span className="mt-1.5 inline-block font-sans text-[10px] text-white/32">
                    New session from the chat sidebar when compaction is insufficient.
                  </span>
                </div>

                {hudTip ? (
                  <p className="border-t border-white/[0.08] pt-2 text-[10px] font-sans leading-snug text-amber-200/75">
                    Tip · {hudTip}
                  </p>
                ) : null}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
