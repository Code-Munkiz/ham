/**
 * Resolve `public/` assets for both web (absolute `/…`) and packaged desktop (`file://` + Vite `base: ./`).
 */
export function publicAssetUrl(filename: string): string {
  const name = filename.replace(/^\//, "");
  const base = (import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
  return `${base}${name}`;
}
