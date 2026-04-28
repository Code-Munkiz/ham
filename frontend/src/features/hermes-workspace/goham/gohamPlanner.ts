/**
 * Optional GoHAM LLM-assisted planner interface.
 *
 * Important: no browser action is executed from this module. It only returns a
 * proposed JSON action. The research loop must validate and may fall back.
 */

import type { HamDesktopRealBrowserClickCandidate } from "@/lib/ham/desktopBundleBridge";
import { hamApiFetch } from "@/lib/ham/api";
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

type GohamPlannerApiResponse = {
  kind: "goham_planner_next_action";
  schema_version: 1;
  status: "ok" | "fallback" | "error";
  planner_mode: "llm" | "fallback";
  action?: unknown;
  warnings?: string[];
};

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

export async function proposeGohamPlannerAction(input: GohamPlannerInput): Promise<GohamPlannerResult> {
  if (!GOHAM_LLM_PLANNER_ENABLED) return { ok: false, reason: "planner_disabled", source: "disabled" };

  let response: Response;
  try {
    response = await hamApiFetch("/api/goham/planner/next-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  } catch {
    return { ok: false, reason: "planner_endpoint_unavailable", source: "unavailable" };
  }
  if (!response.ok) return { ok: false, reason: `planner_http_${response.status}`, source: "unavailable" };

  let payload: GohamPlannerApiResponse;
  try {
    payload = (await response.json()) as GohamPlannerApiResponse;
  } catch {
    return { ok: false, reason: "planner_bad_json", source: "parse" };
  }
  if (payload.kind !== "goham_planner_next_action" || payload.schema_version !== 1) {
    return { ok: false, reason: "planner_bad_schema", source: "parse" };
  }
  if (payload.status !== "ok" || payload.planner_mode !== "llm") {
    const warning = Array.isArray(payload.warnings) && payload.warnings[0] ? String(payload.warnings[0]) : payload.status;
    return { ok: false, reason: warning, source: payload.status === "error" ? "validate" : "unavailable" };
  }

  const parsed = parseGohamPlannerAction(payload.action);
  if (!parsed.ok) {
    const reason = "reason" in parsed ? parsed.reason : "planner_parse_failed";
    return { ok: false, reason, source: "parse" };
  }
  return { ok: true, action: parsed.action, source: "llm" };
}
