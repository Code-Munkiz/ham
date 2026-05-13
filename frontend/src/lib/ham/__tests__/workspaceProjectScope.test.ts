import { describe, expect, it } from "vitest";

import type { ProjectRecord } from "@/lib/ham/types";
import {
  pickWorkspaceScopedProjectId,
  projectRecordsHaveWorkspaceBinding,
  workspaceIdFromProjectRecord,
} from "@/lib/ham/workspaceProjectScope";

function rec(over: Partial<ProjectRecord> & Pick<ProjectRecord, "id">): ProjectRecord {
  return {
    version: "1.0.0",
    name: "x",
    root: "/r",
    description: "",
    metadata: {},
    ...over,
  };
}

describe("workspaceProjectScope", () => {
  it("workspaceIdFromProjectRecord prefers top-level workspace_id; falls back to metadata legacy keys", () => {
    expect(
      workspaceIdFromProjectRecord(
        rec({ id: "a", metadata: { workspace_id: "ws_legacy" }, workspace_id: " ws_top " }),
      ),
    ).toBe("ws_top");

    expect(
      workspaceIdFromProjectRecord(
        rec({ id: "a2", metadata: { workspaceId: "ws_legacy_camel" }, workspace_id: "ws_top2" }),
      ),
    ).toBe("ws_top2");

    expect(
      workspaceIdFromProjectRecord(rec({ id: "b", metadata: { workspace_id: " ws_b " } })),
    ).toBe("ws_b");

    expect(
      workspaceIdFromProjectRecord(rec({ id: "b2", metadata: { workspaceId: " ws_b2 " } })),
    ).toBe("ws_b2");

    expect(workspaceIdFromProjectRecord(rec({ id: "c", metadata: {}, workspace_id: "ws_c" }))).toBe(
      "ws_c",
    );

    expect(
      workspaceIdFromProjectRecord(
        rec({ id: "c2", metadata: { workspace_id: "ws_legacy_only" }, workspace_id: "" }),
      ),
    ).toBe("ws_legacy_only");

    expect(
      workspaceIdFromProjectRecord(rec({ id: "d", metadata: {}, workspace_id: "" })),
    ).toBeNull();

    expect(workspaceIdFromProjectRecord(rec({ id: "e", metadata: {} }))).toBeNull();
  });

  it("projectRecordsHaveWorkspaceBinding is true iff any binding exists", () => {
    expect(
      projectRecordsHaveWorkspaceBinding([
        rec({ id: "a", metadata: { workspace_id: "ws" } }),
        rec({ id: "b", metadata: {} }),
      ]),
    ).toBe(true);

    expect(
      projectRecordsHaveWorkspaceBinding([
        rec({ id: "b", metadata: {} }),
        rec({ id: "c", metadata: {} }),
      ]),
    ).toBe(false);
  });

  it("pickWorkspaceScopedProjectId prefers preferred id when valid", () => {
    const projects = [
      rec({ id: "proj.z", metadata: { workspace_id: "ws1" } }),
      rec({ id: "proj.a", metadata: { workspace_id: "ws1" } }),
    ];

    expect(pickWorkspaceScopedProjectId("ws1", projects, "proj.a")).toBe("proj.a");
    expect(pickWorkspaceScopedProjectId("ws1", projects, null)).toBe("proj.a");
    expect(pickWorkspaceScopedProjectId("ws_missing", projects, null)).toBeNull();
  });
});
