/**
 * Strict GoHAM planner action schema.
 * The model may propose only these actions; existing validators still decide
 * whether anything is executed.
 */

export const GOHAM_PLANNER_ACTION_TYPES = ["observe", "scroll", "wait", "click_candidate", "done", "blocked"] as const;

export type GohamPlannerActionType = (typeof GOHAM_PLANNER_ACTION_TYPES)[number];

export type GohamPlannerAction = {
  type: GohamPlannerActionType;
  candidate_id?: string;
  reason: string;
  confidence: number;
};

export type GohamPlannerParseResult =
  | { ok: true; action: GohamPlannerAction }
  | { ok: false; reason: string };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function parseGohamPlannerAction(raw: unknown): GohamPlannerParseResult {
  let obj: unknown = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return { ok: false, reason: "malformed_json" };
    }
  }
  if (!isRecord(obj)) return { ok: false, reason: "not_object" };

  const type = obj.type;
  if (typeof type !== "string" || !GOHAM_PLANNER_ACTION_TYPES.includes(type as GohamPlannerActionType)) {
    return { ok: false, reason: "unknown_action_type" };
  }

  const confidence = Number(obj.confidence);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    return { ok: false, reason: "invalid_confidence" };
  }

  const reason = typeof obj.reason === "string" ? obj.reason.replace(/\s+/gu, " ").trim() : "";
  if (!reason) return { ok: false, reason: "missing_reason" };

  const candidateId = typeof obj.candidate_id === "string" ? obj.candidate_id.trim() : undefined;
  if (type === "click_candidate" && !candidateId) return { ok: false, reason: "missing_candidate_id" };

  return {
    ok: true,
    action: {
      type: type as GohamPlannerActionType,
      ...(candidateId ? { candidate_id: candidateId } : {}),
      reason: reason.length > 160 ? `${reason.slice(0, 160)}...` : reason,
      confidence,
    },
  };
}
