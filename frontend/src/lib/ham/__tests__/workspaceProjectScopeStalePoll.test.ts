import { describe, expect, it } from "vitest";
import type { ProjectRecord } from "@/lib/ham/types";
import {
  ignoreStaleWorkbenchScope,
  pickWorkspaceScopedProjectId,
  workspaceProjectScope,
  workspaceProjectScopesMatch,
} from "@/lib/ham/workspaceProjectScope";

function stubScopedProject(id: string, workspaceId: string): ProjectRecord {
  return {
    id,
    version: "1",
    name: "stub",
    root: "",
    description: "",
    metadata: {},
    workspace_id: workspaceId,
  };
}

describe("workspace project scope guards (Workbench stale polling)", () => {
  it("keys workspaces and builder projects distinctly", () => {
    expect(workspaceProjectScope("ws_a", "project.builder_x")).not.toEqual(
      workspaceProjectScope("ws_a", "project.builder_y"),
    );
  });

  it("reports stale when scoped pair changed after async start", () => {
    const started = workspaceProjectScope("ws_a", "old");
    expect(
      ignoreStaleWorkbenchScope({
        started,
        currentWorkspaceId: "ws_a",
        currentProjectId: "new",
      }),
    ).toBe(true);
    expect(
      ignoreStaleWorkbenchScope({
        started,
        currentWorkspaceId: "ws_a",
        currentProjectId: "old",
      }),
    ).toBe(false);
  });

  it("scopesMatch delegates to strict equality", () => {
    const a = workspaceProjectScope("w", "p");
    expect(workspaceProjectScopesMatch(a, a)).toBe(true);
    expect(workspaceProjectScopesMatch(a, workspaceProjectScope("w", "p2"))).toBe(false);
  });

  it("still picks deterministic scoped ids (regression)", () => {
    const ws = "ws_a";
    const projects: ProjectRecord[] = [stubScopedProject("z", ws), stubScopedProject("m", ws)];
    expect(pickWorkspaceScopedProjectId(ws, projects, null)).toBe("m");
  });
});
