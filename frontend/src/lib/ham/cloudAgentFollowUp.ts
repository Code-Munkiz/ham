/**
 * Client-only stitching for a *new* Cloud Agent launch that carries short prior-mission
 * context. Does not contact the previous Cursor agent.
 */
import type { ManagedMissionSnapshot } from "@/lib/ham/types";

export type RecentMissionRef = { id: string; label?: string; t: number };

const MAX_SUMMARY_LEN = 1200;

/**
 * Build a short, non-fabricated line from polled snapshot, then recent list label, then id.
 */
export function buildPreviousWorkSummaryLine(args: {
  lastSnapshot: ManagedMissionSnapshot | null;
  activeAgentId: string | null;
  firstRecent: RecentMissionRef | null;
}): string {
  const { lastSnapshot, activeAgentId, firstRecent } = args;
  if (lastSnapshot) {
    const parts = [lastSnapshot.status, lastSnapshot.branchOrPr, lastSnapshot.progress]
      .map((s) => (s ?? "").trim())
      .filter(Boolean);
    if (parts.length) {
      const joined = parts.join(" · ");
      return joined.length > MAX_SUMMARY_LEN
        ? `${joined.slice(0, MAX_SUMMARY_LEN - 1)}…`
        : joined;
    }
  }
  const lab = firstRecent?.label?.trim();
  if (lab) {
    return lab.length > MAX_SUMMARY_LEN ? `${lab.slice(0, MAX_SUMMARY_LEN - 1)}…` : lab;
  }
  const id = (activeAgentId ?? firstRecent?.id ?? "").trim();
  if (id) {
    return `Prior mission (agent id): ${id}`;
  }
  return "Prior managed Cloud Agent work (no additional summary).";
}

/**
 * Operator `cursor_task_prompt` for follow-up: same project/repo/mode, new launch only.
 */
export function stitchCloudAgentFollowUpTask(previousSummary: string, userMessage: string): string {
  const p = previousSummary.trim() || "Prior managed Cloud Agent work.";
  const u = userMessage.trim();
  return `Previous work:\n${p}\n\nNew instruction:\n${u}`;
}
