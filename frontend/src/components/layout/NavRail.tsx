import { useState, useRef, useEffect } from "react";
import { 
  MessageSquare, 
  Activity, 
  Users, 
  Settings, 
  ScrollText,
  BarChart2,
  SlidersHorizontal,
  Sparkles,
  UserCog,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

const primaryNav = [
  { icon: MessageSquare, label: "Chat", path: "/chat" },
  { icon: Activity, label: "Activity", path: "/overview" },
  { icon: Users, label: "Droids", path: "/droids" },
  { icon: UserCog, label: "Agents", path: "/agents" },
  { icon: Sparkles, label: "Skills", path: "/skills" },
];

export function NavRail() {
  const location = useLocation();
  const navigate = useNavigate();
  const [isOpsOpen, setIsOpsOpen] = useState(false);
  const opsRef = useRef<HTMLDivElement>(null);

  const isOpsActive =
    location.pathname === "/analytics" || location.pathname === "/logs";

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (opsRef.current && !opsRef.current.contains(event.target as Node)) {
        setIsOpsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="w-[64px] h-full flex flex-col items-center py-6 bg-[#000000] border-r border-white/5 z-50 transition-colors shrink-0">
      <Link
        to="/"
        className="mb-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/55 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
        title="Ham — home"
        aria-label="Return to landing page"
      >
        <img
          src="/ham-logo.png"
          alt=""
          className="h-7 w-7 object-contain brightness-0 invert opacity-90 pointer-events-none"
        />
      </Link>

      <div className="flex-1 flex flex-col gap-5">
        {primaryNav.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "group relative p-3 rounded-xl transition-all",
                isActive ? "bg-white/10 text-[#FF6B00]" : "text-white/20 hover:text-white hover:bg-white/5"
              )}
              title={item.label}
            >
              <item.icon className="h-5 w-5" />
              {isActive && (
                <div className="absolute left-[-12px] top-1/2 -translate-y-1/2 w-1 h-6 bg-[#FF6B00] rounded-r-full shadow-[0_0_8px_#FF6B00]" />
              )}
            </Link>
          );
        })}
      </div>

      <div className="mt-auto flex flex-col gap-5 items-center">
        <div className="flex flex-col gap-5 relative" ref={opsRef}>
          {/* Ops Popover Trigger */}
          <button
            onClick={() => setIsOpsOpen(!isOpsOpen)}
            className={cn(
              "group relative p-3 rounded-xl transition-all",
              isOpsActive || isOpsOpen ? "bg-white/10 text-[#FF6B00]" : "text-white/20 hover:text-white hover:bg-white/5"
            )}
            title="Ops"
          >
            <SlidersHorizontal className="h-5 w-5" />
          </button>

          {/* Ops Popover */}
          {isOpsOpen && (
            <div className="absolute left-full ml-3 top-[-10px] w-48 bg-[#0a0a0a] border border-white/10 rounded-xl shadow-2xl py-2 overflow-hidden z-[100] animate-in fade-in slide-in-from-left-2 duration-200">
              {[
                { label: "Analytics", path: "/analytics", icon: BarChart2 },
                { label: "Logs", path: "/logs", icon: ScrollText },
              ].map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setIsOpsOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 transition-all cursor-pointer group relative",
                      isActive ? "text-[#FF6B00] bg-[#FF6B00]/5" : "text-white/40 hover:bg-[#FF6B00]/5 hover:text-[#FF6B00]"
                    )}
                  >
                    {isActive && <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-[#FF6B00]" />}
                    <item.icon className="h-4 w-4" />
                    <span className="text-[10px] font-black uppercase tracking-widest">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              if (location.pathname.startsWith("/settings")) {
                navigate("/overview");
              } else {
                navigate("/settings");
              }
            }}
            className={cn(
              "group relative p-3 rounded-xl transition-all",
              location.pathname.startsWith("/settings")
                ? "bg-white/10 text-[#FF6B00]"
                : "text-white/20 hover:text-white hover:bg-white/5",
            )}
            title={
              location.pathname.startsWith("/settings")
                ? "Back to Activity"
                : "Settings"
            }
          >
            <Settings className="h-5 w-5" />
            {location.pathname.startsWith("/settings") && (
              <div className="absolute left-[-12px] top-1/2 -translate-y-1/2 w-1 h-6 bg-[#FF6B00] rounded-r-full shadow-[0_0_8px_#FF6B00]" />
            )}
          </button>
        </div>
        
        <div className="p-3 grayscale contrast-125 opacity-30 hover:opacity-100 transition-opacity cursor-pointer">
          <img 
            src="https://picsum.photos/seed/aaron/100/100" 
            alt="User" 
            className="h-6 w-6 rounded-full border border-white/20" 
            referrerPolicy="no-referrer"
          />
        </div>
      </div>
    </div>
  );
}
