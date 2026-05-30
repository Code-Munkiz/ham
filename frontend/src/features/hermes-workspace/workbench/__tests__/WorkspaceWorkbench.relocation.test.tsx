/**
 * Relocation integration: the managed approval panel mounted in
 * WorkspaceWorkbench must survive workbench tab switches and the mobile
 * right-pane collapse while a build is running, so fetchControlPlaneRun
 * polling state is never reset. We render the real WorkspaceWorkbench with a
 * managed approval payload, drive the OpenCode lane to the running phase, and
 * assert the panel root persists outside the per-tab content subtree.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type {
  CodingConductorCandidate,
  CodingConductorPreviewPayload,
  OpencodeBuildLaunchPayload,
  OpencodeBuildPreviewPayload,
} from "@/lib/ham/api";
import type { ControlPlaneRunPublic } from "@/lib/ham/types";

const {
  fetchWorkspaceToolsMock,
  isLocalRuntimeConfiguredMock,
  listBuilderProjectSourcesMock,
  listBuilderSourceSnapshotsMock,
  listBuilderImportJobsMock,
  getBuilderPreviewStatusMock,
  getBuilderActivityMock,
  getBuilderCloudRuntimeMock,
  createBuilderPreviewProxySessionMock,
  listBuilderCloudRuntimeJobsMock,
  getBuilderCloudRuntimeJobStatusMock,
  subscribeBuilderActivityStreamMock,
  requestBuilderCloudRuntimeMock,
  getBuilderWorkerCapabilitiesMock,
  getBuilderLocalRunProfileMock,
  listBuilderVisualEditRequestsMock,
  createBuilderVisualEditRequestMock,
  listBuilderSnapshotFilesMock,
  getBuilderSnapshotFileContentMock,
  postBuilderSnapshotFileChatMock,
  saveBuilderLocalRunProfileMock,
  deleteBuilderLocalRunProfileMock,
  postBuilderLocalPreviewMock,
  deleteBuilderLocalPreviewMock,
  downloadBuilderProjectZipMock,
  previewOpencodeBuildMock,
  launchOpencodeBuildMock,
  fetchControlPlaneRunMock,
} = vi.hoisted(() => ({
  fetchWorkspaceToolsMock: vi.fn(),
  isLocalRuntimeConfiguredMock: vi.fn(() => false),
  listBuilderProjectSourcesMock: vi.fn(),
  listBuilderSourceSnapshotsMock: vi.fn(),
  listBuilderImportJobsMock: vi.fn(),
  getBuilderPreviewStatusMock: vi.fn(),
  getBuilderActivityMock: vi.fn(),
  getBuilderCloudRuntimeMock: vi.fn(),
  createBuilderPreviewProxySessionMock: vi.fn(),
  listBuilderCloudRuntimeJobsMock: vi.fn(),
  getBuilderCloudRuntimeJobStatusMock: vi.fn(),
  subscribeBuilderActivityStreamMock: vi.fn(),
  requestBuilderCloudRuntimeMock: vi.fn(),
  getBuilderWorkerCapabilitiesMock: vi.fn(),
  getBuilderLocalRunProfileMock: vi.fn(),
  listBuilderVisualEditRequestsMock: vi.fn(),
  createBuilderVisualEditRequestMock: vi.fn(),
  listBuilderSnapshotFilesMock: vi.fn(),
  getBuilderSnapshotFileContentMock: vi.fn(),
  postBuilderSnapshotFileChatMock: vi.fn(),
  saveBuilderLocalRunProfileMock: vi.fn(),
  deleteBuilderLocalRunProfileMock: vi.fn(),
  postBuilderLocalPreviewMock: vi.fn(),
  deleteBuilderLocalPreviewMock: vi.fn(),
  downloadBuilderProjectZipMock: vi.fn(),
  previewOpencodeBuildMock: vi.fn(),
  launchOpencodeBuildMock: vi.fn(),
  fetchControlPlaneRunMock: vi.fn(),
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
    createBuilderPreviewProxySession: (...args: unknown[]) =>
      createBuilderPreviewProxySessionMock(...args),
    listBuilderCloudRuntimeJobs: (...args: unknown[]) => listBuilderCloudRuntimeJobsMock(...args),
    getBuilderCloudRuntimeJobStatus: (...args: unknown[]) =>
      getBuilderCloudRuntimeJobStatusMock(...args),
    subscribeBuilderActivityStream: (...args: unknown[]) =>
      subscribeBuilderActivityStreamMock(...args),
    requestBuilderCloudRuntime: (...args: unknown[]) => requestBuilderCloudRuntimeMock(...args),
    getBuilderWorkerCapabilities: (...args: unknown[]) => getBuilderWorkerCapabilitiesMock(...args),
    getBuilderLocalRunProfile: (...args: unknown[]) => getBuilderLocalRunProfileMock(...args),
    listBuilderVisualEditRequests: (...args: unknown[]) =>
      listBuilderVisualEditRequestsMock(...args),
    createBuilderVisualEditRequest: (...args: unknown[]) =>
      createBuilderVisualEditRequestMock(...args),
    listBuilderSnapshotFiles: (...args: unknown[]) => listBuilderSnapshotFilesMock(...args),
    getBuilderSnapshotFileContent: (...args: unknown[]) =>
      getBuilderSnapshotFileContentMock(...args),
    postBuilderSnapshotFileChat: (...args: unknown[]) => postBuilderSnapshotFileChatMock(...args),
    saveBuilderLocalRunProfile: (...args: unknown[]) => saveBuilderLocalRunProfileMock(...args),
    deleteBuilderLocalRunProfile: (...args: unknown[]) => deleteBuilderLocalRunProfileMock(...args),
    postBuilderLocalPreview: (...args: unknown[]) => postBuilderLocalPreviewMock(...args),
    deleteBuilderLocalPreview: (...args: unknown[]) => deleteBuilderLocalPreviewMock(...args),
    downloadBuilderProjectZip: (...args: unknown[]) => downloadBuilderProjectZipMock(...args),
    previewOpencodeBuild: (...args: unknown[]) => previewOpencodeBuildMock(...args),
    launchOpencodeBuild: (...args: unknown[]) => launchOpencodeBuildMock(...args),
    fetchControlPlaneRun: (...args: unknown[]) => fetchControlPlaneRunMock(...args),
  };
});

vi.mock("../../adapters/localRuntime", () => ({
  isLocalRuntimeConfigured: () => isLocalRuntimeConfiguredMock(),
}));

vi.mock("@/lib/ham/managedBuildSmokePreflight", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/managedBuildSmokePreflight")>(
    "@/lib/ham/managedBuildSmokePreflight",
  );
  return {
    ...actual,
    assertManagedBuildSmokePreflight: vi.fn(async () => ({
      host: "ham-test.vercel.app",
      statusUrl: "https://ham-test.vercel.app/api/status",
      version: "0.1.0",
      runCount: 0,
      traceContext: "test;o=1",
    })),
  };
});

import { WorkspaceWorkbench } from "../WorkspaceWorkbench";

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function candidate(over: Partial<CodingConductorCandidate> = {}): CodingConductorCandidate {
  return {
    provider: "opencode_cli",
    label: "OpenCode workspace build",
    available: true,
    reason: "Managed workspace build with a minimal diff and a preview snapshot.",
    blockers: [],
    confidence: 0.85,
    output_kind: "pull_request",
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    will_open_pull_request: false,
    ...over,
  };
}

function opencodePayload(): CodingConductorPreviewPayload {
  const chosen = candidate();
  return {
    kind: "coding_conductor_preview",
    preview_id: "preview-opencode-1",
    task_kind: "doc_fix",
    task_confidence: 0.9,
    chosen,
    candidates: [chosen],
    blockers: [],
    recommendation_reason: "Low-risk managed edit.",
    requires_approval: true,
    approval_kind: "confirm",
    project: {
      found: true,
      project_id: "project.opencode-1",
      build_lane_enabled: true,
      has_github_repo: false,
      output_target: "managed_workspace",
      has_workspace_id: true,
    },
    is_operator: false,
  };
}

function makeOpencodePreview(): OpencodeBuildPreviewPayload {
  return {
    kind: "opencode_build_preview",
    project_id: "project.opencode-1",
    project_name: "Honey Ham",
    user_prompt: "Add a docstring to main.",
    model: null,
    summary: "OpenCode will add a docstring to the main function.",
    proposal_digest: "b".repeat(64),
    base_revision: "rev-oc-1",
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
  };
}

function makeOpencodeAsyncLaunch(): OpencodeBuildLaunchPayload {
  return {
    kind: "opencode_build_launch",
    project_id: "project.opencode-1",
    ok: null,
    ham_run_id: RUN_ID,
    control_plane_status: "running",
    summary: null,
    error_summary: null,
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
    output_ref: null,
  };
}

function makeRunningRun(): ControlPlaneRunPublic {
  return {
    ham_run_id: RUN_ID,
    provider: "opencode",
    action_kind: "managed_workspace_build",
    project_id: "project.opencode-1",
    status: "running",
    status_reason: "opencode:running",
    external_id: null,
    workflow_id: null,
    summary: null,
    error_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:10Z",
    committed_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:01Z",
    finished_at: null,
    last_observed_at: null,
    last_provider_status: null,
    audit_ref: null,
    output_ref: null,
  };
}

async function driveToRunning() {
  fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
  await waitFor(() => expect(previewOpencodeBuildMock).toHaveBeenCalledTimes(1));
  const checkbox = document.querySelector(
    '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
  ) as HTMLInputElement;
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
  await waitFor(() => {
    const panel = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');
    expect(panel!.getAttribute("data-phase")).toBe("running");
  });
}

beforeEach(() => {
  fetchWorkspaceToolsMock.mockResolvedValue(
    new Response(
      JSON.stringify({ tools: [{ id: "github", connection: "off" }], scan_available: true, scan_hint: null }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );
  isLocalRuntimeConfiguredMock.mockReturnValue(false);
  downloadBuilderProjectZipMock.mockResolvedValue(undefined);
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
  getBuilderActivityMock.mockResolvedValue({ workspace_id: "ws_abc", project_id: "proj_abc", items: [] });
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
  createBuilderPreviewProxySessionMock.mockResolvedValue({
    workspace_id: "ws_abc",
    project_id: "proj_abc",
    status: "ready",
    expires_at: "2026-01-01T00:10:00Z",
  });
  listBuilderCloudRuntimeJobsMock.mockResolvedValue({ workspace_id: "ws_abc", project_id: "proj_abc", jobs: [] });
  getBuilderCloudRuntimeJobStatusMock.mockResolvedValue({
    workspace_id: "ws_abc",
    project_id: "proj_abc",
    job: null,
    runtime_session: null,
    preview_status: null,
    lifecycle: null,
  });
  requestBuilderCloudRuntimeMock.mockResolvedValue({ runtime: null, cloud_runtime: null, preview_status: null, activity_item: null });
  getBuilderWorkerCapabilitiesMock.mockResolvedValue({ workspace_id: "ws_abc", project_id: "proj_abc", workers: [] });
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
  listBuilderSnapshotFilesMock.mockResolvedValue({
    workspace_id: "ws_abc",
    project_id: "proj_abc",
    source_snapshot_id: null,
    files: [],
  });
  subscribeBuilderActivityStreamMock.mockImplementation(
    (_workspaceId: string, _projectId: string, callbacks: { onOpen?: () => void }) => {
      callbacks.onOpen?.();
      return { close: vi.fn() };
    },
  );
  previewOpencodeBuildMock.mockReset();
  launchOpencodeBuildMock.mockReset();
  fetchControlPlaneRunMock.mockReset();
  // Keep the run "running" so the panel does not transition during the test window.
  fetchControlPlaneRunMock.mockResolvedValue(makeRunningRun());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspaceWorkbench relocated approval mount", () => {
  it("renders the relocated approval panel outside the per-tab content subtree", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench
          workspaceId="ws_abc"
          projectId="proj_abc"
          managedApprovalPayload={opencodePayload()}
          managedApprovalPrompt="Add a docstring to main."
        />
      </MemoryRouter>,
    );
    const panel = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');
    expect(panel).not.toBeNull();
    const previewTabContent = screen.getByTestId("hww-workbench-panel-preview");
    expect(previewTabContent.contains(panel)).toBe(false);
  });

  it("VAL-RELOC-013: does NOT unmount the running panel on a workbench tab switch", async () => {
    previewOpencodeBuildMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeBuildMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    render(
      <MemoryRouter>
        <WorkspaceWorkbench
          workspaceId="ws_abc"
          projectId="proj_abc"
          managedApprovalPayload={opencodePayload()}
          managedApprovalPrompt="Add a docstring to main."
        />
      </MemoryRouter>,
    );

    await driveToRunning();
    const runningPanel = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');

    fireEvent.click(screen.getByTestId("hww-workbench-tab-code"));
    expect(screen.getByTestId("hww-workbench-panel-code")).toBeInTheDocument();

    const afterSwitch = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');
    expect(afterSwitch).not.toBeNull();
    expect(afterSwitch).toBe(runningPanel);
    expect(afterSwitch!.getAttribute("data-phase")).toBe("running");
  });

  it("VAL-RELOC-014: relocated running panel survives mobile right-pane collapse layout", async () => {
    previewOpencodeBuildMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeBuildMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    const { rerender } = render(
      <MemoryRouter>
        <div className="md:h-full">
          <WorkspaceWorkbench
            workspaceId="ws_abc"
            projectId="proj_abc"
            managedApprovalPayload={opencodePayload()}
            managedApprovalPrompt="Add a docstring to main."
          />
        </div>
      </MemoryRouter>,
    );

    await driveToRunning();
    const runningPanel = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');

    // Re-render inside the mobile collapsed (max-h-[48vh]) slot wrapper.
    rerender(
      <MemoryRouter>
        <div className="min-h-[min(260px,48vh)] max-h-[48vh]">
          <WorkspaceWorkbench
            workspaceId="ws_abc"
            projectId="proj_abc"
            managedApprovalPayload={opencodePayload()}
            managedApprovalPrompt="Add a docstring to main."
          />
        </div>
      </MemoryRouter>,
    );

    const afterCollapse = document.querySelector('[data-hww-coding-plan="opencode-build-approval"]');
    expect(afterCollapse).not.toBeNull();
    expect(afterCollapse).toBe(runningPanel);
    expect(afterCollapse!.getAttribute("data-phase")).toBe("running");
  });
});
