/**
 * Session list copy for the workspace sidebar — Hermes repomix uses friendly times and
 * short “ID xxxxxxxx” only when needed; HAM list API gives preview + ISO `created_at`.
 */

const dayFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

/** `created_at` from API (ISO). Same-day → time; else month + day (repomix session-item pattern). */
export function formatSessionListTime(iso: string | null | undefined): string {
  if (!iso?.trim()) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return (sameDay ? timeFormatter : dayFormatter).format(date);
}

export function sessionCardTitle(preview: string | null | undefined): string {
  const t = (preview ?? "").trim();
  return t || "New chat";
}

/**
 * One subtitle line: turn count + last activity time. No raw ISO, no full UUID
 * (IDs stay in the URL for routing only).
 */
export function sessionCardSubtitle(turnCount: number, createdAt: string | null | undefined): string {
  const parts: string[] = [];
  if (turnCount > 0) {
    parts.push(`${turnCount} turn${turnCount === 1 ? "" : "s"}`);
  }
  const t = formatSessionListTime(createdAt ?? null);
  if (t) {
    parts.push(t);
  }
  return parts.join(" · ");
}
