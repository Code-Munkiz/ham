import * as React from "react";
import {
  Send,
  Paperclip,
  Sparkles,
  Shield,
  Terminal,
  MessageSquare,
  Activity,
  Zap,
  Globe,
  Monitor,
  Layout,
  ChevronDown,
  X,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ChatComposerStrip } from "@/components/chat/ChatComposerStrip";
import type { WorkbenchMode } from "@/components/chat/ChatComposerStrip";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchModelsCatalog,
  postChatStream,
} from "@/lib/ham/api";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { useAgent } from "@/lib/ham/AgentContext";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";

type ChatRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

export default function Chat() {
  const navigate = useNavigate();
  const { agents, selectedAgentId } = useAgent();
  const {
    activeTask,
    setActiveTask,
    isControlPanelOpen,
    setIsControlPanelOpen,
  } = useWorkspace();
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const [messages, setMessages] = React.useState<ChatRow[]>([]);
  const [input, setInput] = React.useState("");
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);
  const [chatError, setChatError] = React.useState<string | null>(null);

  const [catalog, setCatalog] = React.useState<ModelCatalogPayload>(CLIENT_MODEL_CATALOG_FALLBACK);
  const [catalogLoading, setCatalogLoading] = React.useState(true);
  const [workbenchMode, setWorkbenchMode] = React.useState<WorkbenchMode>("agent");
  const [modelId, setModelId] = React.useState<string | null>(null);
  const [maxMode, setMaxMode] = React.useState(false);
  const [worker, setWorker] = React.useState("builder");
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [activeAgentNote, setActiveAgentNote] = React.useState<string | null>(null);

  // Workbench Modes
  const [viewMode, setViewMode] = React.useState<"chat" | "preview" | "browser" | "split">("chat");

  React.useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    void fetchModelsCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {
        if (!cancelled) setCatalog(CLIENT_MODEL_CATALOG_FALLBACK);
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ctx = await fetchContextEngine();
        const id = await ensureProjectIdForWorkspaceRoot(ctx.cwd);
        if (!cancelled) setProjectId(id);
      } catch {
        if (!cancelled) setProjectId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!import.meta.env.DEV) {
      const raw = import.meta.env.VITE_HAM_API_BASE as string | undefined;
      if (!raw?.trim()) {
        toast.error(
          "Chat needs a Ham API URL. Set VITE_HAM_API_BASE in Vercel (or your host) and redeploy — otherwise the app calls localhost and replies never arrive.",
          { duration: 12_000, id: "ham-api-base-missing" },
        );
      }
    }
  }, []);

  const timeStr = () =>
    new Date().toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;
    const text = input.trim();
    // Preview/Web modes collapse the transcript to w-0 — user sees "nothing happens".
    setViewMode("chat");
    setInput("");
    setChatError(null);

    const userRow: ChatRow = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: timeStr(),
    };
    const assistantPlaceId = `assist-pending-${Date.now()}`;
    const assistantRow: ChatRow = {
      id: assistantPlaceId,
      role: "assistant",
      content: "",
      timestamp: timeStr(),
    };
    setMessages((prev) => [...prev, userRow, assistantRow]);

    setSending(true);
    try {
      const res = await postChatStream(
        {
          session_id: sessionId ?? undefined,
          messages: [{ role: "user", content: text }],
          ...(modelId ? { model_id: modelId } : {}),
          ...(projectId ? { project_id: projectId } : {}),
          workbench_mode: workbenchMode,
          worker,
          max_mode: maxMode,
        },
        {
          onSession: (sid) => setSessionId(sid),
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId
                  ? { ...m, content: m.content + delta }
                  : m,
              ),
            );
          },
        },
      );
      setSessionId(res.session_id);
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: timeStr(),
        })),
      );
      setActiveAgentNote(
        res.active_agent?.guidance_applied
          ? `Active agent guidance: ${res.active_agent.profile_name}`
          : null,
      );
      applyHamUiActions(res.actions ?? [], {
        navigate,
        setIsControlPanelOpen,
        isControlPanelOpen,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setChatError(msg);
      toast.error(msg, { duration: 8_000 });
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
              {activeAgentNote && (
                <span
                  className="text-[9px] font-bold text-emerald-500/80 uppercase tracking-widest truncate max-w-[min(280px,40vw)] hidden sm:inline"
                  title={activeAgentNote}
                >
                  {activeAgentNote}
                </span>
              )}
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

             <form onSubmit={handleSend} className="relative isolate group shadow-2xl">
                {/* Glow sits behind the composer; must not capture clicks or paint over controls */}
                <div
                  className="pointer-events-none absolute -inset-1 z-0 rounded-2xl bg-gradient-to-r from-[#FF6B00]/20 to-[#FF6B00]/5 opacity-20 blur transition duration-700 group-focus-within:opacity-80"
                  aria-hidden
                />
                {/* Card + strip stack above the glow; overflow visible so model/mode dropdowns are not clipped */}
                <div className="relative z-10 flex flex-col overflow-visible rounded-xl border border-white/10 bg-[#0d0d0d] shadow-2xl">
                   <div className="relative z-20 rounded-t-xl bg-black/35">
                      <ChatComposerStrip
                        workbenchMode={workbenchMode}
                        onWorkbenchMode={setWorkbenchMode}
                        modelId={modelId}
                        onModelId={setModelId}
                        maxMode={maxMode}
                        onMaxMode={setMaxMode}
                        worker={worker}
                        onWorker={setWorker}
                        toolsCount={selectedAgent.assignedTools?.length ?? 0}
                        catalog={catalog}
                        catalogLoading={catalogLoading}
                      />
                   </div>
                   <div className="flex flex-col border-t border-white/5">
                      <div className="flex items-start px-6 pt-4 pb-3 gap-3">
                         <Terminal className="h-5 w-5 text-[#FF6B00]/60 mt-1 shrink-0" />
                         <div className="flex-1 min-w-0 flex items-start gap-2">
                           <span className="text-[#FF6B00] font-mono text-[13px] font-bold mt-1.5 shrink-0 select-none">
                             &gt;_
                           </span>
                           <textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                void handleSend(e as unknown as React.FormEvent);
                              }
                            }}
                            placeholder="Initiate mission directive or press / for system commands…"
                            className="flex-1 bg-transparent border-none outline-none text-white text-[13px] font-bold uppercase tracking-[0.06em] placeholder:text-white/10 resize-none min-h-[72px] max-h-[220px] leading-relaxed"
                         />
                         </div>
                      </div>

                      <div className="flex min-h-12 items-center px-6 py-2 bg-white/[0.02] border-t border-white/5 justify-between gap-4 flex-wrap">
                         <div className="flex items-center gap-4 sm:gap-6">
                            <button type="button" className="flex items-center gap-2 text-[9px] text-white/20 hover:text-[#FF6B00] font-black uppercase tracking-widest transition-colors p-2">
                               <Paperclip className="h-3.5 w-3.5" />
                               Attach
                            </button>
                            <button
                              type="button"
                              onClick={() => setMaxMode((m) => !m)}
                              className={cn(
                                "flex items-center gap-2 text-[9px] font-black uppercase tracking-widest transition-colors p-2",
                                maxMode ? "text-[#FF6B00]" : "text-white/20 hover:text-[#FF6B00]",
                              )}
                            >
                               <Zap className="h-3.5 w-3.5" />
                               FAST MODE
                            </button>
                            <div className="h-4 w-px bg-white/5 hidden sm:block" />
                            <div
                              className={cn(
                                "flex items-center gap-2 text-[9px] font-black uppercase tracking-widest",
                                catalog?.openrouter_chat_ready ? "text-emerald-500/90" : "text-amber-500/75",
                              )}
                            >
                               <span
                                 className={cn(
                                   "h-2 w-2 rounded-full shrink-0",
                                   catalog?.openrouter_chat_ready ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]" : "bg-amber-500",
                                 )}
                               />
                               {catalog?.openrouter_chat_ready ? "CONNECTED" : "CHAT GATEWAY OFFLINE"}
                            </div>
                         </div>

                         <div className="flex items-center gap-4 ml-auto">
                            <button type="submit" disabled={sending} className="flex items-center gap-3 px-6 sm:px-8 py-2 bg-[#FF6B00] text-black text-[10px] sm:text-[11px] font-black uppercase tracking-widest hover:bg-[#FF6B00]/90 transition-all rounded-lg shadow-lg hover:shadow-[#FF6B00]/20 disabled:opacity-50 disabled:pointer-events-none">
                               <Send className="h-4 w-4" />
                               {sending ? "Sending…" : "Execute mission"}
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
