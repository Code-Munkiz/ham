/**
 * Read-only view of HAM control-plane runs (Cursor Cloud Agent + Factory Droid launches).
 * This is not mission orchestration, queues, or graphs — only what HAM already recorded.
 */
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { Layers, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl } from "@/lib/ham/api";
import type { ControlPlaneRunPublic } from "@/lib/ham/types";

export default function ControlPlaneRuns() {
  const [params, setParams] = useSearchParams();
  const fromQuery = (params.get("project_id") || "").trim();
  const [projectId, setProjectId] = React.useState(fromQuery);
  const [inputId, setInputId] = React.useState(fromQuery);
  const [runs, setRuns] = React.useState<ControlPlaneRunPublic[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState<Record<string, boolean>>({});

  const load = React.useCallback(
    async (idRaw?: string) => {
      const id = (idRaw ?? inputId).trim();
      if (!id) {
        setError("Enter a registered project_id (e.g. from Chat workspace context).");
        setRuns([]);
        return;
      }
      setInputId(id);
      setLoading(true);
      setError(null);
      setParams({ project_id: id });
      try {
        const url = new URL(apiUrl("/api/control-plane-runs"));
        url.searchParams.set("project_id", id);
        url.searchParams.set("limit", "50");
        const res = await fetch(url.toString());
        if (res.status === 404) {
          const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
          const d = body.detail;
          const errObj =
            typeof d === "object" && d !== null && "error" in d
              ? (d as { error?: { message?: string } }).error
              : null;
          const msg = (errObj?.message as string) || (typeof d === "string" ? d : "Project not found.");
          setError(msg);
          setRuns([]);
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { runs?: ControlPlaneRunPublic[] };
        setRuns(body.runs ?? []);
        setProjectId(id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Request failed");
        setRuns([]);
      } finally {
        setLoading(false);
      }
    },
    [inputId, setParams],
  );

  const initialLoaded = React.useRef(false);
  React.useEffect(() => {
    if (initialLoaded.current) return;
    if (fromQuery) {
      initialLoaded.current = true;
      void load(fromQuery);
    }
  }, [fromQuery, load]);

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto">
      <div className="p-8 space-y-6 max-w-5xl mx-auto w-full">
        <div className="border-b border-white/5 pb-6 space-y-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
              <Layers className="h-4 w-4 text-[#FF6B00]" />
            </div>
            <div>
              <h1 className="text-xl font-black uppercase tracking-[0.2em] text-white">Control-plane runs</h1>
              <p className="text-[10px] text-white/35 font-bold uppercase tracking-widest mt-1 max-w-xl leading-relaxed">
                Recent launches recorded by HAM (Cursor Cloud Agent and Factory Droid). This is not a mission graph,
                queue, or orchestration view — only what HAM started and last observed.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="text-[9px] font-black text-white/30 uppercase tracking-widest block mb-1.5">
              project_id
            </label>
            <input
              type="text"
              value={inputId}
              onChange={(e) => setInputId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void load()}
              placeholder="project.…"
              className="w-full h-10 px-3 bg-white/5 border border-white/10 rounded font-mono text-[11px] text-white/80 placeholder:text-white/20 focus:outline-none focus:border-[#FF6B00]/40"
            />
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="h-10 px-5 bg-[#FF6B00]/20 border border-[#FF6B00]/30 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] rounded hover:bg-[#FF6B00]/30 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load"}
          </button>
        </div>

        {error && (
          <p className="text-[10px] font-bold text-red-500/90 uppercase tracking-widest" role="alert">
            {error}
          </p>
        )}

        {projectId && !error && !loading && runs.length === 0 && (
          <p className="text-[10px] text-white/30 font-mono">No control-plane runs for this project yet.</p>
        )}

        <div className="space-y-px bg-white/5 border border-white/5">
          {runs.map((r) => {
            const isOpen = open[r.ham_run_id] ?? false;
            return (
              <div
                key={r.ham_run_id}
                className="bg-[#080808] border-b border-white/[0.02] last:border-b-0"
              >
                <button
                  type="button"
                  onClick={() =>
                    setOpen((o) => ({ ...o, [r.ham_run_id]: !isOpen }))
                  }
                  className="w-full text-left p-4 flex items-start gap-3 hover:bg-white/[0.04] transition-colors"
                >
                  <div className="pt-0.5 text-white/30">
                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="text-[10px] font-mono text-[#FF6B00]/80">{r.ham_run_id}</span>
                      <span className="text-[9px] font-black uppercase tracking-widest text-white/40">
                        {r.provider}
                      </span>
                      <span
                        className={cn(
                          "text-[9px] font-black uppercase px-2 py-0.5 rounded border",
                          r.status === "succeeded" && "text-green-500/90 border-green-500/30",
                          r.status === "failed" && "text-red-500/90 border-red-500/30",
                          r.status === "running" && "text-amber-500/90 border-amber-500/30",
                          (r.status === "unknown" || !["succeeded", "failed", "running"].includes(r.status)) &&
                            "text-white/50 border-white/20",
                        )}
                      >
                        {r.status}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/55 line-clamp-2">{r.summary || r.error_summary || "—"}</p>
                    <p className="text-[9px] font-mono text-white/25">
                      updated {r.updated_at}
                      {r.external_id ? ` · external ${r.external_id}` : ""}
                    </p>
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pl-12 space-y-2 text-[9px] font-mono text-white/40 border-t border-white/[0.04]">
                    <div>status_reason: {r.status_reason}</div>
                    {r.workflow_id && <div>workflow_id: {r.workflow_id}</div>}
                    {r.last_provider_status && <div>last_provider_status: {r.last_provider_status}</div>}
                    <div>created_at: {r.created_at}</div>
                    <div>committed_at: {r.committed_at}</div>
                    <div>started_at: {r.started_at ?? "—"}</div>
                    <div>finished_at: {r.finished_at ?? "—"}</div>
                    <div>last_observed_at: {r.last_observed_at ?? "—"}</div>
                    {r.audit_ref && (
                      <pre className="text-[8px] text-white/30 whitespace-pre-wrap break-all mt-2 p-2 bg-black/30 rounded">
                        {JSON.stringify(r.audit_ref, null, 2)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
