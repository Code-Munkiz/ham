/**
 * Source: repomix `src/components/settings/settings-sidebar.tsx` (upstream Hermes Workspace).
 * Route: `/settings?section=<id>` for most items; `/settings/mcp` is a separate file route
 * (see `src/routes/settings/mcp.tsx` / `index.tsx` lines using `to="/settings/mcp"` / `search={{ section }}`).
 *
 * HAM: `/workspace/settings?section=…` and `/workspace/settings/mcp`. Legacy `/workspace/settings/providers`
 * redirects to `?section=hermes` (same content as Model & provider).
 */
export type UpstreamSettingsNavId =
  | "connection"
  | "hermes"
  | "tools"
  | "usage"
  | "agent"
  | "routing"
  | "voice"
  | "display"
  | "appearance"
  | "chat"
  | "notifications"
  | "mcp"
  | "language";

/** Sections rendered by `WorkspaceSettingsBridgePanel` (read-only / bridge parity). */
export type WorkspaceSettingsBridgeSectionId = Extract<
  UpstreamSettingsNavId,
  "agent" | "routing" | "voice" | "appearance" | "chat" | "notifications" | "language"
>;

export const UPSTREAM_SETTINGS_NAV_ITEMS: ReadonlyArray<{
  id: UpstreamSettingsNavId;
  label: string;
}> = [
  { id: "connection", label: "Connection" },
  { id: "hermes", label: "Model & Provider" },
  { id: "tools", label: "Connected Tools" },
  { id: "usage", label: "Usage & Billing" },
  { id: "agent", label: "Agent Behavior" },
  { id: "routing", label: "Smart Routing" },
  { id: "voice", label: "Voice" },
  { id: "display", label: "Display" },
  { id: "appearance", label: "Appearance" },
  { id: "chat", label: "Chat" },
  { id: "notifications", label: "Notifications" },
  { id: "mcp", label: "MCP Servers" },
  { id: "language", label: "Language" },
] as const;

const VALID_IDS = new Set<string>(UPSTREAM_SETTINGS_NAV_ITEMS.map((i) => i.id));

const DEFAULT_UPSTREAM_SECTION: UpstreamSettingsNavId = "hermes";

/** repomix `src/routes/settings/index.tsx` uses `section ?? 'hermes'`. */
export function getDefaultWorkspaceSettingsSection(): UpstreamSettingsNavId {
  return DEFAULT_UPSTREAM_SECTION;
}

/**
 * `tab` from older HAM workspace builds -> upstream `section` id.
 */
const LEGACY_TAB_TO_SECTION: Record<string, UpstreamSettingsNavId> = {
  connection: "connection",
  model: "hermes",
  "api-keys": "hermes",
  "context-memory": "hermes",
  mcp: "mcp",
  "tools-extensions": "mcp",
  environment: "connection",
  desktop: "display",
  "desktop-bundle": "display",
  hermes: "hermes",
  language: "language",
  appearance: "appearance",
  chat: "chat",
  notifications: "notifications",
  voice: "voice",
  /** Old nav / bookmark may use `providers`; same as Model & provider. */
  providers: "hermes",
};

/**
 * Coerce a raw `?section=` (or older `?tab=`) to a valid upstream section id, or return default.
 */
export function parseWorkspaceSettingsSection(
  sectionRaw: string | null | undefined,
  tabRaw: string | null | undefined,
): UpstreamSettingsNavId {
  const s0 = (sectionRaw ?? "").trim();
  if (s0 && VALID_IDS.has(s0)) {
    return s0 as UpstreamSettingsNavId;
  }
  const t = (tabRaw ?? "").trim();
  if (t) {
    const m = LEGACY_TAB_TO_SECTION[t];
    if (m && VALID_IDS.has(m)) return m;
  }
  if (s0 && s0 in LEGACY_TAB_TO_SECTION) {
    const m = LEGACY_TAB_TO_SECTION[s0];
    if (m && VALID_IDS.has(m)) return m;
  }
  return DEFAULT_UPSTREAM_SECTION;
}
