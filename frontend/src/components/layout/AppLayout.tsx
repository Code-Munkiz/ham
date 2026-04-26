import * as React from "react";
import { Header } from "./Header";
import { NavRail } from "./NavRail";
import { Toaster } from "sonner";
import { cn } from "@/lib/utils";
import { Info, User, Shield, Activity, Cpu, ToyBrick, Eye, X, Monitor, Terminal, MessageSquare } from "lucide-react";
import { useLocation } from "react-router-dom";

import { useAgent } from "@/lib/ham/AgentContext";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";
import { useHamDeploymentAccess } from "@/lib/ham/ClerkAccessBridge";

import { ControlPanelOverlay } from "../workspace/ControlPanelOverlay";
import { HamDeploymentRestrictedBanner } from "./HamDeploymentRestrictedBanner";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { agents, selectedAgentId } = useAgent();
  const { activeTask, setActiveTask, isControlPanelOpen, setIsControlPanelOpen } = useWorkspace();
  const { restricted: hamDeploymentRestricted } = useHamDeploymentAccess();

  const selectedAgent = agents.find(a => a.id === selectedAgentId) || agents[0];
  const isBareLanding = location.pathname === "/";
  const isChatPage = location.pathname.startsWith("/chat");
  const isSettingsPage = location.pathname.startsWith("/settings");
  // Control state for the global workbench console
  const [isConsoleOpen, setIsConsoleOpen] = React.useState(false);

  // Workbench Modes
  const [viewMode, setViewMode] = React.useState<'chat' | 'preview' | 'split'>('chat');

  // Preview/split collapses the main route to w-0; reset when leaving workbench routes that use that layout.
  React.useEffect(() => {
    if (isSettingsPage || isChatPage) {
      setViewMode('chat');
    }
  }, [isSettingsPage, isChatPage]);

  // Web marketing landing only — desktop shell redirects `/` → `/chat` and never shows this layout.
  if (isBareLanding && !isHamDesktopShell()) {
    return (
      <>
        <HamDeploymentRestrictedBanner show={hamDeploymentRestricted} />
        {children}
        <Toaster theme="dark" position="bottom-right" closeButton richColors />
      </>
    );
  }

  // Route-scoped immersive layout: `/chat` owns the full workspace canvas.
  // Keep providers/auth/runtime seams; hide old HAM shell chrome only on chat.
  if (isChatPage) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#030b11] text-foreground transition-colors duration-300 relative font-sans">
        <HamDeploymentRestrictedBanner show={hamDeploymentRestricted} />
        <div className="h-full w-full min-h-0 min-w-0 overflow-hidden">
          {children}
        </div>
        <Toaster theme="dark" position="bottom-right" closeButton richColors />
        <ControlPanelOverlay
          isOpen={isControlPanelOpen}
          onClose={() => setIsControlPanelOpen(false)}
          activeTask={activeTask}
          onTaskChange={setActiveTask}
          selectedAgent={selectedAgent}
        />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-[#080808] text-foreground transition-colors duration-300 selection:bg-primary/30 relative font-sans">
      {/* Primary Navigation Rail */}
      <NavRail />
      
      {/* No global secondary sidebar: settings uses `UnifiedSettings` internal nav; other routes are single-column. */}
      
      <div className="flex flex-col flex-1 overflow-hidden relative">
        <Header />
        <HamDeploymentRestrictedBanner show={hamDeploymentRestricted} />

        <div className="flex flex-1 overflow-hidden relative">
          <main className="flex-1 overflow-hidden relative flex flex-col">
            <div className="flex-1 overflow-hidden relative">
              {/* Dynamic Workbench Layout — for `/chat`, layout/split is owned by `Chat.tsx` only; this block is for non-chat routes when preview/split is used here. */}
              <div className={cn(
                "h-full w-full flex transition-all duration-500",
                viewMode === 'split' ? "gap-px bg-white/5" : ""
              )}>
                {/* Chat Layer */}
                <div className={cn(
                  "transition-all duration-500 overflow-hidden",
                  viewMode === 'preview' ? "w-0 opacity-0" : 
                  viewMode === 'split' ? "w-1/2" : "w-full"
                )}>
                  {children}
                </div>

                {/* Preview Layer */}
                {(viewMode === 'preview' || viewMode === 'split') && (
                  <div className={cn(
                    "transition-all duration-500 bg-[#0d0d0d] relative",
                    viewMode === 'preview' ? "flex-1" : "w-1/2"
                  )}>
                    <div className="absolute inset-0 flex flex-col">
                      <div className="h-10 flex items-center px-4 bg-black/40 border-b border-white/5 justify-between">
                        <div className="flex items-center gap-3">
                          <Eye className="h-3 w-3 text-[#FF6B00]" />
                          <span className="text-[9px] font-black uppercase tracking-widest text-white/40">Live Preview</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setViewMode('chat')} className="p-1 hover:bg-white/10 rounded text-white/20">
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      <div className="flex-1 bg-[#111] flex items-center justify-center relative group">
                        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(#ffffff_1px,transparent_1px)] [background-size:20px_20px]" />
                        <div className="text-center space-y-4 relative z-10">
                          <div className="h-20 w-20 bg-white/[0.02] border border-white/5 rounded-3xl mx-auto flex items-center justify-center">
                            <Monitor className="h-8 w-8 text-white/10" />
                          </div>
                          <div>
                            <p className="text-[10px] font-black text-white/20 uppercase tracking-[0.3em]">No Active Deployment</p>
                            <p className="text-[9px] font-bold text-white/5 uppercase tracking-widest mt-1 italic">No active preview session.</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </main>
        </div>
        
        {/* Global Console Drawer (Overlaying the bottom strip) */}
        {isConsoleOpen && (
          <div className="absolute bottom-8 inset-x-0 h-64 bg-[#0a0a0a] border-t border-white/10 z-[80] animate-in slide-in-from-bottom duration-300 flex flex-col font-mono">
            <div className="h-8 flex items-center px-4 bg-black/60 border-b border-white/5 justify-between shrink-0">
               <div className="flex items-center gap-2">
                  <Terminal className="h-3 w-3 text-[#FF6B00]" />
                  <span className="text-[9px] font-black uppercase tracking-widest text-white/40 italic">System Kernel Console</span>
               </div>
               <button onClick={() => setIsConsoleOpen(false)} className="hover:text-white text-white/20">
                  <X className="h-3 w-3" />
               </button>
            </div>
            <div className="flex-1 p-4 overflow-y-auto space-y-1 text-[10px] text-white/30 lowercase tracking-tight">
               <p className="text-[#FF6B00]/40">[OK] industrial_tunnel_link_established: 127.0.0.1:9092</p>
               <p>[INFO] sync_pulse: workspace idle (05/05)</p>
               <p>[INFO] cache_flush: successful in 12ms</p>
               <p className="text-white/10 font-bold uppercase tracking-widest pt-2">» waiting for mission directive...</p>
            </div>
          </div>
        )}

        {/* Bottom Utility Strip */}
        <div className="h-8 bg-black border-t border-white/5 flex items-center px-4 justify-between transition-colors shrink-0 z-[90] relative">
          <div className="flex items-center gap-6">
             <button 
                onClick={() => setIsConsoleOpen(!isConsoleOpen)}
                className={cn(
                  "flex items-center gap-2 px-2 h-full hover:bg-white/5 transition-colors group",
                  isConsoleOpen ? "text-[#FF6B00]" : "text-white/20 hover:text-white/40"
                )}
             >
                <Terminal className="h-3 w-3" />
                <span className="text-[9px] font-black uppercase tracking-widest">Toggle Console</span>
             </button>

             <div className="flex items-center gap-2 border-l border-white/5 pl-4">
                <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] animate-pulse" />
                <span className="text-[9px] font-black uppercase tracking-[0.2em] text-white/40">Workspace Ready</span>
             </div>
             <span className="text-[9px] font-mono text-white/10 uppercase italic hidden sm:inline">Workspace synchronized</span>
          </div>
          <div className="flex items-center gap-4">
             <span className="text-[9px] font-mono text-white/10 uppercase tracking-widest group cursor-default">v2.5.0 STABLE</span>
             <span className="text-[9px] font-mono text-white/10 uppercase tracking-[0.2em]">Connected</span>
          </div>
        </div>
      </div>
      
      <Toaster theme="dark" position="bottom-right" closeButton richColors />
      
      {/* Global Control Panel Overlay */}
      <ControlPanelOverlay 
        isOpen={isControlPanelOpen}
        onClose={() => setIsControlPanelOpen(false)}
        activeTask={activeTask}
        onTaskChange={setActiveTask}
        selectedAgent={selectedAgent}
      />
    </div>
  );
}
