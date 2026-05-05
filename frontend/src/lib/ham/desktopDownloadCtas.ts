/**
 * Landing download tile types driven by `public/desktop-downloads.json`
 * (+ embedded twin `desktop-downloads.manifest.json`); see `desktopDownloadsManifest.ts`.
 */

export type DesktopPlatform = "linux" | "windows" | "macos";

export type DesktopDownloadCta = {
  platform: DesktopPlatform;
  /** Short button label, e.g. "Windows" */
  label: string;
  /** Absolute URL to a published artifact. Ignored when `available` is false. */
  href: string;
  /** When false, landing shows a disabled platform control (no link). */
  available: boolean;
  /** Optional hint under the button (e.g. format or arch). */
  subtext?: string;
  /** GitHub Releases tag page or installer page (for verify links). */
  releaseUrl?: string;
  /** Full SHA-256 for the primary download when known. */
  checksumHex?: string;
};
