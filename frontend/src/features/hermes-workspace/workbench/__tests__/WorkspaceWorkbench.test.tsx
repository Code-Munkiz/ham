import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const {
  fetchWorkspaceToolsMock,
  isLocalRuntimeConfiguredMock,
  listBuilderProjectSourcesMock,
  listBuilderSourceSnapshotsMock,
  listBuilderImportJobsMock,
  getBuilderPreviewStatusMock,
  getBuilderActivityMock,
  postBuilderLocalPreviewMock,
  deleteBuilderLocalPreviewMock,
} = vi.hoisted(() => ({
  fetchWorkspaceToolsMock: vi.fn(),
  isLocalRuntimeConfiguredMock: vi.fn(() => false),
  listBuilderProjectSourcesMock: vi.fn(),
  listBuilderSourceSnapshotsMock: vi.fn(),
  listBuilderImportJobsMock: vi.fn(),
  getBuilderPreviewStatusMock: vi.fn(),
  getBuilderActivityMock: vi.fn(),
  postBuilderLocalPreviewMock: vi.fn(),
  deleteBuilderLocalPreviewMock: vi.fn(),
}));

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    fetchWorkspaceTools: (...args: unknown[]) => fetchWorkspaceToolsMock(...args),
    listBuilderProjectSources: (...args: unknown[]) => listBuilderProjectSourcesMock(...args),
    listBuilderSourceSnapshots: (...args: unknown[]) => listBuilderSourceSnapshotsMock(...args),
    listBuilderImportJobs: (...args: unknown[]) => listBuilderImportJobsMock(...args),
    getBuilderPreviewStatus: (...args: unknown[]) => getBuilderPreviewStatusMock(...args),
    getBuilderActivity: (...args: unknown[]) => getBuilderActivityMock(...args),
    postBuilderLocalPreview: (...args: unknown[]) => postBuilderLocalPreviewMock(...args),
    deleteBuilderLocalPreview: (...args: unknown[]) => deleteBuilderLocalPreviewMock(...args),
  };
});

vi.mock("../../adapters/localRuntime", () => ({
  isLocalRuntimeConfigured: () => isLocalRuntimeConfiguredMock(),
}));

import { WorkspaceWorkbench } from "../WorkspaceWorkbench";

