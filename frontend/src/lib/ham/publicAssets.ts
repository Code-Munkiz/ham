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
 * Same `ham-landing.png` portrait as the landing “Enter Ham” hero for visual consistency.
 * Do not use `ham-logo.png` with CSS filters for these surfaces — that reads as a flat/wrong mark in production.
 */
export const HAM_WORKSPACE_LOGO_FILE = "ham-landing.png" as const;

export function hamWorkspaceLogoUrl(): string {
  return publicAssetUrl(HAM_WORKSPACE_LOGO_FILE);
}
