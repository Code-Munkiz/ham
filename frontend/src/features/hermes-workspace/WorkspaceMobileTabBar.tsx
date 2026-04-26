import * as React from "react";
import { NavLink, matchPath, useLocation } from "react-router-dom";
import {
  Brain,
  Briefcase,
  Command,
  FolderOpen,
  Home,
  MessageSquare,
  Settings,
  UserCircle,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";

const MOBILE_TABS: { to: string; label: string; end?: boolean; icon: React.ElementType }[] = [
  { to: "/workspace", label: "Home", end: true, icon: Home },
  { to: "/workspace/chat", label: "Chat", icon: MessageSquare },
  { to: "/workspace/files", label: "Files", icon: FolderOpen },
  { to: "/workspace/terminal", label: "Term", icon: Command },
  { to: "/workspace/jobs", label: "Jobs", icon: Briefcase },
  { to: "/workspace/memory", label: "Mem", icon: Brain },
  { to: "/workspace/skills", label: "Skills", icon: Wrench },
  { to: "/workspace/profiles", label: "Prof", icon: UserCircle },
  { to: "/settings", label: "Set", icon: Settings },
];

/** SHELL-009 — pattern from upstream `mobile-tab-bar.tsx` (hidden on chat routes). */
export function WorkspaceMobileTabBar() {
  const { pathname } = useLocation();
  const isOnChat = pathname === "/workspace/chat" || pathname.startsWith("/workspace/chat/");

  if (isOnChat) {
    return null;
  }

  return (
    <nav
      className="hww-mtab fixed bottom-0 left-0 right-0 z-40 border-t border-[color:var(--ham-workspace-line)] bg-[#040a10]/95 pb-[max(env(safe-area-inset-bottom,0px),2px)] pt-0.5 backdrop-blur-sm md:hidden"
      aria-label="Workspace mobile navigation"
    >
      <ul className="flex max-w-full items-stretch justify-start gap-0.5 overflow-x-auto px-0.5">
        {MOBILE_TABS.map((item) => {
          const IC = item.icon;
          const isActive = Boolean(
            matchPath({ path: item.to, end: item.end ?? false }, pathname),
          );
          return (
            <li key={item.to} className="shrink-0">
              <NavLink
                to={item.to}
                end={item.end ?? false}
                className={cn(
                  "flex h-12 min-w-14 flex-col items-center justify-center gap-0.5 rounded-lg px-1.5 text-[8px] font-medium",
                  isActive ? "text-[#ffb27a]" : "text-white/40 hover:text-white/65",
                )}
              >
                <IC
                  className={cn("h-[18px] w-[18px] shrink-0", isActive ? "opacity-100" : "opacity-70")}
                  strokeWidth={1.5}
                />
                <span className="max-w-14 truncate">{item.label}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
