/**
 * Phase 2 PR 3 ΓÇö useJobStream hook unit tests.
 *
 * Uses a fake EventSource global (no real network). All assertions run in
 * jsdom via vitest; no Clerk, no fetch.
 *
 * Test matrix:
 *   1. null jobId ΓåÆ closed state, no EventSource opened
 *   2. valid jobId ΓåÆ EventSource opened to correct URL
 *   3. open event ΓåÆ connectionState becomes "open"
 *   4. events accumulated from named SSE messages
 *   5. terminal event (job_completed) ΓåÆ EventSource closed
 *   6. terminal event (job_failed)    ΓåÆ EventSource closed
 *   7. terminal event (job_cancelled) ΓåÆ EventSource closed
 *   8. component unmount              ΓåÆ EventSource closed
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SSEEvent } from "@/lib/ham/builderPlan";
import { useJobStream } from "@/lib/ham/useJobStream";

// ---------------------------------------------------------------------------
// Fake EventSource
// ---------------------------------------------------------------------------

type Listener = (ev: Event | MessageEvent) => void;

/**
 * A synchronous, fully-controllable stand-in for the browser EventSource.
 *
 * Tests obtain the latest instance via `FakeEventSource.instances.at(-1)` and
 * call trigger helpers to fire synthetic events.
 */
class FakeEventSource {
  /** All instances created in this test run; cleared in beforeEach. */
  static instances: FakeEventSource[] = [];

  static clear(): void {
    FakeEventSource.instances = [];
  }

  readonly url: string;
  readyState = 0; // 0=CONNECTING, 1=OPEN, 2=CLOSED

  onopen: ((ev: Event) => unknown) | null = null;
  onerror: ((ev: Event) => unknown) | null = null;
  onmessage: ((ev: MessageEvent) => unknown) | null = null;

  private readonly _listeners = new Map<string, Set<Listener>>();

  /** How many times .close() was called ΓÇö assertions check > 0. */
  closeCalled = 0;

  constructor(url: string, _init?: EventSourceInit) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (!this._listeners.has(type)) this._listeners.set(type, new Set());
    const fn = typeof listener === "function" ? listener : listener.handleEvent;
    this._listeners.get(type)!.add(fn as Listener);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const fn = typeof listener === "function" ? listener : listener.handleEvent;
    this._listeners.get(type)?.delete(fn as Listener);
  }

  close(): void {
    this.readyState = 2;
    this.closeCalled += 1;
  }

  // ---- Test-only trigger helpers ------------------------------------------

  /** Simulate the SSE connection opening successfully. */
  triggerOpen(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  /**
   * Simulate an error event.
   * Pass `readyState=2` to simulate a permanent close (won't reconnect).
   */
  triggerError(readyState = 0): void {
    this.readyState = readyState;
    this.onerror?.(new Event("error"));
  }

  /**
   * Simulate an incoming SSE frame with a named event type and JSON data.
   * This dispatches to all `addEventListener(type, ...)` listeners and also
   * to `onmessage` when type is "message".
   */
  triggerEvent(type: string, data: unknown): void {
    const ev = new MessageEvent(type, { data: JSON.stringify(data) });
    const listeners = this._listeners.get(type);
    if (listeners) {
      for (const l of listeners) l(ev);
    }
    if (type === "message") {
      this.onmessage?.(ev);
    }
  }

  /**
   * Simulate malformed data (non-JSON) on a given event type.
   * Used to verify the hook silently ignores bad frames.
   */
  triggerMalformedEvent(type: string): void {
    const ev = new MessageEvent(type, { data: "NOT_JSON{{" });
    const listeners = this._listeners.get(type);
    if (listeners) {
      for (const l of listeners) l(ev);
    }
  }
}

// ---------------------------------------------------------------------------
// Event payload factories
// ---------------------------------------------------------------------------

function makeSSEEvent(seq: number, eventPayload: SSEEvent["event"]): SSEEvent {
  return {
    version: "1.0.0",
    seq,
    job_id: "job-test",
    plan_id: "pln-test",
    occurred_at: "2026-05-18T00:00:00Z",
    event: eventPayload,
  };
}

const stepStarted = (seq: number): SSEEvent =>
  makeSSEEvent(seq, { type: "step_started", step_id: "stp-1", step_index: 0, title: "Step 1" });

const jobCompleted = (seq: number): SSEEvent => makeSSEEvent(seq, { type: "job_completed" });

const jobFailed = (seq: number): SSEEvent =>
  makeSSEEvent(seq, {
    type: "job_failed",
    error: {
      version: "1.0.0",
      error_code: "worker.unknown",
      error_message: "Something broke",
      error_details: null,
      retriable: false,
      fatal: true,
      occurred_at: "2026-05-18T00:00:00Z",
    },
  });

const jobCancelled = (seq: number): SSEEvent =>
  makeSSEEvent(seq, { type: "job_cancelled", cancelled_at_step_id: null });

