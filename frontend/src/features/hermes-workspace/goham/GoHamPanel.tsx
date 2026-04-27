/**
 * GoHAM Mode — action trail and stop control (workspace chat).
 */

import * as React from "react";
import { Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { GoHamTrailStep } from "./gohamObserveFlow";

type GoHamPanelProps = {
  enabled: boolean;
  active: boolean;
  trail: GoHamTrailStep[];
  onStop: () => void;
  gateHint: string | null;
  /** Slice 3 — research loop controls (observe-only runs omit these). */
  researchControls?: {
    paused: boolean;
    takeover: boolean;
    onPause: () => void;
    onResume: () => void;
    onTakeover: () => void;
  };
};

export function GoHamPanel({ enabled, active, trail, onStop, gateHint, researchControls }: GoHamPanelProps) {
  if (!enabled && trail.length === 0 && !gateHint) return null;

  const rc = researchControls;
  const showResearchControls = Boolean(active && rc);

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[40rem] shrink-0 border-t border-white/[0.06] bg-[#050c12]/95 px-3 py-2 backdrop-blur-sm md:px-6",
        enabled && "border-emerald-500/15",
      )}
      role="region"
      aria-label="GoHAM Mode"
    >
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-200/90">GoHAM Mode</div>
            <p className="mt-0.5 text-[10px] leading-snug text-white/55">
              GoHAM uses a separate managed browser window. It will not use your default browser or saved passwords.
            </p>
            {gateHint ? (
              <p className="mt-1 text-[10px] text-amber-200/85" role="status">
                {gateHint}
              </p>
            ) : null}
            {rc?.takeover ? (
              <p className="mt-1 text-[10px] text-sky-200/90" role="status">
                Browser is yours. Click Resume when you want HAM to continue.
              </p>
            ) : rc?.paused ? (
              <p className="mt-1 text-[10px] text-amber-200/85" role="status">
                Paused — HAM will not start a new action until you resume.
              </p>
            ) : null}
          </div>
          {active ? (
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
              {showResearchControls ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-8 rounded-lg text-[11px]"
                    disabled={rc!.paused || rc!.takeover}
                    onClick={rc!.onPause}
                  >
                    Pause
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-8 rounded-lg text-[11px]"
                    disabled={!rc!.paused && !rc!.takeover}
                    onClick={rc!.onResume}
                  >
                    Resume
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 rounded-lg border-white/20 text-[11px] text-white/90"
                    disabled={rc!.takeover}
                    onClick={rc!.onTakeover}
                  >
                    Take over
                  </Button>
                </>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="destructive"
                className="h-8 shrink-0 gap-1.5 rounded-lg text-[11px]"
                onClick={onStop}
              >
                <Square className="h-3 w-3 fill-current" strokeWidth={0} />
                Stop GoHAM
              </Button>
            </div>
          ) : null}
        </div>
        {trail.length > 0 ? (
          <ol className="space-y-1 rounded-lg border border-white/[0.06] bg-black/20 px-2 py-2 text-[10px] text-white/70">
            {trail.map((s) => (
              <li key={s.id} className="flex gap-2">
                <span className="mt-0.5 shrink-0 font-mono text-[9px] text-white/35">
                  {s.status === "done" ? "✓" : s.status === "active" ? "…" : s.status === "error" ? "!" : "·"}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      s.status === "error" && "text-red-200/90",
                      s.status === "active" && "text-emerald-200/90",
                      s.status === "done" && "text-white/80",
                    )}
                  >
                    {s.label}
                  </span>
                  {s.detail ? (
                    <span className="mt-0.5 block break-words text-[9px] text-white/45">{s.detail}</span>
                  ) : null}
                  {s.actionType || s.targetRedacted || s.result || s.errorReason ? (
                    <span className="mt-0.5 block font-mono text-[9px] leading-snug text-white/40">
                      {s.actionType ? (
                        <span>
                          <span className="text-white/50">action</span> {s.actionType}
                        </span>
                      ) : null}
                      {s.targetRedacted ? (
                        <span className={s.actionType ? " block" : ""}>
                          <span className="text-white/50">target</span> {s.targetRedacted}
                        </span>
                      ) : null}
                      {s.result ? (
                        <span className={s.actionType || s.targetRedacted ? " block" : ""}>
                          <span className="text-white/50">result</span> {s.result}
                        </span>
                      ) : null}
                      {s.errorReason ? (
                        <span className="block text-red-200/80">
                          <span className="text-white/50">reason</span> {s.errorReason}
                        </span>
                      ) : null}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ol>
        ) : null}
        {enabled && !active ? (
          <p className="text-[9px] leading-snug text-white/40">
            Include a <code className="rounded bg-white/10 px-0.5">https://</code> or hostname. Messages with{" "}
            <em>find</em>, <em>research</em>, <em>tell me about</em>, etc. run a short multi-step loop (scroll /
            safe link clicks). Use <strong>Pause</strong>, <strong>Take over</strong>, and <strong>Resume</strong>{" "}
            during research. “What you see” style prompts stay on a single-page observe. No forms, logins, or
            purchases.
          </p>
        ) : null}
      </div>
    </div>
  );
}
