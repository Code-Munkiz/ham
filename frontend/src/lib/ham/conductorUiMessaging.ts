import { PROJECT_WORKSPACE_GATE_MESSAGE } from "@/lib/ham/projectWorkspaceGateCopy";

/** Maps server/conductor blocker text that leaks raw ids into a gate message. */
export function sanitizeConductorUserFacingLine(raw: string): string {
  const t = raw.trim();
  if (!t) return t;
  if (/unknown\s+project_id\b/i.test(t)) {
    return PROJECT_WORKSPACE_GATE_MESSAGE;
  }
  if (/project\s+record\s+not\s+found\b/i.test(t)) {
    return PROJECT_WORKSPACE_GATE_MESSAGE;
  }
  return raw;
}