const heartbeat = (seq: number): SSEEvent => makeSSEEvent(seq, { type: "heartbeat" });

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

const ORIG_EVENT_SOURCE = globalThis.EventSource;

beforeEach(() => {
  FakeEventSource.clear();
  // Replace the global EventSource with our fake.
  globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
});

afterEach(() => {
  globalThis.EventSource = ORIG_EVENT_SOURCE;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useJobStream", () => {
  // 1 -----------------------------------------------------------------------
  it("null jobId ΓåÆ closed state, no EventSource opened", () => {
    const { result } = renderHook(() => useJobStream(null));

    expect(result.current.events).toEqual([]);
    expect(result.current.connectionState).toBe("closed");
    expect(result.current.lastSeq).toBe(0);
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  // 2 -----------------------------------------------------------------------
  it("valid jobId ΓåÆ EventSource opened to correct URL", () => {
    renderHook(() => useJobStream("job-abc"));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0]!.url).toBe("/api/jobs/job-abc/stream");
  });

  it("valid jobId ΓåÆ initial connectionState is 'connecting'", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    expect(result.current.connectionState).toBe("connecting");
  });

  // 3 -----------------------------------------------------------------------
  it("open event ΓåÆ connectionState becomes 'open'", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
    });

    expect(result.current.connectionState).toBe("open");
  });

  // 4 -----------------------------------------------------------------------
  it("events accumulated from EventSource messages", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("step_started", stepStarted(1));
      es.triggerEvent("step_started", stepStarted(2));
    });

    expect(result.current.events).toHaveLength(2);
    expect(result.current.events[0]!.seq).toBe(1);
    expect(result.current.events[1]!.seq).toBe(2);
    expect(result.current.lastSeq).toBe(2);
  });

  it("lastSeq tracks highest received seq", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("step_started", stepStarted(10));
      es.triggerEvent("step_started", stepStarted(11));
    });

    expect(result.current.lastSeq).toBe(11);
  });

  it("heartbeat events are NOT accumulated in the events list", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("step_started", stepStarted(1));
      es.triggerEvent("heartbeat", heartbeat(2));
      es.triggerEvent("step_started", stepStarted(3));
    });

    // Only the two step_started events; heartbeat filtered out.
    expect(result.current.events).toHaveLength(2);
  });

  it("malformed event data is silently ignored", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("step_started", stepStarted(1));
      es.triggerMalformedEvent("step_started");
      es.triggerEvent("step_started", stepStarted(2));
    });

    expect(result.current.events).toHaveLength(2);
  });

  // 5 -----------------------------------------------------------------------
  it("terminal event job_completed ΓåÆ EventSource closed", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("job_completed", jobCompleted(5));
    });

    expect(es.closeCalled).toBeGreaterThan(0);
    expect(result.current.connectionState).toBe("closed");
    // The terminal event itself is still accumulated.
    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0]!.event.type).toBe("job_completed");
  });

  // 6 -----------------------------------------------------------------------
  it("terminal event job_failed ΓåÆ EventSource closed", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("job_failed", jobFailed(3));
    });

    expect(es.closeCalled).toBeGreaterThan(0);
    expect(result.current.connectionState).toBe("closed");
    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0]!.event.type).toBe("job_failed");
  });

  // 7 -----------------------------------------------------------------------
  it("terminal event job_cancelled ΓåÆ EventSource closed", () => {
    const { result } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("job_cancelled", jobCancelled(4));
    });

    expect(es.closeCalled).toBeGreaterThan(0);
    expect(result.current.connectionState).toBe("closed");
  });

  // 8 -----------------------------------------------------------------------
  it("component unmount ΓåÆ EventSource closed", () => {
    const { unmount } = renderHook(() => useJobStream("job-abc"));
    const es = FakeEventSource.instances[0]!;
    expect(es.closeCalled).toBe(0);

    act(() => {
      unmount();
    });

    expect(es.closeCalled).toBeGreaterThan(0);
  });

  it("jobId change ΓåÆ old EventSource closed, new one opened", () => {
    const { rerender } = renderHook(({ id }: { id: string | null }) => useJobStream(id), {
      initialProps: { id: "job-first" as string | null },
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    const first = FakeEventSource.instances[0]!;

    act(() => {
      rerender({ id: "job-second" });
    });

    expect(first.closeCalled).toBeGreaterThan(0);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1]!.url).toBe("/api/jobs/job-second/stream");
  });

  it("jobId transitions to null ΓåÆ EventSource closed, events cleared", () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useJobStream(id),
      { initialProps: { id: "job-abc" as string | null } },
    );
    const es = FakeEventSource.instances[0]!;

    act(() => {
      es.triggerOpen();
      es.triggerEvent("step_started", stepStarted(1));
    });

    act(() => {
      rerender({ id: null });
    });

    expect(es.closeCalled).toBeGreaterThan(0);
    expect(result.current.events).toEqual([]);
    expect(result.current.connectionState).toBe("closed");
    expect(result.current.lastSeq).toBe(0);
  });
});
