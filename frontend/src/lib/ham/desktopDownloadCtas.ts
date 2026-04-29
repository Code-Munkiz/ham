/**
 * Landing download tile types driven by `public/desktop-downloads.json`
 * (+ embedded twin `desktop-downloads.manifest.json`); see `desktopDownloadsManifest.ts`.
 * Repo packaging notes still apply separately (Linux electron pipeline vs published AppImages in manifest).
 */

export type DesktopPlatform = "linux" | "windows" | "macos";

export type DesktopDownloadCta = {
  platform: DesktopPlatform;
  /** Short button label, e.g. "Linux" */
  label: string;
  /** Absolute URL to a published artifact. Ignored when `available` is false. */
  href: string;
  /** When false, UI shows a non-navigating "Coming soon" control. */
  available: boolean;
  /** Optional hint under the button (e.g. format or arch). */
  subtext?: string;
  /** GitHub Releases tag page or installer page (for verify links). */
  releaseUrl?: string;
  /** Full SHA-256 for the primary download when known. */
  checksumHex?: string;
};
