/**
 * GoHAM v1 Slice 2 — bounded rules-first research loop (desktop managed browser only).
 * Uses Slice 1 primitives; no model planner, no type/key, no forms.
 */

import type {
  HamDesktopLocalControlApi,
  HamDesktopRealBrowserClickCandidate,
  HamDesktopRealBrowserObserveCompactResult,
} from "@/lib/ham/desktopBundleBridge";
import type { GohamSearchStart } from "./gohamSearchStrategy";

/** Research loop requires Slice 1+ preload IPC; older desktop builds omit these. */
const RESEARCH_DESKTOP_METHODS = [
  "realBrowserObserveCompact",
  "realBrowserWaitMs",
  "realBrowserScrollVertical",
  "realBrowserEnumerateClickCandidates",
  "realBrowserClickCandidate",
] as const satisfies readonly (keyof HamDesktopLocalControlApi)[];

function missingResearchDesktopMethods(api: HamDesktopLocalControlApi): string[] {
  const o = api as Record<string, unknown>;
  return RESEARCH_DESKTOP_METHODS.filter((m) => typeof o[m] !== "function");
}
import { redactUrlForTrail } from "./extractGohamUrl";
import { ensureGohamPolicy, sessionErrorMessage, type GoHamTrailStep } from "./gohamObserveFlow";

const MAX_LOOP_ACTIONS = 5;
const LOOP_WALL_MS = 75_000;
const WAIT_AFTER_CLICK_MS = 1500;
const SCROLL_DELTA = 400;
const SETTLE_WAIT_MS = 1200;

const STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "you",
  "that",
  "with",
  "from",
  "this",
  "your",
  "are",
  "was",
  "have",
  "has",
  "not",
  "but",
  "can",
  "open",
  "https",
  "http",
  "www",
  "tell",
  "me",
  "how",
  "does",
  "did",
  "will",
  "into",
  "onto",
  "one",
  "most",
  "within",
  "bounded",
]);

const RESEARCH_GOAL_STOPWORDS = new Set([
  ...STOPWORDS,
  "find",
  "finding",
  "research",
  "information",
  "info",
  "about",
  "start",
  "page",
  "pages",
  "link",
  "links",
  "available",
  "follow",
  "useful",
  "goham",
  "report",
  "found",
  "shown",
  "show",
  "whether",
  "what",
  "window",
]);

/** User message hints at a multi-step research task (vs v0 “what you see”). */
const RESEARCH_BIAS =
  /\b(find|finding|research|compare|information about|info about|look up|lookup|learn about|what is|what are|tell me about|explain|describe|free tier|pricing|features|documentation|docs)\b/i;

const OBSERVE_ONLY_BIAS = /\bwhat (do )?you see\b|\bjust (open|visit)\b/i;

/**
 * Research loop when the task looks multi-step; keep v0 single-page observe for “what you see” prompts.
 */
export function shouldUseResearchLoop(text: string): boolean {
  const strong =
    /\b(find|finding|research|information about|info about|tell me about|learn about|look up|lookup|what is|what are)\b/i.test(
      text,
    );
  if (strong) return true;
  if (OBSERVE_ONLY_BIAS.test(text)) return false;
  return RESEARCH_BIAS.test(text);
}

export type GohamLoopActionType = "observe" | "scroll" | "wait" | "click_candidate" | "done" | "blocked";

export type GohamLoopAction = {
  type: GohamLoopActionType;
  candidate_id?: string;
  reason: string;
  risk: "low" | "blocked";
};

export type GohamResearchStopReason =
  | "done"
  | "budget"
  | "blocked"
  | "error"
  | "user_stopped"
  | "time"
  | "insufficient_evidence"
  | "budget_without_evidence";

function redactSnippet(s: string, max = 44): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

export function goalTokensFromTask(text: string, url: string): string[] {
  let t = text.toLowerCase();
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    t = t.split(host).join(" ");
  } catch {
    /* ignore */
  }
  const raw = t.split(/\W+/u).filter((w) => w.length > 2 && !STOPWORDS.has(w));
  return [...new Set(raw)];
}

