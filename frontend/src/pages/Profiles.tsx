import { MOCK_PROFILES } from "@/lib/ham/mocks";
import { 
  Plus, 
  Search, 
  Layers, 
  ShieldCheck,
  ChevronRight,
  Zap
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function Profiles() {
  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto">
      <div className="p-8 space-y-12 max-w-6xl mx-auto w-full">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-8">
           <div className="space-y-4">
              <div className="flex items-center gap-4">
                 <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                    <Layers className="h-5 w-5 text-[#FF6B00]" />
                 </div>
                 <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">TEAM / PROFILES</span>
              </div>
              <h1 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none">
                 Team <span className="text-[#FF6B00] not-italic">Profiles</span>
              </h1>
              <p className="text-sm font-bold text-white/20 max-w-xl uppercase tracking-widest leading-relaxed">
                 Configure pre-defined agent roles and shared team capabilities.
              </p>
           </div>
           
           <button className="flex items-center gap-3 px-8 py-4 bg-white/5 border border-white/10 text-white/20 text-[11px] font-black uppercase tracking-[0.2em] cursor-not-allowed opacity-40">
              <Plus className="h-5 w-5" />
              Add_New_Profile
           </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
           {MOCK_PROFILES.map((profile) => (
             <div 
               key={profile.id} 
               className="group relative flex flex-col p-8 bg-[#0a0a0a] border border-white/5 hover:border-[#FF6B00]/40 transition-all duration-300"
             >
                <div className="flex justify-between items-start mb-8">
                   <div className="h-12 w-12 border border-white/20 bg-black flex items-center justify-center text-[#FF6B00] group-hover:scale-110 transition-transform">
                      <Layers className="h-5 w-5" />
                   </div>
                   <span className="text-[9px] font-mono text-white/20">V{profile.version}</span>
                </div>

                <div className="space-y-4 flex-1 mb-8">
                   <h3 className="text-lg font-black uppercase tracking-widest text-[#FF6B00]">{profile.id}</h3>
                   <p className="text-[11px] font-bold text-white/30 tracking-widest leading-relaxed uppercase italic">
                      {profile.description}
                   </p>
                </div>

                <div className="pt-6 border-t border-white/[0.04] space-y-4">
                   <div className="flex justify-between text-[8px] font-black uppercase tracking-widest text-white/40 italic">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="h-3 w-3 text-green-500/60" />
                        Verified
                      </div>
                      <div className="flex items-center gap-2">
                        <Zap className="h-3 w-3 text-amber-500/60" />
                        Production
                      </div>
                   </div>
                   <div className="flex flex-wrap gap-2">
                      {(profile.metadata.tags as string[] || []).map(tag => (
                        <span key={tag} className="text-[8px] font-mono text-white/10 bg-white/[0.02] px-2 py-0.5 border border-white/5 rounded lowercase">
                           #{tag}
                        </span>
                      ))}
                   </div>
                </div>
             </div>
           ))}
        </div>
      </div>
    </div>
  );
}
