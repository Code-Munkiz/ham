/**
 * Canonical download metadata for landing + Electron update checks (mirrors `public/desktop-downloads.json`).
 * Update that JSON when releasing new desktop artifacts — `desktop/package.json` may run ahead until a GitHub tagged build exists.
 */
import { publicAssetUrl } from "@/lib/ham/publicAssets";
import type { DesktopDownloadCta, DesktopPlatform } from "@/lib/ham/desktopDownloadCtas";
import embeddedSnapshot from "@/lib/ham/desktop-downloads.manifest.json";

/** Bundled twin of `public/desktop-downloads.json` for instant first paint; keep in sync when publishing. */
export function embeddedParsedDesktopDownloadsManifest(): DesktopDownloadsManifest | null {
  return parseDesktopDownloadsManifest(embeddedSnapshot as unknown);
}

export type DesktopDownloadsPlatformEntry = {
  label: string;
  arch: string;
  type: string;
  version: string;
  url: string;
  sha256?: string | null;
  release_page_url?: string | null;
};

export type DesktopDownloadsManifest = {
  schema_version: number;
  channel: string;
  build_date?: string;
  distribution: string;
  summary?: string;
  platforms: {
    linux?: DesktopDownloadsPlatformEntry | null;
    windows?: DesktopDownloadsPlatformEntry | null;
    macos?: DesktopDownloadsPlatformEntry | null;
  };
};

function isPlatformEntry(raw: unknown): raw is DesktopDownloadsPlatformEntry {
  if (!raw || typeof raw !== "object") return false;
  const o = raw as Record<string, unknown>;
  return (
    typeof o.label === "string" &&
    typeof o.arch === "string" &&
    typeof o.type === "string" &&
    typeof o.version === "string" &&
    typeof o.url === "string" &&
    o.url.startsWith("https://")
  );
}

/**
 * Validates and narrows fetched JSON — safe for untrusted payloads (drops unknown fields).
 */
export function parseDesktopDownloadsManifest(raw: unknown): DesktopDownloadsManifest | null {
  if (!raw || typeof raw !== "object") return null;
  const root = raw as Record<string, unknown>;
  const schema_version = typeof root.schema_version === "number" ? root.schema_version : null;
  if (schema_version !== 1) return null;
  if (typeof root.channel !== "string" || typeof root.distribution !== "string") return null;
  if (!root.platforms || typeof root.platforms !== "object") return null;
  const plat = root.platforms as Record<string, unknown>;
  const out: DesktopDownloadsManifest = {
    schema_version: 1,
    channel: root.channel,
    distribution: root.distribution,
    build_date: typeof root.build_date === "string" ? root.build_date : undefined,
    summary: typeof root.summary === "string" ? root.summary : undefined,
    platforms: {},
  };

  function pick(key: "linux" | "windows" | "macos"): DesktopDownloadsPlatformEntry | null | false {
    const v = plat[key];
    if (v === undefined || v === null) return null;
    if (!isPlatformEntry(v)) return false;
    return {
      label: v.label,
      arch: v.arch,
      type: v.type,
      version: v.version,
      url: v.url,
      sha256: typeof v.sha256 === "string" ? v.sha256 : v.sha256 === null ? null : undefined,
      release_page_url:
        typeof v.release_page_url === "string"
          ? v.release_page_url
          : v.release_page_url === null
            ? null
            : undefined,
    };
  }

  const pLinux = pick("linux");
  const pWin = pick("windows");
  const pMac = pick("macos");
  if (pLinux === false || pWin === false || pMac === false) return null;

  out.platforms = { linux: pLinux, windows: pWin, macos: pMac };

  return out;
}

/** Build landing CTAs (Windows + macOS only; Linux is ignored for the public landing). */
export function manifestToDownloadCtas(manifest: DesktopDownloadsManifest): DesktopDownloadCta[] {
  const order: DesktopPlatform[] = ["windows", "macos"];
  return order.map((platform) => {
    const raw = manifest.platforms[platform];
    if (!raw) {
      return {
        platform,
        label: platform === "windows" ? "Windows" : "macOS",
        href: "",
        available: false,
      };
    }
    return {
      platform,
      label: raw.label || (platform === "windows" ? "Windows" : "macOS"),
      href: raw.url,
      available: true,
      subtext: [`${raw.type}`, `${raw.arch}`, `v${raw.version}`].join(" · "),
      checksumHex: raw.sha256 || undefined,
      releaseUrl: raw.release_page_url || raw.url,
    };
  });
}

export async function fetchDesktopDownloadsManifest(
  signal?: AbortSignal,
): Promise<DesktopDownloadsManifest | null> {
  const url = publicAssetUrl("desktop-downloads.json");
  try {
    const res = await fetch(url, { signal, credentials: "same-origin", cache: "no-store" });
    if (!res.ok) return null;
    const j: unknown = await res.json();
    return parseDesktopDownloadsManifest(j);
  } catch {
    return null;
  }
}
