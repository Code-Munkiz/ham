/**
 * GoHAM v1 Slice 2 — bounded rules-first research loop (desktop managed browser only).
 * Uses Slice 1 primitives; no model planner, no type/key, no forms.
 */

import type {
  HamDesktopLocalControlApi,
  HamDesktopRealBrowserClickCandidate,
  HamDesktopRealBrowserObserveCompactResult,
} from "@/lib/ham/desktopBundleBridge";
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

export type GohamResearchStopReason = "complete" | "budget" | "time" | "stopped" | "error";

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
};

/** Rules-first planner: token overlap on candidates, else scroll, else done. */
export function rulesFirstPlan(ctx: PlanCtx): GohamLoopAction {
  const { goalTokens, candidates, lastClickedId, scrollsThisPage, loopIteration, lastTitle } = ctx;

  if (taskAppearsComplete(lastTitle, goalTokens)) {
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

  if (scrollsThisPage < 3) {
    return { type: "scroll", reason: "No matching link in view — scrolling", risk: "low" };
  }

  return { type: "done", reason: "No further relevant actions", risk: "low" };
}

export type RunGohamResearchOptions = {
  api: HamDesktopLocalControlApi;
  url: string;
  taskText: string;
  onTrail: (steps: GoHamTrailStep[]) => void;
  shouldAbort: () => boolean;
};

export type RunGohamResearchResult =
  | { ok: true; assistantText: string }
  | { ok: false; userMessage: string; trailSteps: GoHamTrailStep[] };

export async function runGohamResearchFlow(opts: RunGohamResearchOptions): Promise<RunGohamResearchResult> {
  const { api, url, taskText, onTrail, shouldAbort } = opts;
  const redacted = redactUrlForTrail(url);
  const goalTokens = goalTokensFromTask(taskText, url);

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
  const patchId = (id: string, status: GoHamTrailStep["status"], detail?: string) => {
    pushTrail(
      trail.map((s) => (s.id === id ? { ...s, status, ...(detail !== undefined ? { detail } : {}) } : s)),
    );
  };
  const activate = (label: string): string => {
    seq += 1;
    const id = `gr-${seq}`;
    const prev = trail.map((s) => (s.status === "active" ? { ...s, status: "done" as const } : s));
    pushTrail([...prev, { id, label, status: "active" }]);
    return id;
  };

  const visited: { title: string; display: string }[] = [];
  let stopReason: GohamResearchStopReason = "complete";
  let errorMessage: string | null = null;

  if (shouldAbort()) {
    add("GoHAM stopped", "error", "Before start");
    return { ok: false, userMessage: "GoHAM was stopped before it started.", trailSteps: trail };
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
    patchId(shotId, "error", msg);
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  let obs = await readObserve();
  if (!obs || obs.ok !== true) {
    const msg = sessionErrorMessage(obs, "Observe");
    patchId(shotId, "error", msg);
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  const pub0 = await api.getRealBrowserStatus();
  const title0 = (pub0.title || obs.title || "").trim() || "(no title)";
  const display0 = redactUrlForTrail((pub0.display_url || obs.display_url || obs.url || "").trim() || redacted);
  visited.push({ title: title0, display: display0 });
  patchId(shotId, "done", redactUrlForTrail(display0));

  const listId = activate("Listing click candidates");
  let enumR = await api.realBrowserEnumerateClickCandidates();
  if (!enumR || enumR.ok !== true) {
    const msg = sessionErrorMessage(enumR, "Candidates");
    patchId(listId, "error", msg);
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: trail };
  }
  let candidates = enumR.candidates;
  patchId(listId, "done", `${candidates.length} visible`);

  const loopStart = Date.now();
  let lastClickedId: string | null = null;
  let scrollsThisPage = 0;
  let lastDisplayUrl = display0;
  let loopIteration = 0;
  let lastTitle = title0;

  let hitExplicitDone = false;

  if (taskAppearsComplete(lastTitle, goalTokens)) {
    stopReason = "complete";
    hitExplicitDone = true;
  } else {
    while (loopIteration < MAX_LOOP_ACTIONS && Date.now() - loopStart < LOOP_WALL_MS && !shouldAbort()) {
      const action = rulesFirstPlan({
        taskText,
        goalTokens,
        candidates,
        lastClickedId,
        scrollsThisPage,
        loopIteration,
        lastTitle,
      });
      const v = validatePlannerAction(action, candidates);
      if (v.ok === false) {
        stopReason = "error";
        errorMessage = v.reason;
        add("Blocked", "error", "Invalid planned action");
        break;
      }
      if (action.type === "done") {
        stopReason = "complete";
        hitExplicitDone = true;
        add("Done", "done", redactSnippet(action.reason, 80));
        break;
      }

      if (action.type === "click_candidate" && action.candidate_id) {
        const cand = candidates.find((c) => c.id === action.candidate_id);
        const cid = activate("Clicking candidate");
        const clickR = await api.realBrowserClickCandidate(action.candidate_id);
        if (!clickR || clickR.ok !== true) {
          const msg = sessionErrorMessage(clickR, "Click");
          patchId(cid, "error", msg);
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        lastClickedId = action.candidate_id;
        patchId(
          cid,
          "done",
          cand ? redactSnippet(cand.text, 36) : "candidate",
        );
        const w = await api.realBrowserWaitMs(WAIT_AFTER_CLICK_MS);
        if (!w || w.ok !== true) {
          stopReason = "error";
          errorMessage = sessionErrorMessage(w, "Wait after click");
          add("Waiting", "error", errorMessage);
          break;
        }
      } else if (action.type === "scroll") {
        const sid = activate("Scrolling");
        const sr = await api.realBrowserScrollVertical(SCROLL_DELTA);
        if (!sr || sr.ok !== true) {
          const msg = sessionErrorMessage(sr, "Scroll");
          patchId(sid, "error", msg);
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        scrollsThisPage += 1;
        patchId(sid, "done", `Δ ${sr.delta_applied ?? SCROLL_DELTA}`);
      } else if (action.type === "wait") {
        const wid = activate("Waiting");
        const wr = await api.realBrowserWaitMs(SETTLE_WAIT_MS);
        if (!wr || wr.ok !== true) {
          const msg = sessionErrorMessage(wr, "Wait");
          patchId(wid, "error", msg);
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        patchId(wid, "done", `${wr.waited_ms ?? SETTLE_WAIT_MS}ms`);
      } else if (action.type === "observe") {
        const oid = activate("Re-observing");
        obs = await readObserve();
        if (!obs || obs.ok !== true) {
          const msg = sessionErrorMessage(obs, "Observe");
          patchId(oid, "error", msg);
          stopReason = "error";
          errorMessage = msg;
          break;
        }
        patchId(oid, "done", redactSnippet(obs.title || "", 48));
      }

      loopIteration += 1;

      if (shouldAbort()) {
        stopReason = "stopped";
        add("Stopped by user", "error", "Stop GoHAM");
        break;
      }
      if (Date.now() - loopStart >= LOOP_WALL_MS) {
        stopReason = "time";
        hitExplicitDone = true;
        add("Time budget reached", "done", "Wall clock limit");
        break;
      }

      const reId = activate("Re-observing");
      obs = await readObserve();
      if (!obs || obs.ok !== true) {
        const msg = sessionErrorMessage(obs, "Observe");
        patchId(reId, "error", msg);
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
      patchId(reId, "done", redactSnippet(lastTitle, 48));

      enumR = await api.realBrowserEnumerateClickCandidates();
      if (!enumR || enumR.ok !== true) {
        const msg = sessionErrorMessage(enumR, "Candidates");
        add("Listing click candidates", "error", msg);
        stopReason = "error";
        errorMessage = msg;
        break;
      }
      candidates = enumR.candidates;
      add("Listing click candidates", "done", `${candidates.length} visible`);

      if (taskAppearsComplete(lastTitle, goalTokens)) {
        stopReason = "complete";
        hitExplicitDone = true;
        add("Done", "done", "Goal appears satisfied");
        break;
      }
    }

    if (!hitExplicitDone && stopReason === "complete" && loopIteration >= MAX_LOOP_ACTIONS) {
      stopReason = "budget";
      add("Step budget reached", "done", `${MAX_LOOP_ACTIONS} actions`);
    } else if (!hitExplicitDone && stopReason === "complete" && Date.now() - loopStart >= LOOP_WALL_MS) {
      stopReason = "time";
      add("Time budget reached", "done", "Wall clock limit");
    } else if (shouldAbort() && stopReason === "complete" && !errorMessage) {
      stopReason = "stopped";
      add("Stopped by user", "error", "Stop GoHAM");
    }
  }

  const summarizeId = activate("Summarizing");
  const linesVisited = visited
    .map((v, i) => `${i + 1}. ${redactSnippet(v.title, 60)} — ${v.display}`)
    .join("\n");

  const stopLabel = ((): string => {
    switch (stopReason) {
      case "complete":
        return "Task complete or planner finished";
      case "budget":
        return "Step budget (max actions)";
      case "time":
        return "Time budget (~75s)";
      case "stopped":
        return "You stopped GoHAM";
      case "error":
      default:
        return "Error";
    }
  })();

  const assistantText = [
    `**GoHAM research (v1 Slice 2)**`,
    ``,
    `**What we found**`,
    `- **Latest page:** ${redactSnippet(lastTitle, 80)}`,
    goalTokens.length ? `- **Keywords tracked:** ${goalTokens.slice(0, 8).join(", ")}${goalTokens.length > 8 ? "…" : ""}` : `- (No keywords extracted from your message.)`,
    ``,
    `**Pages visited**`,
    linesVisited || `- ${redacted}`,
    ``,
    `**Stop reason:** ${stopLabel}`,
    errorMessage ? `**Error:** ${errorMessage}` : ``,
    ``,
    `**Limitations:** At most **${MAX_LOOP_ACTIONS}** actions after load, **~${Math.round(LOOP_WALL_MS / 1000)}s** wall clock, rules-first planner (token overlap on link text). No forms, logins, downloads, or typing.`,
    ``,
    `Screenshot bytes were used locally only — **not embedded** here. The **managed browser stays open**; use **Stop GoHAM** to close it.`,
    ``,
    `---`,
    `**Safety:** GoHAM does not automate purchases, permissions, or your default browser profile.`,
  ]
    .filter(Boolean)
    .join("\n");

  patchId(summarizeId, "done");
  add("Done", "done", stopLabel);

  return { ok: true, assistantText };
}
