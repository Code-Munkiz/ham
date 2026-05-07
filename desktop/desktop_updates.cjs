"use strict";

const { shell, dialog } = require("electron");

const DEFAULT_MANIFEST_URL =
  "https://raw.githubusercontent.com/Code-Munkiz/ham/main/frontend/public/desktop-downloads.json";

function isHttpsUrl(uString) {
  try {
    const u = new URL(uString);
    return u.protocol === "https:" && u.hostname.endsWith("github.com");
  } catch {
    return false;
  }
}

/**
 * Permit-list desktop download manifest fetches — same JSON as landing `desktop-downloads.json`.
 */
function isTrustedManifestURL(uString) {
  try {
    const u = new URL(uString);
    if (u.protocol !== "https:") return false;
    if (u.hostname !== "raw.githubusercontent.com") return false;
    const p = u.pathname;
    return p.startsWith("/Code-Munkiz/ham/") && p.endsWith("/desktop-downloads.json");
  } catch {
    return false;
  }
}

function manifestUrlFromEnv() {
  const raw = (process.env.HAM_DESKTOP_DOWNLOADS_MANIFEST_URL || "").trim();
  return raw || DEFAULT_MANIFEST_URL;
}

function parseSemverToken(s) {
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(String(s).trim());
  if (!m) return null;
  return [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)];
}

function semverCmp(a, b) {
  const pa = parseSemverToken(a);
  const pb = parseSemverToken(b);
  if (!pa || !pb) return null;
  for (let i = 0; i < 3; i++) {
    if (pa[i] !== pb[i]) return pa[i] < pb[i] ? -1 : 1;
  }
  return 0;
}

/** True if semver a > semver b */
function semverGt(a, b) {
  return semverCmp(a, b) === 1;
}

function isPlatformEntry(v) {
  if (!v || typeof v !== "object") return false;
  return (
    typeof v.label === "string" &&
    typeof v.arch === "string" &&
    typeof v.type === "string" &&
    typeof v.version === "string" &&
    typeof v.url === "string" &&
    v.url.startsWith("https://")
  );
}

/** @returns {object|null} */
function parseDownloadsManifest(raw) {
  if (!raw || typeof raw !== "object") return null;
  /** @type {Record<string, unknown>} */
  const root = raw;
  if (root.schema_version !== 1) return null;
  if (typeof root.channel !== "string" || typeof root.distribution !== "string") return null;
  const platRaw = root.platforms;
  if (!platRaw || typeof platRaw !== "object") return null;
  /** @type {Record<string, unknown>} */
  const plat = platRaw;

  function pick(key) {
    const v = plat[key];
    if (v === undefined || v === null) return null;
    if (!isPlatformEntry(v)) return false;
    const o = v;
    return {
      label: o.label,
      arch: o.arch,
      type: o.type,
      version: o.version,
      url: o.url,
      sha256: typeof o.sha256 === "string" ? o.sha256 : o.sha256 === null ? null : undefined,
      release_page_url:
        typeof o.release_page_url === "string"
          ? o.release_page_url
          : o.release_page_url === null
            ? null
            : undefined,
    };
  }

  const pLinux = pick("linux");
  const pWin = pick("windows");
  const pMac = pick("macos");
  if (pLinux === false || pWin === false || pMac === false) return null;

  return {
    schema_version: 1,
    channel: root.channel,
    distribution: root.distribution,
    build_date: typeof root.build_date === "string" ? root.build_date : undefined,
    summary: typeof root.summary === "string" ? root.summary : undefined,
    platforms: {
      linux: pLinux,
      windows: pWin,
      macos: pMac,
    },
  };
}

function electronPlatformKey() {
  switch (process.platform) {
    case "win32":
      return "windows";
    case "darwin":
      return "macos";
    default:
      return null;
  }
}

/**
 * Minimal update prompt: compares packaged app semver to manifest publish metadata.
 * Opens the GitHub releases page — no silent updater (see prompt / Phase C).
 *
 * @param {{ parentWindow: import('electron').BrowserWindow | null, app: import('electron').App }} opts
 */
async function runStartupDesktopUpdatePrompt(opts) {
  const { parentWindow, app } = opts;
  if (!app || typeof app.isPackaged !== "boolean") return;

  if (!app.isPackaged) {
    if ((process.env.HAM_DESKTOP_UPDATE_CHECK || "").trim() !== "1") return;
  } else if ((process.env.HAM_DESKTOP_UPDATE_CHECK || "").trim() === "0") return;

  const urlRaw = manifestUrlFromEnv();
  if (!isTrustedManifestURL(urlRaw)) {
    console.warn(
      "[ham-desktop] HAM_DESKTOP_DOWNLOADS_MANIFEST_URL ignored (not trusted) — skipping update check.",
    );
    return;
  }

  await new Promise((r) => setTimeout(r, 2500));

  let res;
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 14000);
    res = await fetch(urlRaw, { signal: ac.signal });
    clearTimeout(t);
  } catch {
    return;
  }
  if (!res.ok) return;
  /** @type {unknown} */
  let json;
  try {
    json = await res.json();
  } catch {
    return;
  }

  const manifest = parseDownloadsManifest(json);
  if (!manifest || !manifest.platforms) return;

  const key = electronPlatformKey();
  if (!key || key === "macos") return;

  const entry = manifest.platforms[key];
  if (!entry || typeof entry.version !== "string") return;

  const current = typeof app.getVersion === "function" ? String(app.getVersion()).trim() : "";
  if (!current) return;

  if (!semverGt(entry.version, current)) return;

  const publishLabel = `${entry.type} · ${entry.arch} · v${entry.version}`;
  const detail =
    `Installed: ${current}\n` +
    `Latest published (${key} · ${manifest.channel}): ${entry.version}\n\n` +
    "Update opens the release/downloads page in your browser. Replace the portable .exe manually — " +
    "this build does not download or swap binaries in the background.";

  const preferred =
    typeof entry.release_page_url === "string" && isHttpsUrl(entry.release_page_url)
      ? entry.release_page_url
      : entry.url;
  const openLink = preferred.startsWith("https://") ? preferred : "";

  /** @type {import('electron').MessageBoxSyncOptions | import('electron').MessageBoxOptions} */
  const box = {
    type: "info",
    buttons: ["Update", "Later"],
    defaultId: 0,
    cancelId: 1,
    title: "HAM Desktop",
    message: `A newer download is listed for ${key.replace("windows", "Windows")} (${publishLabel}).`,
    detail,
  };

  /** @type {import('electron').MessageBoxReturnValue} */
  const result = dialog.showMessageBoxSync(parentWindow || undefined, box);

  if (result === 1) return;
  if (!openLink) return;
  try {
    await shell.openExternal(openLink);
  } catch {
    /* ignore */
  }
}

module.exports = {
  semverGt,
  semverCmp,
  parseSemverToken,
  parseDownloadsManifest,
  isTrustedManifestURL,
  isHttpsUrl,
  runStartupDesktopUpdatePrompt,
  electronPlatformKey,
  manifestUrlFromEnv,
};
