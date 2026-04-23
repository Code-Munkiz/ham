/**
 * Desktop install CTAs for the landing page. Keep in sync with real release artifacts only.
 * When `available` is true, set a real `href` (installer or GitHub Releases asset).
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
};

/**
 * M1 ships the Electron shell in-repo; packaged installers are not published yet.
 * Flip `available` + set `href` when GitHub Releases (or similar) hosts real artifacts.
 */
export const HAM_DESKTOP_DOWNLOAD_CTAS: DesktopDownloadCta[] = [
  {
    platform: "linux",
    label: "Linux",
    href: "",
    available: false,
    subtext: "Pop!_OS · Ubuntu-class",
  },
  {
    platform: "windows",
    label: "Windows",
    href: "",
    available: false,
    subtext: "x64",
  },
  {
    platform: "macos",
    label: "macOS",
    href: "",
    available: false,
    subtext: "Apple silicon & Intel",
  },
];
