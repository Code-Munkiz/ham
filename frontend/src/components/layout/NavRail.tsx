import { useState, useRef, useEffect } from "react";
import { 
  MessageSquare, 
  Activity, 
  Users, 
  Settings, 
  ScrollText,
  BarChart2,
  SlidersHorizontal,
  ShoppingBag,
  UserCog,
  Orbit,
  Layers,
  History,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import { publicAssetUrl } from "@/lib/ham/publicAssets";

const primaryNav = [
  { icon: MessageSquare, label: "Chat", path: "/chat" },
  { icon: Activity, label: "Activity", path: "/overview" },
  { icon: Users, label: "Droids", path: "/droids" },
  { icon: UserCog, label: "Agents", path: "/agents" },
  { icon: ShoppingBag, label: "Shop", path: "/shop" },
];

export function NavRail() {
  const location = useLocation();
  const navigate = useNavigate();
  const isDesktop = isHamDesktopShell();
  const logoSrc = publicAssetUrl("ham-logo.png");
  const homePath = isDesktop ? "/chat" : "/";
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState(false);
  const diagnosticsRef = useRef<HTMLDivElement>(null);

  const isDiagnosticsActive =
    location.pathname.startsWith("/hermes") ||
    location.pathname.startsWith("/runs") ||
    location.pathname === "/analytics" ||
    location.pathname === "/logs" ||
    location.pathname === "/control-plane";

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (diagnosticsRef.current && !diagnosticsRef.current.contains(event.target as Node)) {
        setIsDiagnosticsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="w-[64px] h-full flex flex-col items-center py-6 bg-[#000000] border-r border-white/5 z-50 transition-colors shrink-0">
      <Link
        to={homePath}
        className="mb-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg hover:bg-white/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/55 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
        title={isDesktop ? "Ham — chat" : "Ham — home"}
        aria-label={isDesktop ? "Open chat" : "Return to landing page"}
      >
        <img
          src={logoSrc}
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
        <div className="flex flex-col gap-5 relative" ref={diagnosticsRef}>
          <button
            type="button"
            onClick={() => setIsDiagnosticsOpen(!isDiagnosticsOpen)}
            className={cn(
              "group relative p-3 rounded-xl transition-all",
              isDiagnosticsActive || isDiagnosticsOpen ? "bg-white/10 text-[#FF6B00]" : "text-white/20 hover:text-white hover:bg-white/5"
            )}
            title="Diagnostics"
            aria-label="Open Diagnostics menu"
            aria-expanded={isDiagnosticsOpen}
          >
            <SlidersHorizontal className="h-5 w-5" />
          </button>

          {isDiagnosticsOpen && (
            <div className="absolute left-full ml-3 top-[-10px] w-56 bg-[#0a0a0a] border border-white/10 rounded-xl shadow-2xl py-2 overflow-hidden z-[100] animate-in fade-in slide-in-from-left-2 duration-200">
              {[
                { label: "Hermes / Runtime", path: "/hermes", icon: Orbit },
                { label: "Run history", path: "/runs", icon: History },
                { label: "Operational Analytics", path: "/analytics", icon: BarChart2 },
                { label: "Logs", path: "/logs", icon: ScrollText },
                { label: "Control-Plane Runs", path: "/control-plane", icon: Layers },
              ].map((item) => {
                const isActive =
                  item.path === "/runs"
                    ? location.pathname.startsWith("/runs")
                    : item.path === "/hermes"
                      ? location.pathname.startsWith("/hermes")
                      : location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setIsDiagnosticsOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 transition-all cursor-pointer group relative",
                      isActive ? "text-[#FF6B00] bg-[#FF6B00]/5" : "text-white/40 hover:bg-[#FF6B00]/5 hover:text-[#FF6B00]"
                    )}
                  >
                    {isActive && <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-[#FF6B00]" />}
                    <item.icon className="h-4 w-4 shrink-0" />
                    <span className="text-[10px] font-black uppercase tracking-widest leading-snug">{item.label}</span>
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
