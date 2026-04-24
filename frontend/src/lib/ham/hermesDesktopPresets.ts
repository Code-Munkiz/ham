/**
 * Labels for HAM Desktop allowlisted `hermes` presets (argv lives in `desktop/main.cjs` — keep ids in sync).
 */
export const HERMES_DESKTOP_PRESET_IDS = ["version", "plugins_list", "mcp_list"] as const;
export type HermesDesktopPresetId = (typeof HERMES_DESKTOP_PRESET_IDS)[number];

export const HERMES_DESKTOP_PRESET_META: Record<
  HermesDesktopPresetId,
  { label: string; commandLine: string; notes?: string }
> = {
  version: { label: "Version", commandLine: "hermes --version" },
  plugins_list: {
    label: "Plugins list",
    commandLine: "hermes plugins list",
    notes: "Non-interactive; use a terminal for full TUI menus if output is thin.",
  },
  mcp_list: {
    label: "MCP list",
    commandLine: "hermes mcp list",
    notes: "Non-interactive list; some Hermes features require a real TTY.",
  },
};
