import * as React from "react";
import { HamWorkspaceContext } from "@/lib/ham/HamWorkspaceContext";

/** Per-workspace persisted selection (replacing legacy single-global key `hww.workspaceHamProjectId`). */
const STORAGE_MAP_KEY = "hww.workspaceHamProjectIds.v1";
const STORAGE_LEGACY_PROJECT_KEY = "hww.workspaceHamProjectId";

function readSessionJsonMap(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") {
      return Object.fromEntries(
        Object.entries(parsed as Record<string, unknown>).filter(
          ([k, v]) => typeof k === "string" && k.trim() && typeof v === "string" && v.trim(),
        ) as Array<[string, string]>,
      );
    }
  } catch {
    /* stale map */
  }
  return {};
}

function loadProjectMap(): Record<string, string> {
  if (typeof sessionStorage === "undefined") return {};
  try {
    return readSessionJsonMap(sessionStorage.getItem(STORAGE_MAP_KEY));
  } catch {
    return {};
  }
}

function persistProjectMap(map: Record<string, string>): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    if (Object.keys(map).length === 0) {
      sessionStorage.removeItem(STORAGE_MAP_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_MAP_KEY, JSON.stringify(map));
  } catch {
    /* storage blocked */
  }
}

/** One-time migrate legacy singleton key onto the active workspace bucket. */
function consumeLegacyProjectIdIntoWorkspace(activeWorkspaceId: string | null | undefined): void {
  const ws = (activeWorkspaceId || "").trim();
  if (!ws || typeof sessionStorage === "undefined") return;
  try {
    const legacy = (sessionStorage.getItem(STORAGE_LEGACY_PROJECT_KEY) || "").trim();
    if (!legacy) return;
    const map = loadProjectMap();
    if (!(ws in map)) {
      map[ws] = legacy;
      persistProjectMap(map);
    }
    sessionStorage.removeItem(STORAGE_LEGACY_PROJECT_KEY);
  } catch {
    /* best-effort */
  }
}

export type WorkspaceHamProjectContextValue = {
  hamProjectId: string | null;
  setHamProjectId: (id: string | null) => void;
};

const WorkspaceHamProjectContext = React.createContext<WorkspaceHamProjectContextValue | null>(
  null,
);

export function WorkspaceHamProjectProvider({ children }: { children: React.ReactNode }) {
  const hamWs = React.useContext(HamWorkspaceContext);
  const activeWs =
    hamWs?.state.status === "ready" ? hamWs.state.activeWorkspaceId?.trim() || "" : "";

  consumeLegacyProjectIdIntoWorkspace(activeWs || null);

  const [mapRevision, bumpMapRevision] = React.useState(0);

  const hamProjectId = React.useMemo(() => {
    if (!activeWs) return null;
    const row = loadProjectMap();
    const id = row[activeWs];
    return typeof id === "string" && id.trim() ? id.trim() : null;
  }, [activeWs, mapRevision]);

  const setHamProjectId = React.useCallback(
    (id: string | null) => {
      const ws = activeWs;
      if (!ws) return;
      const next = loadProjectMap();
      if (id?.trim()) {
        next[ws] = id.trim();
      } else {
        delete next[ws];
      }
      persistProjectMap(next);
      bumpMapRevision((n) => n + 1);
    },
    [activeWs],
  );

  const value = React.useMemo(
    () => ({ hamProjectId, setHamProjectId }),
    [hamProjectId, setHamProjectId],
  );

  return (
    <WorkspaceHamProjectContext.Provider value={value}>{children}</WorkspaceHamProjectContext.Provider>
  );
}

export function useWorkspaceHamProject(): WorkspaceHamProjectContextValue {
  const ctx = React.useContext(WorkspaceHamProjectContext);
  if (ctx == null) {
    throw new Error("useWorkspaceHamProject must be used within WorkspaceHamProjectProvider");
  }
  return ctx;
}

/** Safe for panels (e.g. UnifiedSettings) that may mount outside the Hermes workspace tree. */
export function useOptionalWorkspaceHamProject(): WorkspaceHamProjectContextValue | null {
  return React.useContext(WorkspaceHamProjectContext);
}
