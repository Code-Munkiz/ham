/**
 * Vitest setup — Phase C.1 baseline.
 *
 * Side-effect import that registers `@testing-library/jest-dom` matchers
 * (toBeInTheDocument, toHaveClass, etc.) on Vitest's global `expect`.
 *
 * Pure-function tests don't actually need DOM matchers, but registering
 * them globally keeps the setup uniform once we add component smoke
 * tests in a follow-up.
 */
import "@testing-library/jest-dom/vitest";

// jsdom does not implement EventSource. Stub for any legacy or incidental EventSource use;
// builder activity streams use fetch + ReadableStream (Clerk Bearer).
if (typeof globalThis.EventSource === "undefined") {
  globalThis.EventSource = class EventSourceStub {
    readonly CONNECTING = 0;
    readonly OPEN = 1;
    readonly CLOSED = 2;
    readonly url: string;
    readyState = 0;
    onopen: ((this: EventSource, ev: Event) => unknown) | null = null;
    onmessage: ((this: EventSource, ev: MessageEvent) => unknown) | null = null;
    onerror: ((this: EventSource, ev: Event) => unknown) | null = null;

    constructor(url: string | URL, _eventSourceInitDict?: Record<string, unknown>) {
      this.url = typeof url === "string" ? url : url.toString();
    }

    addEventListener(_type: string, _listener: EventListenerOrEventListenerObject): void {}

    removeEventListener(_type: string, _listener: EventListenerOrEventListenerObject): void {}

    dispatchEvent(_event: Event): boolean {
      return true;
    }

    close(): void {
      this.readyState = this.CLOSED;
    }
  } as unknown as typeof EventSource;
}
