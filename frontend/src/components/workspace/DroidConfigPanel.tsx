import * as React from 'react';
import { 
  User, 
  Cpu, 
  Shield, 
  ToyBrick, 
  Trash2, 
  Copy, 
  Plus, 
  X,
  Brain,
  MessageSquare,
  ShieldAlert,
  Save,
  ChevronDown,
  Check
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAgent } from '@/lib/ham/AgentContext';
import { Agent } from '@/lib/ham/types';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { AVAILABLE_MODELS, AVAILABLE_PROVIDERS, ALL_TOOLS } from '@/lib/ham/constants';

// Reusable components for the panel
const Label = ({ children }: { children: React.ReactNode }) => (
  <label className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-1.5 block">
    {children}
  </label>
);

const Input = ({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input
    {...props}
    className={cn(
      "w-full bg-black/40 border border-white/5 rounded px-3 py-2 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors placeholder:text-white/5",
      props.className
    )}
  />
);

const Textarea = ({ ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea
    {...props}
    className={cn(
      "w-full bg-black/40 border border-white/5 rounded px-3 py-2 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors placeholder:text-white/5 resize-none scrollbar-hide font-mono",
      props.className
    )}
  />
);

const Select = ({ children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <div className="relative group">
    <select
      {...props}
      className={cn(
        "w-full bg-black/40 border border-white/5 rounded px-3 py-2 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors appearance-none cursor-pointer",
        props.className
      )}
    >
      {children}
    </select>
    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-3 w-3 text-white/20 group-hover:text-white/40 pointer-events-none" />
  </div>
);

const Toggle = ({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) => (
  <button
    onClick={() => onChange(!checked)}
    className={cn(
      "w-8 h-4 rounded-full relative transition-colors duration-200",
      checked ? "bg-[#FF6B00]" : "bg-white/10"
    )}
  >
    <div className={cn(
      "absolute top-0.5 bottom-0.5 w-3 rounded-full bg-white transition-all duration-200",
      checked ? "right-0.5" : "left-0.5"
    )} />
  </button>
);

const SegmentedToggle = <T extends string>({ options, value, onChange }: { options: T[]; value: T; onChange: (v: T) => void }) => (
  <div className="flex bg-black/40 border border-white/5 rounded p-1 gap-1">
    {options.map((opt) => (
      <button
        key={opt}
        onClick={() => onChange(opt)}
        className={cn(
          "flex-1 py-1.5 text-[8px] font-black uppercase tracking-widest rounded transition-all",
          value === opt ? "bg-[#FF6B00] text-black shadow-lg" : "text-white/20 hover:text-white/40"
        )}
      >
        {opt}
      </button>
    ))}
  </div>
);

const TagInput = ({ tags = [], onAdd, onRemove, placeholder }: { tags?: string[]; onAdd: (s: string) => void; onRemove: (s: string) => void; placeholder: string }) => {
  const [input, setInput] = React.useState('');
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && input.trim()) {
      onAdd(input.trim());
      setInput('');
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag, i) => (
          <div key={i} className="flex items-center gap-1.5 px-2 py-0.5 bg-white/[0.03] border border-white/5 rounded text-[8px] font-black text-white/40 uppercase tracking-tight group hover:border-[#FF6B00]/40 transition-all">
            {tag}
            <button onClick={() => onRemove(tag)} className="hover:text-red-500 transition-colors">
              <X className="h-2 w-2" />
            </button>
          </div>
        ))}
      </div>
      <Input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
    </div>
  );
};

