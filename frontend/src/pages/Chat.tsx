import * as React from "react";
import { 
  Send, 
  Paperclip, 
  Sparkles, 
  Shield, 
  Terminal,
  MessageSquare,
  Cpu,
  History as HistoryIcon,
  Search,
  MoreHorizontal,
  Command as CommandIcon,
  Activity,
  ToyBrick,
  User,
  Zap,
  Lock,
  Globe,
  Monitor,
  Layout,
  ChevronDown,
  X,
  Eye,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import { postChat } from "@/lib/ham/api";
import { useAgent } from "@/lib/ham/AgentContext";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";

type ChatRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

export default function Chat() {
  const { agents, selectedAgentId } = useAgent();
  const { activeTask, setActiveTask, isControlPanelOpen, setIsControlPanelOpen } = useWorkspace();
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const [messages, setMessages] = React.useState<ChatRow[]>([]);
  const [input, setInput] = React.useState("");
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);
  const [chatError, setChatError] = React.useState<string | null>(null);
  
  // Workbench Modes
  const [viewMode, setViewMode] = React.useState<'chat' | 'preview' | 'browser' | 'split'>('chat');

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setChatError(null);
    setSending(true);
    try {
      const res = await postChat({
        session_id: sessionId ?? undefined,
        messages: [{ role: "user", content: text }],
      });
      setSessionId(res.session_id);
      const ts = () =>
        new Date().toLocaleTimeString([], {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: ts(),
        })),
      );
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full bg-[#050505] font-sans relative overflow-hidden">
      {/* Background Rail Grid */}
      <div className="absolute inset-0 opacity-[0.012] pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '80px 80px' }} />

      {/* Main Dynamic Workspace Area */}
      <div className="flex-1 flex flex-col relative z-20 overflow-hidden">
        
        {/* Workbench Header */}
        <div className="h-12 flex items-center px-8 border-b border-white/5 bg-black/60 justify-between shrink-0">
           <div className="flex items-center gap-6">
              <div className="flex items-center gap-4">
                 <div className="h-2 w-2 rounded-full bg-[#FF6B00] shadow-[0_0_10px_#FF6B00]" />
                 <span className="text-[10px] font-black tracking-[0.2em] text-[#FF6B00] uppercase italic">Workbench_Session</span>
              </div>
           </div>
           
           {/* View Selection Controls & Control Panel Toggle */}
           <div className="flex items-center gap-4">
              <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-lg p-1">
                 {[
                   { id: 'chat', icon: MessageSquare, label: 'Chat' },
                   { id: 'split', icon: Layout, label: 'Split' },
                   { id: 'preview', icon: Monitor, label: 'Preview' },
                   { id: 'browser', icon: Globe, label: 'Web' },
                 ].map((mode) => (
                   <button 
                     key={mode.id}
                     onClick={() => setViewMode(mode.id as any)}
                     className={cn(
                       "flex items-center gap-2 px-3 py-1.5 rounded-md transition-all group",
                       viewMode === mode.id ? "bg-[#FF6B00] text-black" : "text-white/20 hover:text-white"
                     )}
                   >
                      <mode.icon className="h-3 w-3" />
                      <span className="text-[9px] font-black uppercase tracking-widest hidden lg:block">{mode.label}</span>
                   </button>
                 ))}
              </div>
              <button 
                onClick={() => setIsControlPanelOpen(!isControlPanelOpen)}
                className={cn(
                  "flex items-center gap-3 px-4 py-1.5 border transition-all rounded-lg group shadow-xl",
                  isControlPanelOpen 
                    ? "bg-[#FF6B00]/10 border-[#FF6B00]/40 text-[#FF6B00]" 
                    : "bg-white/5 border-white/10 text-white/40 hover:text-white"
                )}
              >
                 <Activity className="h-3.5 w-3.5" />
                 <span className="text-[10px] font-black uppercase tracking-widest">Control Panel</span>
                 <ChevronDown className={cn("h-3 w-3 transition-transform duration-300", isControlPanelOpen ? "rotate-180" : "")} />
              </button>
           </div>
        </div>
        
        {/* RIGHT-SIDE CONTROL PANEL OVERLAY - HANDLED BY APPLAYOUT NOW */}

        {/* Dynamic Workbench Canvas */}
        <div className="flex-1 flex relative overflow-hidden">
          {/* Main Working Canvas (Chat/Split) */}
          <div className={cn(
            "h-full transition-all duration-700 overflow-hidden flex flex-col",
            (viewMode === 'chat' || viewMode === 'split') ? "flex-1" : "w-0 opacity-0"
          )}>
            <div className="flex-1 overflow-y-auto p-12 space-y-16 scrollbar-hide relative">
              <div className="max-w-3xl mx-auto space-y-16 pb-32">
                {messages.map((msg) => (
                  <div key={msg.id} className={cn("flex gap-10 group animate-in fade-in slide-in-from-bottom-3 duration-700", msg.role === 'user' ? "flex-row-reverse" : "")}>
                    <div className={cn("h-11 w-11 shrink-0 border flex items-center justify-center transition-all rotate-3 group-hover:rotate-0", msg.role === 'assistant' ? "bg-[#FF6B00]/10 border-[#FF6B00]/30 text-[#FF6B00] shadow-[0_0_30px_rgba(255,107,0,0.15)]" : msg.role === 'system' ? "bg-white/5 border-white/10 text-white/20" : "bg-white border-white text-black shadow-xl")}>
                      {msg.role === 'assistant' ? <Sparkles className="h-6 w-6" /> : msg.role === 'system' ? <Shield className="h-5 w-5" /> : <span className="text-[11px] font-black uppercase">User</span>}
                    </div>
                    
                    <div className={cn("flex flex-col gap-4 min-w-0 max-w-2xl", msg.role === 'user' ? "items-end" : "items-start")}>
                      <div className="flex items-center gap-4 opacity-40 group-hover:opacity-100 transition-opacity">
                        <span className="text-[9px] font-black uppercase tracking-[0.4em] text-white italic">{msg.role}</span>
                        <span className="text-[8px] font-mono text-white/20">{msg.timestamp}</span>
                      </div>
                      <div className={cn("relative p-8 border transition-all duration-300", msg.role === 'user' ? "bg-white/[0.04] border-white/10 text-white/90 rounded-2xl rounded-tr-none shadow-2xl" : msg.role === 'system' ? "bg-black border-white/10 text-[#FF6B00]/60 font-mono text-[10px] tracking-tight italic rounded-lg" : "bg-[#0a0a0a] border-white/5 text-white/80 group-hover:border-white/20 rounded-2xl rounded-tl-none shadow-lg")}>
                        {msg.role === 'assistant' && (
                           <div className="absolute -right-6 -top-6 grayscale opacity-20 pointer-events-none overflow-hidden h-16 w-16 border border-white/10 rounded-2xl rotate-12 group-hover:rotate-0 transition-transform bg-black">
                              <img src={`https://picsum.photos/seed/${selectedAgent.name}/200/200`} alt="" className="w-full h-full object-cover" referrerPolicy="no-referrer" />
                           </div>
                        )}
                        <span className="text-[13px] font-medium leading-[1.6] uppercase tracking-[0.02em] whitespace-pre-wrap">{msg.content}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Split/Preview/Browser Overlay Panel */}
          {viewMode !== 'chat' && (
            <div className={cn(
              "h-full border-l border-white/10 bg-[#0d0d0d] relative transition-all duration-700 overflow-hidden",
              viewMode === 'split' ? "w-1/2 shadow-[-40px_0_60px_rgba(0,0,0,0.5)]" : "flex-1"
            )}>
               <div className="absolute inset-0 flex flex-col">
                  {/* Internal Tab Bar for the Active Mode */}
                  <div className="h-12 flex items-center px-6 bg-black/40 border-b border-white/5 justify-between shrink-0">
                     <div className="flex items-center gap-3">
                        {viewMode === 'preview' ? <Monitor className="h-3.5 w-3.5 text-[#FF6B00]" /> : <Globe className="h-3.5 w-3.5 text-[#FF6B00]" />}
                        <div className="flex flex-col">
                           <span className="text-[10px] font-black uppercase tracking-widest text-white/80 italic">{viewMode === 'preview' ? 'Live_Preview' : 'Internal_Browse'}</span>
                           <span className="text-[8px] font-bold text-white/20 uppercase tracking-widest">{viewMode === 'preview' ? 'v1.2.0-beta' : 'secure.sandbox.ham'}</span>
                        </div>
                     </div>
                     <button onClick={() => setViewMode('chat')} className="p-1.5 hover:bg-white/5 rounded text-white/20 hover:text-white transition-colors">
                        <X className="h-4 w-4" />
                     </button>
                  </div>

                  {/* Mode Content Content */}
                  <div className="flex-1 bg-black flex items-center justify-center p-12 text-center group">
                     <div className="absolute inset-0 opacity-[0.03] pointer-events-none" 
                          style={{ backgroundImage: 'radial-gradient(circle, #fff 1px, transparent 1px)', backgroundSize: '16px 16px' }} />
                     
                     <div className="space-y-6 relative z-10 max-w-sm focus-within:ring-0">
                        <div className="h-24 w-24 bg-white/[0.02] border border-white/10 rounded-[2.5rem] mx-auto flex items-center justify-center group-hover:border-[#FF6B00]/40 transition-all duration-500 group-hover:rotate-12">
                           {viewMode === 'preview' ? <Monitor className="h-10 w-10 text-white/10 group-hover:text-[#FF6B00]/40" /> : <Globe className="h-10 w-10 text-white/10 group-hover:text-[#FF6B00]/40" />}
                        </div>
                        <div className="space-y-2">
                           <p className="text-[12px] font-black text-white/40 uppercase tracking-[0.4em] italic leading-tight">Waiting for Deployment Directive</p>
                           <p className="text-[10px] font-bold text-white/10 uppercase tracking-widest leading-relaxed">
                              {viewMode === 'preview' 
                                ? "Direct the droid workforce to generate a previewable endpoint for this session."
                                : "The sandbox browser is currently offline. Initiate web browsing task to connect."}
                           </p>
                        </div>
                        <div className="pt-4 h-8 animate-pulse text-[#FF6B00]/20 font-mono text-[10px]">SYSTEM_IDLE_BYPASS_MODE_OFF</div>
                     </div>
                  </div>
               </div>
            </div>
          )}
        </div>

        {/* COMPOSER Interface */}
        <div className="px-12 pb-10 pt-4 bg-gradient-to-t from-black via-black/95 to-transparent relative z-30">
          <div className="max-w-3xl mx-auto space-y-4">
             {chatError ? (
               <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-[11px] font-bold uppercase tracking-widest text-destructive">
                 <AlertCircle className="h-4 w-4 shrink-0" />
                 {chatError}
               </div>
             ) : null}
             {/* Integrated Context Chips (Compact display) */}
             <div className="flex items-center gap-2 animate-in slide-in-from-bottom-2 duration-500 overflow-x-auto scrollbar-hide">
                <div className="flex items-center gap-3 px-3 py-1.5 bg-white/[0.05] border border-white/10 rounded-lg text-white/40 group shrink-0">
                   <User className="h-3 w-3 text-[#FF6B00]" />
                   <span className="text-[9px] font-black uppercase tracking-widest">{selectedAgent.name}</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-white/[0.02] border border-white/5 rounded-lg text-white/20 shrink-0">
                   <Cpu className="h-3 w-3" />
                   <span className="text-[9px] font-black uppercase tracking-widest">{selectedAgent.model}</span>
                </div>
                {selectedAgent.assignedTools && selectedAgent.assignedTools.length > 0 && (
                   <div className="flex items-center gap-2 px-3 py-1.5 bg-white/[0.02] border border-white/5 rounded-lg text-white/20 shrink-0">
                      <ToyBrick className="h-3 w-3" />
                      <span className="text-[9px] font-black uppercase tracking-widest">{selectedAgent.assignedTools.length} Tools</span>
                   </div>
                )}
             </div>

             <form onSubmit={handleSend} className="relative group shadow-2xl">
                <div className="absolute -inset-1 bg-gradient-to-r from-[#FF6B00]/20 to-[#FF6B00]/5 rounded-2xl blur opacity-20 group-focus-within:opacity-80 transition duration-700" />
                <div className="relative bg-[#0d0d0d] border border-white/10 rounded-xl overflow-hidden shadow-2xl">
                   <div className="flex flex-col">
                      <div className="flex items-start px-6 pt-5 pb-3 gap-5">
                         <Terminal className="h-5 w-5 text-[#FF6B00]/60 mt-0.5 shrink-0" />
                         <textarea 
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                void handleSend(e as unknown as React.FormEvent);
                              }
                            }}
                            placeholder="Direct the workforce or press / for system commands..."
                            className="flex-1 bg-transparent border-none outline-none text-white text-[14px] font-bold uppercase tracking-[0.05em] placeholder:text-white/10 resize-none min-h-[60px] max-h-[200px] leading-relaxed"
                         />
                      </div>

                      <div className="flex h-12 items-center px-6 bg-white/[0.02] border-t border-white/5 justify-between">
                         <div className="flex items-center gap-6">
                            <button type="button" className="flex items-center gap-2 text-[9px] text-white/20 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors p-2">
                               <Paperclip className="h-3.5 w-3.5" />
                               Attach
                            </button>
                            <button type="button" className="flex items-center gap-2 text-[9px] text-white/20 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors p-2">
                               <Zap className="h-3.5 w-3.5" />
                               Fast
                            </button>
                            <div className="h-4 w-px bg-white/5" />
                            <div className={cn("flex items-center gap-2 text-[9px] font-black uppercase tracking-widest italic transition-colors", selectedAgent.keyConnected ? "text-green-500/40" : "text-red-500/40")}>
                               <Shield className="h-3 w-3" />
                               {selectedAgent.keyConnected ? "Connected" : "Unlinked"}
                            </div>
                         </div>

                         <div className="flex items-center gap-4">
                            <button type="submit" disabled={sending} className="flex items-center gap-3 px-8 py-2 bg-[#FF6B00] text-black text-[11px] font-black uppercase tracking-widest hover:bg-[#FF6B00]/80 transition-all rounded-lg shadow-lg hover:shadow-[#FF6B00]/20 disabled:opacity-50 disabled:pointer-events-none">
                               <Send className="h-4 w-4" />
                               {sending ? "Sending…" : "Execute"}
                            </button>
                         </div>
                      </div>
                   </div>
                </div>
             </form>
          </div>
        </div>
      </div>
    </div>
  );
}
