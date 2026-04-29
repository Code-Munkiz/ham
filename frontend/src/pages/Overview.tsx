import {
  Users,
  MessageSquare,
  Activity,
  ArrowUpRight,
  ChevronRight,
  ChevronLeft,
  Clock,
  CheckCircle2,
  AlertCircle,
  Play,
} from "lucide-react";
import { cn } from "@/lib/utils";
import * as React from "react";

import { apiUrl, fetchManagedMissionsList, type ManagedMissionRow } from "@/lib/ham/api";

interface Mission {
  id: string;
  title: string;
  droid: string; // existing UI label; now mapped from mission source
  status: 'In Progress' | 'Completed' | 'Failed' | 'Paused';
  progress: number;
  timeElapsed: string;
  teamMember: string;
  category: string;
  repo: string;
  ref: string;
  prUrl: string | null;
  updatedAt: string | null;
  checkpoint: string | null;
}

function mapLifecycleToCardStatus(row: ManagedMissionRow): Mission["status"] {
  const lc = (row.mission_lifecycle || "").trim().toLowerCase();
  if (lc === "succeeded") return "Completed";
  if (lc === "failed") return "Failed";
  if (lc === "archived") return "Paused";
  return "In Progress";
}

function mapCheckpointProgress(row: ManagedMissionRow): number {
  const cp = (row.latest_checkpoint || "").trim().toLowerCase();
  if (!cp) return 10;
  if (cp === "queued") return 10;
  if (cp === "launched") return 25;
  if (cp === "running") return 55;
  if (cp === "blocked") return 45;
  if (cp === "pr_opened") return 80;
  if (cp === "completed") return 100;
  if (cp === "failed") return 100;
  return 15;
}

function formatCheckpointLabel(raw: string | null): string | null {
  const t = (raw || "").trim();
  if (!t) return null;
  return t.replace(/_/g, " ");
}

function mapMissionTitle(row: ManagedMissionRow): string {
  const checkpoint = (row.latest_checkpoint || "").trim().replace(/_/g, " ");
  const repo = (row.repo_key || row.repository_observed || "managed mission").trim();
  if (checkpoint) return `${repo} · ${checkpoint}`;
  return repo;
}

function toMissionCard(row: ManagedMissionRow): Mission {
  const id = (row.mission_registry_id || row.cursor_agent_id || "mission").trim();
  const status = mapLifecycleToCardStatus(row);
  const updated = (row.last_server_observed_at || row.updated_at || "").trim() || null;
  const repo = (row.repo_key || row.repository_observed || "—").trim();
  const ref = (row.ref_observed || "—").trim();
  return {
    id,
    title: mapMissionTitle(row),
    droid: "Cloud Agent",
    status,
    progress: mapCheckpointProgress(row),
    timeElapsed: updated ? "server-observed" : "—",
    teamMember: "HAM",
    category: "Managed Mission",
    repo,
    ref,
    prUrl: row.pr_url_last_observed?.trim() || null,
    updatedAt: updated,
    checkpoint: row.latest_checkpoint?.trim() || null,
  };
}

