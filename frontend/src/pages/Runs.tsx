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

const API_BASE = "http://localhost:8000";

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
        const res = await fetch(`${API_BASE}/api/runs?limit=50`);
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
    <div className="h-full flex flex-col bg-[#050505] font-sans">
      <div className="p-8 space-y-8 max-w-5xl mx-auto w-full">
        {/* Workspace Sub-Header */}
        <div className="flex items-center justify-between border-b border-white/5 pb-6">
           <div className="space-y-1">
              <h1 className="text-xl font-black uppercase tracking-[0.2em] text-white">Task_History</h1>
              <p className="text-[10px] text-white/20 font-bold uppercase tracking-[0.3em] italic">Comprehensive agent activity log</p>
           </div>
           <div className="flex items-center gap-4">
              <div className="relative group">
                 <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/20 group-focus-within:text-[#FF6B00] transition-colors" />
                 <input 
                    type="text" 
                    placeholder="Search history..." 
                    className="pl-10 h-10 w-64 bg-white/5 border border-white/10 rounded font-bold text-[10px] uppercase tracking-widest text-[#FF6B00] placeholder:text-white/10 focus:outline-none focus:border-[#FF6B00]/40 transition-all"
                 />
              </div>
           </div>
        </div>

        {loading && (
          <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse block">
            Loading...
          </span>
        )}
        {error && (
          <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest block">
            {error}
          </span>
        )}

        {/* Audit Log Table-ish Interface */}
        <div className="space-y-px bg-white/5 border border-white/5">
           {!loading && !error && runs.length === 0 && (
             <div className="p-8 bg-[#080808] text-[10px] font-black uppercase tracking-widest text-white/30">
               No runs recorded yet.
             </div>
           )}
           {runs.map((run) => (
             <div key={run.run_id} className="group grid grid-cols-12 items-center bg-[#080808] hover:bg-white/[0.04] transition-colors border-b border-white/[0.02]">
                <div className="col-span-1 p-4 flex justify-center">
                   <div className={cn(
                     "h-2 w-2 rounded-full",
                     isBridgeSuccess(run.bridge_result) ? "bg-green-500/40 shadow-[0_0_8px_rgba(34,197,94,0.4)]" : "bg-red-500/40 shadow-[0_0_8px_rgba(239,68,68,0.4)]"
                   )} />
                </div>
                
                <div className="col-span-2 p-4 border-l border-white/[0.02]">
                   <span className="text-[10px] font-mono text-white/20 group-hover:text-white/40 transition-colors">#{run.run_id.toUpperCase()}</span>
                </div>

                <div className="col-span-4 p-4 border-l border-white/[0.02]">
                   <div className="flex flex-col">
                      <span className="text-[11px] font-bold text-white/60 group-hover:text-[#FF6B00] transition-colors uppercase tracking-widest">{run.profile_id}</span>
                      <span className="text-[9px] text-white/20 truncate italic">"{run.prompt_summary}"</span>
                   </div>
                </div>

                <div className="col-span-2 p-4 border-l border-white/[0.02]">
                   <div className="flex items-center gap-2">
                      <Terminal className="h-3 w-3 text-white/20" />
                      <span className="text-[10px] font-bold text-white/40 group-hover:text-white/60 transition-colors uppercase tracking-tighter truncate">{run.backend_id}</span>
                   </div>
                </div>

                <div className="col-span-2 p-4 border-l border-white/[0.02]">
                   <div className="flex items-center gap-2">
                      <User className="h-3 w-3 text-white/10" />
                      <span className="text-[9px] font-bold text-white/30 uppercase tracking-widest">{run.author ?? 'unknown'}</span>
                   </div>
                </div>

                <div className="col-span-1 p-4 border-l border-white/[0.02] flex justify-center text-white/10 group-hover:text-[#FF6B00] transition-colors cursor-pointer">
                   <ArrowUpRight className="h-4 w-4" />
                </div>
             </div>
           ))}
        </div>

        {/* Load More Utility */}
        <div className="flex items-center justify-center pt-12">
           <button className="flex items-center gap-3 px-8 py-3 bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.3em] text-white/40 hover:text-[#FF6B00] hover:border-[#FF6B00]/40 transition-all italic">
              <Activity className="h-4 w-4" />
              Fetch_Older_Records
           </button>
        </div>
      </div>
    </div>
  );
}
