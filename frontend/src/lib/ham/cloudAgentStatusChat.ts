/**
 * Client-only Cloud Agent mission status Q&A: no LLM; uses POST .../sync + ManagedMission fields.
 */

import type { ManagedMissionRow } from "@/lib/ham/api";

const STATUS_QUESTION_PATTERNS: RegExp[] = [/is it done/i, /did it finish/i, /what happened/i, /\bstatus\b/i];

/**
 * True when the user is asking for Cloud Agent / mission status (narrow phrase list).
 */
export function isCloudAgentStatusChatQuestion(text: string): boolean {
  const t = text.trim();
  if (t.length < 3) return false;
  return STATUS_QUESTION_PATTERNS.some((p) => p.test(t));
}

/**
 * One-line reply from persisted mission state (existing HAM fields only).
 */
export function formatManagedMissionStatusChatLine(row: ManagedMissionRow): string {
  const lc = String(row.mission_lifecycle ?? "").toLowerCase();
  const reason = String(row.status_reason_last_observed ?? "").trim();
  if (lc === "open") return "Still running.";
  if (lc === "succeeded") return "Completed.";
  if (lc === "failed") return `Failed: ${reason || "Unknown reason"}`;
  if (lc === "archived") return "Ended.";
  if (lc) return `Mission state: ${lc}.`;
  return "Mission state is not available yet.";
}
