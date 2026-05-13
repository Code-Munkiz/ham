import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const {
  fetchWorkspaceToolsMock,
  isLocalRuntimeConfiguredMock,
  listBuilderProjectSourcesMock,
  listBuilderSourceSnapshotsMock,
  listBuilderImportJobsMock,
  getBuilderPreviewStatusMock,
  getBuilderActivityMock,
  getBuilderCloudRuntimeMock,
  listBuilderCloudRuntimeJobsMock,
  getBuilderCloudRuntimeJobStatusMock,
  subscribeBuilderActivityStreamMock,
  createBuilderCloudRuntimeJobMock,
  getBuilderWorkerCapabilitiesMock,
  getBuilderLocalRunProfileMock,
  listBuilderVisualEditRequestsMock,
  createBuilderVisualEditRequestMock,
  saveBuilderLocalRunProfileMock,
  deleteBuilderLocalRunProfileMock,
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
  getBuilderCloudRuntimeMock: vi.fn(),
  listBuilderCloudRuntimeJobsMock: vi.fn(),
  getBuilderCloudRuntimeJobStatusMock: vi.fn(),
  subscribeBuilderActivityStreamMock: vi.fn(),
  createBuilderCloudRuntimeJobMock: vi.fn(),
  getBuilderWorkerCapabilitiesMock: vi.fn(),
  getBuilderLocalRunProfileMock: vi.fn(),
  listBuilderVisualEditRequestsMock: vi.fn(),
  createBuilderVisualEditRequestMock: vi.fn(),
  saveBuilderLocalRunProfileMock: vi.fn(),
  deleteBuilderLocalRunProfileMock: vi.fn(),
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
    getBuilderCloudRuntime: (...args: unknown[]) => getBuilderCloudRuntimeMock(...args),
    listBuilderCloudRuntimeJobs: (...args: unknown[]) => listBuilderCloudRuntimeJobsMock(...args),
    getBuilderCloudRuntimeJobStatus: (...args: unknown[]) =>
      getBuilderCloudRuntimeJobStatusMock(...args),
    subscribeBuilderActivityStream: (...args: unknown[]) =>
      subscribeBuilderActivityStreamMock(...args),
    createBuilderCloudRuntimeJob: (...args: unknown[]) => createBuilderCloudRuntimeJobMock(...args),
    getBuilderWorkerCapabilities: (...args: unknown[]) => getBuilderWorkerCapabilitiesMock(...args),
    getBuilderLocalRunProfile: (...args: unknown[]) => getBuilderLocalRunProfileMock(...args),
    listBuilderVisualEditRequests: (...args: unknown[]) =>
      listBuilderVisualEditRequestsMock(...args),
    createBuilderVisualEditRequest: (...args: unknown[]) =>
      createBuilderVisualEditRequestMock(...args),
    saveBuilderLocalRunProfile: (...args: unknown[]) => saveBuilderLocalRunProfileMock(...args),
    deleteBuilderLocalRunProfile: (...args: unknown[]) => deleteBuilderLocalRunProfileMock(...args),
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

function openPreviewDiagnostics() {
  fireEvent.click(screen.getByText("Advanced / Diagnostics"));
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
    getBuilderCloudRuntimeMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      mode: "cloud",
      status: "experiment_not_enabled",
      message: "Cloud runtime experiments are not enabled in this environment.",
      updated_at: "2026-01-01T00:00:00Z",
      runtime_session_id: null,
      source_snapshot_id: null,
      metadata: {},
    });
    listBuilderCloudRuntimeJobsMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      jobs: [],
    });
    getBuilderCloudRuntimeJobStatusMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      job: {
        id: "crjb_1",
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        source_snapshot_id: null,
        runtime_session_id: "rtms_cloud_1",
        status: "running",
        phase: "provider_accepted",
        provider: "cloud_run_poc",
        requested_by: "user_a",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        completed_at: null,
        error_code: null,
        error_message: null,
        logs_summary: "cloud provider accepted request",
        metadata: {},
      },
      runtime_session: { id: "rtms_cloud_1" },
      preview_status: {
        project_id: "proj_abc",
        workspace_id: "ws_abc",
        mode: "cloud",
        status: "building",
        health: "unknown",
        preview_url: null,
        message: "Cloud runtime is provisioning.",
        updated_at: "2026-01-01T00:00:00Z",
        source_snapshot_id: null,
        runtime_session_id: "rtms_cloud_1",
        preview_endpoint_id: null,
        logs_hint: null,
      },
      lifecycle: {
        phase: "provider_accepted",
        message: "Cloud runtime provider accepted the request.",
        updated_at: "2026-01-01T00:00:00Z",
        provider_status: "accepted by provider",
        logs_summary: "build starting",
      },
    });
    createBuilderCloudRuntimeJobMock.mockResolvedValue({
      job: {
        id: "crjb_1",
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        source_snapshot_id: null,
        runtime_session_id: "rtms_cloud_1",
        status: "succeeded",
        phase: "completed",
        provider: "local_mock",
        requested_by: "user_a",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        completed_at: "2026-01-01T00:00:00Z",
        error_code: null,
        error_message: null,
        logs_summary: "mock",
        metadata: {},
      },
      runtime_session: { id: "rtms_cloud_1" },
      cloud_runtime: {
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        mode: "cloud",
        status: "running",
        message: "Cloud runtime POC simulated. No real sandbox/build executed.",
        updated_at: "2026-01-01T00:00:00Z",
        runtime_session_id: "rtms_cloud_1",
        source_snapshot_id: null,
        metadata: {},
      },
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
      activity_item: null,
    });
    getBuilderWorkerCapabilitiesMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      workers: [
        {
          worker_kind: "cursor_cloud_agent",
          provider: "cursor_cloud_agent",
          display_name: "Cursor Cloud Agent",
          status: "needs_connection",
          capabilities: ["plan", "edit_code", "run_tests", "open_pr"],
          environment_fit: "Hosted/cloud coding runs against remote repositories.",
          required_setup: "Connect Cursor API key.",
          settings_href: "/workspace/settings?section=integrations",
          last_checked_at: "2026-01-01T00:00:00Z",
          metadata: {},
        },
        {
          worker_kind: "local_runtime",
          provider: "builder_local_runtime",
          display_name: "Local Runtime",
          status: "available",
          capabilities: ["local_preview_registration", "local_run_profile"],
          environment_fit: "Operator-run local dev server + loopback preview URL registration.",
          required_setup: "Save profile and connect preview URL.",
          settings_href: null,
          last_checked_at: "2026-01-01T00:00:00Z",
          metadata: {},
        },
        {
          worker_kind: "cloud_runtime_worker",
          provider: "builder_cloud_runtime",
          display_name: "Cloud Runtime Worker (POC)",
          status: "available_mock",
          capabilities: ["request_runtime_job", "read_job_status"],
          environment_fit: "Cloud runtime POC control-plane path.",
          required_setup: "Set local_mock provider.",
          settings_href: "/workspace/settings?section=integrations",
          last_checked_at: "2026-01-01T00:00:00Z",
          metadata: { provider_mode: "local_mock" },
        },
      ],
    });
    getBuilderLocalRunProfileMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      configured: false,
      status: "not_configured",
      profile: null,
    });
    listBuilderVisualEditRequestsMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      visual_edit_requests: [],
    });
    createBuilderVisualEditRequestMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      visual_edit_request: {
        id: "vedit_1",
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        source_snapshot_id: null,
        runtime_session_id: "rtms_1",
        preview_endpoint_id: "prve_1",
        route: "/",
        selector_hints: ["button.save"],
        bbox: null,
        instruction: "Change the CTA text",
        status: "draft",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        created_by: "user_a",
        metadata: {},
      },
    });
    saveBuilderLocalRunProfileMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      configured: true,
      status: "configured",
      profile: {
        id: "rprf_1",
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        source_snapshot_id: null,
        display_name: "Local run profile",
        working_directory: ".",
        install_command_argv: ["npm", "install"],
        dev_command_argv: ["npm", "run", "dev"],
        build_command_argv: ["npm", "run", "build"],
        test_command_argv: ["npm", "test"],
        expected_preview_url: "http://localhost:5173/",
        execution_mode: "local_only",
        status: "configured",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        created_by: "user_a",
        metadata: {},
      },
    });
    deleteBuilderLocalRunProfileMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      configured: false,
      status: "disabled",
      profile: null,
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
    subscribeBuilderActivityStreamMock.mockImplementation(
      (_workspaceId: string, _projectId: string, callbacks: { onOpen?: () => void }) => {
        callbacks.onOpen?.();
        return { close: vi.fn() };
      },
    );
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
      expect(screen.getByTestId("hww-preview-tell-ham")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-preview-iframe")).toBeNull();
    expect(screen.getByTestId("hww-preview-open-new-tab")).toBeDisabled();
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-connect-form")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-preview-activity-section")).toBeInTheDocument();
    expect(screen.getByTestId("hww-preview-activity-stream-copy")).toHaveTextContent(
      "Activity updates live when connected",
    );
    expect(screen.getByTestId("hww-preview-activity-stream-state")).toHaveTextContent("Live");
    expect(screen.getByTestId("hww-preview-activity-empty")).toBeInTheDocument();
    expect(screen.queryByText(/build stream/i)).toBeNull();
  });

  it("No project state does not call builder preview APIs", async () => {
    getBuilderPreviewStatusMock.mockClear();
    getBuilderCloudRuntimeMock.mockClear();
    listBuilderCloudRuntimeJobsMock.mockClear();
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-state-no-project")).toBeInTheDocument();
    });
    expect(getBuilderPreviewStatusMock).not.toHaveBeenCalled();
    expect(getBuilderCloudRuntimeMock).not.toHaveBeenCalled();
    expect(listBuilderCloudRuntimeJobsMock).not.toHaveBeenCalled();
  });

  it("Activity stream updates activity items from live events", async () => {
    let callbacks: { onActivity: (payload: any) => void; onOpen?: () => void } | null = null;
    subscribeBuilderActivityStreamMock.mockImplementation(
      (
        _workspaceId: string,
        _projectId: string,
        cb: { onActivity: (payload: any) => void; onOpen?: () => void },
      ) => {
        callbacks = cb;
        cb.onOpen?.();
        return { close: vi.fn() };
      },
    );
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-activity-stream-state")).toHaveTextContent("Live");
    });
    openPreviewDiagnostics();
    act(() => {
      callbacks?.onActivity({
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        connection_state: "live",
        stream_cursor: "1:act_demo",
        items: [
          {
            id: "act_demo",
            kind: "runtime_status",
            status: "running",
            title: "Cloud runtime provisioning",
            message: "Cloud runtime provider accepted request.",
            timestamp: "2026-01-01T00:00:00Z",
            source_id: null,
            snapshot_id: null,
            import_job_id: null,
            runtime_session_id: "rtms_1",
            preview_endpoint_id: null,
            metadata: {},
          },
        ],
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-activity-list")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Cloud runtime provisioning").length).toBeGreaterThan(0);
  });

  it("Activity stream fallback shows offline state when stream errors", async () => {
    subscribeBuilderActivityStreamMock.mockImplementation(
      (
        _workspaceId: string,
        _projectId: string,
        cb: { onOpen?: () => void; onError?: () => void },
      ) => {
        cb.onError?.();
        return { close: vi.fn() };
      },
    );
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-activity-stream-state")).toHaveTextContent(
        "Offline / refresh manually",
      );
    });
    expect(screen.queryByTestId("hww-preview-activity-list")).toBeNull();
  });

  it("Visual edit request stays disabled when preview not ready", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-visual-edit-section")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-visual-edit-disabled-copy")).toBeInTheDocument();
    expect(screen.getByTestId("hww-visual-edit-toggle")).toBeDisabled();
    expect(screen.getByTestId("hww-visual-edit-target-empty")).toBeInTheDocument();
  });

  it("Visual edit mode captures preview click target", async () => {
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
    const toggle = await screen.findByTestId("hww-visual-edit-toggle");
    expect(toggle).not.toBeDisabled();
    fireEvent.click(toggle);
    const overlay = await screen.findByTestId("hww-visual-edit-overlay");
    fireEvent.click(overlay, { clientX: 100, clientY: 120 });
    await waitFor(() => {
      expect(screen.getByTestId("hww-visual-edit-target-summary")).toBeInTheDocument();
    });
  });

  it("Visual edit request submits contract when preview is ready", async () => {
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
    openPreviewDiagnostics();
    fireEvent.click(await screen.findByTestId("hww-visual-edit-toggle"));
    fireEvent.click(await screen.findByTestId("hww-visual-edit-overlay"), {
      clientX: 120,
      clientY: 140,
    });
    fireEvent.change(await screen.findByTestId("hww-visual-edit-instruction"), {
      target: { value: "Move save button to top right" },
    });
    fireEvent.change(screen.getByTestId("hww-visual-edit-selector-hints"), {
      target: { value: ".toolbar .save-btn" },
    });
    fireEvent.click(screen.getByTestId("hww-visual-edit-submit"));
    await waitFor(() => {
      expect(createBuilderVisualEditRequestMock).toHaveBeenCalledWith("ws_abc", "proj_abc", {
        instruction: "Move save button to top right",
        route: "/",
        preview_url_kind: "local",
        target: {
          x: expect.any(Number),
          y: expect.any(Number),
          width: 1,
          height: 1,
          viewport_width: expect.any(Number),
          viewport_height: expect.any(Number),
          device_mode: expect.stringMatching(/desktop|mobile/),
        },
        selector_hints: [".toolbar .save-btn"],
        bbox: { x: expect.any(Number), y: expect.any(Number), width: 1, height: 1 },
        runtime_session_id: "rtms_1",
        preview_endpoint_id: "prve_1",
        source_snapshot_id: "ssnp_1",
        status: "queued",
      });
    });
    expect(screen.getByTestId("hww-visual-edit-success")).toHaveTextContent(
      "Edit request saved. Agent execution is not connected yet.",
    );
  });

  it("Preview renders local run profile section with not configured status", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-local-run-profile-section")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-local-run-profile-status")).toHaveTextContent("Not configured");
    expect(screen.queryByTestId("hww-local-run-profile-use-preview-url")).toBeNull();
    expect(screen.queryByText(/running build/i)).toBeNull();
  });

  it("Preview renders honest cloud runtime placeholder copy", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-cloud-runtime-section")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-cloud-runtime-status")).toHaveTextContent(
      "experiment_not_enabled",
    );
    expect(screen.getByTestId("hww-cloud-runtime-message")).toHaveTextContent(
      "not enabled in this environment",
    );
    expect(screen.getByTestId("hww-cloud-runtime-section")).toHaveTextContent(
      "control-plane path only",
    );
    expect(screen.queryByText(/deployed successfully/i)).toBeNull();
  });

  it("Cloud runtime POC request button is disabled when provider is disabled", async () => {
    getBuilderWorkerCapabilitiesMock.mockResolvedValueOnce({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      workers: [
        {
          worker_kind: "cloud_runtime_worker",
          provider: "builder_cloud_runtime",
          display_name: "Cloud Runtime Worker (POC)",
          status: "disabled",
          capabilities: ["request_runtime_job", "read_job_status"],
          environment_fit: "Cloud runtime POC control-plane path.",
          required_setup: "Set local_mock provider.",
          settings_href: null,
          last_checked_at: "2026-01-01T00:00:00Z",
          metadata: { provider_mode: "disabled" },
        },
      ],
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-cloud-runtime-request-poc")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-cloud-runtime-request-poc")).toBeDisabled();
    expect(screen.getByTestId("hww-cloud-runtime-disabled-copy")).toBeInTheDocument();
    expect(screen.getByTestId("hww-cloud-runtime-provider-copy")).toHaveTextContent(
      "experiments are not enabled",
    );
  });

  it("Cloud runtime card shows config-missing/unavailable provider state", async () => {
    getBuilderCloudRuntimeMock.mockResolvedValueOnce({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      mode: "cloud",
      status: "config_missing",
      message: "Cloud runtime provider needs configuration before it can run.",
      updated_at: "2026-01-01T00:00:00Z",
      runtime_session_id: null,
      source_snapshot_id: null,
      metadata: {},
    });
    getBuilderWorkerCapabilitiesMock.mockResolvedValueOnce({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      workers: [
        {
          worker_kind: "cloud_runtime_worker",
          provider: "builder_cloud_runtime",
          display_name: "Cloud Runtime Worker (POC)",
          status: "unavailable",
          capabilities: ["request_runtime_job", "read_job_status"],
          environment_fit: "Cloud runtime POC control-plane path.",
          required_setup: "Set GCP project + region.",
          settings_href: null,
          last_checked_at: "2026-01-01T00:00:00Z",
          metadata: { provider_mode: "cloud_run_poc" },
        },
      ],
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-cloud-runtime-provider-status")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-cloud-runtime-provider-status")).toHaveTextContent(
      "unavailable",
    );
    expect(screen.getByTestId("hww-cloud-runtime-provider-copy")).toHaveTextContent(
      "needs configuration",
    );
    expect(screen.getByTestId("hww-cloud-runtime-request-poc")).toBeDisabled();
  });

  it("Cloud runtime POC request calls API and refreshes state", async () => {
    getBuilderPreviewStatusMock.mockResolvedValueOnce({
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
    getBuilderCloudRuntimeMock.mockResolvedValueOnce({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      mode: "cloud",
      status: "provider_ready",
      message: "Cloud runtime provider is configured for experimentation.",
      updated_at: "2026-01-01T00:00:00Z",
      runtime_session_id: null,
      source_snapshot_id: "ssnp_1",
      metadata: {},
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    const btn = await screen.findByTestId("hww-cloud-runtime-request-poc");
    fireEvent.click(btn);
    await waitFor(() => {
      expect(createBuilderCloudRuntimeJobMock).toHaveBeenCalledWith("ws_abc", "proj_abc", {
        source_snapshot_id: "ssnp_1",
        metadata: { request_source: "workbench_preview_tab" },
      });
    });
    expect(screen.getByTestId("hww-cloud-runtime-job-notice")).toHaveTextContent(
      "No production sandbox/build execution was performed",
    );
    expect(screen.getByTestId("hww-cloud-runtime-latest-job")).toHaveTextContent("succeeded");
  });

  it("Preview renders compact builder worker statuses", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-worker-capability-list")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId("hww-worker-capability-item").length).toBe(3);
    expect(screen.getByText("Cursor Cloud Agent")).toBeInTheDocument();
    expect(screen.getByText("Local Runtime")).toBeInTheDocument();
    expect(screen.getByText("Cloud Runtime Worker (POC)")).toBeInTheDocument();
    expect(screen.getByText("needs connection")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(screen.getByText("available mock")).toBeInTheDocument();
  });

  it("Saving local run profile calls API and renders configured summary", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    fireEvent.change(await screen.findByTestId("hww-local-run-profile-dev-command"), {
      target: { value: "npm run dev" },
    });
    fireEvent.change(screen.getByTestId("hww-local-run-profile-working-directory"), {
      target: { value: "." },
    });
    fireEvent.change(screen.getByTestId("hww-local-run-profile-expected-preview-url"), {
      target: { value: "http://localhost:5173" },
    });
    fireEvent.click(screen.getByTestId("hww-local-run-profile-save"));
    await waitFor(() => {
      expect(saveBuilderLocalRunProfileMock).toHaveBeenCalled();
    });
    expect(await screen.findByTestId("hww-local-run-profile-summary")).toHaveTextContent(
      "npm run dev",
    );
    expect(screen.getByTestId("hww-local-run-profile-use-preview-url")).toBeInTheDocument();
  });

  it("Local run profile clear action calls delete helper", async () => {
    getBuilderLocalRunProfileMock.mockResolvedValue({
      workspace_id: "ws_abc",
      project_id: "proj_abc",
      configured: true,
      status: "configured",
      profile: {
        id: "rprf_1",
        workspace_id: "ws_abc",
        project_id: "proj_abc",
        source_snapshot_id: null,
        display_name: "Local run profile",
        working_directory: ".",
        install_command_argv: null,
        dev_command_argv: ["npm", "run", "dev"],
        build_command_argv: null,
        test_command_argv: null,
        expected_preview_url: "http://localhost:3000/",
        execution_mode: "local_only",
        status: "configured",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        created_by: "user_a",
        metadata: {},
      },
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-local-run-profile-clear")).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId("hww-local-run-profile-clear"));
    await waitFor(() => {
      expect(deleteBuilderLocalRunProfileMock).toHaveBeenCalledWith("ws_abc", "proj_abc");
    });
  });

  it("Local run profile save error renders safe copy", async () => {
    saveBuilderLocalRunProfileMock.mockRejectedValueOnce(new Error("LOCAL_RUN_COMMAND_INVALID"));
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
    fireEvent.click(await screen.findByTestId("hww-local-run-profile-save"));
    await waitFor(() => {
      expect(screen.getByTestId("hww-local-run-profile-error")).toBeInTheDocument();
    });
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
    openPreviewDiagnostics();
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
    openPreviewDiagnostics();
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
    openPreviewDiagnostics();
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

  it("Cloud preview normalizes proxy path to same-origin /api route", async () => {
    getBuilderPreviewStatusMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      mode: "cloud",
      status: "ready",
      health: "healthy",
      preview_url: "workspaces/ws_abc/projects/proj_abc/builder/preview-proxy/",
      message: "Preview is ready via authenticated cloud proxy.",
      updated_at: "2026-01-01T00:00:00Z",
      source_snapshot_id: "ssnp_1",
      runtime_session_id: "rtms_cloud_1",
      preview_endpoint_id: "prve_cloud_1",
      logs_hint: null,
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    const iframe = await screen.findByTestId("hww-preview-iframe");
    expect(iframe).toHaveAttribute(
      "src",
      "/api/workspaces/ws_abc/projects/proj_abc/builder/preview-proxy/",
    );
  });

  it("Cloud preview blocks unsafe absolute upstream URL from iframe", async () => {
    getBuilderPreviewStatusMock.mockResolvedValue({
      project_id: "proj_abc",
      workspace_id: "ws_abc",
      mode: "cloud",
      status: "ready",
      health: "healthy",
      preview_url: "https://provider.e2b.app/",
      message: "Preview is ready via authenticated cloud proxy.",
      updated_at: "2026-01-01T00:00:00Z",
      source_snapshot_id: "ssnp_1",
      runtime_session_id: "rtms_cloud_1",
      preview_endpoint_id: "prve_cloud_1",
      logs_hint: null,
    });
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.queryByTestId("hww-preview-iframe")).toBeNull();
    });
    expect(screen.getByTestId("hww-preview-open-new-tab")).toBeDisabled();
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
    expect(screen.queryByTestId("hww-preview-iframe")).toBeNull();
  });

  it("Unknown project errors render safe guidance copy", async () => {
    getBuilderPreviewStatusMock.mockRejectedValueOnce(
      new Error("Unknown project_id 'project.app-f53b52'."),
    );
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="project.app-f53b52" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-state-error")).toHaveTextContent(
        "Project record not found. Refresh workspace or create a new project.",
      );
    });
  });

  it("Preview connect failure renders safe error copy", async () => {
    postBuilderLocalPreviewMock.mockRejectedValueOnce(new Error("LOCAL_PREVIEW_URL_INVALID"));
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    openPreviewDiagnostics();
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
    openPreviewDiagnostics();
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
      expect(screen.getByText(/Recommended for full projects/i)).toBeInTheDocument();
      expect(screen.getByTestId("hww-project-source-workspace-folder-btn")).toBeInTheDocument();
      expect(screen.getByTestId("hww-project-source-chat-import-copy")).toBeInTheDocument();
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

  it("Preview-first Part Z: diagnostics hidden until Advanced is opened", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-advanced")).toBeInTheDocument();
    });
    const details = screen.getByTestId("hww-preview-advanced") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    openPreviewDiagnostics();
    await waitFor(() => {
      expect(screen.getByTestId("hww-local-run-profile-form")).toBeInTheDocument();
      expect(screen.getByTestId("hww-worker-capability-section")).toBeInTheDocument();
      expect(screen.getByTestId("hww-visual-edit-section")).toBeInTheDocument();
      expect(screen.getByTestId("hww-visual-edit-target-empty")).toBeInTheDocument();
    });
  });

  it("Preview-first Part Z: primary copy does not lead with raw HTTP 404", async () => {
    getBuilderPreviewStatusMock.mockRejectedValueOnce(new Error("HTTP 404 Not Found"));
    render(
      <MemoryRouter>
        <WorkspaceWorkbench projectId="proj_abc" workspaceId="ws_abc" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-primary-title")).toHaveTextContent(
        "Preview could not start.",
      );
    });
    const err = screen.getByTestId("hww-preview-state-error").textContent || "";
    expect(err.toLowerCase().includes("http 404")).toBe(false);
    expect(err).toMatch(/not available yet|preview status/i);
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
