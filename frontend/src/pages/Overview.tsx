import { 
  Users, 
  MessageSquare, 
  ToyBrick, 
  Zap,
  Activity,
  ArrowUpRight,
  ChevronRight,
  ChevronLeft,
  Clock,
  CheckCircle2,
  AlertCircle,
  Play
} from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import * as React from "react";

const API_BASE = "http://localhost:8000";

interface Mission {
  id: string;
  title: string;
  droid: string;
  status: 'In Progress' | 'Completed' | 'Failed' | 'Paused';
  progress: number;
  timeElapsed: string;
  teamMember: string;
  category: string;
}

const MOCK_MISSIONS: Mission[] = [
  { id: "m1", title: "Refactor Authentication Middleware", droid: "Builder", status: "In Progress", progress: 65, timeElapsed: "21m", teamMember: "Aaron", category: "Core Development" },
  { id: "m2", title: "Security Audit: bridge-rpc service", droid: "Reviewer", status: "In Progress", progress: 12, timeElapsed: "8m", teamMember: "System", category: "Security" },
  { id: "m3", title: "Find alternative to ESM module loading issue", droid: "Researcher", status: "Completed", progress: 100, timeElapsed: "45m", teamMember: "Aaron", category: "Research" },
  { id: "m4", title: "Generate end-to-end tests for Profile flow", droid: "QA", status: "In Progress", progress: 42, timeElapsed: "1h 12m", teamMember: "QA Team", category: "Quality Assurance" },
  { id: "m5", title: "Decompose user request #882 into tasks", droid: "Coordinator", status: "Completed", progress: 100, timeElapsed: "5m", teamMember: "Manager", category: "Planning" },
  { id: "m6", title: "Audit dependency tree for CVE-2024-X", droid: "Reviewer", status: "Paused", progress: 5, timeElapsed: "2m", teamMember: "Aaron", category: "Security" },
  { id: "m7", title: "Performance Benchmarking: US-East-1 vs US-West-2", droid: "Researcher", status: "In Progress", progress: 88, timeElapsed: "3h 10m", teamMember: "DevOps", category: "Performance" },
  { id: "m8", title: "Implement dark mode theme synchronization", droid: "Builder", status: "Completed", progress: 100, timeElapsed: "2h 15m", teamMember: "Design Team", category: "UI/UX" },
];

export default function Overview() {
  const [currentPage, setCurrentPage] = React.useState(0);
  const [status, setStatus] = React.useState<{ run_count: number } | null>(null);
  const [statusLoading, setStatusLoading] = React.useState(true);
  const [statusError, setStatusError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const res = await fetch(`${API_BASE}/api/status`);
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

  const itemsPerPage = 5;
  const totalPages = Math.ceil(MOCK_MISSIONS.length / itemsPerPage);
  
  const currentMissions = MOCK_MISSIONS.slice(
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
                    {statusLoading ? (
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
                        <div className="px-3 py-1 bg-white/[0.04] border border-white/5 rounded text-[9px] font-black uppercase tracking-widest text-[#FF6B00] italic">Running 00</div>
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
              {currentMissions.map((mission) => (
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
                            </div>
                            <div className="text-right hidden sm:block shrink-0">
                               <p className="text-[10px] font-black text-white/40 uppercase tracking-widest italic">{mission.status}</p>
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
                                  {mission.status === 'In Progress' ? `Running: git diff --name-only [Segment_${mission.id}]` : `Finalized: Mission ${mission.id} lifecycle ended`}
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

        {/* Secondary Context */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8 border-t border-white/5">
           <div className="space-y-6">
              <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic">Team Jobs</h3>
              <div className="p-8 bg-[#0a0a0a] border border-white/5 rounded-xl space-y-6">
                 <div className="flex items-end justify-between gap-1 h-20">
                    {[45, 62, 38, 92, 55, 71, 85, 40, 66, 95].map((h, i) => (
                      <div key={i} className="flex-1 space-y-1">
                         <div 
                           className={cn(
                             "w-full rounded-t-sm transition-all duration-700",
                             i === 9 ? "bg-[#FF6B00] shadow-[0_0_10px_#FF6B00]" : "bg-white/10"
                           )} 
                           style={{ height: `${h}%` }} 
                         />
                      </div>
                    ))}
                 </div>
                 <div className="flex items-center justify-between border-t border-white/5 pt-4">
                    <div className="space-y-1">
                       <p className="text-[9px] font-black text-white/20 uppercase tracking-widest">Completed Jobs / Daily</p>
                       <p className="text-lg font-black text-white italic">24.5 Avg</p>
                    </div>
                    <div className="p-2 bg-green-500/10 rounded text-green-500 text-[9px] font-black uppercase tracking-widest">
                       +12.2% 
                    </div>
                 </div>
              </div>
           </div>

           <div className="space-y-6">
              <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic">Workforce Access</h3>
              <div className="space-y-4">
                 {[
                   { label: "Anthropic Integration", status: "Active", latency: "142ms" },
                   { label: "OpenAI Proxy", status: "Active", latency: "210ms" },
                   { label: "Perplexity Internal Search", status: "Wait", latency: "---" },
                 ].map((sys) => (
                   <div key={sys.label} className="flex items-center justify-between p-4 bg-[#0a0a0a] border border-white/5 hover:border-white/10 transition-colors">
                      <div className="flex items-center gap-3">
                         <div className={cn("h-1.5 w-1.5 rounded-full", sys.status === 'Active' ? 'bg-[#FF6B00]' : 'bg-red-500/20')} />
                         <span className="text-[11px] font-bold text-white uppercase tracking-widest">{sys.label}</span>
                      </div>
                      <div className="flex items-center gap-6">
                         <span className="text-[9px] font-mono text-white/10 italic">LTC: {sys.latency}</span>
                         <ChevronRight className="h-3 w-3 text-white/10" />
                      </div>
                   </div>
                 ))}
              </div>
           </div>
        </div>

      </div>
    </div>
  );
}
