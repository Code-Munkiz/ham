import { MOCK_KEYS, MOCK_EXTENSIONS } from "@/lib/ham/mocks";
import { 
  Plus,
  Shield,
  Circle,
  Users,
  ToyBrick,
  Zap as ZapIcon,
  ChevronDown,
  ChevronRight,
  User,
  ExternalLink,
  Lock,
  MessageSquare,
  Command as CommandIcon,
  Sparkles,
  Database,
  Puzzle,
  FileText,
  Key,
  X
} from "lucide-react";
import { cn } from "@/lib/utils";
import * as React from "react";
import { Link } from "react-router-dom";
import { ModelPicker, ModelOption } from "@/components/workspace/ModelPicker";
import { Agent } from "@/lib/ham/types";
import { useAgent } from "@/lib/ham/AgentContext";

import { DROID_TEMPLATES } from "@/lib/ham/constants";

export default function Droids() {
  const [command, setCommand] = React.useState("");
  const { agents, selectedAgentId, setSelectedAgentId, updateAgent, setAgents } = useAgent();
  const [isHireModalOpen, setIsHireModalOpen] = React.useState(false);
  const [isSetupToolsOpen, setIsSetupToolsOpen] = React.useState(false);

  const selectedAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const handleHireFromTemplate = (template: Partial<Agent>) => {
    const newAgent: Agent = {
      id: `agt_${Math.random().toString(36).substr(2, 9)}`,
      name: template.name || "New Droid",
      role: template.role || "Specialist",
      model: template.model || "Claude 3.5 Sonnet",
      provider: template.provider || "Anthropic",
      status: "Ready",
      keyConnected: true,
      assignedTools: template.assignedTools || [],
      description: template.description,
      traits: template.traits,
      communicationStyle: template.communicationStyle,
    };
    setAgents([...agents, newAgent]);
    setSelectedAgentId(newAgent.id);
    setIsHireModalOpen(false);
  };

  const handleHireFromScratch = () => {
    const newAgent: Agent = {
      id: `agt_${Math.random().toString(36).substr(2, 9)}`,
      name: "New Droid",
      role: "Specialist",
      model: "Claude 3.5 Sonnet",
      provider: "Anthropic",
      status: "Ready",
      keyConnected: false,
      assignedTools: [],
    };
    setAgents([...agents, newAgent]);
    setSelectedAgentId(newAgent.id);
    setIsHireModalOpen(false);
  };

  const handleModelChange = (agentId: string, model: ModelOption) => {
    updateAgent(agentId, { model: model.name, provider: model.provider });
  };

  const handleRoleChange = (agentId: string, newRole: string) => {
    updateAgent(agentId, { role: newRole });
  };

  const handleNotesChange = (agentId: string, newNotes: string) => {
    updateAgent(agentId, { notes: newNotes });
  };

  return (
    <div className="h-full flex flex-col bg-[#050505] relative overflow-hidden font-sans">
      {/* Subtle Background Rail */}
      <div className="absolute inset-0 opacity-[0.02] pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '64px 64px' }} />

      {/* Main Working Area */}
      <div 
        className="flex-1 overflow-y-auto p-12 scrollbar-hide relative z-10 animate-in fade-in duration-1000"
        onClick={() => setSelectedAgentId(null)}
      >
        <div className="max-w-6xl mx-auto space-y-16" onClick={(e) => e.stopPropagation()}>
           
           {/* Droids Header / Stats */}
           <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-10">
              <div className="space-y-4">
                 <div className="flex items-center gap-4">
                    <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                       <Users className="h-5 w-5 text-[#FF6B00]" />
                    </div>
                    <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">TEAM_WORKFORCE / DROIDS</span>
                 </div>
                 <h1 className="text-5xl font-black text-white italic tracking-tighter uppercase leading-none">
                    Droids <span className="text-[#FF6B00] not-italic">Setup</span>
                 </h1>
                 <p className="text-sm font-bold text-white/20 max-w-xl uppercase tracking-widest leading-relaxed">
                    Configure your agent workforce. Select models, connect providers, and assign specialized tools to each droid.
                 </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                 <div className="p-4 bg-white/[0.02] border border-white/5 rounded-lg space-y-1">
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-widest">Active Droids</span>
                    <p className="text-xl font-black text-white italic">{(agents || []).length.toString().padStart(2, '0')}</p>
                 </div>
                 <div className="p-4 bg-white/[0.02] border border-white/5 rounded-lg space-y-1">
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-widest">Systems Ready</span>
                    <p className="text-xl font-black text-[#FF6B00] italic">{(agents || []).filter(a => a.status === 'Ready').length.toString().padStart(2, '0')} / {(agents || []).length.toString().padStart(2, '0')}</p>
                 </div>
              </div>
           </div>

           {/* Team Setup Interface */}
           <div className="space-y-6">
              <div className="flex items-center justify-between">
                 <div className="flex items-center gap-4">
                    <h3 className="text-[11px] font-black uppercase tracking-[0.3em] text-white/60 italic">Operational Workforce</h3>
                    <div className="h-px w-32 bg-white/5" />
                 </div>
                 <div className="flex items-center gap-4 relative">
                    <div className="relative">
                      <button 
                        onClick={() => setIsSetupToolsOpen(!isSetupToolsOpen)}
                        className="flex items-center gap-2 px-4 py-2 border border-white/10 hover:border-[#FF6B00]/40 text-white/40 hover:text-white transition-all text-[10px] font-black uppercase tracking-widest rounded bg-[#0a0a0a]"
                      >
                         <ChevronDown className={cn("h-4 w-4 transition-transform", isSetupToolsOpen ? "rotate-180" : "")} />
                         Setup Tools
                      </button>
                      
                      {isSetupToolsOpen && (
                        <div className="absolute top-full right-0 mt-2 w-64 bg-[#0a0a0a] border border-white/10 rounded overflow-hidden shadow-2xl z-[100] animate-in fade-in slide-in-from-top-2 duration-200">
                          <div className="p-3 bg-white/5 border-b border-white/5">
                            <span className="text-[9px] font-black text-white/40 uppercase tracking-widest italic">Droid Templates</span>
                          </div>
                          <div className="py-1">
                            {DROID_TEMPLATES.map((t) => (
                              <button
                                key={t.name}
                                onClick={() => {
                                  handleHireFromTemplate(t);
                                  setIsSetupToolsOpen(false);
                                }}
                                className="w-full text-left px-4 py-3 hover:bg-[#FF6B00]/5 group border-b border-white/[0.02] last:border-0"
                              >
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-[11px] font-black text-white uppercase italic group-hover:text-[#FF6B00] transition-colors">{t.name}</span>
                                  <ChevronRight className="h-3 w-3 text-white/10 group-hover:text-[#FF6B00]/40" />
                                </div>
                                <p className="text-[8px] font-bold text-white/20 uppercase tracking-widest leading-tight">{t.role}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <button 
                      onClick={() => setIsHireModalOpen(true)}
                      className="flex items-center gap-2 px-4 py-2 border border-[#FF6B00]/40 text-[#FF6B00] hover:bg-[#FF6B00]/10 transition-all text-[10px] font-black uppercase tracking-widest rounded bg-[#FF6B00]/5 shadow-[0_0_15px_rgba(255,107,0,0.1)]"
                    >
                       <Plus className="h-4 w-4" />
                       Hire Droid
                    </button>
                 </div>
              </div>

              <div className="space-y-px bg-white/5 border border-white/5 rounded overflow-hidden shadow-2xl">
                 <div className="grid grid-cols-12 bg-white/[0.04] p-4 text-[9px] font-black uppercase tracking-[0.2em] text-white/30 border-b border-white/5">
                    <div className="col-span-4 pl-4">Droid / Purpose</div>
                    <div className="col-span-3">Assigned Model</div>
                    <div className="col-span-2 text-center">Provider</div>
                    <div className="col-span-2 text-center">Key Status</div>
                    <div className="col-span-1"></div>
                 </div>

                 {agents.map((agent) => (
                   <div 
                    key={agent.id} 
                    onClick={() => setSelectedAgentId(agent.id)}
                    className={cn(
                      "grid grid-cols-12 items-center transition-all p-5 border-b border-white/[0.02] group cursor-pointer relative",
                      selectedAgentId === agent.id ? "bg-white/[0.05]" : "bg-[#080808] hover:bg-white/[0.04]"
                    )}
                   >
                      {selectedAgentId === agent.id && (
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#FF6B00]" />
                      )}
                      <div className="col-span-4 flex items-center gap-4 pl-4">
                         <div className={cn(
                           "h-12 w-12 border flex items-center justify-center transition-all group-hover:border-[#FF6B00]/40",
                           agent.status === 'Ready' || agent.status === 'Working' ? "bg-black text-white/80 border-white/10" : "bg-black/40 text-white/20 border-dashed border-white/5"
                         )}>
                            <User className="h-5 w-5" />
                         </div>
                         <div className="space-y-1 flex-1 min-w-0">
                            <h4 className="text-[13px] font-black text-white uppercase group-hover:text-[#FF6B00] transition-colors tracking-widest italic">{agent.name}</h4>
                            <input 
                              type="text"
                              value={agent.role}
                              onChange={(e) => handleRoleChange(agent.id, e.target.value)}
                              className="w-full bg-transparent border-none outline-none p-0 text-[10px] font-bold text-white/20 uppercase tracking-widest placeholder:text-white/5 focus:text-[#FF6B00]/60 transition-colors"
                              placeholder="Define purpose..."
                              onClick={(e) => e.stopPropagation()}
                            />
                         </div>
                      </div>

                      <div className="col-span-3">
                         <ModelPicker 
                           currentModel={agent.model} 
                           onSelect={(model) => handleModelChange(agent.id, model)} 
                         />
                      </div>

                      <div className="col-span-2 text-center">
                         <span className="text-[10px] font-black uppercase tracking-widest text-white/20 group-hover:text-white/40 transition-colors">{agent.provider}</span>
                      </div>

                      <div className="col-span-2 flex flex-col items-center">
                         <div className="flex items-center gap-2">
                            <div className={cn(
                              "h-1.5 w-1.5 rounded-full",
                              agent.keyConnected ? "bg-green-500 shadow-[0_0_8px_#22c55e]" : "bg-red-500/40"
                            )} />
                            <span className={cn(
                              "text-[9px] font-black uppercase tracking-widest italic",
                              agent.keyConnected ? "text-green-500/60" : "text-white/20"
                            )}>
                               {agent.keyConnected ? 'Ready' : 'Setup Required'}
                            </span>
                         </div>
                         {!agent.keyConnected && (
                            <Link to="/settings" className="text-[8px] font-bold text-[#FF6B00] hover:underline mt-1 uppercase tracking-tighter">Connect Key</Link>
                         )}
                      </div>

                      <div className="col-span-1 flex justify-end pr-4">
                         <Sparkles className={cn(
                           "h-4 w-4 transition-colors",
                           selectedAgentId === agent.id ? "text-[#FF6B00]" : "text-white/10"
                         )} />
                      </div>

                      {/* Notes Section for each card */}
                      <div className="col-span-12 mt-4 pt-4 border-t border-white/[0.03] space-y-2">
                         <div className="flex items-center justify-between">
                            <p className="text-[9px] font-black text-[#FF6B00]/40 uppercase tracking-widest italic">Operational Notes</p>
                            <div className="flex items-center gap-2">
                               <div className="h-1 w-8 bg-white/5 rounded-full" />
                               <span className="text-[7px] font-black text-white/10 uppercase tracking-widest italic">Encrypted_Sync</span>
                            </div>
                         </div>
                         <textarea 
                            className="w-full h-24 bg-black/40 border border-white/5 rounded-xl p-4 text-[11px] font-mono text-white/40 uppercase tracking-tight focus:border-[#FF6B00]/40 outline-none transition-all resize-none placeholder:text-white/5"
                            value={agent.notes || ""}
                            onChange={(e) => handleNotesChange(agent.id, e.target.value)}
                            placeholder="DIRECTIVE_NOTES: Add custom operational context or behavioral override notes for this unit..."
                            onClick={(e) => e.stopPropagation()}
                         />
                      </div>
                   </div>
                 ))}
              </div>
           </div>

           {/* Setup Surfaces Container */}
           <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pt-8 border-t border-white/5">
              
              {/* Surface 1: Selected Droid Details & Notes */}
              <div className="space-y-6">
                 <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                       <FileText className="h-4 w-4 text-[#FF6B00]" />
                       <span className="text-[10px] font-black uppercase tracking-[0.3em] text-white">Droid Details</span>
                    </div>
                    {/* Add a generic \"Edit Notes\" action if needed */}
                 </div>
                 <div className="p-6 bg-[#0a0a0a] border border-white/5 rounded-xl space-y-4">
                    <div className="space-y-1">
                       <p className="text-[10px] font-black text-white/40 uppercase tracking-widest italic">Description</p>
                       <p className="text-[11px] font-bold text-white/60 uppercase tracking-widest leading-relaxed italic">
                          {selectedAgent.description || "No specialized description defined for this workforce unit."}
                       </p>
                    </div>
                    <div className="space-y-1 pt-2">
                       <p className="text-[10px] font-black text-[#FF6B00]/40 uppercase tracking-widest italic">Current Context / Notes</p>
                       <textarea 
                          className="w-full h-28 bg-black/40 border border-white/5 rounded-xl p-4 text-[11px] font-mono text-white/40 uppercase tracking-tight focus:border-[#FF6B00]/40 outline-none transition-all resize-none"
                          value={selectedAgent.notes || ""}
                          onChange={(e) => handleNotesChange(selectedAgent.id, e.target.value)}
                          placeholder="Add operational notes..."
                       />
                    </div>
                 </div>
              </div>

              {/* Surface 2: Assigned Tools & Extensions */}
              <div className="space-y-6">
                 <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                       <Puzzle className="h-4 w-4 text-[#FF6B00]" />
                       <span className="text-[10px] font-black uppercase tracking-[0.3em] text-white">Assigned Tools</span>
                    </div>
                    <Link to="/extensions" className="text-[8px] font-black text-white/20 hover:text-white uppercase tracking-widest">Add Tools</Link>
                 </div>
                 <div className="grid grid-cols-1 gap-2">
                    {(selectedAgent.assignedTools || []).map((tool, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-white/[0.04] border border-white/5 rounded group hover:border-[#FF6B00]/40 transition-all">
                         <div className="flex items-center gap-3">
                            <ToyBrick className="h-3.5 w-3.5 text-white/20 group-hover:text-[#FF6B00] transition-colors" />
                            <span className="text-[10px] font-black text-white/60 uppercase tracking-widest">{tool}</span>
                         </div>
                         <div className="h-1.5 w-1.5 rounded-full bg-green-500/40" />
                      </div>
                    ))}
                    {(!selectedAgent.assignedTools || selectedAgent.assignedTools.length === 0) && (
                      <div className="p-4 border border-dashed border-white/5 rounded text-center">
                         <p className="text-[9px] font-bold text-white/10 uppercase tracking-widest italic">No tools assigned</p>
                      </div>
                    )}
                 </div>
              </div>

              {/* Surface 3: Key Status & Connected Providers */}
              <div className="space-y-6">
                 <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                       <Key className="h-4 w-4 text-[#FF6B00]" />
                       <span className="text-[10px] font-black uppercase tracking-[0.3em] text-white">Key Connectors</span>
                    </div>
                    <Link to="/settings" className="text-[8px] font-black text-white/20 hover:text-white uppercase tracking-widest">Settings</Link>
                 </div>
                 <div className="p-6 bg-white/[0.02] border border-white/10 rounded-xl space-y-6">
                    <div className="flex items-center justify-between">
                       <span className="text-[10px] font-black text-white/40 uppercase tracking-widest italic">Provider Status</span>
                       <span className="text-[9px] font-mono text-green-500 italic uppercase">System_Linked</span>
                    </div>
                    <div className="space-y-4">
                       {MOCK_KEYS.map((key) => (
                         <div key={key.id} className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                               <div className={cn(
                                 "h-1.5 w-1.5 rounded-full",
                                 key.status === 'Connected' ? "bg-[#FF6B00]" : "bg-white/10"
                               )} />
                               <span className="text-[10px] font-black text-white/60 uppercase tracking-widest">{key.provider}</span>
                            </div>
                            <span className="text-[9px] font-mono text-white/10 tracking-widest">{key.maskedKey.split('••••')[0]}••••</span>
                         </div>
                       ))}
                    </div>
                    <button className="w-full py-3 bg-white/5 border border-white/10 text-[9px] font-black uppercase tracking-[0.2em] text-white/40 hover:text-white hover:border-[#FF6B00]/40 transition-all rounded">
                       Test All Connections
                    </button>
                 </div>
              </div>

           </div>
        </div>
      </div>

      {/* Primary Directive Interface */}
      <div className="px-12 pb-8 pt-4 bg-gradient-to-t from-black to-transparent relative z-20">
        <div className="max-w-4xl mx-auto">
           <div className="relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-[#FF6B00]/20 to-white/5 rounded-2xl blur opacity-10 group-focus-within:opacity-40 transition duration-500" />
              <div className="relative bg-[#0d0d0d] border border-white/10 rounded-xl overflow-hidden shadow-2xl">
                 <div className="flex h-16 items-center px-8 gap-4">
                    <CommandIcon className="h-5 w-5 text-[#FF6B00]" />
                    <input 
                       type="text" 
                       value={command}
                       onChange={(e) => setCommand(e.target.value)}
                       placeholder="DIRECTIVE_INPUT: Command your droids..."
                       className="flex-1 bg-transparent border-none outline-none text-white text-sm font-bold uppercase tracking-widest placeholder:text-white/10"
                    />
                    <div className="flex items-center gap-3">
                       <span className="text-[9px] font-black text-white/20 bg-white/5 px-2 py-1 rounded tracking-widest">⌘ K</span>
                       <button className="px-4 py-2 bg-[#FF6B00] text-black text-[10px] font-black uppercase tracking-widest rounded hover:bg-[#FF6B00]/80 transition-colors">Start Work</button>
                    </div>
                 </div>
              </div>
           </div>
        </div>
      </div>
      {/* Hire Droid Modal */}
      {isHireModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[200] flex items-center justify-center p-6 animate-in fade-in duration-300">
          <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl w-full max-w-2xl overflow-hidden shadow-[0_0_100px_rgba(255,107,0,0.1)] flex flex-col max-h-[90vh]">
            <div className="p-8 border-b border-white/5 flex items-center justify-between">
              <div className="space-y-2">
                <h2 className="text-3xl font-black text-white uppercase italic tracking-tighter italic">Hire <span className="text-[#FF6B00] not-italic">Droid</span></h2>
                <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em]">Acquire new specialized workforce units</p>
              </div>
              <button 
                onClick={() => setIsHireModalOpen(false)}
                className="h-10 w-10 border border-white/5 hover:border-white/20 flex items-center justify-center rounded transition-all text-white/20 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-8 space-y-12">
              <div className="space-y-6">
                <span className="text-[10px] font-black text-white/20 uppercase tracking-[0.4em]">Start From Template</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {DROID_TEMPLATES.map((t) => (
                    <button
                      key={t.name}
                      onClick={() => handleHireFromTemplate(t)}
                      className="text-left p-6 bg-white/[0.02] border border-white/5 rounded-xl hover:border-[#FF6B00]/40 transition-all hover:bg-[#FF6B00]/5 group flex flex-col justify-between h-48"
                    >
                      <div className="space-y-3">
                         <div className="flex items-center justify-between">
                            <h4 className="text-xl font-black text-white uppercase italic group-hover:text-[#FF6B00] transition-colors">{t.name}</h4>
                            <ChevronRight className="h-4 w-4 text-white/10 group-hover:text-[#FF6B00]" />
                         </div>
                         <p className="text-[9px] font-bold text-white/20 uppercase tracking-[0.2em]">{t.role}</p>
                         <p className="text-[10px] font-bold text-white/40 leading-relaxed uppercase tracking-widest line-clamp-2 italic">{t.description}</p>
                      </div>
                      
                      <div className="flex gap-1.5 pt-4 border-t border-white/5">
                        {t.assignedTools?.slice(0, 2).map(tool => (
                          <div key={tool} className="px-2 py-0.5 bg-black rounded text-[7px] font-black text-white/20 uppercase tracking-widest">{tool}</div>
                        ))}
                      </div>
                    </button>
                  ))}
                  
                  <button
                    onClick={handleHireFromScratch}
                    className="text-left p-6 border border-dashed border-white/10 rounded-xl hover:border-white/40 transition-all hover:bg-white/[0.02] group flex flex-col items-center justify-center h-48 gap-4"
                  >
                    <Plus className="h-8 w-8 text-white/10 group-hover:text-white transition-colors" />
                    <div className="text-center">
                      <span className="text-[11px] font-black text-white/40 uppercase tracking-widest group-hover:text-white transition-colors">Start From Scratch</span>
                      <p className="text-[8px] font-bold text-white/10 uppercase tracking-widest mt-1">Configure your own specialist</p>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
