import type {
  ManagedDeployReadiness,
  ManagedMissionReview,
  ManagedMissionSnapshot,
  ManagedReviewEvidenceLevel,
} from "@/lib/ham/types";

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

/** Internal: what the API-shaped payload actually exposes (facts), before HAM inference. */
type ReviewFacts = {
  terminal: boolean;
  hasExplicitErrorOrBlocker: boolean;
  hasPrOrBranch: boolean;
  progressLen: number;
  hasProgress: boolean;
  statusText: string;
  statusIsPlaceholder: boolean;
  hasUpdatedAt: boolean;
  /** Composite: how much we can safely say from non-fabricated fields */
  signalStrength: ManagedReviewEvidenceLevel;
  /** Thin payload + no explicit failure: prefer limited-signal messaging */
  limitedSignal: boolean;
};

function isPlaceholderStatusLabel(s: string | null | undefined): boolean {
  const t = (s ?? "").trim();
  return !t || t === "No status details from API";
}

/**
 * Evidence from real fields only. `high` = explicit handoff/error fields or strong transcript + metadata;
 * `medium` = some progress or metadata; `low` = sparse or ambiguous.
 */
function extractReviewFacts(agent: Record<string, unknown>, snap: ManagedMissionSnapshot): ReviewFacts {
  const terminal = isCloudAgentTerminal(agent);
  const err0 = readString(agent.error) ?? readString(agent.error_message);
  const failStr = typeof agent.failure === "string" ? readString(agent.failure) : null;
  const failBool = agent.failure === true;
  const snapBlocker = snap.blocker?.trim() || null;
  const hasExplicitErrorOrBlocker = Boolean(
    (err0 && err0.length > 0) || (failStr && failStr.length > 0) || failBool || (snapBlocker && snapBlocker.length > 0),
  );
  const hasPrOrBranch = Boolean(snap.branchOrPr?.trim());
  const progress = (snap.progress ?? "").trim();
  const progressLen = progress.length;
  const hasProgress = progressLen > 0;
  const statusText = (snap.status ?? "").trim() || "—";
  const statusIsPlaceholder = isPlaceholderStatusLabel(snap.status);
  const hasUpdatedAt = Boolean(snap.updatedAt?.trim());

  let score = 0;
  if (hasExplicitErrorOrBlocker) score += 4;
  if (hasPrOrBranch) score += 3;
  if (progressLen >= 40) score += 2;
  else if (progressLen >= 12) score += 1;
  if (hasUpdatedAt) score += 1;
  if (!statusIsPlaceholder) score += 1;

  let signalStrength: ManagedReviewEvidenceLevel;
  if (hasExplicitErrorOrBlocker || hasPrOrBranch) {
    signalStrength = "high";
  } else if (score >= 3) {
    signalStrength = "high";
  } else if (score >= 1) {
    signalStrength = "medium";
  } else {
    signalStrength = "low";
  }

  const limitedSignal = !hasExplicitErrorOrBlocker && signalStrength === "low";

  return {
    terminal,
    hasExplicitErrorOrBlocker,
    hasPrOrBranch,
    progressLen,
    hasProgress,
    statusText,
    statusIsPlaceholder,
    hasUpdatedAt,
    signalStrength,
    limitedSignal,
  };
}

/** Shown in HAM review when the full excerpt already appears under `Progress` in the mission summary (avoids duplicating long transcript tails in the right pane). */
const POINTER_SEE_SNAPSHOT_PROGRESS =
  "The latest activity excerpt is in the mission summary (Progress) above. Open the Transcript tab for the full log.";

function limitedSignalReview(hasTerminal: boolean): ManagedMissionReview {
  return {
    severity: "info",
    headline: "HAM review: limited signal",
    details:
      "The current agent response is too sparse to assess PR, branch, blocker, or final handoff confidently. This is often a shape or timing issue, not proof of failure.",
    nextStep: "Open Tracker and Transcript in the War Room, or refresh after the next poll.",
    hasTerminalAssessment: hasTerminal,
    evidenceLevel: "low",
    limitedSignal: true,
  };
}

/**
 * Deterministic, compact assessment from the same data as the managed snapshot. No LLM, no extra HTTP.
 * Facts are separated from wording: conservative when `limitedSignal` or low evidence.
 */