export function DroidConfigPanel() {
  const { agents, selectedAgentId, updateAgent, setSelectedAgentId, setAgents } = useAgent();
  const agent = agents.find(a => a.id === selectedAgentId);

  if (!agent) return null;

  const handleChange = (updates: Partial<Agent>) => {
    updateAgent(agent.id, updates);
  };

  const handleDelete = () => {
    if (confirm(`DECOMMISSION DROID: ${agent.name}?`)) {
      setAgents(agents.filter(a => a.id !== agent.id));
      setSelectedAgentId(null);
    }
  };

  const handleDuplicate = () => {
    const newAgent: Agent = {
      ...agent,
      id: `agt_${Math.random().toString(36).substr(2, 9)}`,
      name: `Copy of ${agent.name}`,
    };
    setAgents([...agents, newAgent]);
    setSelectedAgentId(newAgent.id);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="h-10 flex items-center px-4 border-b border-white/5 bg-black/40 justify-between shrink-0">
         <span className="text-[9px] font-black text-white/30 uppercase tracking-[0.4em] italic leading-none">Configuration Panel</span>
         <Save className="h-2.5 w-2.5 text-[#FF6B00]/60" />
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide pb-20">
        {/* Section 1: Identity */}
        <CollapsibleSection title="Identity" defaultOpen>
          <div className="space-y-4 pt-2">
            <div className="flex items-center gap-4 mb-4">
              <div className="h-12 w-12 bg-white/[0.03] border border-white/5 rounded-xl flex items-center justify-center group relative overflow-hidden shrink-0">
                <User className="h-6 w-6 text-white/20 group-hover:text-[#FF6B00] transition-colors" />
                <div className={cn(
                  "absolute bottom-0 inset-x-0 h-1",
                  agent.status === 'Ready' ? "bg-green-500" : agent.status === 'Working' ? "bg-[#FF6B00]" : "bg-red-500"
                )} />
              </div>
              <div className="flex-1 min-w-0">
                <Input 
                  value={agent.name} 
                  onChange={(e) => handleChange({ name: e.target.value })}
                  className="text-lg font-black italic tracking-tighter bg-transparent border-none p-0 focus:border-none focus:text-[#FF6B00]"
                />
                <Input 
                  value={agent.role} 
                  onChange={(e) => handleChange({ role: e.target.value })}
                  className="text-[9px] font-bold text-[#FF6B00] tracking-[0.2em] opacity-80 bg-transparent border-none p-0 focus:border-none"
                />
              </div>
            </div>
            
            <div>
              <Label>Description</Label>
              <Textarea 
                value={agent.description} 
                onChange={(e) => handleChange({ description: e.target.value })}
                className="h-20"
                placeholder="Experimental workforce Droid assigned to high-priority mission segments."
              />
            </div>
          </div>
        </CollapsibleSection>

        {/* Section 2: Persona */}
        <CollapsibleSection title="Droid Persona">
          <div className="space-y-4 pt-2">
            <div>
              <Label>Identity Kernel (System Prompt)</Label>
              <Textarea 
                value={agent.systemPrompt} 
                onChange={(e) => handleChange({ systemPrompt: e.target.value })}
                className="h-40 text-[10px] leading-relaxed"
                placeholder="DEFINE_COGNITIVE_BOUNDARIES: How this Droid thinks, communicates, and approaches problems..."
              />
            </div>

            <div>
              <Label>Communication Protocol</Label>
              <Select 
                value={agent.communicationStyle || 'Technical & Precise'}
                onChange={(e) => handleChange({ communicationStyle: e.target.value })}
              >
                <option>Technical & Precise</option>
                <option>Military / Terse</option>
                <option>Tactical Conversational</option>
                <option>Verbose / Educational</option>
                <option>Encrypted (Custom)</option>
              </Select>
            </div>

            <div>
               <Label>Behavioral Traits</Label>
               <TagInput 
                  tags={agent.traits} 
                  onAdd={(t) => handleChange({ traits: [...(agent.traits || []), t] })}
                  onRemove={(t) => handleChange({ traits: (agent.traits || []).filter(x => x !== t) })}
                  placeholder="Add behavioral trait..."
               />
            </div>

            <div>
               <Label>Domain Expertise (Knowledge Areas)</Label>
               <TagInput 
                  tags={agent.knowledgeAreas} 
                  onAdd={(k) => handleChange({ knowledgeAreas: [...(agent.knowledgeAreas || []), k] })}
                  onRemove={(k) => handleChange({ knowledgeAreas: (agent.knowledgeAreas || []).filter(x => x !== k) })}
                  placeholder="Add expertise area..."
               />
            </div>
          </div>
        </CollapsibleSection>

        {/* Section 3: Model & Provider */}
        <CollapsibleSection title="Model & Provider">
          <div className="space-y-4 pt-2">
            <div>
              <Label>Model</Label>
              <Select 
                value={agent.model} 
                onChange={(e) => handleChange({ model: e.target.value })}
              >
                {AVAILABLE_MODELS.map(m => <option key={m}>{m}</option>)}
              </Select>
            </div>

            <div>
              <Label>Provider</Label>
              <Select 
                value={agent.provider} 
                onChange={(e) => handleChange({ provider: e.target.value })}
              >
                {AVAILABLE_PROVIDERS.map(p => <option key={p}>{p}</option>)}
              </Select>
            </div>

            <div>
              <Label>Reasoning Depth</Label>
              <SegmentedToggle 
                options={['Fast', 'Balanced', 'Deep']} 
                value={agent.reasoningDepth || 'Balanced'} 
                onChange={(v) => handleChange({ reasoningDepth: v as any })}
              />
              <p className="text-[7px] font-bold text-white/20 uppercase mt-1 tracking-widest leading-relaxed italic">
                Controls how much structured thinking the model performs before responding.
              </p>
            </div>

            <div className="flex items-center justify-between py-2 border-y border-white/5">
               <div className="space-y-0.5">
                  <Label>Key Status</Label>
                  <p className={cn(
                    "text-[9px] font-black uppercase tracking-widest leading-none",
                    agent.keyConnected ? "text-green-500" : "text-red-500"
                  )}>
                    {agent.keyConnected ? "SECURELY_CONNECTED" : "SETUP_REQUIRED"}
                  </p>
               </div>
               <div className="text-right">
                  <Label>Context Size</Label>
                  <p className="text-[9px] font-black text-white/60 uppercase tracking-widest leading-none">200K Tokens</p>
               </div>
            </div>
          </div>
        </CollapsibleSection>

        {/* Section 4: Tools & Capabilities */}
        <CollapsibleSection title="Tools" count={agent.assignedTools.length}>
          <div className="space-y-4 pt-2">
            <div className="space-y-1">
              {ALL_TOOLS.map((tool) => (
                <div key={tool.name} className="flex items-center justify-between py-2 border-b border-white/[0.02] last:border-0 group">
                  <div className="flex items-center gap-3">
                    <div className="p-1 px-1.5 bg-white/[0.03] border border-white/5 rounded">
                       <ToyBrick className="h-2.5 w-2.5 text-white/20 group-hover:text-[#FF6B00]/60" />
                    </div>
                    <span className="text-[9px] font-black text-white/40 uppercase tracking-widest group-hover:text-white/60">{tool.name}</span>
                  </div>
                  <Toggle 
                    checked={agent.assignedTools.includes(tool.name)} 
                    onChange={(checked) => {
                      if (checked) {
                        handleChange({ assignedTools: [...agent.assignedTools, tool.name] });
                      } else {
                        handleChange({ assignedTools: agent.assignedTools.filter(t => t !== tool.name) });
                      }
                    }} 
                  />
                </div>
              ))}
            </div>
          </div>
        </CollapsibleSection>

        {/* Section 5: Behavior & Safety */}
        <CollapsibleSection title="Behavior & Safety">
          <div className="space-y-4 pt-2">
            <div>
              <Label>Autonomy Profile</Label>
              <SegmentedToggle 
                options={['Supervised', 'Semi-Auto', 'Full Auto']} 
                value={agent.autonomyLevel || 'Semi-Auto'} 
                onChange={(v) => handleChange({ autonomyLevel: v as any })}
              />
              <div className="mt-2 p-2 bg-black/40 border-l border-[#FF6B00]/40 italic">
                <p className="text-[8px] font-bold text-white/30 uppercase tracking-widest leading-relaxed">
                  {agent.autonomyLevel === 'Full Auto' ? 'ACTING_WITHOUT_RESTRAINT: DROID HAS FULL EXECUTION AUTHORITY.' : 
                   agent.autonomyLevel === 'Supervised' ? 'MANDATORY_ACK_REQUIRED: EVERY ACTION REQUIRES OPERATOR SIGN-OFF.' : 
                   'RISK_AWARE_OPERATIONS: DROID ASKS FOR DANGEROUS COMMANDS ONLY.'}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between py-2 border-y border-white/5">
               <div className="space-y-0.5">
                  <Label>Safe Mode Protocol</Label>
                  <p className="text-[8px] font-bold text-[#FF6B00]/60 uppercase tracking-widest leading-none italic">
                     ENFORCE_DESTRUCTIVE_LOCK: Blocks all delete operations
                  </p>
               </div>
               <Toggle checked={!!agent.safeMode} onChange={(v) => handleChange({ safeMode: v })} />
            </div>

            <div>
              <Label>Mandatory Intercepts (Require Approval For)</Label>
              <div className="grid grid-cols-1 gap-2">
                 {['File Deletion', 'External Network', 'Package Installation', 'Remote Workspace Push', 'Admin Shell Access'].map(opt => (
                    <button 
                      key={opt}
                      onClick={() => {
                        const current = agent.requireApprovalFor || [];
                        if (current.includes(opt)) {
                          handleChange({ requireApprovalFor: current.filter(x => x !== opt) });
                        } else {
                          handleChange({ requireApprovalFor: [...current, opt] });
                        }
                      }}
                      className="flex items-center justify-between p-3 bg-white/[0.015] border border-white/5 hover:border-white/10 rounded-xl group transition-all"
                    >
                      <span className={cn(
                         "text-[9px] font-bold uppercase tracking-widest transition-colors",
                         (agent.requireApprovalFor || []).includes(opt) ? "text-white" : "text-white/20"
                      )}>{opt}</span>
                      <div className={cn(
                        "h-4 w-4 border transition-all flex items-center justify-center rounded",
                        (agent.requireApprovalFor || []).includes(opt) ? "bg-[#FF6B00] border-[#FF6B00] shadow-[0_0_10px_rgba(255,107,0,0.3)]" : "border-white/10 group-hover:border-white/20"
                      )}>
                        {(agent.requireApprovalFor || []).includes(opt) && <Check className="h-2.5 w-2.5 text-black font-black" />}
                      </div>
                    </button>
                 ))}
              </div>
            </div>

            <div>
              <Label>Industrial Command Policy</Label>
              <div className="space-y-3">
                <div className="space-y-2">
                  <label className="text-[7px] font-black text-white/20 uppercase tracking-widest block italic leading-none ml-1">Whitelist_Authorized</label>
                  <Textarea 
                    value={agent.allowlist} 
                    onChange={(e) => handleChange({ allowlist: e.target.value })}
                    className="h-20 text-[9px] font-mono p-3 bg-green-500/[0.02] border-green-500/10 focus:border-green-500/30"
                    placeholder="ls, git status, npm run dev..."
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[7px] font-black text-white/20 uppercase tracking-widest block italic leading-none ml-1">Blacklist_Forbidden</label>
                  <Textarea 
                    value={agent.denylist} 
                    onChange={(e) => handleChange({ denylist: e.target.value })}
                    className="h-20 text-[9px] font-mono p-3 bg-red-500/[0.02] border-red-500/10 focus:border-red-500/30"
                    placeholder="rm -rf, sudo, mkfs..."
                  />
                </div>
              </div>
            </div>
          </div>
        </CollapsibleSection>

        {/* Section 6: Memory */}
        <CollapsibleSection title="Memory">
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
               <div className="space-y-0.5">
                  <Label>Neural Memory</Label>
                  <p className="text-[8px] font-bold text-white/20 uppercase tracking-widest leading-none italic">
                     Persist context across sessions
                  </p>
               </div>
               <Toggle checked={!!agent.memoryEnabled} onChange={(v) => handleChange({ memoryEnabled: v })} />
            </div>

            <div>
              <Label>Scope</Label>
              <Select 
                value={agent.memoryScope || 'This Project'}
                onChange={(e) => handleChange({ memoryScope: e.target.value })}
              >
                <option>This Thread</option>
                <option>This Project</option>
                <option>All Projects</option>
              </Select>
            </div>

            <div>
              <Label>Knowledge Sources</Label>
              <div className="space-y-2">
                {(agent.knowledgeSources || []).map(source => (
                  <div key={source.id} className="flex items-center justify-between p-2 bg-white/[0.02] border border-white/5 rounded">
                    <span className="text-[9px] font-black text-white/40 uppercase tracking-widest italic">{source.name}</span>
                    <button onClick={() => handleChange({ knowledgeSources: agent.knowledgeSources?.filter(s => s.id !== source.id) })}>
                       <X className="h-2.5 w-2.5 text-white/20 hover:text-red-500" />
                    </button>
                  </div>
                ))}
                <button 
                  onClick={() => handleChange({ knowledgeSources: [...(agent.knowledgeSources || []), { name: 'New Source', id: Math.random().toString() }] })}
                  className="w-full py-1.5 border border-dashed border-white/10 rounded text-[8px] font-black text-white/20 uppercase tracking-widest hover:text-white/40 hover:border-white/20 transition-all"
                >
                  Add Source
                </button>
              </div>
            </div>

            <div className="text-right">
               <p className="text-[7px] font-bold text-white/10 uppercase tracking-widest italic">Last updated: 2 min ago</p>
            </div>
          </div>
        </CollapsibleSection>
      </div>

      {/* Footer */}
      <div className="shrink-0 p-4 border-t border-white/5 bg-black/40 grid grid-cols-2 gap-3">
        <button 
          onClick={handleDuplicate}
          className="flex items-center justify-center gap-2 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded transition-all group"
        >
          <Copy className="h-3 w-3 text-white/20 group-hover:text-white/60" />
          <span className="text-[9px] font-black text-white/40 group-hover:text-white/80 uppercase tracking-widest">Duplicate</span>
        </button>
        <button 
          onClick={handleDelete}
          className="flex items-center justify-center gap-2 py-2 bg-red-500/5 hover:bg-red-500/10 border border-red-500/20 rounded transition-all group"
        >
          <Trash2 className="h-3 w-3 text-red-500/40 group-hover:text-red-500/80" />
          <span className="text-[9px] font-black text-red-500/40 group-hover:text-red-500/80 uppercase tracking-widest">Delete Droid</span>
        </button>
      </div>
    </div>
  );
}
