import { Search, Sun, Moon, Activity, ChevronDown } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useTheme } from "next-themes";
import * as React from "react";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";

export function Header() {
  const location = useLocation();
  const { theme, setTheme } = useTheme();
  const { isControlPanelOpen, setIsControlPanelOpen } = useWorkspace();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);
  
  const getPath = () => {
    const segments = location.pathname.split("/").filter(Boolean);
    if (segments.length === 0) return ["HAM", "ACTIVITY"];
    return ["HAM", ...segments.map(s => {
      const mapping: Record<string, string> = {
        'command-center': 'COMMAND CENTER',
        'activity': 'ACTIVITY',
        'shop': 'CAPABILITIES',
        'hermes': 'HERMES DETAILS',
        'skills': 'SKILLS CATALOG',
        'agents': 'AGENTS',
        'storage': 'STORAGE',
        'control-plane': 'CONTROL PLANE',
        'overview': 'ACTIVITY',
        'runs': 'HISTORY',
        'extensions': 'TOOLS',
        'settings': 'SETTINGS',
        'advanced': 'SYSTEM',
        'logs': 'LOGS',
        'analytics': 'ANALYTICS',
      };
      return mapping[s] || s.toUpperCase().replace(/-/g, " ");
    })];
  };

  if (location.pathname.startsWith("/chat") || location.pathname.startsWith("/legacy-chat")) return null;

  return (
    <header className="sticky top-0 z-40 flex h-11 shrink-0 items-center justify-between border-b border-[color:var(--ham-workspace-line)] bg-[#040d14]/80 px-5 backdrop-blur-sm transition-colors">
      <div className="flex items-center gap-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/42">
        {getPath().map((seg, i) => (
          <React.Fragment key={seg}>
            <span
              className={cn(
                i === getPath().length - 1 ? "text-[#ffb27a]/95" : "text-white/28",
              )}
            >
              {seg}
            </span>
            {i < getPath().length - 1 && <span className="text-white/12">/</span>}
          </React.Fragment>
        ))}
      </div>
      
      <div className="flex items-center gap-5">
        <button 
          type="button"
          onClick={() => setIsControlPanelOpen(!isControlPanelOpen)}
          className={cn(
            "group flex items-center gap-1.5 rounded-md px-1.5 py-1 transition-colors",
            isControlPanelOpen
              ? "text-[#ffb27a]"
              : "text-white/42 hover:bg-white/[0.04] hover:text-white/90",
          )}
        >
          <Activity className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
          <span className="text-[10px] font-medium uppercase tracking-[0.1em] leading-none">Control Panel</span>
          <ChevronDown className={cn("h-3 w-3 shrink-0 transition-transform", isControlPanelOpen ? "rotate-180" : "")} strokeWidth={1.5} />
        </button>

        <div className="hidden cursor-default items-center gap-2 rounded-md border border-[color:var(--ham-workspace-line)] bg-black/25 px-2.5 py-1 text-[9px] font-mono text-white/38 md:flex">
          <Search className="h-3 w-3 opacity-70" strokeWidth={1.5} />
          <span>Quick Open (CMD+P)</span>
        </div>

        <div className="flex h-6 items-center gap-4 border-l border-[color:var(--ham-workspace-line)] pl-4">
          <div className="flex items-center gap-1.5">
            <div className="h-1 w-1 rounded-full bg-emerald-400/90 shadow-[0_0_8px_rgba(16,185,129,0.35)]" />
            <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-white/38">Ready</span>
          </div>
          
          <button 
            type="button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="rounded p-0.5 text-white/30 transition-colors hover:bg-white/[0.06] hover:text-white/90"
            aria-label="Toggle theme"
          >
            {mounted && (theme === 'dark' ? <Sun className="h-3.5 w-3.5" strokeWidth={1.5} /> : <Moon className="h-3.5 w-3.5" strokeWidth={1.5} />)}
          </button>
        </div>
      </div>
    </header>
  );
}