export function deriveManagedMissionReview(
  agent: Record<string, unknown>,
  _conversation: unknown,
  snap: ManagedMissionSnapshot,
): ManagedMissionReview {
  const f = extractReviewFacts(agent, snap);

  /** First-class path: do not overclaim on thin payloads */
  if (f.limitedSignal) {
    return limitedSignalReview(f.terminal);
  }

  if (f.terminal) {
    if (f.hasExplicitErrorOrBlocker) {
      return {
        severity: "error",
        headline: "Terminal: failure or error fields are present in the agent payload.",
        details: snap.blocker ?? readString(agent.error) ?? readString(agent.error_message) ?? readString(agent.failure),
        nextStep: "Inspect the Cloud Agent run, transcript, and repository before a follow-up.",
        hasTerminalAssessment: true,
        evidenceLevel: "high",
        limitedSignal: false,
      };
    }
    if (f.hasPrOrBranch) {
      return {
        severity: "success",
        headline: "Terminal: a branch/PR or link field is present in the latest agent data.",
        details: f.hasProgress
          ? `Status: ${f.statusText}. ${POINTER_SEE_SNAPSHOT_PROGRESS}`
          : `Status: ${f.statusText}`,
        nextStep: "Confirm the linked change set in Cursor or the remote before any merge or deploy step.",
        hasTerminalAssessment: true,
        evidenceLevel: "high",
        limitedSignal: false,
      };
    }
    if (f.signalStrength === "high") {
      return {
        severity: "warning",
        headline:
          "Terminal: no PR or branch link has surfaced in the latest agent data yet. That does not prove none exists elsewhere.",
        details: f.hasProgress ? POINTER_SEE_SNAPSHOT_PROGRESS : "Limited transcript/activity in this payload shape.",
        nextStep: "If a handoff was expected, check Cursor, Tracker, and the remote repository.",
        hasTerminalAssessment: true,
        evidenceLevel: "high",
        limitedSignal: false,
      };
    }
    return {
      severity: "info",
      headline: "Terminal: handoff in this response is incomplete or unclear; avoid assuming PR/branch or failure from this view alone.",
      details: f.hasProgress ? POINTER_SEE_SNAPSHOT_PROGRESS : `Status: ${f.statusText}`,
      nextStep: "Use Transcript/Tracker, or wait for a richer poll, before concluding.",
      hasTerminalAssessment: true,
      evidenceLevel: f.signalStrength,
      limitedSignal: false,
    };
  }

  if (f.hasExplicitErrorOrBlocker) {
    return {
      severity: "warning",
      headline: "Not terminal: error or blocker text appears in the latest agent data.",
      details: snap.blocker ?? readString(agent.error) ?? readString(agent.error_message) ?? (agent.failure === true ? "failure" : null),
      nextStep: "Check env/config, credentials, and the live Transcript in Cursor for the most recent error.",
      hasTerminalAssessment: false,
      evidenceLevel: "high",
      limitedSignal: false,
    };
  }
  if (f.hasProgress && f.signalStrength !== "low") {
    return {
      severity: "info",
      headline: "In progress: recent transcript/activity is present in the API payload.",
      details: POINTER_SEE_SNAPSHOT_PROGRESS,
      nextStep: "Let the run continue, or nudge the Cloud Agent in Cursor if the task is blocked.",
      hasTerminalAssessment: false,
      evidenceLevel: f.signalStrength,
      limitedSignal: false,
    };
  }
  if (f.hasProgress) {
    return {
      severity: "info",
      headline: "Transcript/activity is short or thin; not enough to claim steady progress or blockage.",
      details: POINTER_SEE_SNAPSHOT_PROGRESS,
      nextStep: "Open Transcript in the War Room, or wait for a fuller poll.",
      hasTerminalAssessment: false,
      evidenceLevel: "low",
      limitedSignal: false,
    };
  }
  return {
    severity: "info",
    headline: "Not terminal: no strong progress line yet; the agent may still be working.",
    details: f.statusIsPlaceholder
      ? "Status/labels from the API are limited in this view."
      : `Status: ${f.statusText}`,
    nextStep: "Watch the managed summary, Transcript, and Tracker; refresh as the run evolves.",
    hasTerminalAssessment: false,
    evidenceLevel: f.signalStrength,
    limitedSignal: false,
  };
}

