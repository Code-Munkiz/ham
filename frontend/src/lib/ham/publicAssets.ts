/**
 * Resolve `public/` assets for both web (absolute `/…`) and packaged desktop (`file://` + Vite `base: ./`).
 */
export function publicAssetUrl(filename: string): string {
  const name = filename.replace(/^\//, "");
  const base = (import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
  return `${base}${name}`;
}

/**
 * Single canonical HAM product mark for workspace shell, chat chrome, empty states, and floating launcher.
 * Do not use `ham-logo.png` with CSS filters for these surfaces — that reads as a flat/wrong mark in production.
 * Marketing hero on `/` may still use `ham-landing.png` via `publicAssetUrl` directly.
 */
export const HAM_WORKSPACE_LOGO_FILE = "ham-app-moon.png" as const;

export function hamWorkspaceLogoUrl(): string {
  return publicAssetUrl(HAM_WORKSPACE_LOGO_FILE);
}
