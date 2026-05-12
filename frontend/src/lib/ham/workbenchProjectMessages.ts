import { PROJECT_WORKSPACE_GATE_MESSAGE } from "@/lib/ham/projectWorkspaceGateCopy";

/** Softens backend builder errors that echo raw ids for mismatched workspace/project ids. */
export function sanitizeWorkbenchProjectAccessMessage(raw: string): string {
  const t = raw.trim();
  if (/unknown\s+project_id\b/i.test(t)) {
    return PROJECT_WORKSPACE_GATE_MESSAGE;
  }
  if (/project\s+record\s+not\s+found\b/i.test(t)) {
    return PROJECT_WORKSPACE_GATE_MESSAGE;
  }
  return raw;
}
