/**
 * Phase 2 PR 3 ΓÇö SSE migration hard cut.
 *
 * Custom React hook: opens a native EventSource against
 * GET /api/jobs/<jobId>/stream, accumulates SSEEvents, and closes on
 * terminal events or component unmount.
 *
 * Contract (Subsystem 4):
 *   useJobStream(jobId) ΓåÆ { events, connectionState, lastSeq }
 *   - jobId=null ΓåÆ { events:[], connectionState:"closed", lastSeq:0 }, no EventSource
 *   - Honors Last-Event-ID reconnect natively (browser sends `id:` on reconnect)
 *   - Auto-reconnects on transient disconnect (native EventSource behaviour)
 *   - Closes EventSource on unmount AND on terminal events
 *     (job_completed | job_failed | job_cancelled)
 *
 * Spec:  docs/PHASE_2_DESIGN.md ┬º Subsystem 4
 * ADR:   docs/adr/0010-sse-migration-hard-cut.md
 * ADR:   docs/adr/0002-sse-with-replay-for-worker-events.md
 * Types: src/ham/builder_plan.py (Python mirror) ΓåÉ frontend/src/lib/ham/builderPlan.ts
 */
import * as React from "react";

import { apiUrl } from "@/lib/ham/api";
import type { SSEEvent } from "@/lib/ham/builderPlan";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Job status event types that terminate the stream. */
const TERMINAL_EVENT_TYPES = new Set<string>([
  "job_completed",
  "job_failed",
  "job_cancelled",
]);

/**
 * All 11 event payload types from Phase 0 Contract 4.
 *
 * We register one addEventListener listener per type because native
 * EventSource `onmessage` does NOT fire for SSE frames that carry an
 * explicit `event:` field (only fires for frames without one, or with
 * `event: message`).  The backend always sends a named event type.
 */
const ALL_PAYLOAD_TYPES: readonly string[] = [
  "step_started",
  "step_log",
  "step_completed",
  "step_failed",
  "job_started",
  "job_completed",
  "job_failed",
  "job_cancelled",
  "cancel_acknowledged",
  "runtime_error",
  "heartbeat",
] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type JobStreamConnectionState = "connecting" | "open" | "closed" | "error";

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useJobStream ΓÇö consumes the per-job SSE stream.
 *
 * @param jobId - Phase 2 CloudRuntimeJob id.  Pass `null` before a Plan is
 *   approved ΓÇö the hook returns empty/closed state without opening any socket.
 */
export function useJobStream(jobId: string | null): {
  events: SSEEvent[];
  connectionState: JobStreamConnectionState;
  lastSeq: number;
} {
  const [events, setEvents] = React.useState<SSEEvent[]>([]);
  const [connectionState, setConnectionState] =
    React.useState<JobStreamConnectionState>("closed");
  const [lastSeq, setLastSeq] = React.useState(0);

  React.useEffect(() => {
    if (!jobId) {
      setEvents([]);
      setConnectionState("closed");
      setLastSeq(0);
      return;
    }

    // Reset accumulated state for this new jobId.
    setEvents([]);
    setLastSeq(0);
    setConnectionState("connecting");

    const url = apiUrl(`/api/jobs/${encodeURIComponent(jobId)}/stream`);
    const es = new EventSource(url, { withCredentials: true });

    // Guard: once we intentionally close the EventSource, suppress further
    // state updates (avoids setState-after-unmount warnings).
    let closed = false;

    const closeAndMark = (): void => {
      if (!closed) {
        closed = true;
        es.close();
        setConnectionState("closed");
      }
    };

    // -- lifecycle callbacks --------------------------------------------------

    es.onopen = () => {
      if (!closed) setConnectionState("open");
    };

    es.onerror = () => {
      if (closed) return;
      // readyState 2 = CLOSED: the EventSource will not reconnect.
      // readyState 0 = CONNECTING: the browser is attempting reconnect.
      // We reflect the native state but do NOT call closeAndMark() here ΓÇö
      // let the EventSource handle its own reconnect loop per ADR-0002.
      setConnectionState(es.readyState === 2 ? "error" : "connecting");
    };

    // -- event handler --------------------------------------------------------

    const handleEvent = (ev: MessageEvent): void => {
      if (closed) return;
      try {
        const sseEvent = JSON.parse(ev.data as string) as SSEEvent;
        // Heartbeats are in-band keep-alives; filter them from the events list.
        if (sseEvent.event?.type === "heartbeat") return;
        setEvents((prev) => [...prev, sseEvent]);
        setLastSeq(sseEvent.seq);
        if (TERMINAL_EVENT_TYPES.has(sseEvent.event?.type)) {
          closeAndMark();
        }
      } catch {
        // Ignore malformed frames ΓÇö network noise must not crash the hook.
      }
    };

    // Register a listener for every named payload type (backend always sends
    // a named `event:` field).  Also register the generic `message` listener
    // as a safety net for frames without an explicit event type.
    for (const type of ALL_PAYLOAD_TYPES) {
      es.addEventListener(type, handleEvent as EventListener);
    }
    es.addEventListener("message", handleEvent as EventListener);

    // -- cleanup --------------------------------------------------------------

    return () => {
      closeAndMark();
    };
  }, [jobId]);

  return { events, connectionState, lastSeq };
}
