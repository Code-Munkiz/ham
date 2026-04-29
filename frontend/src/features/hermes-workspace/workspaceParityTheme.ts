import type { CSSProperties } from "react";

/**
 * Upstream: `src/screens/agents/operations-screen.tsx` + `src/screens/gateway/conductor.tsx` THEME_STYLE.
 * Values adjusted for the dark HAM workspace shell; keys match var(--theme-*) used in repomix.
 */
export const HWS_PARITY_THEME: CSSProperties = {
  ["--theme-bg" as string]: "#0a0f14",
  ["--theme-card" as string]: "rgba(0,0,0,0.32)",
  ["--theme-card2" as string]: "rgba(255,255,255,0.06)",
  ["--theme-border" as string]: "rgba(255,255,255,0.12)",
  ["--theme-border2" as string]: "rgba(255,255,255,0.2)",
  ["--theme-text" as string]: "#e8edf7",
  ["--theme-muted" as string]: "#9ca3af",
  ["--theme-muted-2" as string]: "#94a3b8",
  ["--theme-accent" as string]: "#10b981",
  ["--theme-accent-strong" as string]: "#059669",
  ["--theme-accent-soft" as string]: "color-mix(in srgb, #10b981 12%, transparent)",
  ["--theme-accent-soft-strong" as string]: "color-mix(in srgb, #10b981 18%, transparent)",
  ["--theme-shadow" as string]: "rgba(0,0,0,0.45)",
  ["--theme-danger" as string]: "#dc2626",
  ["--theme-danger-soft" as string]: "color-mix(in srgb, #dc2626 12%, transparent)",
  ["--theme-danger-border" as string]: "color-mix(in srgb, #dc2626 35%, white)",
  ["--theme-warning" as string]: "#d97706",
  ["--theme-warning-soft" as string]: "color-mix(in srgb, #d97706 12%, transparent)",
  ["--theme-warning-border" as string]: "color-mix(in srgb, #d97706 35%, white)",
};
