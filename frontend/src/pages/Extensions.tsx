import { MOCK_EXTENSIONS } from "@/lib/ham/mocks";
import { 
  Puzzle, 
  Search, 
  CheckCircle2, 
  ArrowUpRight, 
  Store, 
  Zap, 
  Shield, 
  Box,
  Cpu,
  MoreVertical,
  Plus
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function Extensions() {
  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto scrollbar-hide">
      <div className="p-8 space-y-12 max-w-6xl mx-auto w-full">
        {/* Workbench Module Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-8">
           <div className="space-y-4">
              <div className="flex items-center gap-4">
                 <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                    <Puzzle className="h-5 w-5 text-[#FF6B00]" />
                 </div>
                 <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">WORKSPACE / TOOLS</span>
              </div>
              <h1 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none">
                 Tools & <span className="text-[#FF6B00] not-italic">Extensions</span>
              </h1>
              <p className="text-sm font-bold text-white/20 max-w-xl uppercase tracking-widest leading-relaxed">
                 Extend your team's capabilities with specialized tools and marketplace extensions.
              </p>
           </div>
           
           <button className="flex items-center gap-3 px-8 py-4 bg-white text-black text-[11px] font-black uppercase tracking-[0.2em] hover:bg-[#FF6B00] transition-colors shadow-[8px_8px_0_rgba(255,107,0,0.5)] active:shadow-none translate-x-[-4px] translate-y-[-4px] active:translate-x-0 active:translate-y-0">
              <Plus className="h-5 w-5" />
              Browse Tools
           </button>
        </div>

        {/* Categories Bar */}
        <div className="flex items-center gap-6 overflow-x-auto pb-2 border-b border-white/[0.02]">
           {['All_Modules', 'Connectivity', 'Security', 'Intelli', 'Compute'].map((cat, i) => (
             <button key={cat} className={cn(
               "text-[9px] font-black uppercase tracking-[0.3em] whitespace-nowrap transition-colors",
               i === 0 ? "text-[#FF6B00]" : "text-white/20 hover:text-white"
             )}>
                {cat}
             </button>
           ))}
        </div>

        {/* Extensions Workbench Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
           {MOCK_EXTENSIONS.map((ext) => (
             <div 
               key={ext.id} 
               className={cn(
                 "group relative flex flex-col p-8 bg-[#0a0a0a] border transition-all duration-300",
                 ext.installed 
                   ? "border-white/5 hover:border-[#FF6B00]/40" 
                   : "border-dashed border-white/10 opacity-40 hover:opacity-100 hover:border-white/20"
               )}
             >
                <div className="flex justify-between items-start mb-8">
                   <div className={cn(
                     "h-12 w-12 border flex items-center justify-center transition-transform group-hover:scale-110",
                     ext.installed ? "bg-black border-white/20 text-white" : "bg-black/40 border-white/5 text-white/20"
                   )}>
                      {ext.category === 'Security' ? <Shield className="h-5 w-5" /> :
                       ext.category === 'Intelli' ? <Cpu className="h-5 w-5" /> :
                       <Box className="h-5 w-5" />}
                   </div>
                   <div className="flex flex-col items-end gap-1">
                      <span className="text-[8px] font-black uppercase tracking-widest text-white/20">{ext.category}</span>
                      {ext.installed && <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] shadow-[0_0_8px_#FF6B00]" />}
                   </div>
                </div>

                <div className="space-y-4 flex-1 mb-10">
                   <h3 className="text-xl font-black uppercase tracking-tighter text-white/90 group-hover:text-[#FF6B00] transition-colors">{ext.name}</h3>
                   <p className="text-[11px] font-bold text-white/30 tracking-widest leading-relaxed uppercase">
                      {ext.description}
                   </p>
                   <div className="flex flex-wrap gap-2 pt-2">
                      {ext.powers.map(power => (
                        <span key={power} className="text-[8px] font-mono text-white/20 px-2 py-0.5 border border-white/5 rounded">
                           {power.replace(' ', '_').toUpperCase()}
                        </span>
                      ))}
                   </div>
                </div>

                <div className="pt-6 border-t border-white/[0.04] flex items-center justify-between">
                   <div className="flex items-center gap-2">
                      <span className="text-[9px] font-mono text-white/20">v{ext.id.split('_').pop() || '1.0'}</span>
                   </div>
                   <button className={cn(
                     "px-6 py-2 text-[9px] font-black uppercase tracking-widest transition-all",
                     ext.installed ? "bg-white/5 text-white/40 hover:text-white" : "bg-[#FF6B00] text-black"
                   )}>
                      {ext.installed ? 'Config' : 'Inject'}
                   </button>
                </div>
             </div>
           ))}

           {/* Create Placeholder */}
           <div className="flex flex-col items-center justify-center p-8 border border-dashed border-white/5 bg-transparent hover:bg-white/[0.02] transition-all group cursor-pointer space-y-4 min-h-[300px]">
              <Plus className="h-8 w-8 text-white/10 group-hover:text-[#FF6B00] transition-colors" />
              <span className="text-[9px] font-black uppercase tracking-[0.4em] text-white/20">Build_Custom_Kernel</span>
           </div>
        </div>
      </div>
    </div>
  );
}
