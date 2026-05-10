/**
 * Phase 1c: HAM-native multi-user workspace provider.
 *
 * Wraps `/api/me` + `/api/workspaces` consumption with a small state machine
 * and per-user localStorage selection. Distinct from the legacy
 * `WorkspaceContext` (UI cockpit state) — see `frontend/src/lib/ham/WorkspaceContext.tsx`.
 *
 * The provider intentionally **never throws during render**: all error paths
 * surface as `state: "error"` so `App.tsx` stays mountable even when the
 * backend is unreachable, the API base is misconfigured, or workspace UI bypass
 * is off.
 */
import * as React from "react";

import {
  createWorkspace as apiCreateWorkspace,
  getMe as apiGetMe,
  patchWorkspace as apiPatchWorkspace,
  HamWorkspaceApiError,
  type HamAuthMode,
  type HamCreateWorkspaceBody,
  type HamMeResponse,
  type HamPatchWorkspaceBody,
  type HamWorkspaceSummary,
} from "./workspaceApi";
import {
  buildHamApiStatusUrl,
  getHamApiOriginLabel,
  isLikelyHamApiFetchNetworkFailure,
} from "./api";
import { readActiveWorkspaceId, writeActiveWorkspaceId } from "./hamWorkspaceStorage";
import {
  buildLocalDevWorkspaceMeResponse,
  LOCAL_UI_QA_WORKSPACE_ID,
  shouldActivateLocalWorkspaceUiBypass,
} from "./localDevWorkspaceBypass";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

/** Shown when GET /api/me fails before an HTTP response (fetch/network layer). */
export interface HamWorkspaceNetworkUnreachableInfo {
  /** API origin only — never secrets or tokens. */
  apiOrigin: string;
  /** `${apiOrigin}/api/status` for manual checks in a new tab. */
  statusUrl: string;
}

export type HamWorkspaceState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "auth_loading" }
  | { status: "auth_not_configured" }
  | { status: "setup_needed" }
  | { status: "auth_required" }
  | {
      status: "error";
      message: string;
      code: string | null;
      /** Present only for browser-level fetch failures (not HTTP JSON errors). */
      networkUnreachable?: HamWorkspaceNetworkUnreachableInfo;
    }
  | {
      status: "onboarding";
      me: HamMeResponse;
    }
  | {
      status: "ready";
      me: HamMeResponse;
      activeWorkspaceId: string | null;
    };

export interface HamWorkspaceContextValue {
  state: HamWorkspaceState;
  workspaces: HamWorkspaceSummary[];
  active: HamWorkspaceSummary | null;
  authMode: HamAuthMode | null;
  hostedAuth: HamWorkspaceHostedAuthState | null;
  openSignIn?: () => void;
  refresh: () => Promise<void>;
  selectWorkspace: (workspaceId: string) => void;
  createWorkspace: (body: HamCreateWorkspaceBody) => Promise<HamWorkspaceSummary>;
  patchActiveWorkspace: (patch: HamPatchWorkspaceBody) => Promise<HamWorkspaceSummary>;
  hasPerm: (perm: string) => boolean;
}

export type HamWorkspaceHostedAuthState = {
  clerkConfigured: boolean;
  isLoaded: boolean;
  isSignedIn: boolean;
};

export interface HamWorkspaceProviderProps {
  children: React.ReactNode;
  /**
   * When provided by App's Clerk wrapper, prevents protected workspace calls
   * until Clerk has loaded and the user is signed in.
   */
  hostedAuth?: HamWorkspaceHostedAuthState | null;
  openSignIn?: () => void;
}

const HamWorkspaceContext = React.createContext<HamWorkspaceContextValue | null>(null);

// ---------------------------------------------------------------------------
// Helpers (pure)
// ---------------------------------------------------------------------------

function chooseActiveWorkspaceId(
  workspaces: HamWorkspaceSummary[],
  defaultWorkspaceId: string | null,
  storedId: string | null,
): string | null {
  const activeIds = new Set(
    workspaces.filter((w) => w.status === "active").map((w) => w.workspace_id),
  );
  if (storedId && activeIds.has(storedId)) return storedId;
  if (defaultWorkspaceId && activeIds.has(defaultWorkspaceId)) return defaultWorkspaceId;
  if (activeIds.size === 1) {
    return Array.from(activeIds)[0];
  }
  return null;
}

