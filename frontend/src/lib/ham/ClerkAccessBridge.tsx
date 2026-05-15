/**
 * Registers Clerk `getToken` for `api.ts` fetch helpers and probes deployment access
 * so the shell can show a global restricted-access banner (HAM_EMAIL_RESTRICTION).
 */
import * as React from "react";
import { useAuth } from "@clerk/clerk-react";
import { fastApiStructuredErrorCode, hamApiFetch } from "./api";
import { registerClerkSessionGetter } from "./clerkSession";

export type HamDeploymentAccessState = {
  /** Signed in with Clerk but HAM email/domain gate rejected this identity. */
  restricted: boolean;
  checking: boolean;
};

const HamDeploymentAccessContext = React.createContext<HamDeploymentAccessState>({
  restricted: false,
  checking: false,
});

export function useHamDeploymentAccess(): HamDeploymentAccessState {
  return React.useContext(HamDeploymentAccessContext);
}

export function ClerkAccessBridge({ children }: { children: React.ReactNode }) {
  const { getToken, isSignedIn, isLoaded } = useAuth();
  const [restricted, setRestricted] = React.useState(false);
  const [checking, setChecking] = React.useState(false);

  React.useLayoutEffect(() => {
    registerClerkSessionGetter(async (opts) => {
      if (opts?.forceRefresh) {
        return await getToken({ skipCache: true });
      }
      return await getToken();
    });
    return () => registerClerkSessionGetter(null);
  }, [getToken]);

  React.useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      setRestricted(false);
      setChecking(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setChecking(true);
      try {
        const res = await hamApiFetch("/api/clerk-access-probe");
        if (cancelled) return;
        if (res.status === 403) {
          let body: { detail?: unknown };
          try {
            body = (await res.json()) as { detail?: unknown };
          } catch {
            body = {};
          }
          setRestricted(fastApiStructuredErrorCode(body?.detail) === "HAM_EMAIL_RESTRICTION");
          return;
        }
        setRestricted(false);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn]);

  const value = React.useMemo(() => ({ restricted, checking }), [restricted, checking]);

  return (
    <HamDeploymentAccessContext.Provider value={value}>
      {children}
    </HamDeploymentAccessContext.Provider>
  );
}
