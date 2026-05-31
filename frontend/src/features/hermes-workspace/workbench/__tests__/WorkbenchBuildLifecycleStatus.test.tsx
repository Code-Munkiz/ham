/**
 * Right-pane build lifecycle → status shell integration.
 *
 * After the approval relocation, the build lifecycle (preview → approve →
 * building → completed) lives inside ManagedProviderBuildApprovalPanel. These
 * tests lock the new wiring that surfaces that lifecycle as plain-language
 * right-pane status (via the read-only onPhaseChange notifier), so the user can
 * always tell whether HAM is preparing a preview, building, done, or needs
 * attention — without re-hosting approval controls or leaking build-kit
 * internals.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorkbenchManagedApprovalMount } from "../WorkbenchManagedApprovalMount";
import {
  WorkbenchBuildStatusPanel,
  buildStatusFromManagedPhase,
} from "../WorkbenchBuildStatusPanel";
import { FORBIDDEN_USER_COPY_PATTERN } from "@/lib/ham/workbenchPreviewMessages";
import type { ManagedProviderBuildPhase } from "@/features/hermes-workspace/screens/chat/coding-plan/ManagedProviderBuildApprovalPanel";
import type {
  CodingConductorCandidate,
  CodingConductorPreviewPayload,
  DroidBuildLaunchPayload,
  DroidBuildPreviewPayload,
  OpencodeBuildLaunchPayload,
  OpencodeBuildPreviewPayload,
} from "@/lib/ham/api";
import type { ControlPlaneRunPublic } from "@/lib/ham/types";

vi.mock("@/lib/ham/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/api")>("@/lib/ham/api");
  return {
    ...actual,
    previewDroidBuild: vi.fn(),
    launchDroidBuild: vi.fn(),
    previewOpencodeBuild: vi.fn(),
    launchOpencodeBuild: vi.fn(),
    fetchControlPlaneRun: vi.fn(),
  };
});

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

import * as api from "@/lib/ham/api";

const previewDroidMock = api.previewDroidBuild as unknown as ReturnType<typeof vi.fn>;
const launchDroidMock = api.launchDroidBuild as unknown as ReturnType<typeof vi.fn>;
const previewOpencodeMock = api.previewOpencodeBuild as unknown as ReturnType<typeof vi.fn>;
const launchOpencodeMock = api.launchOpencodeBuild as unknown as ReturnType<typeof vi.fn>;
const pollMock = api.fetchControlPlaneRun as unknown as ReturnType<typeof vi.fn>;

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

const FORBIDDEN_BUILD_REGISTRY_TOKENS = [
  "registry_v2_app_type",
  "pack.site",
  "pack.game",
  "site.landing-page-core",
  "game.",
  "build registry v2",
  "fallback_reason",
  "gate report",
  "scaffold_quality",
  "recipe id",
  "pack id",
  "yaml",
  "playbook context",
] as const;

function candidate(over: Partial<CodingConductorCandidate> = {}): CodingConductorCandidate {
  return {
    provider: "factory_droid_build",
    label: "Managed workspace build",
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

function droidPayload(): CodingConductorPreviewPayload {
  const chosen = candidate();
  return {
    kind: "coding_conductor_preview",
    preview_id: "preview-managed-1",
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
      project_id: "project.app-f53b52",
      build_lane_enabled: true,
      has_github_repo: false,
      output_target: "managed_workspace",
      has_workspace_id: true,
    },
    is_operator: false,
  };
}

function opencodePayload(): CodingConductorPreviewPayload {
  const chosen = candidate({ provider: "opencode_cli" });
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

function makeDroidPreview(): DroidBuildPreviewPayload {
  return {
    kind: "droid_build_preview",
    project_id: "project.app-f53b52",
    project_name: "Honey Ham",
    user_prompt: "Tidy README typos.",
    summary: "This action proposes a low-risk managed workspace snapshot: docs and comments only.",
    proposal_digest: "a".repeat(64),
    base_revision: "rev-test",
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
  };
}

function makeDroidSyncLaunch(): DroidBuildLaunchPayload {
  return {
    kind: "droid_build_launch",
    project_id: "project.app-f53b52",
    ok: true,
    ham_run_id: RUN_ID,
    control_plane_status: "succeeded",
    pr_url: null,
    pr_branch: null,
    pr_commit_sha: null,
    build_outcome: null,
    summary: "Snapshot captured.",
    error_summary: null,
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
    output_ref: {
      snapshot_id: "snap_abc",
      changed_paths_count: 3,
      neutral_outcome: "snapshot_published",
    },
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

function makeRun(status: string, over: Partial<ControlPlaneRunPublic> = {}): ControlPlaneRunPublic {
  return {
    ham_run_id: RUN_ID,
    provider: "opencode",
    action_kind: "managed_workspace_build",
    project_id: "project.opencode-1",
    status,
    status_reason: "",
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
    ...over,
  };
}

/**
 * Mirror of the WorkspaceWorkbench wiring: the mount's onPhaseChange feeds the
 * presentational status shell via buildStatusFromManagedPhase (falling back to
 * a neutral preview-phase status when idle).
 */
