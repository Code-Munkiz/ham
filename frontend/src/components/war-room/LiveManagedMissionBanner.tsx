import * as React from "react";
import { Activity, Clock, Radio } from "lucide-react";

import { useManagedCloudAgentContext } from "@/contexts/ManagedCloudAgentContext";
import { cn } from "@/lib/utils";

function shortAgentId(id: string): string {
  const t = id.trim();
  if (t.length <= 14) return t;
  return `${t.slice(0, 6)}…${t.slice(-4)}`;
}

function formatSyncAgo(lastMs: number | null, now: number): string {
  if (lastMs == null) return "not yet";
  const s = Math.floor((now - lastMs) / 1000);
  if (s < 0) return "just now";
  if (s < 8) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

export type LiveManagedMissionBannerProps = {
  /** When false, the component renders nothing (hooks still run; parent should gate visibility if needed). */
  when: boolean;
  className?: string;
};

/**
 * Full-width workbench ribbon for managed Cloud Agent: ties HAM (left) to execution (right) with live status.
 * Driven only by `ManagedCloudAgentContext` + poll state — no extra API.
 */
export function LiveManagedMissionBanner({ when, className }: LiveManagedMissionBannerProps) {
  const managed = useManagedCloudAgentContext();
  const [now, setNow] = React.useState(() => Date.now());

  React.useEffect(() => {
    if (!when) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [when]);

  if (!when) return null;

  const id = (managed.activeCloudAgentId ?? "").trim();
  if (!id) return null;

  const status =
    managed.pollPending && !managed.lastSnapshot?.status?.trim()
      ? "Syncing"
      : managed.lastSnapshot?.status?.trim() || (managed.pollPending ? "Syncing" : "Live");
  const progress = managed.lastSnapshot?.progress?.trim() || null;
  const pollErr = managed.pollError;

  return (
    <div
      className={cn(
        "shrink-0 w-full border-b border-white/10 bg-gradient-to-b from-[#0f0a08]/95 to-[#080808]/98",
        className,
      )}
      role="status"
      aria-label="Managed cloud mission"
    >
      <div
        className="h-px w-full bg-gradient-to-r from-[#FF6B00] via-[#00E5FF]/35 to-[#00E5FF]/70"
        aria-hidden
      />
      <div className="flex min-h-0 flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-[#FF6B00]/35 bg-[#FF6B00]/10">
            <Radio className="h-3.5 w-3.5 text-[#FF6B00]" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-[9px] font-black uppercase tracking-[0.2em] text-white/40">Live mission</p>
            <p className="truncate font-mono text-[12px] font-bold text-white/90" title={id}>
              {shortAgentId(id)}
            </p>
          </div>
        </div>

        <div className="hidden h-8 w-px bg-white/10 sm:block" aria-hidden />

        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <div className="flex min-w-0 items-center gap-1.5">
            <span
              className={cn(
                "h-1.5 w-1.5 shrink-0 rounded-full",
                pollErr ? "bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.6)]" : "bg-emerald-400/90",
                !pollErr && managed.pollPending ? "animate-pulse" : "shadow-[0_0_6px_rgba(52,211,153,0.4)]",
              )}
            />
            <span className="min-w-0 text-[12px] font-bold uppercase tracking-wide text-white/80">{status}</span>
          </div>
          {progress ? (
            <p className="min-w-0 max-w-[min(200px,28vw)] truncate text-[11px] text-white/45" title={progress}>
              {progress}
            </p>
          ) : null}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-3 pl-1">
          {pollErr ? (
            <span
              className="max-w-[min(200px,40vw)] truncate text-[10px] font-mono text-amber-400/90"
              title={pollErr}
            >
              {pollErr}
            </span>
          ) : (
            <>
              <div className="hidden items-center gap-1.5 text-[10px] text-white/35 sm:flex" title="Last successful poll">
                <Clock className="h-3 w-3 shrink-0 opacity-50" />
                <span>Sync {formatSyncAgo(managed.lastUpdated, now)}</span>
              </div>
              {managed.pollPending ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-[#00E5FF]/80">
                  <Activity className="h-3 w-3 animate-pulse" />
                  Pulse
                </span>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
