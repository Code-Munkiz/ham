import * as React from "react";
import { UserCircle, Palette, Sparkles, Wand2, Shield, Camera } from "lucide-react";

export default function Avatar() {
  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto">
      <div className="p-12 space-y-16 max-w-5xl mx-auto w-full animate-in fade-in duration-700">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-10">
           <div className="space-y-4">
              <div className="flex items-center gap-4">
                 <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                    <UserCircle className="h-5 w-5 text-[#FF6B00]" />
                 </div>
                 <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">IDENTITY / AVATAR</span>
              </div>
              <h1 className="text-5xl font-black text-white italic tracking-tighter uppercase leading-none">
                 Your <span className="text-[#FF6B00] not-italic">Avatar</span>
              </h1>
              <p className="text-sm font-bold text-white/20 max-w-xl uppercase tracking-widest leading-relaxed">
                 Customize your digital presence. Design styles, appearance modes, and saved identities for cross-system interaction.
              </p>
           </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            <div className="space-y-8">
               <div className="aspect-square bg-[#0a0a0a] border border-white/5 rounded-3xl flex items-center justify-center relative overflow-hidden group">
                  <img 
                    src="https://picsum.photos/seed/avatar-ham/800/800" 
                    alt="Avatar Large" 
                    className="w-full h-full object-cover opacity-60 group-hover:scale-110 transition-transform duration-1000 grayscale group-hover:grayscale-0"
                    referrerPolicy="no-referrer"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />
                  <div className="absolute bottom-8 left-8">
                     <p className="text-[10px] font-black text-white/20 uppercase tracking-[0.4em] mb-2">Current Identity</p>
                     <p className="text-2xl font-black text-white uppercase italic tracking-tighter">AARON_BUNDY_V2</p>
                  </div>
                  <button className="absolute top-8 right-8 p-3 bg-white/10 hover:bg-[#FF6B00] text-white rounded-full transition-all group-hover:shadow-[0_0_20px_#FF6B00]">
                     <Camera className="h-5 w-5" />
                  </button>
               </div>

               <div className="grid grid-cols-3 gap-4">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="aspect-square bg-white/[0.02] border border-white/5 rounded-xl hover:border-[#FF6B00]/40 transition-all cursor-pointer overflow-hidden">
                       <img src={`https://picsum.photos/seed/avatar-${i}/200/200`} className="w-full h-full object-cover opacity-20 hover:opacity-100 transition-opacity grayscale hover:grayscale-0" referrerPolicy="no-referrer" />
                    </div>
                  ))}
               </div>

               <div className="space-y-6 pt-8">
                  <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic underline decoration-[#FF6B00]/40 decoration-2 underline-offset-8">Personal Persona Builder</h3>
                  <div className="space-y-6 bg-[#0a0a0a] border border-white/5 p-8 rounded-2xl">
                    <div className="space-y-4">
                      <div>
                         <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-2 block">Display Name</label>
                         <input 
                           type="text" 
                           defaultValue="Aaron Bundy"
                           className="w-full bg-black/40 border border-white/5 rounded px-4 py-3 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors"
                         />
                      </div>
                      <div>
                         <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-2 block">Bio / Objective</label>
                         <textarea 
                           placeholder="Full-stack operator focusing on high-durability system architecture..."
                           className="w-full h-32 bg-black/40 border border-white/5 rounded px-4 py-3 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors resize-none scrollbar-hide font-mono"
                         />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                         <div>
                            <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-2 block">Working Style</label>
                            <select className="w-full bg-black/40 border border-white/5 rounded px-4 py-3 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors appearance-none">
                               <option>Async-First</option>
                               <option>Deep Work / Focus</option>
                               <option>Collaborative / Sync</option>
                               <option>Chaos / Rapid</option>
                            </select>
                         </div>
                         <div>
                            <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-2 block">Comm. Preference</label>
                            <select className="w-full bg-black/40 border border-white/5 rounded px-4 py-3 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors appearance-none">
                               <option>Terse / Minimal</option>
                               <option>Detailed</option>
                               <option>Voice/Video</option>
                               <option>Chat only</option>
                            </select>
                         </div>
                      </div>
                      <div>
                         <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-2 block">Primary Focus (Tags)</label>
                         <div className="flex flex-wrap gap-2 mb-3">
                            {['Architecture', 'Security', 'Frontend', 'Automation'].map(tag => (
                              <div key={tag} className="px-2 py-0.5 bg-[#FF6B00]/10 border border-[#FF6B00]/20 rounded text-[8px] font-black text-[#FF6B00] uppercase tracking-widest italic">{tag}</div>
                            ))}
                         </div>
                         <input 
                           type="text" 
                           placeholder="Add tag..."
                           className="w-full bg-black/40 border border-white/5 rounded px-4 py-3 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors"
                         />
                      </div>
                    </div>
                  </div>
               </div>
            </div>

            <div className="space-y-12">
               <div className="space-y-6">
                  <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic underline decoration-[#FF6B00]/40 decoration-2 underline-offset-8">Style Presets</h3>
                  <div className="grid grid-cols-1 gap-4">
                     {[
                       { name: "Minimalist Synth", desc: "Clean lines, high contrast, obsidian scheme.", icon: Wand2 },
                       { name: "Cyber Industrial", desc: "Raw textures, hazard accents, functional focus.", icon: Shield },
                       { name: "Neon Vanguard", desc: "Digital glow, vibrant overlays, future-forward.", icon: Sparkles },
                     ].map(style => (
                       <button key={style.name} className="flex items-center gap-6 p-6 bg-[#0a0a0a] border border-white/5 hover:border-[#FF6B00]/40 text-left transition-all rounded-xl group">
                          <div className="p-3 bg-white/5 rounded-lg group-hover:bg-[#FF6B00]/10 transition-colors">
                             <style.icon className="h-5 w-5 text-white/40 group-hover:text-[#FF6B00]" />
                          </div>
                          <div>
                             <p className="text-[12px] font-black text-white uppercase tracking-widest mb-1">{style.name}</p>
                             <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest">{style.desc}</p>
                          </div>
                       </button>
                     ))}
                  </div>
               </div>

               <div className="space-y-6">
                  <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic underline decoration-[#FF6B00]/40 decoration-2 underline-offset-8">Account Context</h3>
                  <div className="space-y-6 bg-white/[0.02] p-8 rounded-2xl border border-white/5">
                     <div className="flex items-center gap-4">
                        <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                        <span className="text-[10px] font-black text-white/40 uppercase tracking-widest leading-relaxed italic">Identity Synced to Kernel_V2</span>
                     </div>
                     <button className="w-full py-4 bg-[#FF6B00] text-black text-[10px] font-black uppercase tracking-[0.2em] rounded-lg mt-4 hover:shadow-[0_0_20px_#FF6B00] transition-all">
                        Sync Identity
                     </button>
                  </div>
               </div>
            </div>
        </div>
      </div>
    </div>
  );
}
