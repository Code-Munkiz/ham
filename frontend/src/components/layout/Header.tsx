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
        'overview': 'LIVE ACTIVITY',
        'runs': 'HISTORY',
        'activity': 'ACTIVITY STREAM',
        'extensions': 'TOOLS',
        'settings': 'SETTINGS',
        'advanced': 'SYSTEM'
      };
      return mapping[s] || s.toUpperCase();
    })];
  };

  if (location.pathname.startsWith("/chat")) return null;

  return (
    <header className="flex h-12 items-center justify-between px-6 bg-[#080808] border-b border-white/5 sticky top-0 z-40 transition-colors shrink-0">
      <div className="flex items-center gap-4 text-[10px] font-bold uppercase tracking-widest text-white/40">
        {getPath().map((seg, i) => (
          <React.Fragment key={seg}>
            <span className={cn(i === getPath().length - 1 ? "text-[#FF6B00]" : "text-white/20")}>{seg}</span>
            {i < getPath().length - 1 && <span className="text-white/10 opacity-50">/</span>}
          </React.Fragment>
        ))}
      </div>
      
      <div className="flex items-center gap-6">
        <button 
          onClick={() => setIsControlPanelOpen(!isControlPanelOpen)}
          className={cn(
            "flex items-center gap-2 group transition-all",
            isControlPanelOpen ? "text-[#FF6B00]" : "text-white/40 hover:text-white"
          )}
        >
          <Activity className="h-3.5 w-3.5" />
          <span className="text-[10px] font-black uppercase tracking-widest leading-none">Control Panel</span>
          <ChevronDown className={cn("h-3 w-3 transition-transform", isControlPanelOpen ? "rotate-180" : "")} />
        </button>

        <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-white/5 border border-white/10 rounded text-[9px] font-mono text-white/40 cursor-text">
          <Search className="h-3 w-3" />
          <span>Quick Open (CMD+P)</span>
        </div>

        <div className="flex items-center gap-6 border-l border-white/10 pl-6 h-6">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] shadow-[0_0_8px_#FF6B00]" />
            <span className="text-[10px] uppercase font-black text-[#FF6B00]/60 tracking-widest italic">Ready</span>
          </div>
          
          <button 
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="text-white/20 hover:text-white transition-colors"
          >
            {mounted && (theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />)}
          </button>
        </div>
      </div>
    </header>
  );
}
