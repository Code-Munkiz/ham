import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { listBuilderProjectSourcesMock, listBuilderSourceSnapshotsMock } = vi.hoisted(() => ({
  listBuilderProjectSourcesMock: vi.fn(),
  listBuilderSourceSnapshotsMock: vi.fn(),
}));

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    listBuilderProjectSources: (...args: unknown[]) => listBuilderProjectSourcesMock(...args),
    listBuilderSourceSnapshots: (...args: unknown[]) => listBuilderSourceSnapshotsMock(...args),
  };
});

import { WorkbenchSavedVersionsDialog } from "../WorkbenchSavedVersionsDialog";

function snapshotRow(createdAt: string, fileCount: number) {
  return {
    id: "ssnp_test_1",
    project_id: "proj_abc",
    workspace_id: "ws_abc",
    project_source_id: "psrc_1",
    status: "materialized",
    digest_sha256: "abc",
    size_bytes: 123,
    artifact_uri: "builder-artifact://hidden",
    manifest: { file_count: fileCount },
    created_at: createdAt,
    created_by: "user_a",
    metadata: {},
  };
}

describe("WorkbenchSavedVersionsDialog", () => {
  beforeEach(() => {
    listBuilderProjectSourcesMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      sources: [{ id: "psrc_1", active_snapshot_id: "ssnp_test_1" }],
    });
    listBuilderSourceSnapshotsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      source_snapshots: [],
    });
  });

  it("shows empty state when no snapshots exist", async () => {
    render(
      <WorkbenchSavedVersionsDialog
        open
        onOpenChange={() => {}}
        workspaceId="ws_abc"
        projectId="proj_abc"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-saved-versions-empty")).toBeInTheDocument();
    });
    expect(screen.getByText(/No saved versions yet/i)).toBeInTheDocument();
  });

  it("renders populated saved version rows", async () => {
    listBuilderSourceSnapshotsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      source_snapshots: [snapshotRow("2026-01-02T10:00:00Z", 5)],
    });
    render(
      <WorkbenchSavedVersionsDialog
        open
        onOpenChange={() => {}}
        workspaceId="ws_abc"
        projectId="proj_abc"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-saved-versions-list")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-saved-version-label-0")).toHaveTextContent(
      "Current saved version",
    );
    expect(screen.getByTestId("hww-saved-version-files-0")).toHaveTextContent("5 files");
    const dialogText = screen.getByTestId("hww-saved-versions-dialog").textContent || "";
    expect(dialogText).not.toMatch(/ssnp_/);
    expect(dialogText).not.toMatch(/builder-artifact/);
  });

  it("shows loading state while fetching", () => {
    listBuilderSourceSnapshotsMock.mockImplementation(() => new Promise(() => {}));
    render(
      <WorkbenchSavedVersionsDialog
        open
        onOpenChange={() => {}}
        workspaceId="ws_abc"
        projectId="proj_abc"
      />,
    );
    expect(screen.getByTestId("hww-saved-versions-loading")).toBeInTheDocument();
  });

  it("shows friendly error state", async () => {
    listBuilderSourceSnapshotsMock.mockRejectedValue(
      new Error("ssnp_leak builder-artifact://secret digest_sha256"),
    );
    render(
      <WorkbenchSavedVersionsDialog
        open
        onOpenChange={() => {}}
        workspaceId="ws_abc"
        projectId="proj_abc"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-saved-versions-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-saved-versions-error")).toHaveTextContent(
      /Could not load saved versions/i,
    );
  });

  it("calls onViewVersion when View in Code is clicked", async () => {
    const onViewVersion = vi.fn();
    listBuilderSourceSnapshotsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      source_snapshots: [snapshotRow("2026-01-02T10:00:00Z", 2)],
    });
    render(
      <WorkbenchSavedVersionsDialog
        open
        onOpenChange={() => {}}
        workspaceId="ws_abc"
        projectId="proj_abc"
        onViewVersion={onViewVersion}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-saved-version-view-0")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("hww-saved-version-view-0"));
    expect(onViewVersion).toHaveBeenCalledWith("ssnp_test_1");
  });
});