function LifecycleHarness({ payload }: { payload: CodingConductorPreviewPayload }) {
  const [phase, setPhase] = React.useState<ManagedProviderBuildPhase>("idle");
  const status = buildStatusFromManagedPhase(phase) ?? "ready-to-build";
  return (
    <div>
      <WorkbenchBuildStatusPanel status={status} />
      <WorkbenchManagedApprovalMount
        payload={payload}
        userPrompt="Tidy README."
        onPhaseChange={setPhase}
      />
    </div>
  );
}

function statusText(): string {
  return screen.getByTestId("hww-build-status-shell").textContent ?? "";
}

beforeEach(() => {
  previewDroidMock.mockReset();
  launchDroidMock.mockReset();
  previewOpencodeMock.mockReset();
  launchOpencodeMock.mockReset();
  pollMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("right-pane build lifecycle status", () => {
  it("VAL-STATUS-001: starts at a neutral plain-language status before any build", () => {
    render(<LifecycleHarness payload={droidPayload()} />);
    expect(statusText()).toContain("Ready to build");
    expect(FORBIDDEN_USER_COPY_PATTERN.test(statusText())).toBe(false);
  });

  it("VAL-STATUS-002: announces preview-ready then build-completed across the Droid lifecycle", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidSyncLaunch());
    const { container } = render(<LifecycleHarness payload={droidPayload()} />);

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(statusText()).toContain("Preview ready"));

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(statusText()).toContain("Build completed"));
    expect(FORBIDDEN_USER_COPY_PATTERN.test(statusText())).toBe(false);
  });

  it("VAL-STATUS-003: shows Building… during async OpenCode run, then Build completed on poll success", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    pollMock.mockResolvedValue(makeRun("succeeded"));
    const { container } = render(<LifecycleHarness payload={opencodePayload()} />);

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(statusText()).toContain("Preview ready"));

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(statusText()).toContain("Building…"));
    await waitFor(() => expect(statusText()).toContain("Build completed"), { timeout: 7000 });
  });

  it("VAL-STATUS-004: surfaces attention status when an async build fails", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    pollMock.mockResolvedValue(makeRun("failed", { status_reason: "opencode:runner_error" }));
    const { container } = render(<LifecycleHarness payload={opencodePayload()} />);

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(statusText()).toContain("Preview ready"));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(statusText()).toContain("Something needs attention"), {
      timeout: 7000,
    });
  });

  it("VAL-STATUS-005: keeps exactly one approval root and never leaks internals into the status shell", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidSyncLaunch());
    render(<LifecycleHarness payload={droidPayload()} />);

    expect(document.querySelectorAll('[data-hww-coding-plan$="-approval"]')).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(statusText()).toContain("Preview ready"));

    const shell = (screen.getByTestId("hww-build-status-shell").textContent ?? "").toLowerCase();
    for (const token of FORBIDDEN_BUILD_REGISTRY_TOKENS) {
      expect(shell).not.toContain(token);
    }
    // The status shell is presentational — no controls.
    const shellNode = screen.getByTestId("hww-build-status-shell");
    expect(shellNode.querySelector("button")).toBeNull();
    expect(shellNode.querySelector('input[type="checkbox"]')).toBeNull();
  });
});
