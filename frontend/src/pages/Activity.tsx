import { MOCK_ACTIVITY } from "@/lib/ham/mocks";
import { activitySourceBadgeClass, activitySourceLabel } from "@/lib/ham/activityEventSource";
import { fetchHermesGatewaySnapshot } from "@/lib/ham/api";
import type { ActivityEvent } from "@/lib/ham/types";
import { AlertCircle, Info, AlertTriangle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import * as React from "react";
import { Link } from "react-router-dom";

function gatewayEventsFromSnapshot(s: Awaited<ReturnType<typeof fetchHermesGatewaySnapshot>>): ActivityEvent[] {
  const ts = s.captured_at || new Date().toISOString();
  const out: ActivityEvent[] = [
    {
      id: `gw-snap-${s.captured_at}`,
      type: "runtime_event",
      level: "info",
      message: `Hermes gateway snapshot ${s.schema_version} · gateway_mode=${(s.hermes_hub as { gateway_mode?: string }).gateway_mode ?? "?"}`,
      timestamp: ts,
      source: "ham",
      metadata: { source: "ham" },
    },
  ];
  (s.warnings ?? []).forEach((w, i) => {
    out.push({
      id: `gw-warn-${i}`,
      type: "warning",
      level: "warn",
      message: w,
      timestamp: ts,
      source: "ham",
      metadata: { source: "ham" },
    });
  });
  for (const d of s.degraded_capabilities ?? []) {
    out.push({
      id: `gw-degraded-${d}`,
      type: "runtime_event",
      level: "warn",
      message: `Degraded capability: ${d}`,
      timestamp: ts,
      source: "ham",
      metadata: { source: "ham" },
    });
  }
  const hg = s.http_gateway as { status?: string; error?: string };
  if (hg?.error) {
    out.push({
      id: "gw-http-err",
      type: "runtime_event",
      level: "warn",
      message: `Hermes HTTP probe: ${hg.error}`,
      timestamp: ts,
      source: "ham",
      metadata: { source: "ham" },
    });
  }
  for (const row of s.activity.control_plane_runs ?? []) {
    const r = row as { ham_run_id: string; status?: string; summary?: string; provider?: string };
    out.push({
      id: `cp-${r.ham_run_id}`,
      type: "run_event",
      level: "info",
      message: `[${r.provider ?? "control_plane"}] ${r.status ?? "?"} — ${r.summary ?? r.ham_run_id}`,
      timestamp: ts,
      source: "cloud_agent",
      metadata: { source: "cloud_agent" },
    });
  }
  return out;
}

export default function Activity() {
  const [live, setLive] = React.useState<ActivityEvent[]>([]);
  const [liveErr, setLiveErr] = React.useState<string | null>(null);
  const [source, setSource] = React.useState<"live" | "demo">("demo");

  React.useEffect(() => {
    let cancelled = false;
    const tick = () => {
      void fetchHermesGatewaySnapshot()
        .then((s) => {
          if (cancelled) return;
          const ev = gatewayEventsFromSnapshot(s);
          setLive(ev);
          setLiveErr(null);
          setSource("live");
        })
        .catch((e) => {
          if (cancelled) return;
          setLiveErr(e instanceof Error ? e.message : "Gateway snapshot failed");
          setLive([]);
          setSource("demo");
        });
    };
    tick();
    const id = window.setInterval(tick, 35_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const events = source === "live" && live.length > 0 ? live : MOCK_ACTIVITY;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[#02080c] font-sans text-[#e8eef8]">
      <div className="mx-auto flex w-full max-w-5xl min-h-0 flex-1 flex-col space-y-6 overflow-y-auto p-6 sm:p-8">
        <div className="flex flex-col gap-4 border-b border-[color:var(--ham-workspace-line)] pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1.5">
            <h1 className="text-lg font-semibold tracking-tight text-white/95">Activity</h1>
            <p className="max-w-xl text-[11px] font-normal leading-relaxed text-white/40">
              Read-only stream from <span className="font-mono text-white/50">GET /api/hermes-gateway/snapshot</span>{" "}
              and control-plane hints. If the API is unreachable, rows show{" "}
              <span className="text-amber-300/90">demo fallback</span> — not a full system log.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  source === "live" ? "animate-pulse bg-emerald-400" : "bg-amber-400/90",
                )}
              />
              <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-white/50">
                {source === "live" ? "Live snapshot" : "Demo fallback"}
              </span>
            </div>
            <Link
              to="/command-center"
              className="text-[10px] font-medium text-[#ffb27a]/90 transition-colors hover:text-[#ffc896]"
            >
              Open Command Center →
            </Link>
          </div>
        </div>

        {liveErr ? (
          <p className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-[11px] font-mono text-amber-200/90">
            {liveErr}
          </p>
        ) : null}

        <div className="flex flex-col gap-2">
          {events.map((event) => (
            <div
              key={event.id}
              className="group flex items-start gap-4 rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/50 p-4 transition-colors hover:border-white/[0.12] hover:bg-[#040d14]/75"
            >
              <div
                className={cn(
                  "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                  event.level === "info"
                    ? "border-sky-500/25 bg-sky-500/10 text-sky-300/90"
                    : event.level === "warn"
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-200/90"
                      : "border-red-500/30 bg-red-500/10 text-red-300/90",
                )}
              >
                {event.level === "info" ? (
                  <Info className="h-4 w-4" strokeWidth={1.5} />
                ) : event.level === "warn" ? (
                  <AlertTriangle className="h-4 w-4" strokeWidth={1.5} />
                ) : (
                  <AlertCircle className="h-4 w-4" strokeWidth={1.5} />
                )}
              </div>

              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="text-[9px] font-mono text-white/35">
                    {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span
                    className={cn(
                      "rounded-md border px-1.5 py-0.5 text-[7px] font-semibold uppercase tracking-[0.14em]",
                      activitySourceBadgeClass(event),
                    )}
                    title="Event source / mission family"
                  >
                    {activitySourceLabel(event)}
                  </span>
                  <span
                    className={cn(
                      "text-[9px] font-medium uppercase tracking-[0.08em]",
                      event.level === "info"
                        ? "text-sky-400/70"
                        : event.level === "warn"
                          ? "text-amber-400/70"
                          : "text-red-400/70",
                    )}
                  >
                    {event.type}
                  </span>
                  <span className="ml-auto text-[8px] font-mono text-white/15 opacity-0 transition-opacity group-hover:opacity-100">
                    {event.id}
                  </span>
                </div>
                <p className="text-[12px] font-normal leading-relaxed text-white/70 transition-colors group-hover:text-white/88">
                  {event.message}
                </p>
              </div>

              <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100">
                <ChevronRight className="h-4 w-4 text-white/30" strokeWidth={1.5} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
