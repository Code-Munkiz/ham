import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  Box,
  Brain,
  Layers,
  Calendar,
  FileSearch,
  HardDrive,
  Key,
  Languages,
  MessageSquare,
  Mic,
  Monitor,
  Network,
  Orbit,
  Palette,
  Server,
  Zap,
} from "lucide-react";
import {
  type SettingsSubSectionId,
  normalizeSettingsTabParam,
} from "@/components/workspace/UnifiedSettings";

/** URL `tab` values for `/workspace/settings?tab=…` (upstream slugs and HAM subsection ids). */
export type WorkspaceSettingsUrlSlug = string;

export type WorkspaceSettingsNavTarget =
  | { type: "unified"; section: SettingsSubSectionId }
  | { type: "bridge"; key: string };

export type WorkspaceSettingsNavItem = {
  id: WorkspaceSettingsUrlSlug;
  label: string;
  icon: LucideIcon;
  target: WorkspaceSettingsNavTarget;
  group: "core" | "system";
};

const BRIDGE = (key: string) => ({ type: "bridge" as const, key });
const U = (section: SettingsSubSectionId) => ({ type: "unified" as const, section });

/**
 * Upstream-style IA: core list mirrors `SETTINGS_NAV_ITEMS` / settings-sidebar patterns
 * (Hermes repomix). System group = remaining HAM `UnifiedSettings` subsections. Bridge
 * rows show a placeholder where HAM has no full upstream-equivalent yet.
 */
export const WORKSPACE_SETTINGS_NAV: WorkspaceSettingsNavItem[] = [
  { id: "connection", label: "Connection", icon: Key, target: U("api-keys"), group: "core" },
  { id: "model", label: "Model & provider", icon: Brain, target: U("context-memory"), group: "core" },
  { id: "environment", label: "Environment", icon: Server, target: U("environment"), group: "core" },
  { id: "mcp", label: "MCP servers", icon: Network, target: U("tools-extensions"), group: "core" },
  { id: "providers", label: "Providers", icon: Layers, target: BRIDGE("providers"), group: "core" },
  { id: "desktop", label: "Desktop", icon: Monitor, target: U("desktop-bundle"), group: "core" },
  { id: "language", label: "Language", icon: Languages, target: BRIDGE("language"), group: "core" },
  { id: "appearance", label: "Appearance", icon: Palette, target: BRIDGE("appearance"), group: "core" },
  { id: "chat", label: "Chat", icon: MessageSquare, target: BRIDGE("chat"), group: "core" },
  { id: "notifications", label: "Notifications", icon: Bell, target: BRIDGE("notifications"), group: "core" },
  { id: "voice", label: "Voice", icon: Mic, target: BRIDGE("voice"), group: "core" },
  { id: "hermes", label: "Hermes", icon: Orbit, target: BRIDGE("hermes"), group: "core" },
  { id: "execution-history", label: "Execution history", icon: BookOpen, target: U("execution-history"), group: "system" },
  { id: "system-logs", label: "System logs", icon: Activity, target: U("system-logs"), group: "system" },
  { id: "diagnostics", label: "Diagnostics", icon: BarChart3, target: U("diagnostics"), group: "system" },
  { id: "kernel-health", label: "Kernel health", icon: Zap, target: U("kernel-health"), group: "system" },
  { id: "context-audit", label: "Context audit", icon: FileSearch, target: U("context-audit"), group: "system" },
  { id: "bridge-dump", label: "Bridge dump", icon: HardDrive, target: U("bridge-dump"), group: "system" },
  { id: "resource-storage", label: "Resource storage", icon: Box, target: U("resource-storage"), group: "system" },
  { id: "jobs", label: "Jobs", icon: Calendar, target: U("jobs"), group: "system" },
];

const NAV_BY_ID = new Map(WORKSPACE_SETTINGS_NAV.map((i) => [i.id, i]));

const SLUG_BY_SECTION = new Map<SettingsSubSectionId, string>();
for (const row of WORKSPACE_SETTINGS_NAV) {
  if (row.target.type === "unified" && !SLUG_BY_SECTION.has(row.target.section)) {
    SLUG_BY_SECTION.set(row.target.section, row.id);
  }
}

const ALL_SUBSECTIONS = new Set<SettingsSubSectionId>(
  [
    "api-keys",
    "environment",
    "tools-extensions",
    "context-memory",
    "desktop-bundle",
    "execution-history",
    "system-logs",
    "diagnostics",
    "kernel-health",
    "context-audit",
    "bridge-dump",
    "resource-storage",
    "jobs",
  ],
);

/**
 * If `tab` is a raw HAM `SettingsSubSectionId` (e.g. old bookmarks `?tab=api-keys`),
 * return the best upstream-style slug. Otherwise return `tab` unchanged.
 */
function canonicalizeWorkspaceSettingsSlug(tab: string): string {
  if (NAV_BY_ID.has(tab)) return tab;
  const norm = normalizeSettingsTabParam(tab);
  if (ALL_SUBSECTIONS.has(norm)) {
    return SLUG_BY_SECTION.get(norm) ?? norm;
  }
  return tab;
}

export type WorkspaceSettingsResolvedView =
  | { kind: "unified"; section: SettingsSubSectionId; slug: string }
  | { kind: "bridge"; key: string; slug: string };

const DEFAULT_SLUG = "connection";

/**
 * Resolves the active `/workspace/settings?tab=…` value to either a
 * `UnifiedSettings` section or a bridge placeholder. Unknown values fall
 * back to `connection`.
 */
export function resolveWorkspaceSettingsView(raw: string | null | undefined): WorkspaceSettingsResolvedView {
  const tab = (raw ?? "").trim() || DEFAULT_SLUG;
  const slug = canonicalizeWorkspaceSettingsSlug(tab);
  const row = NAV_BY_ID.get(slug);
  if (row) {
    if (row.target.type === "unified") {
      return { kind: "unified", section: row.target.section, slug: row.id };
    }
    return { kind: "bridge", key: row.target.key, slug: row.id };
  }
  if (ALL_SUBSECTIONS.has(tab as SettingsSubSectionId)) {
    const id = tab as SettingsSubSectionId;
    return { kind: "unified", section: id, slug: SLUG_BY_SECTION.get(id) ?? id };
  }
  return { kind: "unified", section: "api-keys", slug: DEFAULT_SLUG };
}

/**
 * When `UnifiedSettings` changes the active HAM section, set the query `tab=`
 * to a stable, upstream-shaped slug.
 */
export function settingsSectionToWorkspaceUrlSlug(section: SettingsSubSectionId): string {
  return SLUG_BY_SECTION.get(section) ?? section;
}

export function getDefaultWorkspaceSettingsSlug(): string {
  return DEFAULT_SLUG;
}
