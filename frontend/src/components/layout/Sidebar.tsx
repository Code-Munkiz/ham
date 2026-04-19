import { 
  MessageSquare,
  History as HistoryIcon, 
  Settings as SettingsIcon, 
  Activity as ActivityIcon,
  Layers,
  Database,
  Terminal,
  Shield,
  Users,
  ToyBrick,
  Store,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  Menu,
  Sparkles,
  Command,
  Plus,
  Palette,
  Eye,
  Wand2,
  Key,
  Puzzle,
  Cpu
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Link, useLocation } from "react-router-dom";
import * as React from "react";

export function Sidebar({ isVisible, onToggle, className, hideHeader = false }: { isVisible: boolean, onToggle?: () => void, className?: string, hideHeader?: boolean }) {
  const location = useLocation();

  if (!isVisible) return null;

  const getContextTitle = () => {
    const path = location.pathname;
    if (path.startsWith("/chat")) return "CONVERSATIONS";
    if (path === "/") return "MISSION DECK";
    if (path.startsWith("/droids")) return "CREW SETUP";
    if (path.startsWith("/avatar")) return "STYLE MODS";
    if (path.startsWith("/settings") || path.startsWith("/extensions")) return "INTEGRATIONS";
    if (path.startsWith("/advanced") || path.startsWith("/runs") || path.startsWith("/storage") || path.startsWith("/activity") || path.startsWith("/profiles")) return "CORE SYSTEM";
    return "NAVIGATOR";
  };

  const renderContext = () => {
    const path = location.pathname;
    
    // 1. CHAT CONTEXT
    if (path.startsWith("/chat")) {
      return (
        <div className="space-y-8 animate-in fade-in duration-300">
           <div className="px-4 space-y-4 pt-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Recent Threads</h3>
              <nav className="space-y-px">
                 {["Authentication Flow", "Bridge RPC Refactor", "UI Design System", "Marketplace API"].map((thread) => (
                   <div key={thread} className="flex items-center justify-between group px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg">
                      <div className="flex items-center gap-3">
                         <MessageSquare className="h-3.5 w-3.5 text-white/10 group-hover:text-[#FF6B00]" />
                         <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-tight">{thread}</span>
                      </div>
                   </div>
                 ))}
              </nav>
           </div>
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Workspace Sessions</h3>
              <nav className="space-y-px">
                 {["Project Arch", "Core Workforce"].map((session) => (
                   <div key={session} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg text-white/20 hover:text-white/60">
                      <Command className="h-3.5 w-3.5" />
                      <span className="text-[11px] font-bold uppercase tracking-widest">{session}</span>
                   </div>
                 ))}
                 <div className="flex items-center gap-3 px-4 py-3 text-[#FF6B00]/40 hover:text-[#FF6B00] transition-colors cursor-pointer">
                    <Plus className="h-3.5 w-3.5" />
                    <span className="text-[10px] font-black uppercase tracking-widest">New Session</span>
                 </div>
              </nav>
           </div>
        </div>
      );
    }

    // 2. ACTIVITY CONTEXT (Missions)
    if (path === "/") {
      return (
        <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-300">
           <div className="px-4 space-y-4 pt-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Filters</h3>
              <nav className="space-y-px">
                 {[
                   { label: "My Active Jobs", icon: ActivityIcon, color: "text-[#FF6B00]" },
                   { label: "Team Jobs", icon: Users, color: "text-white/40" },
                   { label: "Completed Jobs", icon: Store, color: "text-white/40" },
                 ].map((item) => (
                   <div key={item.label} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg group">
                      <item.icon className={cn("h-3.5 w-3.5 transition-colors", item.color)} />
                      <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-widest">{item.label}</span>
                   </div>
                 ))}
              </nav>
           </div>
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Categories</h3>
              <div className="grid grid-cols-2 gap-2 px-4">
                 {["Research", "Security", "Dev", "QA"].map(f => (
                   <button key={f} className="p-2 border border-white/5 bg-white/[0.02] text-[9px] font-black uppercase tracking-widest text-white/20 hover:border-[#FF6B00]/40 hover:text-white transition-all rounded">
                      {f}
                   </button>
                 ))}
              </div>
           </div>
        </div>
      );
    }

    // 3. DROIDS CONTEXT
    if (path.startsWith("/droids")) {
      return (
        <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-300">
           <div className="px-4 space-y-6 pt-4">
              <div className="px-4">
                 <div className="flex p-0.5 bg-white/[0.02] border border-white/5 rounded-md">
                    <button className="flex-1 py-1.5 text-[8px] font-black uppercase tracking-widest bg-white/5 text-white/80 rounded-sm">Project Crew</button>
                    <button className="flex-1 py-1.5 text-[8px] font-black uppercase tracking-widest text-white/20 hover:text-white/40">All Droids</button>
                 </div>
              </div>
              
              <div className="space-y-4">
                 <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Active Crew</h3>
                 <nav className="space-y-px">
                    {["Builder", "Researcher", "Reviewer", "QA", "Coordinator"].map((role) => (
                      <div key={role} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg group">
                         <div className="h-1.5 w-1.5 rounded-full bg-white/20 group-hover:bg-[#FF6B00]" />
                         <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-widest">{role}</span>
                      </div>
                    ))}
                 </nav>
              </div>
           </div>
        </div>
      );
    }

    // 4. AVATAR CONTEXT
    if (path.startsWith("/avatar")) {
      return (
        <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-300">
           <div className="px-4 space-y-4 pt-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Visual Mods</h3>
              <nav className="space-y-px">
                 {[
                   { label: "Style Presets", icon: Wand2 },
                   { label: "Appearance", icon: Palette },
                   { label: "Identity Sync", icon: Eye },
                 ].map((item) => (
                   <div key={item.label} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg group">
                      <item.icon className="h-3.5 w-3.5 text-white/10 group-hover:text-[#FF6B00]" />
                      <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-widest">{item.label}</span>
                   </div>
                 ))}
              </nav>
           </div>
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Saved Looks</h3>
              <div className="px-4">
                 <div className="p-4 border border-dashed border-white/5 rounded-lg bg-white/[0.01] text-center">
                    <p className="text-[9px] font-bold text-white/10 uppercase tracking-widest leading-relaxed italic">No saved looks yet. Save a look from your identity stack.</p>
                 </div>
              </div>
           </div>
        </div>
      );
    }

    // 5. SETTINGS CONTEXT
    if (path.startsWith("/settings") || path.startsWith("/extensions")) {
      return (
        <div className="space-y-8 animate-in fade-in duration-300 pt-4">
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Core Setup</h3>
              <nav className="space-y-px">
                 {[
                   { label: "API Keys", icon: Key, path: "/settings" },
                   { label: "Tools", icon: Puzzle, path: "/extensions" },
                   { label: "Providers", icon: Users, path: "/settings" },
                   { label: "Databases", icon: Database, path: "/storage" },
                 ].map((item) => (
                   <Link key={item.label} to={item.path} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg group">
                      <item.icon className="h-3.5 w-3.5 text-white/10 group-hover:text-[#FF6B00]" />
                      <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-tight tracking-widest">{item.label}</span>
                   </Link>
                 ))}
              </nav>
           </div>
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Preferences</h3>
              <nav className="space-y-px">
                 {["Account", "Notifications", "Security"].map(item => (
                   <div key={item} className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/10 hover:text-white/40 transition-colors cursor-pointer">
                      {item}
                   </div>
                 ))}
              </nav>
           </div>
        </div>
      );
    }

    // 6. ADVANCED CONTEXT
    if (path.startsWith("/advanced") || path.startsWith("/runs") || path.startsWith("/activity") || path.startsWith("/profiles") || path.startsWith("/storage")) {
      return (
        <div className="space-y-8 animate-in fade-in duration-300 pt-4">
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">System Ops</h3>
              <nav className="space-y-px">
                 {[
                   { label: "Mission History", icon: HistoryIcon, path: "/runs" },
                   { label: "System Logs", icon: ActivityIcon, path: "/activity" },
                   { label: "Diagnostics", icon: Cpu, path: "/advanced" },
                   { label: "Workforce Profiles", icon: Layers, path: "/profiles" },
                 ].map((item) => (
                   <Link key={item.label} to={item.path} className="flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer rounded-lg group">
                      <item.icon className="h-3.5 w-3.5 text-white/10 group-hover:text-[#FF6B00]" />
                      <span className="text-[11px] font-bold text-white/40 group-hover:text-white uppercase tracking-widest">{item.label}</span>
                   </Link>
                 ))}
              </nav>
           </div>
           <div className="px-4 space-y-4">
              <h3 className="px-4 text-[9px] font-black uppercase tracking-[0.4em] text-white/20 italic">Debug Tools</h3>
              <nav className="space-y-px">
                 {["Shell Access", "Context Audit", "Bridge Dump"].map(item => (
                   <div key={item} className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00]/40 hover:text-[#FF6B00] transition-colors cursor-pointer">
                      {item}
                   </div>
                 ))}
              </nav>
           </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div className={cn(
      "flex h-screen flex-col bg-[#0d0d0d] transition-all duration-300 z-40 font-sans relative shrink-0",
      !className && "w-60 border-r border-white/5",
      className
    )}>
      {!hideHeader && (
        <div className="flex h-12 items-center px-8 border-b border-white/5 bg-black/40 justify-between">
          <span className="text-[10px] font-black tracking-[0.3em] text-white/40 uppercase italic truncate">{getContextTitle()}</span>
          {onToggle && (
            <button onClick={onToggle} className="text-white/20 hover:text-white transition-colors shrink-0">
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {renderContext()}
      </div>
    </div>
  );
}
