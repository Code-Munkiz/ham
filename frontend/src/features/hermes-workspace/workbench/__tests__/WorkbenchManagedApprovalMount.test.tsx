/**
 * Right-pane relocation of the managed build approval experience.
 *
 * The approval engine (ManagedProviderBuildApprovalPanel via the Droid /
 * OpenCode wrappers) is mounted in the workbench right pane through
 * WorkbenchManagedApprovalMount, gated by the SAME exported pure predicates
 * the chat card used to use. These tests lock the relocation contract:
 * gating, provider selection, preview→approve→launch gating, verbatim launch
 * payloads, running-phase polling, and no-internals leakage — all in the
 * right-pane subtree, with a single approval root document-wide.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorkbenchManagedApprovalMount } from "../WorkbenchManagedApprovalMount";
import { CodingPlanCard } from "@/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard";
import { FORBIDDEN_CARD_TOKENS } from "@/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy";
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
  "site.dashboard-ui-core",
  "game.",
  "build registry v2",
  "registry route",
  "route matched",
  "fallback_reason",
  "gate report",
  "gate review",
  "scaffold_quality",
  "dashboard_",
  "city_",
  "tactics_",
  "landing_",
  "recipe id",
  "pack id",
  "yaml",
  "render length",
  "render budget",
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

function nonManagedPayload(): CodingConductorPreviewPayload {
  const chosen = candidate({
    provider: "cursor_cloud",
    will_open_pull_request: true,
  });
  return {
    kind: "coding_conductor_preview",
    preview_id: "preview-pr-1",
    task_kind: "feature",
    task_confidence: 0.7,
    chosen,
    candidates: [chosen],
    blockers: [],
    recommendation_reason: "Opens a pull request.",
    requires_approval: true,
    approval_kind: "confirm",
    project: {
      found: true,
      project_id: "p1",
      build_lane_enabled: true,
      has_github_repo: true,
      output_target: "github_pr",
      has_workspace_id: false,
    },
    is_operator: false,
  };
}

function makeDroidPreview(over: Partial<DroidBuildPreviewPayload> = {}): DroidBuildPreviewPayload {
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
    ...over,
  };
}

function makeDroidLaunch(over: Partial<DroidBuildLaunchPayload> = {}): DroidBuildLaunchPayload {
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
      preview_url: "https://snapshots.example.test/p/abc",
      changed_paths_count: 3,
      neutral_outcome: "snapshot_published",
    },
    ...over,
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

function makeOpencodeSyncLaunch(): OpencodeBuildLaunchPayload {
  return {
    kind: "opencode_build_launch",
    project_id: "project.opencode-1",
    ok: true,
    ham_run_id: RUN_ID,
    control_plane_status: "succeeded",
    summary: "Done.",
    error_summary: null,
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
    output_ref: { snapshot_id: "snap_sync", changed_paths_count: 1 },
  };
}

function makeRun(
  status: string,
  status_reason: string,
  over: Partial<ControlPlaneRunPublic> = {},
): ControlPlaneRunPublic {
  return {
    ham_run_id: RUN_ID,
    provider: "opencode",
    action_kind: "managed_workspace_build",
    project_id: "project.opencode-1",
    status,
    status_reason,
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

function rightPaneRoot(): HTMLElement {
  return document.querySelector('[data-testid="hww-right-pane-approval"]') as HTMLElement;
}

function assertNoForbiddenTokens(node: HTMLElement) {
  const blob = (node.textContent || "").toLowerCase();
  for (const token of FORBIDDEN_CARD_TOKENS) {
    expect(blob, `right pane leaks ${token}`).not.toContain(token);
  }
  for (const token of FORBIDDEN_BUILD_REGISTRY_TOKENS) {
    expect(blob, `right pane leaks build-registry token ${token}`).not.toContain(token);
  }
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

describe("WorkbenchManagedApprovalMount — gating + provider selection", () => {
  it("VAL-RELOC-001: mounts the Droid managed-build-approval panel when gated true", () => {
    render(<WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy docs" />);
    const root = rightPaneRoot();
    expect(root).not.toBeNull();
    expect(root.querySelector('[data-hww-coding-plan="managed-build-approval"]')).not.toBeNull();
  });

  it("VAL-RELOC-002: mounts the OpenCode opencode-build-approval panel when gated true", () => {
    render(<WorkbenchManagedApprovalMount payload={opencodePayload()} userPrompt="Tidy docs" />);
    const root = rightPaneRoot();
    expect(root).not.toBeNull();
    expect(root.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).not.toBeNull();
  });

  it("VAL-RELOC-003: renders no approval panel when neither predicate is satisfied", () => {
    const { container } = render(
      <WorkbenchManagedApprovalMount payload={nonManagedPayload()} userPrompt="x" />,
    );
    expect(container.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
    expect(container.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();
    expect(rightPaneRoot()).toBeNull();
  });

  it("renders nothing when payload is null", () => {
    const { container } = render(<WorkbenchManagedApprovalMount payload={null} userPrompt="x" />);
    expect(container.firstChild).toBeNull();
  });

  it("VAL-RELOC-004: Droid payload mounts only Droid; OpenCode payload mounts only OpenCode", () => {
    const { container: droid } = render(
      <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="x" />,
    );
    expect(droid.querySelector('[data-hww-coding-plan="managed-build-approval"]')).not.toBeNull();
    expect(droid.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();

    const { container: oc } = render(
      <WorkbenchManagedApprovalMount payload={opencodePayload()} userPrompt="x" />,
    );
    expect(oc.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).not.toBeNull();
    expect(oc.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
  });
});

describe("WorkbenchManagedApprovalMount — preserved launch mechanics", () => {
  it("VAL-RELOC-005: launch stays disabled until preview success AND approve checkbox ticked", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    const { container } = render(
      <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));

    const launchBtn = (await screen.findByRole("button", {
      name: /approve build/i,
    })) as HTMLButtonElement;
    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("0");
    expect(launchBtn.disabled).toBe(true);

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("1");
    expect(launchBtn.disabled).toBe(false);
  });

  it("VAL-RELOC-006/007: Droid launch sends verbatim digest/base_revision + confirmed + accept_pr", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidLaunch());
    const { container } = render(
      <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(launchDroidMock).toHaveBeenCalledTimes(1));

    const launchArgs = launchDroidMock.mock.calls[0]![0]!;
    expect(launchArgs).toMatchObject({
      project_id: "project.app-f53b52",
      user_prompt: "Tidy README typos.",
      proposal_digest: "a".repeat(64),
      base_revision: "rev-test",
      confirmed: true,
      accept_pr: true,
    });
  });

  it("VAL-RELOC-008: OpenCode launch sends verbatim digest/base_revision + confirmed and omits accept_pr", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeSyncLaunch());
    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={opencodePayload()}
        userPrompt="Add a docstring to main."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewOpencodeMock).toHaveBeenCalledTimes(1));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(launchOpencodeMock).toHaveBeenCalledTimes(1));

    const launchArgs = launchOpencodeMock.mock.calls[0]![0]!;
    expect(launchArgs).toMatchObject({
      project_id: "project.opencode-1",
      proposal_digest: "b".repeat(64),
      base_revision: "rev-oc-1",
      confirmed: true,
    });
    expect(Object.prototype.hasOwnProperty.call(launchArgs, "accept_pr")).toBe(false);
  });

  it("VAL-RELOC-012: synchronous ok:true launch goes to success without polling", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeSyncLaunch());
    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={opencodePayload()}
        userPrompt="Add a docstring to main."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewOpencodeMock).toHaveBeenCalledTimes(1));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());
    expect(pollMock).not.toHaveBeenCalled();
  });
});

describe("WorkbenchManagedApprovalMount — running-phase polling", () => {
  it("VAL-RELOC-010: running → succeeded polls fetchControlPlaneRun and reaches success", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    pollMock.mockResolvedValue(
      makeRun("succeeded", "opencode:snapshot_emitted", {
        output_ref: {
          snapshot_id: "snap_xyz",
          preview_url: "https://snapshots.example.test/p/xyz",
          changed_paths_count: 2,
        },
      }),
    );

    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={opencodePayload()}
        userPrompt="Add a docstring to main."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewOpencodeMock).toHaveBeenCalledTimes(1));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    const panel = await waitFor(() => {
      const el = container.querySelector('[data-hww-coding-plan="opencode-build-approval"]');
      expect(el!.getAttribute("data-phase")).toBe("running");
      return el as HTMLElement;
    });
    expect(panel.getAttribute("data-phase")).toBe("running");

    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull(), {
      timeout: 7000,
    });
    expect(pollMock).toHaveBeenCalledWith(RUN_ID);
  }, 12000);

  it("VAL-RELOC-011: running → failed renders normie message, hides raw internals", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    pollMock.mockResolvedValue(
      makeRun("failed", "opencode:timeout", {
        error_summary: "internal: asyncio.TimeoutError after 270s",
      }),
    );

    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={opencodePayload()}
        userPrompt="Add a docstring to main."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewOpencodeMock).toHaveBeenCalledTimes(1));
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(screen.queryByText(/Build did not complete/i)).not.toBeNull(), {
      timeout: 7000,
    });
    expect(screen.queryByText(/asyncio\.TimeoutError/)).toBeNull();
    expect(screen.queryByText(/internal:/)).toBeNull();
    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  }, 12000);
});

describe("WorkbenchManagedApprovalMount — leakage + single source of truth", () => {
  it("VAL-RELOC-015: no forbidden internals across idle/preview/approve/success states", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidLaunch());
    const { container } = render(
      <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />,
    );

    assertNoForbiddenTokens(rightPaneRoot());

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
    assertNoForbiddenTokens(rightPaneRoot());

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(launchDroidMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());
    assertNoForbiddenTokens(rightPaneRoot());
  });

  it("VAL-RELOC-016 / VAL-CHAT1-004: exactly one approval root and one approve checkbox document-wide", async () => {
    const payload = droidPayload();
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    const { container } = render(
      <>
        <CodingPlanCard payload={payload} userPrompt="Tidy README." />
        <WorkbenchManagedApprovalMount payload={payload} userPrompt="Tidy README." />
      </>,
    );

    expect(container.querySelectorAll('[data-hww-coding-plan$="-approval"]').length).toBe(1);

    // Drive the (single) right-pane panel to the approve step.
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
    expect(container.querySelectorAll('[data-hww-coding-plan$="-approve-checkbox"]').length).toBe(
      1,
    );
  });
});
