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
    <div className="h-full flex flex-col bg-[#050505] font-sans">
      <div className="p-8 space-y-8 max-w-5xl mx-auto w-full">
        <div className="flex items-center justify-between border-b border-white/5 pb-6">
          <div className="space-y-1">
            <h1 className="text-xl font-black uppercase tracking-[0.2em] text-white">Workspace_Logs</h1>
            <p className="text-[10px] text-white/20 font-bold uppercase tracking-[0.3em] italic">
              Activity — Hermes gateway feed + demo fallback
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  source === "live" ? "bg-emerald-500 animate-pulse" : "bg-amber-500",
                )}
              />
              <span className="text-[10px] font-bold text-white/50 uppercase tracking-widest">
                {source === "live" ? "Gateway_Poll" : "Demo_Fallback"}
              </span>
            </div>
            <Link
              to="/command-center"
              className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
            >
              Command Center →
            </Link>
          </div>
        </div>

        {liveErr ? (
          <p className="text-[11px] text-amber-400/90 font-mono border border-amber-500/20 rounded-lg p-3">
            {liveErr}
          </p>
        ) : null}

        <div className="space-y-1">
          {events.map((event) => (
            <div
              key={event.id}
              className="group flex items-start gap-6 p-4 bg-[#080808] border border-white/[0.02] hover:border-white/10 transition-all"
            >
              <div
                className={cn(
                  "h-8 w-8 flex items-center justify-center shrink-0 border mt-0.5",
                  event.level === "info"
                    ? "bg-blue-500/10 text-blue-500 border-blue-500/20"
                    : event.level === "warn"
                      ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                      : "bg-red-500/10 text-red-500 border-red-500/20",
                )}
              >
                {event.level === "info" ? (
                  <Info className="h-4 w-4" />
                ) : event.level === "warn" ? (
                  <AlertTriangle className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
              </div>

              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-[9px] font-mono text-white/20">
                    {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span
                    className={cn(
                      "rounded border px-1.5 py-0.5 text-[7px] font-black uppercase tracking-widest",
                      activitySourceBadgeClass(event),
                    )}
                    title="Event source / mission family"
                  >
                    {activitySourceLabel(event)}
                  </span>
                  <span
                    className={cn(
                      "text-[9px] font-black uppercase tracking-widest",
                      event.level === "info"
                        ? "text-blue-500/60"
                        : event.level === "warn"
                          ? "text-amber-500/60"
                          : "text-red-500/60",
                    )}
                  >
                    {event.type}
                  </span>
                  <span className="ml-auto text-[8px] font-mono text-white/10 opacity-0 group-hover:opacity-100 transition-opacity">
                    UUID: {event.id}
                  </span>
                </div>
                <p className="text-[11px] font-bold text-white/60 group-hover:text-white transition-colors uppercase tracking-wider leading-relaxed">
                  {event.message}
                </p>
              </div>

              <div className="shrink-0 flex items-center opacity-0 group-hover:opacity-100 transition-all">
                <ChevronRight className="h-4 w-4 text-[#FF6B00]" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