/**
 * Classify `branchOrPr` as URL vs branch name from API text only.
 */
function splitBranchOrPr(raw: string | null): { prUrl: string | null; branch: string | null } {
  const t = raw?.trim() || null;
  if (!t) return { prUrl: null, branch: null };
  const lower = t.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://") || lower.includes("github.com/")) {
    return { prUrl: t, branch: null };
  }
  return { prUrl: null, branch: t };
}

function extractRepoForDeploy(agent: Record<string, unknown>): string | null {
  const top = readString(agent["repository"]);
  if (top) return top;
  const src = asRecord(agent["source"]);
  if (src) {
    return readString(src["repository"] ?? src["url"]) ?? null;
  }
  return null;
}

/**
 * Whether a Vercel deploy hook handoff is *appropriate* from current mission data (not whether the hook is configured).
 * Deterministic; no LLM.
 */
export function deriveManagedDeployReadiness(
  agent: Record<string, unknown>,
  _conversation: unknown,
  snap: ManagedMissionSnapshot,
  review: ManagedMissionReview,
): ManagedDeployReadiness {
  const repo = extractRepoForDeploy(agent);
  const { prUrl, branch } = splitBranchOrPr(snap.branchOrPr);
  const hasHandoff = Boolean(prUrl || branch);
  const terminal = isCloudAgentTerminal(agent);
  const target =
    "Vercel project linked to the HAM-configured deploy hook (build runs on the hook’s connected repo)";

  if (!terminal) {
    return {
      ready: false,
      severity: "info",
      headline: "Deploy handoff: mission is not in a terminal state in the latest agent data.",
      details: review.details ?? snap.progress ?? null,
      nextStep: "Wait for the Cloud Agent to finish, then refresh or re-poll.",
      prUrl,
      branch,
      repo,
      deploymentTarget: null,
    };
  }
  if (review.severity === "error" && review.hasTerminalAssessment) {
    return {
      ready: false,
      severity: "error",
      headline: "Deploy handoff is not ready: terminal state includes error or failure fields.",
      details: review.details,
      nextStep: "Resolve errors in the mission before a deploy handoff.",
      prUrl,
      branch,
      repo,
      deploymentTarget: null,
    };
  }
  if (review.limitedSignal) {
    return {
      ready: false,
      severity: "warning",
      headline: "Deploy handoff: mission data is too limited to confirm a PR, branch, or repository target.",
      details: review.details,
      nextStep: "Open Tracker/Transcript, then re-assess when the API shows clearer fields.",
      prUrl,
      branch,
      repo,
      deploymentTarget: null,
    };
  }
  if (!hasHandoff) {
    return {
      ready: false,
      severity: "warning",
      headline: "Deploy handoff is blocked: no branch or PR link in the latest agent payload.",
      details: "Without a handoff line in the agent response, HAM will not offer a ready deploy trigger.",
      nextStep: "Confirm branch/PR in Cursor or the remote, then re-poll this mission.",
      prUrl: null,
      branch: null,
      repo,
      deploymentTarget: null,
    };
  }
  if (!repo?.trim()) {
    return {
      ready: true,
      severity: "success",
      headline: "Terminal with branch/PR text in the payload; deploy hook can be triggered when configured (repository field not in this shape).",
      details: prUrl || branch,
      nextStep: "Verify the Vercel hook’s Git repo matches your mission before triggering.",
      prUrl,
      branch,
      repo: null,
      deploymentTarget: target,
    };
  }
  return {
    ready: true,
    severity: "success",
    headline: "Mission reached a terminal handoff: branch/PR information is available for deploy hook handoff.",
    details:
      "Handoff and repository match Branch / PR in the mission summary above; the hook is configured on the server (not per-PR).",
    nextStep: "Trigger only when the hook’s Vercel project matches this work; the hook does not target a specific PR automatically.",
    prUrl,
    branch,
    repo,
    deploymentTarget: target,
  };
}

/**
 * Stricter than panel: optional chat only for terminal + strong evidence + error/warning (not limited-signal).
 */
export function shouldEmitReviewChatLine(review: ManagedMissionReview): boolean {
  if (!review.hasTerminalAssessment) return false;
  if (review.limitedSignal) return false;
  if (review.severity !== "error" && review.severity !== "warning") return false;
  if (review.evidenceLevel !== "high") return false;
  return true;
}

