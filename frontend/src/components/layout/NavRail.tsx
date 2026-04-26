import { useState, useRef, useEffect } from "react";
import { 
  MessageSquare, 
  Activity, 
  Settings, 
  ScrollText,
  BarChart2,
  SlidersHorizontal,
  ShoppingBag,
  UserCog,
  Orbit,
  Layers,
  History,
  Cpu,
  Sparkles,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import { publicAssetUrl } from "@/lib/ham/publicAssets";
import { primaryChatPath } from "@/features/hermes-workspace/workspaceFlags";

/** Match exact path or a child sub-route, without treating unrelated prefixes as active. */
function isPrimaryPathActive(path: string, pathname: string): boolean {
  if (path === "/") return pathname === "/";
  return pathname === path || pathname.startsWith(`${path}/`);
}

export function NavRail() {
  const location = useLocation();
  const navigate = useNavigate();
  const isDesktop = isHamDesktopShell();
  const logoSrc = publicAssetUrl("ham-logo.png");
  const chatPath = primaryChatPath();
  const homePath = isDesktop ? chatPath : "/";
  const primaryNav = [
    { icon: MessageSquare, label: "Chat", path: chatPath },
    { icon: Cpu, label: "Command Center", path: "/command-center" },
    { icon: Activity, label: "Activity", path: "/activity" },
    { icon: ShoppingBag, label: "Capabilities", path: "/shop" },
    { icon: UserCog, label: "Agents", path: "/agents" },
  ];
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState(false);
  const diagnosticsRef = useRef<HTMLDivElement>(null);

  const isDiagnosticsActive =
    location.pathname.startsWith("/hermes") ||
    location.pathname.startsWith("/runs") ||
    location.pathname.startsWith("/skills") ||
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
    <div className="flex h-full w-[64px] shrink-0 flex-col items-center border-r border-[color:var(--ham-workspace-line)] bg-[#030a10]/85 py-5 backdrop-blur-md transition-colors z-50">
      <Link
        to={homePath}
        className="mb-8 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#c45c12]/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[#030a10]"
        title={isDesktop ? "Ham — chat" : "Ham — home"}
        aria-label={isDesktop ? "Open chat" : "Return to landing page"}
      >
        <img
          src={logoSrc}
          alt=""
          className="h-7 w-7 object-contain brightness-0 invert opacity-90 pointer-events-none"
        />
      </Link>

      <div className="flex flex-1 flex-col gap-3.5">
        {primaryNav.map((item) => {
          const isActive = isPrimaryPathActive(item.path, location.pathname);
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "group relative rounded-lg p-2.5 transition-colors",
                isActive
                  ? "bg-white/[0.07] text-[#e8eef8]"
                  : "text-white/32 hover:bg-white/[0.05] hover:text-white/85"
              )}
              title={item.label}
            >
              <item.icon className="h-5 w-5" strokeWidth={isActive ? 1.75 : 1.5} />
              {isActive && (
                <div className="absolute left-[-1px] top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-[#c45c12]/90" />
              )}
            </Link>
          );
        })}
      </div>

      <div className="mt-auto flex flex-col items-center gap-4">
        <div className="relative flex flex-col gap-3.5" ref={diagnosticsRef}>
          <button
            type="button"
            onClick={() => setIsDiagnosticsOpen(!isDiagnosticsOpen)}
            className={cn(
              "group relative rounded-lg p-2.5 transition-colors",
              isDiagnosticsActive || isDiagnosticsOpen
                ? "bg-white/[0.08] text-[#e8eef8]"
                : "text-white/32 hover:bg-white/[0.05] hover:text-white/85"
            )}
            title="Diagnostics"
            aria-label="Open Diagnostics menu"
            aria-expanded={isDiagnosticsOpen}
          >
            <SlidersHorizontal className="h-5 w-5" strokeWidth={1.5} />
          </button>

          {isDiagnosticsOpen && (
            <div className="absolute left-full top-[-6px] z-[100] ml-2.5 w-56 overflow-hidden rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/95 py-1.5 shadow-[0_12px_40px_rgba(0,0,0,0.45)] backdrop-blur-md animate-in fade-in slide-in-from-left-2 duration-200">
              {[
                { label: "Hermes details", path: "/hermes", icon: Orbit },
                { label: "Skills catalog", path: "/skills", icon: Sparkles },
                { label: "Run history", path: "/runs", icon: History },
                { label: "Control-plane", path: "/control-plane", icon: Layers },
                { label: "Analytics", path: "/analytics", icon: BarChart2 },
                { label: "Logs", path: "/logs", icon: ScrollText },
              ].map((item) => {
                const isActive =
                  item.path === "/runs"
                    ? location.pathname.startsWith("/runs")
                    : item.path === "/hermes"
                      ? location.pathname.startsWith("/hermes")
                      : item.path === "/skills"
                        ? location.pathname.startsWith("/skills")
                        : location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setIsDiagnosticsOpen(false)}
                    className={cn(
                      "group relative flex cursor-pointer items-center gap-2.5 px-3 py-2.5 transition-colors",
                      isActive
                        ? "bg-white/[0.05] text-[#ffb27a]"
                        : "text-white/45 hover:bg-white/[0.04] hover:text-[#e8eef8]"
                    )}
                  >
                    {isActive && <div className="absolute bottom-0.5 left-0 top-0.5 w-px bg-[#c45c12]/80" />}
                    <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                    <span className="text-[10px] font-semibold uppercase leading-snug tracking-[0.12em]">
                      {item.label}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              if (location.pathname.startsWith("/settings")) {
                navigate("/command-center");
              } else {
                navigate("/settings");
              }
            }}
            className={cn(
              "group relative rounded-lg p-2.5 transition-colors",
              location.pathname.startsWith("/settings")
                ? "bg-white/[0.08] text-[#e8eef8]"
                : "text-white/32 hover:bg-white/[0.05] hover:text-white/85",
            )}
            title={
              location.pathname.startsWith("/settings")
                ? "Back to Command Center"
                : "Settings"
            }
            aria-label={
              location.pathname.startsWith("/settings")
                ? "Back to Command Center"
                : "Open settings"
            }
          >
            <Settings className="h-5 w-5" strokeWidth={1.5} />
            {location.pathname.startsWith("/settings") && (
              <div className="absolute left-[-1px] top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-[#c45c12]/90" />
            )}
          </button>
        </div>
        
        <div className="cursor-pointer p-2.5 opacity-40 grayscale transition-opacity contrast-125 hover:opacity-100">
          <img 
            src="https://picsum.photos/seed/aaron/100/100" 
            alt="User" 
            className="h-6 w-6 rounded-full border border-[color:var(--ham-workspace-line)]" 
            referrerPolicy="no-referrer"
          />
        </div>
      </div>
    </div>
  );
}
