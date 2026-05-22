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

/** User-facing copy for Workbench project download failures (no internal paths or codes). */
export function sanitizeWorkbenchDownloadErrorMessage(raw: string): string {
  const t = raw.trim();
  if (!t) return "Could not download the project. Try again in a moment.";
  if (/unknown\s+project_id\b/i.test(t) || /project\s+record\s+not\s+found\b/i.test(t)) {
    return PROJECT_WORKSPACE_GATE_MESSAGE;
  }
  if (/not ready to download/i.test(t)) return t;
  if (/could not download/i.test(t)) return t;
  if (/http\s+\d+/i.test(t)) return "Could not download the project. Try again in a moment.";
  if (/artifact|snapshot|builder-artifact|gcs|bucket|argv|token|runner/i.test(t)) {
    return "Could not download the project. Try again in a moment.";
  }
  return "Could not download the project. Try again in a moment.";
}
