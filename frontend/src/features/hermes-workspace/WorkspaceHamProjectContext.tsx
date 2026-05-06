import * as React from "react";

const STORAGE_KEY = "hww.workspaceHamProjectId";

export type WorkspaceHamProjectContextValue = {
  hamProjectId: string | null;
  setHamProjectId: (id: string | null) => void;
};

const WorkspaceHamProjectContext = React.createContext<WorkspaceHamProjectContextValue | null>(
  null,
);

export function WorkspaceHamProjectProvider({ children }: { children: React.ReactNode }) {
  const [hamProjectId, setState] = React.useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return sessionStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const setHamProjectId = React.useCallback((id: string | null) => {
    setState(id);
    try {
      if (id) {
        sessionStorage.setItem(STORAGE_KEY, id);
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      /* storage blocked */
    }
  }, []);

  const value = React.useMemo(
    () => ({ hamProjectId, setHamProjectId }),
    [hamProjectId, setHamProjectId],
  );

  return (
    <WorkspaceHamProjectContext.Provider value={value}>
      {children}
    </WorkspaceHamProjectContext.Provider>
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
