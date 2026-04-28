/**
 * Optional GoHAM LLM-assisted planner interface.
 *
 * Important: no browser action is executed from this module. It only returns a
 * proposed JSON action. The research loop must validate and may fall back.
 */

import type { HamDesktopRealBrowserClickCandidate } from "@/lib/ham/desktopBundleBridge";
import { classifyGohamCandidate } from "./gohamSafetyClassifier";
import { parseGohamPlannerAction, type GohamPlannerAction } from "./gohamPlannerSchema";

export const GOHAM_LLM_PLANNER_ENABLED =
  (import.meta.env.VITE_GOHAM_LLM_PLANNER as string | undefined)?.trim() === "1";

export const GOHAM_PLANNER_MIN_CONFIDENCE = 0.55;

export type GohamPlannerCandidate = {
  id: string;
  text: string;
  tag: string;
  role: string | null;
  risk: string;
  score: number;
  safety: string;
};

export type GohamPlannerInput = {
  goal: string;
  currentUrl: string;
  title: string;
  requiredEvidenceTerms: string[];
  observedEvidenceTerms: string[];
  missingEvidenceTerms: string[];
  candidates: GohamPlannerCandidate[];
  stepNumber: number;
  remainingBudget: number;
};

export type GohamPlannerResult =
  | { ok: true; action: GohamPlannerAction; source: "llm" }
  | { ok: false; reason: string; source: "disabled" | "unavailable" | "parse" | "validate" };

export function compactPlannerCandidate(
  candidate: HamDesktopRealBrowserClickCandidate,
  score: number,
): GohamPlannerCandidate {
  const safety = classifyGohamCandidate(candidate);
  return {
    id: candidate.id,
    text: candidate.text.replace(/\s+/gu, " ").trim().slice(0, 80),
    tag: candidate.tag,
    role: candidate.role,
    risk: candidate.risk,
    score,
    safety: safety.blocked ? safety.reason : "safe",
  };
}

export function validateGohamPlannerAction(
  action: GohamPlannerAction,
  candidates: HamDesktopRealBrowserClickCandidate[],
): { ok: true } | { ok: false; reason: string } {
  if (action.confidence < GOHAM_PLANNER_MIN_CONFIDENCE) return { ok: false, reason: "low_confidence" };
  if (/\b(type|keyboard|form|submit|login|download|upload|purchase|checkout|selector|coordinate|javascript)\b/iu.test(action.reason)) {
    return { ok: false, reason: "unsafe_reason" };
  }
  if (action.type === "click_candidate") {
    const c = candidates.find((x) => x.id === action.candidate_id);
    if (!c) return { ok: false, reason: "unknown_candidate" };
    const safety = classifyGohamCandidate(c);
    if (safety.blocked) return { ok: false, reason: safety.reason };
  }
  return { ok: true };
}

/**
 * Placeholder for a future safe planner transport. We intentionally do not call
 * `/api/chat` here because it persists chat sessions and injects broad assistant
 * context. Until a narrow planner endpoint exists, enabling the flag records an
 * unavailable planner and the loop falls back to rules-first.
 */
export async function proposeGohamPlannerAction(_input: GohamPlannerInput): Promise<GohamPlannerResult> {
  if (!GOHAM_LLM_PLANNER_ENABLED) return { ok: false, reason: "planner_disabled", source: "disabled" };

  // Keep parse/validate exercised as the boundary for future transport.
  const parsed = parseGohamPlannerAction(null);
  if (!parsed.ok) return { ok: false, reason: "safe_planner_transport_unavailable", source: "unavailable" };
  return { ok: false, reason: "safe_planner_transport_unavailable", source: "unavailable" };
}