function deriveStateFromMe(me: HamMeResponse, storedId: string | null): HamWorkspaceState {
  if (me.workspaces.length === 0) {
    return { status: "onboarding", me };
  }
  const activeWorkspaceId = chooseActiveWorkspaceId(
    me.workspaces,
    me.default_workspace_id,
    storedId,
  );
  return { status: "ready", me, activeWorkspaceId };
}

function classifyError(err: unknown): HamWorkspaceState {
  if (err instanceof HamWorkspaceApiError) {
    if (err.status === 401 && err.code === "HAM_WORKSPACE_AUTH_REQUIRED") {
      return { status: "setup_needed" };
    }
    if (err.status === 401 && err.code === "CLERK_SESSION_REQUIRED") {
      return { status: "auth_required" };
    }
    return {
      status: "error",
      message: err.message,
      code: err.code,
    };
  }
  const message = err instanceof Error ? err.message : "Failed to load workspace";
  if (isLikelyHamApiFetchNetworkFailure(err)) {
    return {
      status: "error",
      message,
      code: null,
      networkUnreachable: {
        apiOrigin: getHamApiOriginLabel(),
        statusUrl: buildHamApiStatusUrl(),
      },
    };
  }
  return {
    status: "error",
    message,
    code: null,
  };
}

function selectActiveSummary(state: HamWorkspaceState): HamWorkspaceSummary | null {
  if (state.status !== "ready" || !state.activeWorkspaceId) return null;
  return state.me.workspaces.find((w) => w.workspace_id === state.activeWorkspaceId) || null;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function HamWorkspaceProvider({
  children,
  hostedAuth = null,
  openSignIn,
}: HamWorkspaceProviderProps) {
  const [state, setState] = React.useState<HamWorkspaceState>({ status: "idle" });
  const inflightRef = React.useRef<Promise<void> | null>(null);

  const persistSelection = React.useCallback((userId: string, workspaceId: string | null) => {
    try {
      writeActiveWorkspaceId(userId, workspaceId);
    } catch {
      /* storage is best-effort */
    }
  }, []);

  const refresh = React.useCallback(async (): Promise<void> => {
    if (shouldActivateLocalWorkspaceUiBypass(hostedAuth)) {
      inflightRef.current = null;
      const nowIso = new Date().toISOString();
      const me = buildLocalDevWorkspaceMeResponse(nowIso);
      persistSelection(me.user.user_id, LOCAL_UI_QA_WORKSPACE_ID);
      setState({
        status: "ready",
        me,
        activeWorkspaceId: LOCAL_UI_QA_WORKSPACE_ID,
      });
      return;
    }
    if (hostedAuth) {
      if (!hostedAuth.clerkConfigured) {
        setState({ status: "auth_not_configured" });
        return;
      }
      if (!hostedAuth.isLoaded) {
        setState({ status: "auth_loading" });
        return;
      }
      if (!hostedAuth.isSignedIn) {
        setState({ status: "auth_required" });
        return;
      }
    }
    if (inflightRef.current) {
      return inflightRef.current;
    }
    setState((prev) =>
      prev.status === "idle"
        ? { status: "loading" }
        : prev.status === "error"
          ? { status: "loading" }
          : { status: "loading" },
    );
    const p = (async () => {
      try {
        const me = await apiGetMe();
        const stored = readActiveWorkspaceId(me.user.user_id);
        const next = deriveStateFromMe(me, stored);
        if (next.status === "ready" && next.activeWorkspaceId) {
          persistSelection(me.user.user_id, next.activeWorkspaceId);
        }
        setState(next);
      } catch (err) {
        setState(classifyError(err));
      } finally {
        inflightRef.current = null;
      }
    })();
    inflightRef.current = p;
    return p;
  }, [hostedAuth, persistSelection]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectWorkspace = React.useCallback(
    (workspaceId: string) => {
      setState((prev) => {
        if (prev.status !== "ready") return prev;
        const exists = prev.me.workspaces.some(
          (w) => w.workspace_id === workspaceId && w.status === "active",
        );
        if (!exists) return prev;
        persistSelection(prev.me.user.user_id, workspaceId);
        return { ...prev, activeWorkspaceId: workspaceId };
      });
    },
    [persistSelection],
  );

  const createWorkspace = React.useCallback(
    async (body: HamCreateWorkspaceBody): Promise<HamWorkspaceSummary> => {
      const resp = await apiCreateWorkspace(body);
      // Refetch /api/me so we see the new workspace alongside any backend-side
      // mirroring (org rows, default-id changes), then auto-select the new one.
      try {
        const me = await apiGetMe();
        const stored = readActiveWorkspaceId(me.user.user_id);
        // Prefer the freshly-created workspace as the new active id.
        const newId = resp.workspace.workspace_id;
        const exists = me.workspaces.some((w) => w.workspace_id === newId && w.status === "active");
        const activeWorkspaceId = exists
          ? newId
          : chooseActiveWorkspaceId(me.workspaces, me.default_workspace_id, stored);
        if (activeWorkspaceId) {
          persistSelection(me.user.user_id, activeWorkspaceId);
        }
        if (me.workspaces.length === 0) {
          setState({ status: "onboarding", me });
        } else {
          setState({ status: "ready", me, activeWorkspaceId });
        }
      } catch {
        // Refresh failed — fall back to a single-workspace projected state so
        // the UI still moves out of onboarding.
        setState((prev) => {
          if (prev.status === "onboarding" || prev.status === "ready") {
            const me = prev.status === "onboarding" ? prev.me : prev.me;
            const merged = {
              ...me,
              workspaces: [...me.workspaces, resp.workspace],
              default_workspace_id: me.default_workspace_id ?? resp.workspace.workspace_id,
            };
            persistSelection(merged.user.user_id, resp.workspace.workspace_id);
            return {
              status: "ready",
              me: merged,
              activeWorkspaceId: resp.workspace.workspace_id,
            };
          }
          return prev;
        });
      }
      return resp.workspace;
    },
    [persistSelection],
  );

  const patchActiveWorkspace = React.useCallback(
    async (patch: HamPatchWorkspaceBody): Promise<HamWorkspaceSummary> => {
      let activeWid: string | null = null;
      setState((prev) => {
        if (prev.status === "ready") {
          activeWid = prev.activeWorkspaceId;
        }
        return prev;
      });
      if (!activeWid) {
        throw new HamWorkspaceApiError(
          409,
          "HAM_WORKSPACE_NO_ACTIVE",
          "No active workspace to update.",
        );
      }
      const resp = await apiPatchWorkspace(activeWid, patch);
      setState((prev) => {
        if (prev.status !== "ready") return prev;
        const updated = prev.me.workspaces.map((w) =>
          w.workspace_id === resp.workspace.workspace_id ? resp.workspace : w,
        );
        return {
          ...prev,
          me: { ...prev.me, workspaces: updated },
        };
      });
      return resp.workspace;
    },
    [],
  );

  const value = React.useMemo<HamWorkspaceContextValue>(() => {
    const workspaces =
      state.status === "ready" || state.status === "onboarding" ? state.me.workspaces : [];
    const active = selectActiveSummary(state);
    const authMode =
      state.status === "ready" || state.status === "onboarding" ? state.me.auth_mode : null;
    const hasPerm = (perm: string) => Boolean(active?.perms.includes(perm));
    return {
      state,
      workspaces,
      active,
      authMode,
      hostedAuth,
      openSignIn,
      refresh,
      selectWorkspace,
      createWorkspace,
      patchActiveWorkspace,
      hasPerm,
    };
  }, [
    state,
    hostedAuth,
    openSignIn,
    refresh,
    selectWorkspace,
    createWorkspace,
    patchActiveWorkspace,
  ]);

  return <HamWorkspaceContext.Provider value={value}>{children}</HamWorkspaceContext.Provider>;
}

export function useHamWorkspace(): HamWorkspaceContextValue {
  const ctx = React.useContext(HamWorkspaceContext);
  if (!ctx) {
    throw new Error("useHamWorkspace must be used inside <HamWorkspaceProvider>");
  }
  return ctx;
}

// Test seam — exported helpers (NOT public API).
export const __TEST__ = {
  chooseActiveWorkspaceId,
  deriveStateFromMe,
  classifyError,
  selectActiveSummary,
};
