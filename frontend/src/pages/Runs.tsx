// import { MOCK_RUNS } from "@/lib/ham/mocks"; // fallback: restore and swap `runs` → MOCK_RUNS
import * as React from "react";
import { type RunRecord, isBridgeSuccess } from "@/lib/ham/types";
import { 
  Search, 
  Terminal,
  Activity,
  ArrowUpRight,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { apiUrl } from "@/lib/ham/api";

export default function Runs() {
  const [runs, setRuns] = React.useState<RunRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(apiUrl("/api/runs?limit=50"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { runs: RunRecord[] };
        if (!cancelled) setRuns(body.runs ?? []);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[#02080c] font-sans text-[#e8eef8]">
      <div className="mx-auto flex w-full max-w-5xl min-h-0 flex-1 flex-col space-y-6 overflow-y-auto p-6 sm:p-8">
        <div className="flex flex-col gap-4 border-b border-[color:var(--ham-workspace-line)] pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h1 className="text-lg font-semibold tracking-tight text-white/95">Run history</h1>
            <p className="text-[11px] font-normal leading-relaxed text-white/40">
              Comprehensive agent run log — from <span className="font-mono text-white/50">GET /api/runs</span>.
            </p>
          </div>
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30"
              strokeWidth={1.5}
            />
            <input
              type="text"
              placeholder="Search history..."
              className="h-9 w-full rounded-lg border border-[color:var(--ham-workspace-line)] bg-black/30 pl-9 pr-3 text-[11px] text-white/60 placeholder:text-white/28 focus:outline-none focus:ring-1 focus:ring-white/10"
            />
          </div>
        </div>

        {loading && (
          <p className="text-[12px] font-medium text-white/40 animate-pulse">Loading runs…</p>
        )}
        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12px] text-red-200/90">
            {error}
          </p>
        )}

        <div className="overflow-hidden rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/40">
          {!loading && !error && runs.length === 0 && (
            <div className="p-8 text-center text-[12px] text-white/38">No runs recorded yet.</div>
          )}
          {runs.map((run) => (
            <div
              key={run.run_id}
              className="group grid grid-cols-12 items-center border-b border-[color:var(--ham-workspace-line)] bg-[#040d14]/30 transition-colors last:border-b-0 hover:bg-[#040d14]/55"
            >
              <div className="col-span-1 flex justify-center p-3 sm:p-4">
                <div
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    isBridgeSuccess(run.bridge_result)
                      ? "bg-emerald-400/80 shadow-[0_0_6px_rgba(16,185,129,0.35)]"
                      : "bg-red-400/80 shadow-[0_0_6px_rgba(248,113,113,0.3)]",
                  )}
                />
              </div>

              <div className="col-span-2 border-l border-[color:var(--ham-workspace-line)] p-3 sm:p-4">
                <span className="text-[10px] font-mono text-white/45 transition-colors group-hover:text-white/65">
                  #{run.run_id.toUpperCase()}
                </span>
              </div>

              <div className="col-span-4 border-l border-[color:var(--ham-workspace-line)] p-3 sm:p-4">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-[12px] font-medium text-white/80 transition-colors group-hover:text-white">
                    {run.profile_id}
                  </span>
                  <span className="truncate text-[10px] text-white/35">{run.prompt_summary}</span>
                </div>
              </div>

              <div className="col-span-2 border-l border-[color:var(--ham-workspace-line)] p-3 sm:p-4">
                <div className="flex min-w-0 items-center gap-2">
                  <Terminal className="h-3.5 w-3.5 shrink-0 text-white/25" strokeWidth={1.5} />
                  <span className="truncate text-[10px] text-white/45 transition-colors group-hover:text-white/65">
                    {run.backend_id}
                  </span>
                </div>
              </div>

              <div className="col-span-2 border-l border-[color:var(--ham-workspace-line)] p-3 sm:p-4">
                <div className="flex items-center gap-2">
                  <User className="h-3.5 w-3.5 text-white/22" strokeWidth={1.5} />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-white/40">
                    {run.author ?? "unknown"}
                  </span>
                </div>
              </div>

              <div className="col-span-1 flex justify-center p-3 text-white/20 transition-colors sm:p-4 group-hover:text-[#ffb27a]/80">
                <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-center pt-4">
          <button
            type="button"
            className="flex items-center gap-2 rounded-lg border border-[color:var(--ham-workspace-line)] bg-white/[0.03] px-5 py-2.5 text-[10px] font-medium uppercase tracking-[0.12em] text-white/40 transition-colors hover:border-white/15 hover:bg-white/[0.05] hover:text-white/60"
          >
            <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
            Load older
          </button>
        </div>
      </div>
    </div>
  );
}
