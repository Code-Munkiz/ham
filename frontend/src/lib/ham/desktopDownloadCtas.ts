/**
 * Desktop install CTAs for the landing page. Linux installers are not published from this repo;
 * Windows portable links may point at GitHub Release assets when `available` is true.
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

/** Linux installer CTA deprecated — packaged Linux desktop/browser-control path removed */
export const HAM_DESKTOP_DOWNLOAD_CTAS: DesktopDownloadCta[] = [
  {
    platform: "linux",
    label: "Linux",
    href: "",
    available: false,
    subtext: "Installers not published from repo — use Ham API browser features or npm start in desktop/",
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
