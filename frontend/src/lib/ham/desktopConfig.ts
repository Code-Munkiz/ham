/**
 * Desktop shell (Electron) injects `window.__HAM_DESKTOP_CONFIG__` via preload.
 * Web builds never set this — keep product logic HTTP-first; Phase 2 adds more surface here.
 */

export type HamDesktopPublicConfig = {
  /** Ham API origin only (no path, no `/api` suffix). Empty/absent = use Vite env + dev proxy rules. */
  apiBase?: string;
  /** Use HashRouter for file:// or static loads where BrowserRouter breaks. */
  useHashRouter?: boolean;
  /** Set by main for debugging; renderer may ignore. */
  loadMode?: string;
};

declare global {
  interface Window {
    __HAM_DESKTOP_CONFIG__?: HamDesktopPublicConfig;
  }
}

export function getHamDesktopConfig(): HamDesktopPublicConfig | null {
  if (typeof window === "undefined") return null;
  const cfg = window.__HAM_DESKTOP_CONFIG__;
  if (!cfg || typeof cfg !== "object") return null;
  return cfg;
}

export function isHamDesktopShell(): boolean {
  return getHamDesktopConfig() !== null;
}
