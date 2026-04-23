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

/** Linux artifact: GitHub Release `desktop-v0.1.2` (AppImage x64). */
export const HAM_DESKTOP_DOWNLOAD_CTAS: DesktopDownloadCta[] = [
  {
    platform: "linux",
    label: "Linux",
    href: "https://github.com/Code-Munkiz/ham/releases/download/desktop-v0.1.2/HAM.Desktop-0.1.2.AppImage",
    available: true,
    subtext: "AppImage · x64 · v0.1.2",
  },
  {
    platform: "windows",
    label: "Windows",
    href: "https://github.com/Code-Munkiz/ham/releases/download/desktop-v0.1.2/HAM-Desktop-0.1.2-Win-x64-Portable.exe",
    available: true,
    subtext: "Portable · x64 · v0.1.2",
  },
  {
    platform: "macos",
    label: "macOS",
    href: "",
    available: false,
    subtext: "Apple silicon & Intel",
  },
];
