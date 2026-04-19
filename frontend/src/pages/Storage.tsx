import { MOCK_BACKENDS } from "@/lib/ham/mocks";
import { 
  Database, 
  Cpu, 
  CheckCircle2, 
  Lock,
  Plus,
  ArrowUpRight,
  Server,
  Network
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function Storage() {
  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto">
      <div className="p-8 space-y-12 max-w-6xl mx-auto w-full">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-8">
           <div className="space-y-4">
              <div className="flex items-center gap-4">
                 <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                    <Database className="h-5 w-5 text-[#FF6B00]" />
                 </div>
                 <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">CONNECTIONS / STORAGE</span>
              </div>
              <h1 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none">
                 Connected <span className="text-[#FF6B00] not-italic">Systems</span>
              </h1>
              <p className="text-sm font-bold text-white/20 max-w-xl uppercase tracking-widest leading-relaxed">
                 Manage storage nodes and connected cloud environments for your team.
              </p>
           </div>
           
           <button className="flex items-center gap-3 px-8 py-4 bg-white/5 border border-white/10 text-white/20 text-[11px] font-black uppercase tracking-[0.2em] cursor-not-allowed opacity-40">
              <Plus className="h-5 w-5" />
              Connect_New_System
           </button>
        </div>

        <div className="space-y-4">
           {MOCK_BACKENDS.map((backend) => (
             <div 
               key={backend.id} 
               className="group flex flex-col md:flex-row bg-[#0a0a0a] border border-white/5 hover:border-[#FF6B00]/40 transition-all duration-300 relative overflow-hidden"
             >
                <div className="p-8 md:w-80 border-b md:border-b-0 md:border-r border-white/[0.04] space-y-6">
                   <div className="flex items-center gap-4">
                      <div className="h-12 w-12 border border-white/20 bg-black flex items-center justify-center text-white/60">
                         <Database className="h-6 w-6" />
                      </div>
                      <div>
                         <h3 className="text-lg font-black text-white group-hover:text-[#FF6B00] transition-colors leading-none uppercase italic">{backend.display_name}</h3>
                         <span className="text-[9px] font-mono text-white/20 mt-1 block uppercase tracking-widest">v{backend.version}</span>
                      </div>
                   </div>
                   {backend.is_default && (
                      <div className="inline-block px-3 py-1 bg-[#FF6B00]/10 border border-[#FF6B00]/40 text-[#FF6B00] text-[8px] font-black uppercase tracking-widest">
                         [ PRIMARY_STORAGE ]
                      </div>
                   )}
                </div>

                <div className="flex-1 p-8 grid grid-cols-2 lg:grid-cols-4 gap-8">
                   {[
                     { icon: CheckCircle2, label: "Status", val: "Operational" },
                     { icon: Cpu, label: "Efficiency", val: "Optimized" },
                     { icon: Lock, label: "Secured", val: "AES-256" },
                     { icon: Network, label: "Relay", val: "RPC_v1" },
                   ].map(stat => (
                     <div key={stat.label} className="space-y-2">
                        <div className="flex items-center gap-2 text-[9px] font-black text-white/20 uppercase tracking-widest">
                           <stat.icon className="h-3 w-3" />
                           {stat.label}
                        </div>
                        <p className="text-[11px] font-bold text-white/60 uppercase tracking-tighter">{stat.val}</p>
                     </div>
                   ))}
                </div>

                <div className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e]" />
             </div>
           ))}
        </div>
      </div>
    </div>
  );
}
