/**
 * GoHAM Mode v0: extract a single http(s) URL from user chat text.
 * Does not validate reachability — desktop local control validates navigation policy.
 */

const URL_IN_TEXT = /\b(https?:\/\/[^\s<>"'`)}\]]+)/i;

export function extractGohamUrl(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const m = URL_IN_TEXT.exec(trimmed);
  if (!m?.[1]) return null;
  try {
    const u = new URL(m[1]);
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
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
