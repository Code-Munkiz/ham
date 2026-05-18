/**
 * Posture fields (`workbench_mode`, `worker`) attached to outbound `/api/chat/stream` payloads.
 *
 * Ordinary chat must NOT default to `workbench_mode: "agent"` / `worker: "builder"` — those values
 * mean "treat this turn as a builder/agent turn" and contaminate normal chat voice. The fields are
 * included only when the operator has explicitly chosen them through the workbench / builder UI
 * affordance.
 */

export type WorkbenchModePosture = "ask" | "plan" | "agent";

export type WorkspaceChatPostureInputs = {
  workbenchMode?: WorkbenchModePosture | null;
  worker?: string | null;
};

export type WorkspaceChatPostureFields = {
  workbench_mode?: WorkbenchModePosture;
  worker?: string;
};

export function buildWorkspaceChatPostureFields(
  opts: WorkspaceChatPostureInputs,
): WorkspaceChatPostureFields {
  const out: WorkspaceChatPostureFields = {};
  const mode = opts.workbenchMode;
  if (mode === "ask" || mode === "plan" || mode === "agent") {
    out.workbench_mode = mode;
  }
  const worker = typeof opts.worker === "string" ? opts.worker.trim() : "";
  if (worker) {
    out.worker = worker;
  }
  return out;
}
