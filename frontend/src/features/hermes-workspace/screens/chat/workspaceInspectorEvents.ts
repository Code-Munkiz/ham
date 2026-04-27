/**
 * Real workspace chat inspector timeline — derived from HAM `/api/chat/stream` turns
 * and session history loads only (no synthetic Hermes VM activity).
 */

export type WorkspaceInspectorEventKind =
  | "session_history_loaded"
  | "user_message_sent"
  | "assistant_stream_started"
  | "session_assigned"
  | "assistant_response_completed"
  | "stream_error";

export type WorkspaceInspectorEventStatus = "ok" | "error" | "info" | "warning";

export type WorkspaceInspectorEvent = {
  id: string;
  atIso: string;
  kind: WorkspaceInspectorEventKind;
  status: WorkspaceInspectorEventStatus;
  /** Activity tab — human-readable, no secrets */
  summary: string;
  /** Logs tab — safe scalar metadata only */
  meta?: Record<string, string | number | boolean | null>;
};

const MAX_EVENTS = 200;

let seq = 0;

export function nextInspectorEventId(): string {
  seq += 1;
  return `hww-ins-${Date.now()}-${seq}`;
}

/** Truncate user-facing error text; avoid dumping long HTML or traces. */
export function safeInspectorErrorMessage(message: string, maxLen = 240): string {
  const t = message.replace(/\s+/g, " ").trim();
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen)}…`;
}

export function appendInspectorEvent(
  prev: WorkspaceInspectorEvent[],
  ev: Omit<WorkspaceInspectorEvent, "id"> & { id?: string },
): WorkspaceInspectorEvent[] {
  const row: WorkspaceInspectorEvent = {
    ...ev,
    id: ev.id ?? nextInspectorEventId(),
  };
  const next = [...prev, row];
  return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next;
}

/** Fill `meta.session_id` on rows that are missing it (live turn before server assigns id). */
export function patchInspectorEventsSessionId(
  prev: WorkspaceInspectorEvent[],
  sessionId: string,
): WorkspaceInspectorEvent[] {
  return prev.map((e) => {
    const sid = e.meta?.session_id;
    if (sid != null && sid !== "") return e;
    return {
      ...e,
      meta: { ...e.meta, session_id: sessionId },
    };
  });
}