function toolsOk() {
  return new Response(
    JSON.stringify({
      tools: [{ id: "github", connection: "off" }],
      scan_available: true,
      scan_hint: null,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("WorkspaceWorkbench", () => {
  beforeEach(() => {
    fetchWorkspaceToolsMock.mockResolvedValue(toolsOk());
    isLocalRuntimeConfiguredMock.mockReturnValue(false);
    listBuilderProjectSourcesMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      sources: [],
    });
    listBuilderSourceSnapshotsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      source_snapshots: [],
    });
    listBuilderImportJobsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      import_jobs: [],
    });
    getBuilderPreviewStatusMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      mode: "local",
      status: "not_connected",
      health: "unknown",
      preview_url: null,
      message: "Local preview runtime is not connected.",
      updated_at: "2026-01-01T00:00:00Z",
      source_snapshot_id: null,
      runtime_session_id: null,
      preview_endpoint_id: null,
      logs_hint: null,
    });
    getBuilderActivityMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      items: [],
    });
    postBuilderLocalPreviewMock.mockResolvedValue({
      runtime_session: {},
      preview_endpoint: {},
      preview_status: {
        project_id: "proj_abc",
        workspace_id: "ws_abc",
        mode: "local",
        status: "ready",
        health: "healthy",
        preview_url: "http://localhost:3000/",
        message: "Preview is ready.",
        updated_at: "2026-01-01T00:00:00Z",
        source_snapshot_id: null,
        runtime_session_id: "rtms_1",
        preview_endpoint_id: "prve_1",
        logs_hint: null,
      },
    });
    deleteBuilderLocalPreviewMock.mockResolvedValue({
      preview_status: {
        project_id: "proj_abc",
        workspace_id: "ws_abc",
        mode: "local",
        status: "not_connected",
        health: "unknown",
        preview_url: null,
        message: "Local preview runtime is not connected.",
        updated_at: "2026-01-01T00:00:00Z",
        source_snapshot_id: null,
        runtime_session_id: null,
        preview_endpoint_id: null,
        logs_hint: null,
      },
    });
  });

  it("select Preview by default and switches panel content", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-panel-preview")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-preview").getAttribute("data-active")).toBe(
      "true",
    );

    fireEvent.click(screen.getByTestId("hww-workbench-tab-code"));
    expect(screen.getByTestId("hww-workbench-panel-code")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-code").getAttribute("data-active")).toBe("true");
  });

  it("Preview shows not-connected state and no iframe", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-status-copy")).toHaveTextContent("not connected");
    });
    expect(screen.getByTestId("hww-preview-no-iframe")).toBeInTheDocument();
    expect(screen.queryByTestId("hww-preview-iframe")).toBeNull();
    expect(screen.getByTestId("hww-preview-open-new-tab")).toBeDisabled();
    expect(screen.getByTestId("hww-preview-connect-form")).toBeInTheDocument();
    expect(screen.getByTestId("hww-preview-activity-section")).toBeInTheDocument();
    expect(screen.getByTestId("hww-preview-activity-empty")).toBeInTheDocument();
    expect(screen.queryByText(/build stream/i)).toBeNull();
  });

  it("Preview renders activity timeline entries from API", async () => {
    getBuilderActivityMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      items: [
        {
          id: "act_1",
          kind: "source_import",
          status: "succeeded",
          title: "Source snapshot created",
          message: "Source snapshot created",
          timestamp: "2026-01-01T00:00:00Z",
          source_id: "psrc_1",
          snapshot_id: "ssnp_1",
          import_job_id: "ijob_1",
          runtime_session_id: null,
          preview_endpoint_id: null,
          metadata: {},
        },
        {
          id: "act_2",
          kind: "preview_connected",
          status: "ready",
          title: "Local preview connected",
          message: "Local preview connected",
          timestamp: "2026-01-01T00:01:00Z",
          source_id: null,
          snapshot_id: null,
          import_job_id: null,
          runtime_session_id: "rtms_1",
          preview_endpoint_id: "prve_1",
          metadata: {},
        },
      ],
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-activity-list")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId("hww-preview-activity-item").length).toBe(2);
    expect(screen.getAllByText("Source snapshot created").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Local preview connected").length).toBeGreaterThan(0);
  });

  it("Preview activity failed item shows safe copy", async () => {
    getBuilderActivityMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      items: [
        {
          id: "act_failed",
          kind: "source_import",
          status: "failed",
          title: "Source import failed",
          message: "Source import failed.",
          timestamp: "2026-01-01T00:00:00Z",
          source_id: null,
          snapshot_id: null,
          import_job_id: "ijob_2",
          runtime_session_id: null,
          preview_endpoint_id: null,
          metadata: {},
        },
      ],
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Source import failed.")).toBeInTheDocument();
    });
  });

  it("Preview connect form submits localhost URL and renders ready iframe", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    const input = await screen.findByTestId("hww-preview-url-input");
    fireEvent.change(input, { target: { value: "http://127.0.0.1:5173" } });
    fireEvent.click(screen.getByTestId("hww-preview-connect-submit"));
    await waitFor(() => {
      expect(postBuilderLocalPreviewMock).toHaveBeenCalledWith("ws_abc", "proj_abc", {
        preview_url: "http://127.0.0.1:5173",
        source_snapshot_id: null,
      });
    });
    expect(await screen.findByTestId("hww-preview-iframe")).toBeInTheDocument();
  });

  it("Preview renders iframe only when status is ready with preview_url", async () => {
    getBuilderPreviewStatusMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      mode: "local",
      status: "ready",
      health: "healthy",
      preview_url: "http://127.0.0.1:3000/",
      message: "Preview is ready.",
      updated_at: "2026-01-01T00:00:00Z",
      source_snapshot_id: "ssnp_1",
      runtime_session_id: "rtms_1",
      preview_endpoint_id: "prve_1",
      logs_hint: null,
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-iframe")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-preview-open-new-tab")).not.toBeDisabled();
  });

  it("Preview refresh triggers status fetch call", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(getBuilderPreviewStatusMock.mock.calls.length).toBeGreaterThan(0);
    });
    const before = getBuilderPreviewStatusMock.mock.calls.length;
    const beforeActivity = getBuilderActivityMock.mock.calls.length;
    fireEvent.click(screen.getByTestId("hww-preview-refresh"));
    await waitFor(() => {
      expect(getBuilderPreviewStatusMock.mock.calls.length).toBeGreaterThan(before);
      expect(getBuilderActivityMock.mock.calls.length).toBeGreaterThan(beforeActivity);
    });
  });

  it("Preview error state shows safe copy", async () => {
    getBuilderPreviewStatusMock.mockRejectedValue(new Error("HTTP 500"));
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-state-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-preview-no-iframe")).toBeInTheDocument();
  });

  it("Preview connect failure renders safe error copy", async () => {
    postBuilderLocalPreviewMock.mockRejectedValueOnce(new Error("LOCAL_PREVIEW_URL_INVALID"));
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    fireEvent.change(await screen.findByTestId("hww-preview-url-input"), {
      target: { value: "https://example.com" },
    });
    fireEvent.click(screen.getByTestId("hww-preview-connect-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-state-error")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-preview-iframe")).toBeNull();
  });

  it("Disconnect preview returns to not-connected state", async () => {
    getBuilderPreviewStatusMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      mode: "local",
      status: "ready",
      health: "healthy",
      preview_url: "http://localhost:3000/",
      message: "Preview is ready.",
      updated_at: "2026-01-01T00:00:00Z",
      source_snapshot_id: null,
      runtime_session_id: "rtms_1",
      preview_endpoint_id: "prve_1",
      logs_hint: null,
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-iframe")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("hww-preview-disconnect"));
    await waitFor(() => {
      expect(deleteBuilderLocalPreviewMock).toHaveBeenCalledWith("ws_abc", "proj_abc");
    });
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-connect-form")).toBeInTheDocument();
    });
  });

  it("Share and Publish are disabled (not wired)", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-share")).toBeDisabled();
    expect(screen.getByTestId("hww-workbench-publish")).toBeDisabled();
  });

  it("embedded settings lists integrations with connect UI", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-preview-state-no-project")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-database"));
    expect(screen.getByText(/not available in this placeholder/i)).toBeInTheDocument();

    expect(screen.queryByTestId("hww-workbench-tab-github")).toBeNull();
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).toBeNull();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-storage"));
    const storagePanel = screen.getByTestId("hww-workbench-panel-storage");
    expect(within(storagePanel).getByTestId("hww-add-project-source")).toBeInTheDocument();
    expect(screen.getByText(/Select an active workspace and project/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-settings"));
    const settingsPanel = screen.getByTestId("hww-workbench-panel-settings");
    expect(settingsPanel).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-settings-nav-models")).toBeInTheDocument();
    expect(screen.getByText(/No project pinned/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-settings-nav-integrations"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Connected tools" })).toBeInTheDocument();
    });
  });

  it("Workbench settings Usage links to full-screen Usage & Billing with optional project_id", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/chat"]}>
        <WorkspaceWorkbench projectId="proj_abc" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("hww-workbench-tab-settings"));
    fireEvent.click(screen.getByTestId("hww-workbench-settings-nav-usage"));
    const usageLink = screen.getByTestId("hww-workbench-usage-full-settings");
    expect(usageLink).toHaveAttribute(
      "href",
      "/workspace/settings?section=usage&project_id=proj_abc",
    );
  });

  it("does not expose a workbench Terminal tab", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).toBeNull();
  });

  it("Add project source opens shared dialog from code and storage tabs", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    for (const tab of ["code", "storage"] as const) {
      fireEvent.click(screen.getByTestId(`hww-workbench-tab-${tab}`));
      const buttons = screen.getAllByTestId("hww-add-project-source");
      expect(buttons.length).toBe(1);
      fireEvent.click(buttons[0]!);
      expect(await screen.findByTestId("hww-project-source-dialog")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Close" }));
      await waitFor(() => {
        expect(screen.queryByTestId("hww-project-source-dialog")).not.toBeInTheDocument();
      });
    }
  });

  it("Project Source shows empty state for active project/workspace", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("hww-workbench-tab-storage"));
    await waitFor(() => {
      expect(screen.getByTestId("hww-project-source-empty-state")).toBeInTheDocument();
    });
  });

  it("Project Source renders source list and latest failed import", async () => {
    listBuilderProjectSourcesMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      sources: [
        {
          id: "psrc_1",
          project_id: "proj_abc",
          workspace_id: "ws_abc",
          kind: "zip_upload",
          status: "ready",
          display_name: "sample.zip",
          origin_ref: "zip_upload",
          active_snapshot_id: "ssnp_1",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by: "user_a",
          metadata: {},
        },
      ],
    });
    listBuilderSourceSnapshotsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      source_snapshots: [
        {
          id: "ssnp_1",
          project_id: "proj_abc",
          workspace_id: "ws_abc",
          project_source_id: "psrc_1",
          status: "materialized",
          digest_sha256: "abc",
          size_bytes: 1234,
          artifact_uri: "builder-artifact://bzip_1",
          manifest: {},
          created_at: "2026-01-01T00:00:00Z",
          created_by: "user_a",
          metadata: {},
        },
      ],
    });
    listBuilderImportJobsMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      import_jobs: [
        {
          id: "ijob_1",
          project_id: "proj_abc",
          workspace_id: "ws_abc",
          project_source_id: "psrc_1",
          source_snapshot_id: "ssnp_1",
          phase: "failed",
          status: "failed",
          error_code: "ZIP_PATH_TRAVERSAL",
          error_message: "ZIP contains unsafe path traversal entries.",
          stats: {},
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by: "user_a",
          metadata: {},
        },
      ],
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("hww-workbench-tab-storage"));
    await waitFor(() => {
      expect(screen.getByTestId("hww-project-source-list")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-project-source-active-snapshot")).toHaveTextContent("ssnp_1");
    expect(screen.getByTestId("hww-project-source-latest-job")).toHaveTextContent(
      "ZIP_PATH_TRAVERSAL",
    );
  });

  it("Preview tab keeps expected labels and no terminal tab", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-tab-preview")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-code")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-database")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-storage")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-settings")).toBeInTheDocument();
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).toBeNull();
  });
});
