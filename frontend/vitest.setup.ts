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

/** jsdom lacks ResizeObserver; workspace composer and other panels use layout observers. */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
