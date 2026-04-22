/**
 * Optional Clerk session token bridge for non-React callers (e.g. `api.ts` fetch helpers).
 * `ClerkSessionBridge` in `App.tsx` registers `getToken` when `ClerkProvider` is active.
 */
export type ClerkSessionGetter = () => Promise<string | null>;

let clerkSessionGetter: ClerkSessionGetter | null = null;

export function registerClerkSessionGetter(fn: ClerkSessionGetter | null): void {
  clerkSessionGetter = fn;
}

export async function getRegisteredClerkSessionToken(): Promise<string | null> {
  if (!clerkSessionGetter) return null;
  try {
    return await clerkSessionGetter();
  } catch {
    return null;
  }
}
