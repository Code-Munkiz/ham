import { describe, expect, it, vi } from "vitest";

import {
  assertManagedBuildSmokePreflight,
  DEFAULT_CANONICAL_HOST,
  isHostExemptFromSmokeCanonicalCheck,
  SmokePreflightError,
  type SmokePreflightFailureCode,
} from "@/lib/ham/managedBuildSmokePreflight";

const CANONICAL_ORIGIN = `https://${DEFAULT_CANONICAL_HOST}`;

function jsonResponse(
  body: unknown,
  init: {
    status?: number;
    contentType?: string;
    traceContext?: string | null;
  } = {},
): Response {
  const headers = new Headers();
  headers.set("content-type", init.contentType ?? "application/json");
  if (init.traceContext) headers.set("x-cloud-trace-context", init.traceContext);
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status: init.status ?? 200,
    headers,
  });
}

function healthyBody() {
  return {
    version: "0.1.0",
    run_count: 0,
    capabilities: { project_agent_profiles_read: true },
  };
}

function makeFetch(response: Response | (() => Response | Promise<Response>) | Error) {
  return vi.fn(async () => {
    if (response instanceof Error) throw response;
    if (typeof response === "function") return await response();
    return response;
  });
}

async function expectCode(
  promise: Promise<unknown>,
  code: SmokePreflightFailureCode,
): Promise<SmokePreflightError> {
  let err: unknown = null;
  try {
    await promise;
  } catch (e) {
    err = e;
  }
  expect(err, `expected SmokePreflightError(${code})`).toBeInstanceOf(SmokePreflightError);
  const sm = err as SmokePreflightError;
  expect(sm.code).toBe(code);
  return sm;
}

describe("isHostExemptFromSmokeCanonicalCheck", () => {
  it("exempts localhost / 127.0.0.1 / ::1 with or without ports", () => {
    expect(isHostExemptFromSmokeCanonicalCheck("localhost")).toBe(true);
    expect(isHostExemptFromSmokeCanonicalCheck("localhost:3000")).toBe(true);
    expect(isHostExemptFromSmokeCanonicalCheck("127.0.0.1")).toBe(true);
    expect(isHostExemptFromSmokeCanonicalCheck("127.0.0.1:8000")).toBe(true);
    expect(isHostExemptFromSmokeCanonicalCheck("::1")).toBe(true);
    expect(isHostExemptFromSmokeCanonicalCheck("")).toBe(true);
  });

  it("does NOT exempt any *.vercel.app host (including stale preview / team URLs)", () => {
    expect(isHostExemptFromSmokeCanonicalCheck("ham-nine-mu.vercel.app")).toBe(false);
    expect(isHostExemptFromSmokeCanonicalCheck("ham-grvil614b-team-clarity.vercel.app")).toBe(
      false,
    );
    expect(isHostExemptFromSmokeCanonicalCheck("ham-feature-foo-team.vercel.app")).toBe(false);
  });

  it("does NOT exempt arbitrary hosts", () => {
    expect(isHostExemptFromSmokeCanonicalCheck("evil.example.com")).toBe(false);
    expect(isHostExemptFromSmokeCanonicalCheck("192.168.1.10")).toBe(false);
  });
});

describe("assertManagedBuildSmokePreflight", () => {
  it("passes on the canonical host when /api/status is healthy and trace-anchored", async () => {
    const fetchImpl = makeFetch(jsonResponse(healthyBody(), { traceContext: "abc123def456;o=1" }));
    const snap = await assertManagedBuildSmokePreflight({
      locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
      fetchImpl,
    });
    expect(snap.host).toBe(DEFAULT_CANONICAL_HOST);
    expect(snap.statusUrl).toBe(`${CANONICAL_ORIGIN}/api/status`);
    expect(snap.version).toBe("0.1.0");
    expect(snap.runCount).toBe(0);
    expect(snap.traceContext).toBe("abc123def456;o=1");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("passes on localhost dev (exempt host) when backend is healthy", async () => {
    const fetchImpl = makeFetch(
      jsonResponse(healthyBody(), { traceContext: "loopback-trace;o=1" }),
    );
    const snap = await assertManagedBuildSmokePreflight({
      locationOverride: { host: "localhost:3000", origin: "http://localhost:3000" },
      fetchImpl,
    });
    expect(snap.host).toBe("localhost:3000");
  });

  it("fails SMOKE_PREFLIGHT_STALE_FRONTEND_HOST on the known stale URL", async () => {
    const fetchImpl = makeFetch(jsonResponse(healthyBody(), { traceContext: "x;o=1" }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: {
          host: "ham-grvil614b-team-clarity.vercel.app",
          origin: "https://ham-grvil614b-team-clarity.vercel.app",
        },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_STALE_FRONTEND_HOST",
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fails SMOKE_PREFLIGHT_STALE_FRONTEND_HOST on any other *.vercel.app preview", async () => {
    const fetchImpl = makeFetch(jsonResponse(healthyBody(), { traceContext: "x;o=1" }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: {
          host: "ham-feature-foo-team-x.vercel.app",
          origin: "https://ham-feature-foo-team-x.vercel.app",
        },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_STALE_FRONTEND_HOST",
    );
  });

  it("fails SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED when /api/status returns text/html (SPA fallback)", async () => {
    const fetchImpl = makeFetch(
      new Response("<!doctype html>...", {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" },
      }),
    );
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED",
    );
  });

  it("fails SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED on non-200 from /api/status", async () => {
    const fetchImpl = makeFetch(
      new Response('{"error":"nope"}', {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED",
    );
  });

  it("fails SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT when version is missing", async () => {
    const body = { ...healthyBody(), version: undefined };
    delete (body as { version?: unknown }).version;
    const fetchImpl = makeFetch(jsonResponse(body, { traceContext: "x;o=1" }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
    );
  });

  it("fails SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT when capabilities.project_agent_profiles_read is false", async () => {
    const body = { ...healthyBody(), capabilities: { project_agent_profiles_read: false } };
    const fetchImpl = makeFetch(jsonResponse(body, { traceContext: "x;o=1" }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
    );
  });

  it("fails SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT when run_count is negative", async () => {
    const body = { ...healthyBody(), run_count: -1 };
    const fetchImpl = makeFetch(jsonResponse(body, { traceContext: "x;o=1" }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
    );
  });

  it("fails SMOKE_PREFLIGHT_NO_BACKEND_TRACE when x-cloud-trace-context is absent", async () => {
    const fetchImpl = makeFetch(jsonResponse(healthyBody(), { traceContext: null }));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_NO_BACKEND_TRACE",
    );
  });

  it("fails SMOKE_PREFLIGHT_NETWORK_ERROR when fetch rejects", async () => {
    const fetchImpl = makeFetch(new TypeError("Failed to fetch"));
    await expectCode(
      assertManagedBuildSmokePreflight({
        locationOverride: { host: DEFAULT_CANONICAL_HOST, origin: CANONICAL_ORIGIN },
        fetchImpl,
      }),
      "SMOKE_PREFLIGHT_NETWORK_ERROR",
    );
  });

  it("allows overriding the canonical host (for staging-of-the-canonical-app rollouts)", async () => {
    const fetchImpl = makeFetch(jsonResponse(healthyBody(), { traceContext: "x;o=1" }));
    const snap = await assertManagedBuildSmokePreflight({
      canonicalHost: "ham-staging.vercel.app",
      locationOverride: {
        host: "ham-staging.vercel.app",
        origin: "https://ham-staging.vercel.app",
      },
      fetchImpl,
    });
    expect(snap.host).toBe("ham-staging.vercel.app");
  });
});
