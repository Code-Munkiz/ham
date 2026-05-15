/**
 * Optional Clerk session token bridge for non-React callers (e.g. `api.ts` fetch helpers).
 * `ClerkSessionBridge` in `App.tsx` registers `getToken` when `ClerkProvider` is active.
 */
export type ClerkSessionGetter = (opts?: { forceRefresh?: boolean }) => Promise<string | null>;

const CLERK_TOKEN_CACHE_TTL_MS = 30_000;
const CLERK_TOKEN_FAILURE_BACKOFF_MS = 1_500;

let clerkSessionGetter: ClerkSessionGetter | null = null;
let cachedToken: string | null = null;
let cachedTokenAtMs = 0;
let tokenFailureBackoffUntilMs = 0;
let inFlightTokenPromise: Promise<string | null> | null = null;

function clearSessionTokenCache(): void {
  cachedToken = null;
  cachedTokenAtMs = 0;
  tokenFailureBackoffUntilMs = 0;
  inFlightTokenPromise = null;
}

export function registerClerkSessionGetter(fn: ClerkSessionGetter | null): void {
  // Session getter changes should invalidate in-memory auth cache.
  clearSessionTokenCache();
  clerkSessionGetter = fn;
}

export function clearClerkSessionTokenCache(): void {
  clearSessionTokenCache();
}

export async function getRegisteredClerkSessionToken(opts?: {
  forceRefresh?: boolean;
}): Promise<string | null> {
  if (!clerkSessionGetter) return null;
  const forceRefresh = opts?.forceRefresh === true;
  const now = Date.now();
  if (!forceRefresh && cachedToken && now - cachedTokenAtMs < CLERK_TOKEN_CACHE_TTL_MS) {
    return cachedToken;
  }
  if (!forceRefresh && tokenFailureBackoffUntilMs > now) {
    return null;
  }
  if (inFlightTokenPromise) {
    return inFlightTokenPromise;
  }
  inFlightTokenPromise = (async () => {
    const invokeAt = Date.now();
    try {
      const token = (await clerkSessionGetter?.({ forceRefresh })) || null;
      if (token) {
        cachedToken = token;
        cachedTokenAtMs = invokeAt;
        tokenFailureBackoffUntilMs = 0;
        return token;
      }
      cachedToken = null;
      cachedTokenAtMs = 0;
      tokenFailureBackoffUntilMs = invokeAt + CLERK_TOKEN_FAILURE_BACKOFF_MS;
      return null;
    } catch {
      cachedToken = null;
      cachedTokenAtMs = 0;
      tokenFailureBackoffUntilMs = invokeAt + CLERK_TOKEN_FAILURE_BACKOFF_MS;
      return null;
    } finally {
      inFlightTokenPromise = null;
    }
  })();
  try {
    return await inFlightTokenPromise;
  } catch {
    return null;
  }
}
