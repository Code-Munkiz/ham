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
  | "stream_error"
  | "goham_observe_started"
  | "goham_observe_completed"
  | "goham_research_started"
  | "goham_research_completed";

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

/** Short label for the event type — used in the Inspector, not as raw `kind` snake_case. */
export function humanInspectorKindLabel(kind: WorkspaceInspectorEventKind): string {
  switch (kind) {
    case "session_history_loaded":
      return "History";
    case "user_message_sent":
      return "Your message";
    case "assistant_stream_started":
      return "Reply started";
    case "session_assigned":
      return "Session";
    case "assistant_response_completed":
      return "Reply";
    case "stream_error":
      return "Error";
    case "goham_observe_started":
      return "Observe started";
    case "goham_observe_completed":
      return "Observe completed";
    case "goham_research_started":
      return "Research started";
    case "goham_research_completed":
      return "Research completed";
    default:
      return "Event";
  }
}

/**
 * One optional detail line from meta, excluding internal ids.
 * (Ids remain on the event for debugging via devtools, not in the main UI.)
 */
export function publicMetaSummary(meta: WorkspaceInspectorEvent["meta"]): string | null {
  if (!meta || Object.keys(meta).length === 0) return null;
  const parts: string[] = [];
  const mc = meta.message_count;
  if (typeof mc === "number" && mc > 0) {
    parts.push(`${mc} message${mc === 1 ? "" : "s"}`);
  }
  const ac = meta.assistant_char_count;
  if (typeof ac === "number" && ac > 0) {
    parts.push(`reply ${ac} character${ac === 1 ? "" : "s"}`);
  }
  if (meta.gateway_code != null && String(meta.gateway_code).trim()) {
    parts.push(`notice: ${String(meta.gateway_code)}`);
  }
  if (meta.code === "HAM_EMAIL_RESTRICTION") {
    parts.push("access check");
  } else if (meta.code != null && String(meta.code).trim() && meta.code !== "stream_error") {
    parts.push(String(meta.code));
  }
  if (parts.length === 0) return null;
  return parts.join(" · ");
}

export function statusLabelForUi(status: WorkspaceInspectorEventStatus): string {
  switch (status) {
    case "ok":
      return "Done";
    case "error":
      return "Problem";
    case "info":
      return "Info";
    case "warning":
      return "Notice";
    default:
      return status;
  }
}
