/**
 * Narrow, client-side intent for chat-native Cloud Agent handoff (preview + explicit launch only).
 * Avoids treating general coding questions as launch requests.
 *
 * On match, Chat routes to `runChatNativeHandoffPreview` → `cursor_agent_preview` → mission card
 * (no auto-launch; launch only from card + token).
 */

/** Legacy / product-specific phrases (unchanged behavior). */
const HANDOFF_LINE_PATTERNS_LEGACY: RegExp[] = [
  /\buse\s+a\s+cloud\s+agent\b/i,
  /\blaunch\s+a\s+cloud\s+agent\b/i,
  /\brun\s+this\s+with\s+cloud\s+agent\b/i,
  /\bhave\s+cloud\s+agent\b/i,
  /\bmanaged\s+by\s+ham\b/i,
];

/**
 * Natural Cloud Agent preview triggers (case-insensitive).
 * Explicit Cursor wording and shorter “cloud agent” phrases all route to the same preview flow.
 */
const HANDOFF_LINE_PATTERNS_NATURAL: RegExp[] = [
  /\bcursor\s+cloud\s+agents?\b/i,
  /\buse\s+(the\s+)?cursor\s+cloud\s+agents?\b/i,
  /\bfire\s+up\s+(the\s+)?cursor\s+cloud\s+agents?\b/i,
  /\bcloud\s+agents?\b/i,
  /\buse\s+(the\s+)?cloud\s+agents?\b/i,
  /\bfire\s+up\s+(the\s+)?cloud\s+agents?\b/i,
];

const HANDOFF_LINE_PATTERNS: RegExp[] = [
  ...HANDOFF_LINE_PATTERNS_NATURAL,
  ...HANDOFF_LINE_PATTERNS_LEGACY,
];

/** Allow short utterances like “cloud agent” (11 chars) while still ignoring empty noise. */
const MIN_LEN = 8;

/**
 * True when the user asks for a Cloud Agent / Cursor Cloud Agent handoff in natural language.
 */
export function isCloudAgentHandoffRequest(text: string): boolean {
  const t = text.trim();
  if (t.length < MIN_LEN) return false;
  return HANDOFF_LINE_PATTERNS.some((p) => p.test(t));
}

/** One-line label for the mission card title (inferred, not an LLM). */
export function inferCloudHandoffMissionTitle(utterance: string, max = 72): string {
  const t = utterance.replace(/\s+/g, " ").trim();
  if (!t) return "Cloud Agent mission";
  const one = t.split(/(?<=[.!?\n])/)[0]?.trim() || t;
  return one.length > max ? `${one.slice(0, max - 1)}…` : one;
}

/** Prefer "New instruction" line when task is stitched follow-up. */
export function inferMissionTitleForCard(cursorTaskPrompt: string, max = 72): string {
  const raw = cursorTaskPrompt.replace(/\r\n/g, "\n");
  const m = raw.match(/New instruction:\s*([\s\S]+?)\s*$/m);
  if (m) {
    return inferCloudHandoffMissionTitle(m[1].trim(), max);
  }
  return inferCloudHandoffMissionTitle(raw, max);
}
