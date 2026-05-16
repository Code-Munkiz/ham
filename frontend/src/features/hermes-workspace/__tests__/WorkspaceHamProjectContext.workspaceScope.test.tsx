import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import { HamWorkspaceContext } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";
import { WorkspaceHamProjectProvider, useWorkspaceHamProject } from "../WorkspaceHamProjectContext";

const MAP_KEY = "hww.workspaceHamProjectIds.v1";

function wsSummary(id: string): HamWorkspaceSummary {
  return {
    workspace_id: id,
    org_id: null,
    name: id,
    slug: id.toLowerCase().replace(/\s+/g, "-"),
    description: "",
    status: "active",
    role: "owner",
    perms: [],
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function readyCtx(workspaceId: string | null): HamWorkspaceContextValue {
  const w = workspaceId ? wsSummary(workspaceId) : null;
  return {
    state: {
      status: "ready",
      me: {
        user: {
          user_id: "user_1",
          email: null,
          display_name: null,
          photo_url: null,
          primary_org_id: null,
        },
        orgs: [],
        workspaces: w ? [w] : [],
        default_workspace_id: workspaceId,
        auth_mode: "clerk",
      },
      activeWorkspaceId: workspaceId,
    },
    workspaces: w ? [w] : [],
    active: w,
    authMode: "clerk",
    hostedAuth: null,
    refresh: async () => undefined,
    selectWorkspace: () => undefined,
    createWorkspace: async () => w ?? wsSummary(workspaceId ?? "x"),
    patchActiveWorkspace: async () => w ?? wsSummary(workspaceId ?? "x"),
    archiveWorkspaceById: async () => {
      throw new Error("unexpected");
    },
    hasPerm: () => false,
    openSignIn: undefined,
  };
}

function ScopedProbe(props: { ws: string | null; label: string }) {
  return (
    <HamWorkspaceContext.Provider value={readyCtx(props.ws)}>
      <WorkspaceHamProjectProvider>
        <Inner label={props.label} />
      </WorkspaceHamProjectProvider>
    </HamWorkspaceContext.Provider>
  );
}

function Inner({ label }: { label: string }) {
  const { hamProjectId, setHamProjectId } = useWorkspaceHamProject();
  return (
    <div>
      <span data-testid={`id-${label}`}>{hamProjectId ?? ""}</span>
      <button
        type="button"
        data-testid={`set-a-${label}`}
        onClick={() => setHamProjectId("project_alpha")}
      >
        set-alpha
      </button>
      <button
        type="button"
        data-testid={`set-b-${label}`}
        onClick={() => setHamProjectId("project_beta")}
      >
        set-beta
      </button>
      <button type="button" data-testid={`clear-${label}`} onClick={() => setHamProjectId(null)}>
        clear
      </button>
    </div>
  );
}

describe("WorkspaceHamProjectProvider workspace scope", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("stores project ids keyed by workspace in sessionStorage", () => {
    const { rerender } = render(<ScopedProbe ws="ws_one" label="t1" />);
    fireEvent.click(screen.getByTestId("set-a-t1"));
    expect(screen.getByTestId("id-t1").textContent).toBe("project_alpha");
    let raw = JSON.parse(sessionStorage.getItem(MAP_KEY) ?? "{}") as Record<string, string>;
    expect(raw.ws_one).toBe("project_alpha");

    rerender(<ScopedProbe ws="ws_two" label="t1" />);
    expect(screen.getByTestId("id-t1").textContent).toBe("");
    fireEvent.click(screen.getByTestId("set-b-t1"));
    expect(screen.getByTestId("id-t1").textContent).toBe("project_beta");
    raw = JSON.parse(sessionStorage.getItem(MAP_KEY) ?? "{}") as Record<string, string>;
    expect(raw.ws_one).toBe("project_alpha");
    expect(raw.ws_two).toBe("project_beta");

    rerender(<ScopedProbe ws="ws_one" label="t1" />);
    expect(screen.getByTestId("id-t1").textContent).toBe("project_alpha");
  });
});