function normalizeEvidenceText(s: string): string {
  return s
    .toLowerCase()
    .replace(/[._/-]+/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
}

function deriveRequiredEvidenceTerms(text: string, url: string): string[] {
  let t = text.toLowerCase();
  try {
    const u = new URL(url);
    t = t.split(u.hostname.toLowerCase()).join(" ");
    t = t.split(u.origin.toLowerCase()).join(" ");
  } catch {
    /* ignore */
  }

  const terms: string[] = [];
  const add = (term: string) => {
    const cleaned = normalizeEvidenceText(term);
    if (cleaned.length >= 2 && !terms.includes(cleaned)) terms.push(cleaned);
  };

  const versionLike = t.match(/\b[a-z]+\d+(?:[._-]\d+)+\b|\b[a-z]+\s+\d+(?:[._-]\d+)+\b/giu) ?? [];
  versionLike.forEach(add);

  if (/\bfree\s+tier\b/iu.test(t)) {
    add("free tier");
    add("free");
    add("tier");
  }
  if (/\bcontext\s+window\b/iu.test(t)) {
    add("context window");
    add("context");
  }

  t.split(/[^\p{L}\p{N}.]+/u)
    .map((w) => w.trim().toLowerCase())
    .filter((w) => w.length > 2 && !RESEARCH_GOAL_STOPWORDS.has(w))
    .forEach(add);

  return terms.slice(0, 10);
}

type EvidenceLedger = {
  requiredTerms: string[];
  observedTerms: Set<string>;
  snippets: string[];
};

function makeEvidenceLedger(requiredTerms: string[]): EvidenceLedger {
  return { requiredTerms, observedTerms: new Set(), snippets: [] };
}

function evidenceMissingTerms(evidence: EvidenceLedger): string[] {
  return evidence.requiredTerms.filter((term) => !evidence.observedTerms.has(term));
}

function hasMissingEvidence(evidence: EvidenceLedger): boolean {
  return evidenceMissingTerms(evidence).length > 0;
}

function addEvidenceSnippet(evidence: EvidenceLedger, snippet: string) {
  const clean = redactSnippet(snippet, 96);
  if (!clean || evidence.snippets.includes(clean)) return;
  if (evidence.snippets.length < 8) evidence.snippets.push(clean);
}

function observeEvidenceFromText(evidence: EvidenceLedger, sourceLabel: string, text: string) {
  const normalized = normalizeEvidenceText(text);
  if (!normalized) return;
  for (const term of evidence.requiredTerms) {
    if (!evidence.observedTerms.has(term) && normalized.includes(term)) {
      evidence.observedTerms.add(term);
      addEvidenceSnippet(evidence, `${sourceLabel}: ${text}`);
    }
  }
}

function observeEvidenceFromPage(
  evidence: EvidenceLedger,
  title: string,
  displayUrl: string,
  candidates: HamDesktopRealBrowserClickCandidate[] = [],
  opts: { includePageMeta?: boolean } = {},
) {
  if (opts.includePageMeta !== false) {
    observeEvidenceFromText(evidence, "title", title);
    observeEvidenceFromText(evidence, "url", displayUrl);
  }
  for (const c of candidates.slice(0, 12)) {
    observeEvidenceFromText(evidence, "candidate", c.text);
  }
}

function isSearchProviderLocation(searchStart: GohamSearchStart | null, displayUrl: string): boolean {
  if (!searchStart) return false;
  try {
    const u = new URL(displayUrl);
    const su = new URL(searchStart.url);
    return u.hostname === su.hostname;
  } catch {
    return displayUrl.startsWith("https://duckduckgo.com");
  }
}

function scoreCandidate(c: HamDesktopRealBrowserClickCandidate, tokens: string[]): number {
  const blob = `${c.text} ${c.role ?? ""}`.toLowerCase();
  return tokens.filter((k) => k.length > 2 && blob.includes(k)).length;
}

function taskAppearsComplete(title: string, tokens: string[]): boolean {
  if (!title.trim() || tokens.length === 0) return false;
  const t = title.toLowerCase();
  const hits = tokens.filter((k) => k.length > 2 && t.includes(k));
  if (tokens.length === 1) return hits.length >= 1;
  return hits.length >= 2;
}

export function validatePlannerAction(
  action: GohamLoopAction,
  candidates: HamDesktopRealBrowserClickCandidate[],
): { ok: true } | { ok: false; reason: string } {
  const allowed: GohamLoopActionType[] = ["observe", "scroll", "wait", "click_candidate", "done", "blocked"];
  if (!allowed.includes(action.type)) return { ok: false, reason: "invalid_action_type" };
  if (action.risk !== "low") return { ok: false, reason: "risk_not_low" };
  if (action.type === "click_candidate") {
    const id = action.candidate_id?.trim();
    if (!id) return { ok: false, reason: "missing_candidate_id" };
    const c = candidates.find((x) => x.id === id);
    if (!c) return { ok: false, reason: "unknown_candidate" };
    if (c.risk !== "low") return { ok: false, reason: "candidate_risk" };
  }
  if (action.type === "blocked") return { ok: false, reason: "blocked_action" };
  return { ok: true };
}

type PlanCtx = {
  taskText: string;
  goalTokens: string[];
  candidates: HamDesktopRealBrowserClickCandidate[];
  lastClickedId: string | null;
  scrollsThisPage: number;
  loopIteration: number;
  lastTitle: string;
  evidenceMissing: boolean;
};

/** Rules-first planner: token overlap on candidates, else scroll, else done. */
export function rulesFirstPlan(ctx: PlanCtx): GohamLoopAction {
  const { goalTokens, candidates, lastClickedId, scrollsThisPage, loopIteration, lastTitle, evidenceMissing } = ctx;

  if (!evidenceMissing && taskAppearsComplete(lastTitle, goalTokens)) {
    return { type: "done", reason: "Page title matches research keywords", risk: "low" };
  }
  if (loopIteration >= MAX_LOOP_ACTIONS) {
    return { type: "done", reason: "Step budget reached", risk: "low" };
  }

  const scored = candidates
    .filter((c) => c.risk === "low")
    .map((c) => ({ c, score: scoreCandidate(c, goalTokens) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);

  const best = scored[0];
  if (best && best.c.id !== lastClickedId) {
    return {
      type: "click_candidate",
      candidate_id: best.c.id,
      reason: `Candidate matches topic: ${redactSnippet(best.c.text)}`,
      risk: "low",
    };
  }

  if (scrollsThisPage < (evidenceMissing ? MAX_LOOP_ACTIONS : 3)) {
    return { type: "scroll", reason: "No matching link in view — scrolling", risk: "low" };
  }

  return {
    type: "done",
    reason: evidenceMissing ? "No further relevant actions with required evidence still missing" : "No further relevant actions",
    risk: "low",
  };
}

export type GohamHoldState = "none" | "pause" | "takeover";

export type RunGohamResearchOptions = {
  api: HamDesktopLocalControlApi;
  url: string;
  taskText: string;
  searchStart?: GohamSearchStart | null;
  onTrail: (steps: GoHamTrailStep[]) => void;
  shouldAbort: () => boolean;
  /** Slice 3 — pause / takeover: HAM must not start a new action while not `none`. */
  getHoldState: () => GohamHoldState;
};

export type RunGohamResearchResult =
  | { ok: true; assistantText: string }
  | { ok: false; userMessage: string; trailSteps: GoHamTrailStep[] };

export async function runGohamResearchFlow(opts: RunGohamResearchOptions): Promise<RunGohamResearchResult> {
  const { api, url, taskText, searchStart = null, onTrail, shouldAbort, getHoldState } = opts;
  const redacted = redactUrlForTrail(url);
  const goalTokens = goalTokensFromTask(taskText, url);
  const evidence = makeEvidenceLedger(deriveRequiredEvidenceTerms(taskText, url));

  let trail: GoHamTrailStep[] = [];
  let seq = 0;
  const pushTrail = (next: GoHamTrailStep[]) => {
    trail = next;
    onTrail(next);
  };
  const add = (label: string, status: GoHamTrailStep["status"], detail?: string) => {
    seq += 1;
    pushTrail([...trail, { id: `gr-${seq}`, label, status, detail }]);
  };
  const addRow = (row: Pick<GoHamTrailStep, "label" | "status"> & Partial<Omit<GoHamTrailStep, "id">>) => {
    seq += 1;
    pushTrail([...trail, { id: `gr-${seq}`, ...row }]);
  };
  const patchId = (id: string, status: GoHamTrailStep["status"], detail?: string) => {
    pushTrail(
      trail.map((s) => (s.id === id ? { ...s, status, ...(detail !== undefined ? { detail } : {}) } : s)),
    );
  };
  const patchIdFull = (
    id: string,
    status: GoHamTrailStep["status"],
    patch: Partial<Pick<GoHamTrailStep, "detail" | "result" | "errorReason" | "targetRedacted" | "actionType">>,
  ) => {
    pushTrail(trail.map((s) => (s.id === id ? { ...s, status, ...patch } : s)));
  };
  const activate = (label: string): string => {
    seq += 1;
    const id = `gr-${seq}`;
    const prev = trail.map((s) => (s.status === "active" ? { ...s, status: "done" as const } : s));
    pushTrail([...prev, { id, label, status: "active" }]);
    return id;
  };

  const bridgeMissing = missingResearchDesktopMethods(api);
  if (bridgeMissing.length > 0) {
    addRow({
      label: "Desktop bridge outdated",
      status: "error",
      detail: `Missing API: ${bridgeMissing.join(", ")}`,
      actionType: "bridge",
      errorReason: "preload_mismatch",
    });
    return {
      ok: false,
      userMessage: [
        `GoHAM research needs a **newer HAM Desktop** build. The running app’s preload does not expose: **${bridgeMissing.join(", ")}** (Slice 1 browser IPC).`,
        ``,
        `**What to do:** Fully **quit** HAM Desktop (all windows), update this repo to **main** (or rebuild from the same commit as the web UI), then from \`desktop/\` run \`npm start\` again so Electron loads the current \`preload.cjs\`.`,
        ``,
        `If you use a packaged install, reinstall from a build that includes GoHAM Slice 1+ desktop changes.`,
      ].join("\n"),
      trailSteps: trail,
    };
  }

  /** Wait until pause/takeover released or user aborts. */
  const yieldToUserHold = async (): Promise<"continue" | "abort"> => {
    const h0 = getHoldState();
    if (h0 === "none") return "continue";
    if (shouldAbort()) return "abort";
    if (h0 === "takeover") {
      addRow({
        label: "Takeover — HAM idle",
        status: "done",
        detail: "Browser is yours. Click Resume when you want HAM to continue.",
        actionType: "takeover",
        result: "waiting",
      });
    } else {
      addRow({
        label: "Paused",
        status: "done",
        detail: "HAM will not start a new action until you resume.",
        actionType: "pause",
        result: "waiting",
      });
    }
    while (getHoldState() !== "none") {
      if (shouldAbort()) return "abort";
      await new Promise((r) => setTimeout(r, 120));
    }
    if (shouldAbort()) return "abort";
    addRow({
      label: "Resumed",
      status: "done",
      detail: "Continuing research loop.",
      actionType: "resume",
      result: "ok",
    });
    return "continue";
  };

  const visited: { title: string; display: string }[] = [];
  let stopReason: GohamResearchStopReason | null = null;
  let errorMessage: string | null = null;
  let screenshotCaptureCount = 0;
  let loopActionCount = 0;

  if (shouldAbort()) {
    add("GoHAM stopped", "error", "Before start");
    return { ok: false, userMessage: "GoHAM was stopped before it started.", trailSteps: trail };
  }

  if (searchStart) {
    addRow({
      label: "Searching the web",
      status: "done",
      detail: `Searching the web for: ${redactSnippet(searchStart.displayQuery, 96)}`,
      actionType: "search",
      targetRedacted: redactUrlForTrail(searchStart.url),
      result: searchStart.provider,
    });
  }

  const polId = activate("Preparing managed browser policy");
  const pol = await ensureGohamPolicy(api);
  if (pol.ok === false) {
    patchId(polId, "error", pol.reason);
    return { ok: false, userMessage: pol.reason, trailSteps: trail };
  }
  patchId(polId, "done");

  if (shouldAbort()) {
    add("GoHAM stopped", "error", "After policy");
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: trail };
  }

  const startId = activate("Starting managed browser");
  const startR = await api.startRealBrowserSession();
  if (!startR || (startR as { ok?: boolean }).ok === false) {
    const msg = sessionErrorMessage(startR, "Start session");
    patchId(startId, "error", msg);
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  patchId(startId, "done");

  if (shouldAbort()) {
    await api.stopRealBrowserSession();
    add("GoHAM stopped", "error", "After start");
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: trail };
  }

  const navId = activate("Navigating");
  const navR = await api.navigateRealBrowser(url);
  if (!navR || (navR as { ok?: boolean }).ok === false) {
    const msg = sessionErrorMessage(navR, "Navigate");
    patchId(navId, "error", msg);
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  patchId(navId, "done", redacted);

  if (shouldAbort()) {
    await api.stopRealBrowserSession();
    add("GoHAM stopped", "error", "After navigate");
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: trail };
  }

  const readObserve = async (): Promise<HamDesktopRealBrowserObserveCompactResult> => api.realBrowserObserveCompact();

  const shotId = activate("Observing page");
  const shot = await api.captureRealBrowserScreenshot();
  if (!shot || shot.ok !== true) {
    const msg = sessionErrorMessage(shot, "Screenshot");
    patchIdFull(shotId, "error", { detail: msg, actionType: "screenshot", errorReason: msg });
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  screenshotCaptureCount += 1;
  let obs = await readObserve();
  if (!obs || obs.ok !== true) {
    const msg = sessionErrorMessage(obs, "Observe");
    patchIdFull(shotId, "error", { detail: msg, actionType: "observe", errorReason: msg });
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  const pub0 = await api.getRealBrowserStatus();
  const title0 = (pub0.title || obs.title || "").trim() || "(no title)";
  const display0 = redactUrlForTrail((pub0.display_url || obs.display_url || obs.url || "").trim() || redacted);
  visited.push({ title: title0, display: display0 });
  patchIdFull(shotId, "done", {
    detail: redactUrlForTrail(display0),
    actionType: "screenshot",
    result: "ok",
    targetRedacted: redactUrlForTrail(display0),
  });

  const listId = activate("Listing click candidates");
  let enumR = await api.realBrowserEnumerateClickCandidates();
  if (!enumR || enumR.ok !== true) {
    const msg = sessionErrorMessage(enumR, "Candidates");
    patchIdFull(listId, "error", { detail: msg, actionType: "enumerate", errorReason: msg });
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  let candidates = enumR.candidates;
  observeEvidenceFromPage(evidence, title0, display0, candidates, {
    includePageMeta: !isSearchProviderLocation(searchStart, display0),
  });
  patchIdFull(listId, "done", {
    detail: `${candidates.length} visible`,
    actionType: "enumerate",
    result: `${candidates.length} candidates`,
  });

  const loopStart = Date.now();
  let lastClickedId: string | null = null;
  let scrollsThisPage = 0;
  let lastDisplayUrl = display0;
  let loopIteration = 0;
  let lastTitle = title0;

  let hitExplicitDone = false;

  if (!hasMissingEvidence(evidence) && taskAppearsComplete(lastTitle, goalTokens)) {
    stopReason = "done";
    hitExplicitDone = true;
  } else {
    stopReason = null;
    const yPre = await yieldToUserHold();
    if (yPre === "abort") {
      stopReason = "user_stopped";
      addRow({
        label: "Stopped by user",
        status: "error",
        detail: "Stop GoHAM",
        actionType: "stop",
        errorReason: "user",
      });
    } else {
      while (loopIteration < MAX_LOOP_ACTIONS && Date.now() - loopStart < LOOP_WALL_MS && !shouldAbort()) {
      const y = await yieldToUserHold();
      if (y === "abort") {
        stopReason = "user_stopped";
        addRow({
          label: "Stopped by user",
          status: "error",
          detail: "Stop GoHAM",
          actionType: "stop",
          errorReason: "user",
        });
        break;
      }
      const action = rulesFirstPlan({
        taskText,
        goalTokens,
        candidates,
        lastClickedId,
        scrollsThisPage,
        loopIteration,
        lastTitle,
        evidenceMissing: hasMissingEvidence(evidence),
      });
      const v = validatePlannerAction(action, candidates);
      if (v.ok === false) {
        stopReason = "blocked";
        errorMessage = v.reason;
        addRow({
          label: "Blocked",
          status: "error",
          detail: "Invalid planned action",
          actionType: "plan",
          errorReason: v.reason,
        });
        break;
      }
      if (action.type === "done") {
        const missingEvidence = hasMissingEvidence(evidence);
        stopReason = missingEvidence ? "insufficient_evidence" : "done";
        hitExplicitDone = true;
        addRow({
          label: missingEvidence ? "Insufficient evidence" : "Done",
          status: "done",
          detail: missingEvidence
            ? `Missing: ${evidenceMissingTerms(evidence).map((t) => redactSnippet(t, 18)).join(", ")}`
            : redactSnippet(action.reason, 80),
          actionType: "done",
          result: missingEvidence ? "insufficient_evidence" : "planner_done",
        });
        break;
      }

      if (action.type === "click_candidate" && action.candidate_id) {
        const cand = candidates.find((c) => c.id === action.candidate_id);
        const cid = activate("Clicking candidate");
        loopActionCount += 1;
        const clickR = await api.realBrowserClickCandidate(action.candidate_id);
        if (!clickR || clickR.ok !== true) {
          const msg = sessionErrorMessage(clickR, "Click");
          patchIdFull(cid, "error", {
            detail: msg,
            actionType: "click_candidate",
            targetRedacted: cand ? redactSnippet(cand.text, 36) : action.candidate_id,
            errorReason: msg,
          });
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        lastClickedId = action.candidate_id;
        patchIdFull(cid, "done", {
          detail: cand ? redactSnippet(cand.text, 36) : "candidate",
          actionType: "click_candidate",
          targetRedacted: cand ? redactSnippet(cand.text, 36) : undefined,
          result: "clicked",
        });
        const w = await api.realBrowserWaitMs(WAIT_AFTER_CLICK_MS);
        if (!w || w.ok !== true) {
          stopReason = "error";
          errorMessage = sessionErrorMessage(w, "Wait after click");
          addRow({
            label: "Waiting",
            status: "error",
            detail: errorMessage,
            actionType: "wait",
            errorReason: errorMessage,
          });
          break;
        }
      } else if (action.type === "scroll") {
        const sid = activate("Scrolling");
        loopActionCount += 1;
        const sr = await api.realBrowserScrollVertical(SCROLL_DELTA);
        if (!sr || sr.ok !== true) {
          const msg = sessionErrorMessage(sr, "Scroll");
          patchIdFull(sid, "error", { detail: msg, actionType: "scroll", errorReason: msg });
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        scrollsThisPage += 1;
        patchIdFull(sid, "done", {
          detail: `Δ ${sr.delta_applied ?? SCROLL_DELTA}`,
          actionType: "scroll",
          result: `delta ${sr.delta_applied ?? SCROLL_DELTA}`,
        });
      } else if (action.type === "wait") {
        const wid = activate("Waiting");
        loopActionCount += 1;
        const wr = await api.realBrowserWaitMs(SETTLE_WAIT_MS);
        if (!wr || wr.ok !== true) {
          const msg = sessionErrorMessage(wr, "Wait");
          patchIdFull(wid, "error", { detail: msg, actionType: "wait", errorReason: msg });
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        patchIdFull(wid, "done", {
          detail: `${wr.waited_ms ?? SETTLE_WAIT_MS}ms`,
          actionType: "wait",
          result: `${wr.waited_ms ?? SETTLE_WAIT_MS}ms`,
        });
      } else if (action.type === "observe") {
        const oid = activate("Re-observing");
        loopActionCount += 1;
        obs = await readObserve();
        if (!obs || obs.ok !== true) {
          const msg = sessionErrorMessage(obs, "Observe");
          patchIdFull(oid, "error", { detail: msg, actionType: "observe", errorReason: msg });
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        patchIdFull(oid, "done", {
          detail: redactSnippet(obs.title || "", 48),
          actionType: "observe",
          result: "ok",
        });
      }

      loopIteration += 1;

      if (shouldAbort()) {
        stopReason = "user_stopped";
        addRow({
          label: "Stopped by user",
          status: "error",
          detail: "Stop GoHAM",
          actionType: "stop",
          errorReason: "user",
        });
        break;
      }
      if (Date.now() - loopStart >= LOOP_WALL_MS) {
        const missingEvidence = hasMissingEvidence(evidence);
        stopReason = missingEvidence ? "budget_without_evidence" : "time";
        hitExplicitDone = true;
        addRow({
          label: missingEvidence ? "Time budget reached without evidence" : "Time budget reached",
          status: "done",
          detail: missingEvidence
            ? `Missing: ${evidenceMissingTerms(evidence).map((t) => redactSnippet(t, 18)).join(", ")}`
            : "Wall clock limit",
          actionType: "budget",
          result: missingEvidence ? "budget_without_evidence" : "time",
        });
        break;
      }

      const reId = activate("Re-observing");
      obs = await readObserve();
      if (!obs || obs.ok !== true) {
        const msg = sessionErrorMessage(obs, "Observe");
        patchIdFull(reId, "error", { detail: msg, actionType: "observe", errorReason: msg });
        stopReason = "error";
        errorMessage = msg;
        break;
      }
      const pub = await api.getRealBrowserStatus();
      lastTitle = (pub.title || obs.title || "").trim() || "(no title)";
      const disp = redactUrlForTrail((pub.display_url || obs.display_url || obs.url || "").trim() || lastDisplayUrl);
      if (disp !== lastDisplayUrl) {
        scrollsThisPage = 0;
        lastClickedId = null;
        lastDisplayUrl = disp;
        visited.push({ title: lastTitle, display: disp });
      }
      patchIdFull(reId, "done", {
        detail: redactSnippet(lastTitle, 48),
        actionType: "observe",
        result: "ok",
        targetRedacted: disp,
      });

      enumR = await api.realBrowserEnumerateClickCandidates();
      if (!enumR || enumR.ok !== true) {
        const msg = sessionErrorMessage(enumR, "Candidates");
        addRow({
          label: "Listing click candidates",
          status: "error",
          detail: msg,
          actionType: "enumerate",
          errorReason: msg,
        });
        stopReason = "error";
        errorMessage = msg;
        break;
      }
      candidates = enumR.candidates;
      observeEvidenceFromPage(evidence, lastTitle, disp, candidates, {
        includePageMeta: !isSearchProviderLocation(searchStart, disp),
      });
      addRow({
        label: "Listing click candidates",
        status: "done",
        detail: `${candidates.length} visible`,
        actionType: "enumerate",
        result: `${candidates.length} candidates`,
      });

      if (!hasMissingEvidence(evidence) && taskAppearsComplete(lastTitle, goalTokens)) {
        stopReason = "done";
        hitExplicitDone = true;
        addRow({
          label: "Done",
          status: "done",
          detail: "Goal appears satisfied",
          actionType: "done",
          result: "title_match",
        });
        break;
      }
    }
    }

    if (!hitExplicitDone && stopReason === null && loopIteration >= MAX_LOOP_ACTIONS) {
      const missingEvidence = hasMissingEvidence(evidence);
      stopReason = missingEvidence ? "budget_without_evidence" : "budget";
      addRow({
        label: missingEvidence ? "Step budget reached without evidence" : "Step budget reached",
        status: "done",
        detail: missingEvidence
          ? `Missing: ${evidenceMissingTerms(evidence).map((t) => redactSnippet(t, 18)).join(", ")}`
          : `${MAX_LOOP_ACTIONS} actions`,
        actionType: "budget",
        result: missingEvidence ? "budget_without_evidence" : "max_actions",
      });
    } else if (!hitExplicitDone && stopReason === null && Date.now() - loopStart >= LOOP_WALL_MS) {
      const missingEvidence = hasMissingEvidence(evidence);
      stopReason = missingEvidence ? "budget_without_evidence" : "time";
      addRow({
        label: missingEvidence ? "Time budget reached without evidence" : "Time budget reached",
        status: "done",
        detail: missingEvidence
          ? `Missing: ${evidenceMissingTerms(evidence).map((t) => redactSnippet(t, 18)).join(", ")}`
          : "Wall clock limit",
        actionType: "budget",
        result: missingEvidence ? "budget_without_evidence" : "time",
      });
    } else if (shouldAbort() && stopReason === null && !errorMessage) {
      stopReason = "user_stopped";
      addRow({
        label: "Stopped by user",
        status: "error",
        detail: "Stop GoHAM",
        actionType: "stop",
        errorReason: "user",
      });
    }
  }

  if (stopReason === null) stopReason = "done";

  const finalShot = await api.captureRealBrowserScreenshot();
  if (finalShot && finalShot.ok === true) {
    screenshotCaptureCount += 1;
  }

  const summarizeId = activate("Summarizing");
  const linesVisited = visited
    .map((v, i) => `${i + 1}. ${redactSnippet(v.title, 60)} — ${v.display}`)
    .join("\n");

  const stopLabel = ((): string => {
    switch (stopReason) {
      case "done":
        return "Done (goal met or planner finished)";
      case "budget":
        return "Budget (max actions)";
      case "insufficient_evidence":
        return "Insufficient evidence";
      case "budget_without_evidence":
        return "Budget reached without required evidence";
      case "time":
        return "Budget (wall clock)";
      case "blocked":
        return "Blocked (invalid plan)";
      case "user_stopped":
        return "User stopped (includes Stop during pause or takeover)";
      case "error":
      default:
        return "Error";
    }
  })();

  const pagesVisitedCount = visited.length;
  const visitedUrlsLines = visited.map((v) => `- ${v.display}`).join("\n");
  const missingTerms = evidenceMissingTerms(evidence);
  const evidenceTarget = evidence.requiredTerms.length
    ? evidence.requiredTerms.map((t) => redactSnippet(t, 28)).join("/")
    : "the requested research claim";
  const insufficientEvidence = stopReason === "insufficient_evidence" || stopReason === "budget_without_evidence";
  const observedTerms = [...evidence.observedTerms].map((t) => redactSnippet(t, 28));
  const observedEvidenceLines = evidence.snippets.map((s) => `- ${s}`).join("\n");

  const assistantText = [
    `**GoHAM research (v1 Slice 3)**`,
    ``,
    insufficientEvidence
      ? `I did not find enough visible evidence for ${evidenceTarget} within this bounded GoHAM pass.`
      : ``,
    insufficientEvidence ? `` : ``,
    `**Evidence summary**`,
    `- **Pages visited:** ${pagesVisitedCount}`,
    `- **Loop actions executed:** ${loopActionCount} (scroll / click / wait / observe in the research loop)`,
    `- **Screenshot captures:** ${screenshotCaptureCount} (local validation only — not embedded here)`,
    searchStart ? `- **Search start:** DuckDuckGo results for “${redactSnippet(searchStart.displayQuery, 96)}”` : ``,
    `- **Stop reason:** ${stopLabel}`,
    `- **Stop reason code:** \`${stopReason}\` (machine-readable: \`done\` | \`budget\` | \`time\` | \`insufficient_evidence\` | \`budget_without_evidence\` | \`blocked\` | \`error\` | \`user_stopped\`; use **Pause** / **Take over** + **Stop** → \`user_stopped\`)`,
    evidence.requiredTerms.length
      ? `- **Required evidence terms:** ${evidence.requiredTerms.map((t) => redactSnippet(t, 24)).join(", ")}`
      : `- **Required evidence terms:** (none extracted)`,
    evidence.requiredTerms.length
      ? `- **Observed required terms:** ${observedTerms.length ? observedTerms.join(", ") : "(none)"}`
      : ``,
    missingTerms.length ? `- **Missing evidence terms:** ${missingTerms.map((t) => redactSnippet(t, 24)).join(", ")}` : ``,
    ``,
    `**Visited locations (redacted)**`,
    visitedUrlsLines || `- ${redacted}`,
    ``,
    `**What we found**`,
    `- **Latest page title:** ${redactSnippet(lastTitle, 80)}`,
    goalTokens.length ? `- **Keywords tracked:** ${goalTokens.slice(0, 8).join(", ")}${goalTokens.length > 8 ? "…" : ""}` : `- (No keywords extracted from your message.)`,
    observedEvidenceLines ? `**Observed bounded evidence snippets**\n${observedEvidenceLines}` : `**Observed bounded evidence snippets**\n- (No required evidence terms were visible in title, URL, or bounded candidate text.)`,
    ``,
    `**Pages visited (detail)**`,
    linesVisited || `- ${redacted}`,
    errorMessage ? `**Error / block detail:** ${errorMessage}` : ``,
    ``,
    `**Limitations (this version)**`,
    `- No typing, form fill, or submit/post/send.`,
    `- No hidden browsing or full-page HTML extraction — title, redacted URL, compact observe, and screenshot bytes only.`,
    `- Rules-first planner only; no search typing in this version.`,
    `- Rules-first planner: at most **${MAX_LOOP_ACTIONS}** actions after load, **~${Math.round(LOOP_WALL_MS / 1000)}s** wall clock.`,
    ``,
    `The **managed browser stays open**; use **Stop GoHAM** to close it. **Pause** / **Take over** let you control the window without ending the session until you **Resume** or **Stop**.`,
    ``,
    `---`,
    `**Safety:** GoHAM does not automate purchases, permissions, or your default browser profile.`,
  ]
    .filter(Boolean)
    .join("\n");

  patchIdFull(summarizeId, "done", { actionType: "summarize", result: stopLabel });
  addRow({
    label: insufficientEvidence ? "Insufficient evidence" : "Done",
    status: "done",
    detail: stopLabel,
    actionType: "done",
    result: stopReason,
  });

  return { ok: true, assistantText };
}
