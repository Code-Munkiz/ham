/** Browser opens the Cursor SaaS Agent page — no Cursor Provider API keys or REST calls from HAM frontend. */

const BC_AGENT_PREFIX = /^bc-/i;

/** Cursor Cloud Agents use identifiers like `bc-…` (hosted agent id). */
export function isBcCursorAgentId(raw: string | null | undefined): boolean {
  const s = String(raw || "").trim();
  if (!s.startsWith("bc-") && !s.startsWith("BC-")) return false;
  // Exclude empty / trivial tokens after prefix
  const rest = s.slice(3).trim();
  if (!rest || rest.length < 4) return false;
  // Allow alphanumeric, underscore, hyphen in tail (Cursor formats evolve)
  return /^[A-Za-z0-9_-]+$/.test(rest);
}

/** Public agent deep link (navigation only). */
export function cursorCloudAgentWebHref(agentId: string): string {
  const id = agentId.trim();
  return `https://cursor.com/agents/${encodeURIComponent(id)}?app=code`;
}