const MAX_REVIEW_CHAT_LEN = 800;

/**
 * Distinct from `buildManagedCompletionMessage`: short assessment line for chat, only when `shouldEmitReviewChatLine`.
 */
export function buildManagedReviewChatMessage(review: ManagedMissionReview): string {
  const parts = [`[HAM] Review: ${review.headline}`];
  if (review.details?.trim()) {
    const d = review.details.trim();
    parts.push(d.length > 240 ? `${d.slice(0, 239)}…` : d);
  }
  const body = parts.join("\n");
  return body.length > MAX_REVIEW_CHAT_LEN ? `${body.slice(0, MAX_REVIEW_CHAT_LEN - 1)}…` : body;
}

/**
 * Stable key for one-time terminal review line per mission + assessment shape (separate from completion map).
 */
export function reviewChatInjectionSignature(
  activeAgentId: string,
  review: ManagedMissionReview,
  agent: Record<string, unknown>,
): string {
  const st =
    (readString(agent.status) ?? readString(agent.state) ?? "").toLowerCase().trim() || "—";
  const h = review.headline.slice(0, 80);
  return `${activeAgentId.trim()}::${review.severity}::${st}::${h}`;
}

/** Fixed interval for managed-mode Cloud Agent status refresh (ms). */
export const MANAGED_CLOUD_AGENT_POLL_MS = 15_000;

/**
 * Full-string terminal labels (lowercase) from status/state after `normalize` — no substring matching.
 * Cursor returns opaque JSON; add literals here only if repo or confirmed samples reference them.
 */
export const MANAGED_COMPLETION_STATUS_ALLOWLIST: ReadonlySet<string> = new Set([
  "finished",
  "completed",
  "complete",
  "failed",
  "error",
  "stopped",
  "expired",
  "cancelled",
  "canceled",
  "succeeded",
  "success",
  "done",
  "closed",
]);

function normalizeStatusField(raw: string): string {
  return raw.trim().toLowerCase();
}

/**
 * True if the proxied agent JSON clearly indicates a terminal run (defensive, real fields only).
 */
export function isCloudAgentTerminal(agent: Record<string, unknown>): boolean {
  if (readString(agent.error) || readString(agent.error_message)) {
    return true;
  }
  if (readString(agent.failure) || agent.failure === true) {
    return true;
  }
  const s = readString(agent.status) ?? readString(agent.state) ?? null;
  if (s) {
    const n = normalizeStatusField(s);
    if (MANAGED_COMPLETION_STATUS_ALLOWLIST.has(n)) return true;
  }
  return false;
}

/**
 * Stable signature to dedupe in localStorage: mission id + normalized status + small error tail.
 */
export function completionInjectionSignature(
  agent: Record<string, unknown>,
  activeAgentId: string,
): string {
  const st =
    (readString(agent.status) ?? readString(agent.state) ?? "").toLowerCase().trim() || "—";
  const err = (readString(agent.error) ?? readString(agent.error_message) ?? "").trim().slice(0, 64);
  return `${activeAgentId.trim()}::${st}::${err}`;
}

const MAX_COMPLETION_LEN = 1200;

/**
 * One compact, factual completion notice for the chat thread (no fake streaming, no full JSON).
 */
export function buildManagedCompletionMessage(
  agent: Record<string, unknown>,
  conversation: unknown,
): string {
  const snap = deriveManagedMissionSnapshot(agent, conversation);
  const parts: string[] = ["[HAM] Managed Cloud Agent mission reached a terminal state (from Cursor)."];
  if (snap.status) parts.push(`Status: ${snap.status}`);
  if (snap.progress) parts.push(`Last activity: ${snap.progress}`);
  if (snap.branchOrPr) parts.push(`Branch / PR: ${snap.branchOrPr}`);
  if (snap.blocker) parts.push(`Blocker / error: ${snap.blocker}`);
  if (snap.updatedAt) parts.push(`Updated: ${snap.updatedAt}`);
  const body = parts.join("\n");
  return body.length > MAX_COMPLETION_LEN ? `${body.slice(0, MAX_COMPLETION_LEN - 1)}…` : body;
}
