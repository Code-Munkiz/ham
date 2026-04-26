import type { LucideIcon } from "lucide-react";
import {
  Brain,
  Briefcase,
  CheckSquare,
  LayoutDashboard,
  MessageSquare,
  Network,
  FolderOpen,
  Settings,
  Waypoints,
  Terminal,
  UserCircle,
  Wrench,
} from "lucide-react";

export type MainNavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };
export type KnowledgeNavItem = { to: string; label: string; icon: LucideIcon };

/**
 * Hermes Workspace IA: MAIN + KNOWLEDGE routes (all under `/workspace/*`).
 * Session list in the shell is HAM-backed; other routes are placeholders or chat until further adapters.
 */
export const mainNavItems: MainNavItem[] = [
  { to: "/workspace", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/workspace/chat", label: "Chat", icon: MessageSquare },
  { to: "/workspace/files", label: "Files", icon: FolderOpen },
  { to: "/workspace/terminal", label: "Terminal", icon: Terminal },
  { to: "/workspace/jobs", label: "Jobs", icon: Briefcase },
  { to: "/workspace/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/workspace/conductor", label: "Conductor", icon: Waypoints },
  { to: "/workspace/operations", label: "Operations", icon: Network },
  { to: "/workspace/settings", label: "Settings", icon: Settings },
];

export const knowledgeNavItems: KnowledgeNavItem[] = [
  { to: "/workspace/memory", label: "Memory", icon: Brain },
  { to: "/workspace/skills", label: "Skills", icon: Wrench },
  { to: "/workspace/profiles", label: "Profiles", icon: UserCircle },
];

const MOBILE_TITLE_RULES: { test: (p: string) => boolean; title: string }[] = [
  { test: (p) => p === "/workspace/chat" || p.startsWith("/workspace/chat/"), title: "Chat" },
  { test: (p) => p === "/workspace/files" || p.startsWith("/workspace/files/"), title: "Files" },
  { test: (p) => p === "/workspace/terminal" || p.startsWith("/workspace/terminal/"), title: "Terminal" },
  { test: (p) => p === "/workspace/jobs" || p.startsWith("/workspace/jobs/"), title: "Jobs" },
  { test: (p) => p === "/workspace/tasks" || p.startsWith("/workspace/tasks/"), title: "Tasks" },
  { test: (p) => p === "/workspace/conductor" || p.startsWith("/workspace/conductor/"), title: "Conductor" },
  { test: (p) => p === "/workspace/operations" || p.startsWith("/workspace/operations/"), title: "Operations" },
  { test: (p) => p === "/workspace/memory" || p.startsWith("/workspace/memory/"), title: "Memory" },
  { test: (p) => p === "/workspace/skills" || p.startsWith("/workspace/skills/"), title: "Skills" },
  { test: (p) => p === "/workspace/profiles" || p.startsWith("/workspace/profiles/"), title: "Profiles" },
  { test: (p) => p === "/workspace/settings" || p.startsWith("/workspace/settings/"), title: "Settings" },
];

/**
 * Mobile header title for the current `/workspace/*` path.
 */
export function workspacePathTitle(pathname: string): string {
  for (const { test, title } of MOBILE_TITLE_RULES) {
    if (test(pathname)) return title;
  }
  if (pathname === "/workspace" || pathname === "/workspace/") return "Dashboard";
  return "Workspace";
}
