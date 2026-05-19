/**
 * Sentry SDK wiring for the HAM frontend — Phase 1 #9 (ADR-0008).
 *
 * Wraps Sentry.init() with HAM defaults. SDK is dormant when
 * VITE_SENTRY_DSN is unset or empty — no network traffic, no errors thrown.
 *
 * Usage: call init() once before the React root render (main.tsx).
 */

import * as Sentry from "@sentry/react";

/** True after init() has been called with a non-empty DSN. */
let _initialized = false;

export function init(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn || !dsn.trim()) {
    return;
  }
  if (_initialized) {
    return;
  }
  Sentry.init({
    dsn: dsn.trim(),
    tracesSampleRate: 0, // no perf overhead until owner opts in (ADR-0008)
    sendDefaultPii: false,
    integrations: [Sentry.browserTracingIntegration()],
  });
  _initialized = true;
}

/** Return true if init() was called with a non-empty DSN. */
export function isActive(): boolean {
  return _initialized;
}

/** Reset state between tests. Call from test teardown only. */
export function resetForTests(): void {
  _initialized = false;
}
