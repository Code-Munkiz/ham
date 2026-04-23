import type { ManagedMissionSnapshot } from "@/lib/ham/types";

export type BuildManagedCloudAgentPromptArgs = {
  userPrompt: string;
  repository: string;
  ref?: string;
};

/**
 * Deterministic, client-only brief for managed launches. Direct mode uses the raw user prompt (unchanged).
 */
export function buildManagedCloudAgentPrompt(input: BuildManagedCloudAgentPromptArgs): string {
  const u = input.userPrompt.trim();
  const repo = input.repository.trim();
  const ref = input.ref?.trim();
  const parts = [
    "[HAM] Managed Cloud Agent mission",
    "HAM coordinates this work; the Cloud Agent implements changes in the repository below.",
    "",
    `Repository: ${repo}`,
  ];
  if (ref) parts.push(`Ref: ${ref}`);
  parts.push(
    "---",
    "User request:",
    u,
    "---",
    "Instructions: complete the user request in this repository, follow existing project conventions, keep changes focused, and use a clear commit/PR flow when applicable.",
  );
  return parts.join("\n");
}

function readString(x: unknown): string | null {
  if (typeof x === "string" && x.trim()) return x.trim();
  return null;
}

function pickFromRecord(
  o: Record<string, unknown>,
  keys: string[],
  maxLen = 240,
): string | null {
  for (const k of keys) {
    const s = readString(o[k]);
    if (s) return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s;
  }
  return null;
}

function asRecord(x: unknown): Record<string, unknown> | null {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : null;
}

function oneMessageLine(msg: unknown): string | null {
  const o = asRecord(msg);
  if (!o) return null;
  const t =
    readString(o.text) ??
    readString(o.content) ??
    readString(o.body) ??
    readString(o.message);
  if (t) return t.length > 200 ? `${t.slice(0, 199)}…` : t;
  return null;
}

/**
 * Best-effort tail from Cursor conversation JSON (shapes vary). No fabrication.
 */
function extractConversationProgress(conversation: unknown): string | null {
  if (conversation == null) return null;
  if (Array.isArray(conversation)) {
    for (let i = conversation.length - 1; i >= 0; i--) {
      const line = oneMessageLine(conversation[i]);
      if (line) return line;
    }
    return null;
  }
  const rec = asRecord(conversation);
  if (rec) {
    const nested = rec.messages ?? rec.items ?? rec.turns;
    if (nested !== undefined) return extractConversationProgress(nested);
    const t = readString(rec.text) ?? readString(rec.content) ?? readString(rec.body);
    if (t) return t.length > 200 ? `${t.slice(0, 199)}…` : t;
  }
  return null;
}

/**
 * Map proxied Cursor agent + conversation JSON into a UI snapshot. Uses "No status details from API" when nothing is inferable.
 */
export function deriveManagedMissionSnapshot(
  agent: Record<string, unknown>,
  conversation: unknown,
): ManagedMissionSnapshot {
  const status = pickFromRecord(agent, ["status", "state", "phase", "current_step"]) ?? null;
  const blocker = pickFromRecord(agent, [
    "error",
    "error_message",
    "failure_reason",
    "failure",
  ]);
  const updatedAt = pickFromRecord(agent, [
    "updated_at",
    "created_at",
    "finished_at",
    "ended_at",
  ]);

  let branchOrPr: string | null = null;
  const target = asRecord(agent["target"]) ?? asRecord(agent["pr"]) ?? asRecord(agent["pull_request"]);
  if (target) {
    branchOrPr =
      pickFromRecord(target, ["html_url", "url", "pr_url", "web_url", "link"]) ??
      pickFromRecord(target, ["branch", "ref", "name", "title"]);
  }
  if (!branchOrPr) {
    branchOrPr = pickFromRecord(agent, ["branch", "branch_name", "pr_url", "html_url"]);
  }

  const progress = extractConversationProgress(conversation);

  const hasAny = Boolean(status || progress || blocker || branchOrPr || updatedAt);
  return {
    status: status ?? (!hasAny ? "No status details from API" : null),
    progress: progress ?? null,
    blocker: blocker ?? null,
    branchOrPr: branchOrPr ?? null,
    updatedAt: updatedAt ?? null,
  };
}

/** Fixed interval for managed-mode Cloud Agent status refresh (ms). */
export const MANAGED_CLOUD_AGENT_POLL_MS = 15_000;
