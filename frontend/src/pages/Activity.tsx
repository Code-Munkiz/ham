import { MOCK_ACTIVITY } from "@/lib/ham/mocks";
import { activitySourceBadgeClass, activitySourceLabel } from "@/lib/ham/activityEventSource";
import { AlertCircle, Info, AlertTriangle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Activity() {
  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans">
      <div className="p-8 space-y-8 max-w-5xl mx-auto w-full">
        <div className="flex items-center justify-between border-b border-white/5 pb-6">
           <div className="space-y-1">
              <h1 className="text-xl font-black uppercase tracking-[0.2em] text-white">Workspace_Logs</h1>
              <p className="text-[10px] text-white/20 font-bold uppercase tracking-[0.3em] italic">Real-time activity and agent events</p>
           </div>
           <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                 <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] animate-pulse" />
                 <span className="text-[10px] font-bold text-[#FF6B00] uppercase tracking-widest">Live_Activity</span>
              </div>
           </div>
        </div>

        <div className="space-y-1">
           {MOCK_ACTIVITY.map((event) => (
             <div key={event.id} className="group flex items-start gap-6 p-4 bg-[#080808] border border-white/[0.02] hover:border-white/10 transition-all">
                <div className={cn(
                  "h-8 w-8 flex items-center justify-center shrink-0 border mt-0.5",
                  event.level === 'info' ? "bg-blue-500/10 text-blue-500 border-blue-500/20" :
                  event.level === 'warn' ? "bg-amber-500/10 text-amber-500 border-amber-500/20" :
                  "bg-red-500/10 text-red-500 border-red-500/20"
                )}>
                  {event.level === 'info' ? <Info className="h-4 w-4" /> : 
                   event.level === 'warn' ? <AlertTriangle className="h-4 w-4" /> :
                   <AlertCircle className="h-4 w-4" />}
                </div>
                
                <div className="flex-1 min-w-0 space-y-1">
                   <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="text-[9px] font-mono text-white/20">{new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}</span>
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-[7px] font-black uppercase tracking-widest",
                          activitySourceBadgeClass(event),
                        )}
                        title="Event source / mission family"
                      >
                        {activitySourceLabel(event)}
                      </span>
                      <span className={cn(
                        "text-[9px] font-black uppercase tracking-widest",
                        event.level === 'info' ? "text-blue-500/60" : 
                        event.level === 'warn' ? "text-amber-500/60" : "text-red-500/60"
                      )}>{event.type}</span>
                      <span className="ml-auto text-[8px] font-mono text-white/10 opacity-0 group-hover:opacity-100 transition-opacity">UUID: {event.id}</span>
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
