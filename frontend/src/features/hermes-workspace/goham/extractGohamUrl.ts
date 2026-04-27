/**
 * GoHAM Mode v0: extract a single http(s) URL from user chat text.
 * Accepts explicit `http(s)://…` or a bare hostname (`google.com`, `www.example.com/path`).
 * Does not validate reachability — desktop local control validates navigation policy.
 */

const URL_IN_TEXT = /\b(https?:\/\/[^\s<>"'`)}\]]+)/i;

/** Hostname + optional port + optional path — no scheme (we assume https). */
const BARE_HOST_IN_TEXT =
  /\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d{1,5})?(?:\/[^\s<>"'`)}\]]*)?)\b/i;

function looksLikeBareHostCandidate(hostPart: string): boolean {
  const h = hostPart.split("/")[0]?.split(":")[0]?.toLowerCase() ?? "";
  if (!h.includes(".")) return false;
  if (h === "localhost" || h.endsWith(".local")) return false;
  return true;
}

export function extractGohamUrl(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const explicit = URL_IN_TEXT.exec(trimmed);
  if (explicit?.[1]) {
    try {
      const u = new URL(explicit[1]);
      if (u.protocol !== "http:" && u.protocol !== "https:") return null;
      return u.toString();
    } catch {
      return null;
    }
  }
  const bare = BARE_HOST_IN_TEXT.exec(trimmed);
  if (!bare?.[1]) return null;
  const raw = bare[1].replace(/\/+$/u, "");
  if (!looksLikeBareHostCandidate(raw)) return null;
  try {
    const u = new URL(`https://${raw}`);
    if (u.protocol !== "https:") return null;
    if (!u.hostname.includes(".")) return null;
    return u.toString();
  } catch {
    return null;
  }
}

/** Strip query/hash for action-trail display (no secrets in query). */
export function redactUrlForTrail(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 52 ? `${u.pathname.slice(0, 52)}…` : u.pathname;
    return `${u.origin}${path}`;
  } catch {
    return "(invalid URL)";
  }
}
