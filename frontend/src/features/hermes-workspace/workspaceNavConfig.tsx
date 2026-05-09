import type { LucideIcon } from "lucide-react";
import {
  Bot,
  Briefcase,
  CheckSquare,
  LayoutDashboard,
  Library,
  MessageSquare,
  Network,
  Share2,
  FolderOpen,
  Settings,
  Waypoints,
  Terminal,
  UserCircle,
  Wrench,
  Brain,
} from "lucide-react";

export type MainNavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };

/**
 * Hermes Workspace IA: persistent primary rail (Chat, Social, Coding agents) + Library flyout.
 * `/workspace` index redirects to `/workspace/chat`. `/workspace/projects` lives under Library (first item).
 */
export const primaryRailItems: MainNavItem[] = [
  { to: "/workspace/chat", label: "Chat", icon: MessageSquare },
  { to: "/workspace/social", label: "Social", icon: Share2 },
  { to: "/workspace/coding-agents", label: "Coding agents", icon: Bot },
];

export const settingsRailItem: MainNavItem = {
  to: "/workspace/settings",
  label: "Settings",
  icon: Settings,
};

export const libraryRailMeta = { label: "Library", icon: Library } as const;

/** Library flyout — Projects first, then operator surfaces (routes unchanged). */
export const libraryNavItems: MainNavItem[] = [
  { to: "/workspace/projects", label: "Projects", icon: LayoutDashboard, end: true },
  { to: "/workspace/files", label: "Files", icon: FolderOpen },
  { to: "/workspace/terminal", label: "Terminal", icon: Terminal },
  { to: "/workspace/jobs", label: "Jobs", icon: Briefcase },
  { to: "/workspace/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/workspace/conductor", label: "Conductor", icon: Waypoints },
  { to: "/workspace/operations", label: "Operations", icon: Network },
];

/** Linked from Settings side nav; not in the primary rail. */
export const knowledgeSettingsLinks: MainNavItem[] = [
  { to: "/workspace/memory", label: "Memory", icon: Brain },
  { to: "/workspace/skills", label: "Skills", icon: Wrench },
  { to: "/workspace/profiles", label: "Profiles", icon: UserCircle },
];

export function pathMatchesLibraryRoute(pathname: string): boolean {
  for (const item of libraryNavItems) {
    if (pathname === item.to || pathname.startsWith(`${item.to}/`)) return true;
  }
  return false;
}

export function pathMatchesSettingsRail(pathname: string): boolean {
  if (pathname === "/workspace/settings" || pathname.startsWith("/workspace/settings/")) {
    return true;
  }
  for (const item of knowledgeSettingsLinks) {
    if (pathname === item.to || pathname.startsWith(`${item.to}/`)) return true;
  }
  return false;
}

const MOBILE_TITLE_RULES: { test: (p: string) => boolean; title: string }[] = [
  {
    test: (p) => p === "/workspace/projects" || p.startsWith("/workspace/projects/"),
    title: "Projects",
  },
  { test: (p) => p === "/workspace/chat" || p.startsWith("/workspace/chat/"), title: "Chat" },
  { test: (p) => p === "/workspace/files" || p.startsWith("/workspace/files/"), title: "Files" },
  {
    test: (p) => p === "/workspace/terminal" || p.startsWith("/workspace/terminal/"),
    title: "Terminal",
  },
  { test: (p) => p === "/workspace/jobs" || p.startsWith("/workspace/jobs/"), title: "Jobs" },
  { test: (p) => p === "/workspace/tasks" || p.startsWith("/workspace/tasks/"), title: "Tasks" },
  {
    test: (p) => p === "/workspace/conductor" || p.startsWith("/workspace/conductor/"),
    title: "Conductor",
  },
  {
    test: (p) => p === "/workspace/operations" || p.startsWith("/workspace/operations/"),
    title: "Operations",
  },
  {
    test: (p) => p === "/workspace/coding-agents" || p.startsWith("/workspace/coding-agents/"),
    title: "Coding agents",
  },
  { test: (p) => p === "/workspace/social" || p.startsWith("/workspace/social/"), title: "Social" },
  { test: (p) => p === "/workspace/memory" || p.startsWith("/workspace/memory/"), title: "Memory" },
  { test: (p) => p === "/workspace/skills" || p.startsWith("/workspace/skills/"), title: "Skills" },
  {
    test: (p) => p === "/workspace/profiles" || p.startsWith("/workspace/profiles/"),
    title: "Profiles",
  },
  {
    test: (p) => p === "/workspace/settings" || p.startsWith("/workspace/settings/"),
    title: "Settings",
  },
];

/**
 * Mobile header title for the current `/workspace/*` path.
 */
export function workspacePathTitle(pathname: string): string {
  for (const { test, title } of MOBILE_TITLE_RULES) {
    if (test(pathname)) return title;
  }
  if (pathname === "/workspace" || pathname === "/workspace/") return "Chat";
  return "Workspace";
}