export default function Overview() {
  const [currentPage, setCurrentPage] = React.useState(0);
  const [status, setStatus] = React.useState<{ run_count: number } | null>(null);
  const [statusLoading, setStatusLoading] = React.useState(true);
  const [statusError, setStatusError] = React.useState<string | null>(null);
  const [managedMissions, setManagedMissions] = React.useState<Mission[]>([]);
  const [missionsLoading, setMissionsLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const res = await fetch(apiUrl("/api/status"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { version?: string; run_count: number };
        if (!cancelled) setStatus({ run_count: data.run_count });
      } catch (e) {
        if (!cancelled)
          setStatusError(e instanceof Error ? e.message : "Request failed");
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    setMissionsLoading(true);
    void fetchManagedMissionsList(120)
      .then((rows) => {
        if (cancelled) return;
        setManagedMissions(rows.map(toMissionCard));
        setCurrentPage(0);
      })
      .catch(() => {
        if (!cancelled) setManagedMissions([]);
      })
      .finally(() => {
        if (!cancelled) setMissionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const itemsPerPage = 5;
  const totalPages = Math.max(1, Math.ceil(managedMissions.length / itemsPerPage));
  
  const currentMissions = managedMissions.slice(
    currentPage * itemsPerPage, 
    (currentPage + 1) * itemsPerPage
  );

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto overflow-x-hidden">
      <div className="p-8 pb-20 space-y-12 max-w-6xl mx-auto w-full animate-in fade-in duration-700">
        
        {/* Page Header */}
        <div className="flex items-center justify-between gap-8 border-b border-white/5 pb-8">
           <div className="flex items-center gap-6">
              <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20 shrink-0">
                 <Activity className="h-4 w-4 text-[#FF6B00]" />
              </div>
              <div className="flex items-center gap-4">
                 <h1 className="text-3xl font-black text-white italic tracking-tighter uppercase leading-none">
                    Live <span className="text-[#FF6B00] not-italic">Activity</span>
                 </h1>
                 <div className="flex gap-4">
                    {statusLoading || missionsLoading ? (
                      <>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-[#FF6B00] italic flex items-center">
                          <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
                        </div>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-white/40 italic flex items-center">
                          <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
                        </div>
                      </>
                    ) : statusError ? (
                      <>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-red-500/80 italic">
                          {statusError}
                        </div>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-white/40 italic">—</div>
                      </>
                    ) : (
                      <>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-[#FF6B00] italic">Running {managedMissions.filter((m) => m.status === "In Progress").length}</div>
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-white/40 italic">Completed {status?.run_count ?? 0}</div>
                      </>
                    )}
                 </div>
              </div>
           </div>
           <p className="hidden md:block text-[10px] font-medium text-white/20 uppercase tracking-widest italic">Monitoring real-time droid workforce segments</p>
        </div>

        {/* Missions / Jobs Surface */}
        <div className="space-y-6">
           <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                 <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic underline decoration-[#FF6B00]/40 decoration-2 underline-offset-8">Running Missions Now</h3>
              </div>
              
              <div className="flex items-center gap-4">
                 <span className="text-[10px] font-black text-white/20 uppercase tracking-widest italic">Page {currentPage + 1} of {totalPages}</span>
                 <div className="flex gap-2">
                    <button 
                      onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                      disabled={currentPage === 0}
                      className={cn(
                        "p-2 border border-white/10 rounded transition-all",
                        currentPage === 0 ? "opacity-20 cursor-not-allowed" : "hover:border-[#FF6B00]/40 hover:text-[#FF6B00] text-white/40"
                      )}
                    >
                       <ChevronLeft className="h-4 w-4" />
                    </button>
                    <button 
                      onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                      disabled={currentPage === totalPages - 1}
                      className={cn(
                        "p-2 border border-white/10 rounded transition-all",
                        currentPage === totalPages - 1 ? "opacity-20 cursor-not-allowed" : "hover:border-[#FF6B00]/40 hover:text-[#FF6B00] text-white/40"
                      )}
                    >
                       <ChevronRight className="h-4 w-4" />
                    </button>
                 </div>
              </div>
           </div>

           <div className="grid grid-cols-1 gap-px bg-white/5 border border-white/5 rounded-lg overflow-hidden shadow-2xl">
              {missionsLoading ? (
                <div className="bg-[#080808] p-6 text-[11px] text-white/45 uppercase tracking-widest">Loading managed mission history…</div>
              ) : currentMissions.length === 0 ? (
                <div className="bg-[#080808] p-6 text-[11px] text-white/45 uppercase tracking-widest">No managed missions recorded on this API host yet.</div>
              ) : currentMissions.map((mission) => (
                <div key={mission.id} className="bg-[#080808] hover:bg-white/[0.04] p-6 transition-all group border-b border-white/[0.02] last:border-b-0">
                   <div className="flex flex-col md:flex-row md:items-center gap-6">
                      
                      {/* Status Icon */}
                      <div className="shrink-0">
                         <div className={cn(
                           "h-14 w-14 border flex items-center justify-center rounded-lg transition-transform group-hover:scale-105",
                           mission.status === 'In Progress' ? "bg-[#FF6B00]/5 border-[#FF6B00]/20 text-[#FF6B00]" : 
                           mission.status === 'Completed' ? "bg-green-500/5 border-green-500/20 text-green-500" :
                           mission.status === 'Failed' ? "bg-red-500/5 border-red-500/20 text-red-500" : 
                           "bg-white/5 border-white/10 text-white/40"
                         )}>
                            {mission.status === 'In Progress' ? <Play className="h-6 w-6 fill-[#FF6B00]" /> : 
                             mission.status === 'Completed' ? <CheckCircle2 className="h-6 w-6" /> :
                             mission.status === 'Failed' ? <AlertCircle className="h-6 w-6" /> : 
                             <Clock className="h-6 w-6" />}
                         </div>
                      </div>

                      {/* Main Details */}
                      <div className="flex-1 space-y-3 min-w-0">
                         <div className="flex items-start justify-between gap-4">
                            <div className="space-y-1">
                               <div className="flex items-center gap-2">
                                  <span className="text-[9px] font-black text-[#FF6B00]/60 uppercase tracking-widest">{mission.category}</span>
                                  <span className="text-white/10 text-[9px] uppercase font-bold">•</span>
                                  <span className="text-[9px] font-black text-white/20 uppercase tracking-widest">ID: {mission.id.toUpperCase()}</span>
                               </div>
                               <h4 className="text-lg font-black text-white uppercase italic tracking-wider leading-tight group-hover:text-[#FF6B00] transition-colors">{mission.title}</h4>
                               <p className="text-[9px] text-white/35 mt-1 font-mono">repo: {mission.repo} · ref: {mission.ref}</p>
                               {mission.prUrl ? (
                                 <a
                                   href={mission.prUrl}
                                   target="_blank"
                                   rel="noreferrer"
                                   className="text-[9px] text-[#00E5FF] underline underline-offset-2 break-all"
                                 >
                                   {mission.prUrl}
                                 </a>
                               ) : null}
                               {mission.updatedAt ? (
                                 <p className="text-[8px] text-white/25 mt-1">Last observed: {mission.updatedAt}</p>
                               ) : null}
                            </div>
                            <div className="text-right hidden sm:block shrink-0">
                               <p className="text-[10px] font-black text-white/40 uppercase tracking-widest italic">{mission.status}</p>
                               {formatCheckpointLabel(mission.checkpoint) ? (
                                 <p className="text-[8px] font-mono text-cyan-300/80 uppercase tracking-widest mt-1">
                                   {formatCheckpointLabel(mission.checkpoint)}
                                 </p>
                               ) : null}
                               <p className="text-[14px] font-black text-white tabular-nums">{mission.progress}%</p>
                            </div>
                         </div>

                         {/* Progress Bar */}
                         <div className="space-y-2">
                            <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                               <div 
                                 className={cn(
                                   "h-full transition-all duration-1000",
                                   mission.status === 'In Progress' ? "bg-[#FF6B00] shadow-[0_0_10px_#FF6B00]" : 
                                   mission.status === 'Completed' ? "bg-green-500" :
                                   mission.status === 'Failed' ? "bg-red-500" : "bg-white/20"
                                 )}
                                 style={{ width: `${mission.progress}%` }}
                               />
                            </div>
                            <div className="flex items-center justify-between text-[8px] font-black uppercase tracking-widest text-white/20">
                               <div className="flex items-center gap-3">
                                  <div className="flex items-center gap-1.5 hover:text-white transition-colors cursor-default">
                                     <Users className="h-3 w-3" />
                                     <span>{mission.droid}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5 hover:text-white transition-colors cursor-default">
                                     <MessageSquare className="h-3 w-3" />
                                     <span>{mission.teamMember}</span>
                                  </div>
                               </div>
                               <div className="flex items-center gap-1.5">
                                  <Clock className="h-3 w-3" />
                                  <span>{mission.timeElapsed}</span>
                               </div>
                            </div>
                            <div className="pt-2 border-t border-white/[0.02] flex items-center gap-2">
                               <span className="h-1 w-1 bg-[#FF6B00] rounded-full animate-pulse" />
                               <span className="text-[8px] font-mono text-white/10 uppercase tracking-widest italic group-hover:text-white/30 transition-colors">
                                  {mission.status === 'In Progress' ? `Running: managed mission ${mission.id}` : `Finalized: Mission ${mission.id} lifecycle ended`}
                               </span>
                            </div>
                         </div>
                      </div>

                      {/* Action */}
                      <div className="hidden lg:block shrink-0 pl-4 border-l border-white/5">
                         <button className="h-10 w-10 flex items-center justify-center text-white/20 hover:text-white hover:bg-white/5 transition-all rounded">
                            <ArrowUpRight className="h-5 w-5" />
                         </button>
                      </div>
                   </div>
                </div>
              ))}
           </div>
        </div>

      </div>
    </div>
  );
}
