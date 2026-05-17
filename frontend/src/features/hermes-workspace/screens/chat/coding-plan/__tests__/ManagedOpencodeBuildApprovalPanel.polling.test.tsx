/**
 * Tests for the async job / polling flow in the OpenCode approval panel.
 *
 * The OpenCode launch_proxy now returns {ok: null, control_plane_status: "running",
 * ham_run_id} immediately. The panel must:
 *   1. Enter "running" phase (show running headline + note).
 *   2. Poll GET /api/control-plane-runs/{ham_run_id} until terminal status.
 *   3. Transition to "succeeded" or "failed" based on the polled run.
 *
 * We test via ManagedProviderBuildApprovalPanel directly so we can inject
 * `pollIntervalMs: 0` — this avoids any fake-timer / waitFor interaction.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import {
  ManagedProviderBuildApprovalPanel,
  type ManagedProviderBuildConfig,
} from "../ManagedProviderBuildApprovalPanel";
import {
  normieFailMessageForOpencode,
  OPENCODE_BUILD_RUNNING_HEADLINE,
  OPENCODE_BUILD_RUNNING_NOTE,
  OPENCODE_BUILD_SUCCESS_HEADLINE,
  OPENCODE_BUILD_FAILURE_HEADLINE,
} from "../codingPlanCardCopy";
import type { OpencodeBuildLaunchPayload, OpencodeBuildPreviewPayload } from "@/lib/ham/api";
import type { ControlPlaneRunPublic } from "@/lib/ham/types";

vi.mock("@/lib/ham/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/api")>("@/lib/ham/api");
  return {
    ...actual,
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

const pollMock = api.fetchControlPlaneRun as unknown as ReturnType<typeof vi.fn>;

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function makePreview(): OpencodeBuildPreviewPayload {
  return {
    kind: "opencode_build_preview",
    project_id: "project.opencode-1",
    project_name: "Honey Ham",
    user_prompt: "Add a docstring to main.",
    summary: "OpenCode will add a docstring to the main function.",
    proposal_digest: "b".repeat(64),
    base_revision: "rev-oc-1",
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
  };
}

function makeAsyncLaunch(): OpencodeBuildLaunchPayload {
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

function makeSyncLaunch(): OpencodeBuildLaunchPayload {
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

function buildTestConfig(
  launchFn: () => Promise<OpencodeBuildLaunchPayload>,
): ManagedProviderBuildConfig<OpencodeBuildPreviewPayload, OpencodeBuildLaunchPayload> {
  return {
    providerKey: "opencode_managed_build",
    testIdPrefix: "opencode-build",
    ariaLabel: "OpenCode managed workspace build approval",
    copy: {
      headline: "Review OpenCode build",
      body: "HAM will run OpenCode in a managed workspace.",
      noPrNote: "Managed workspace builds never open a pull request.",
      checkbox: "I approve HAM to create a managed workspace snapshot with OpenCode.",
      previewCta: "Preview",
      previewBusy: "Previewing…",
      launchCta: "Approve build",
      launchBusy: "Building…",
      successHeadline: OPENCODE_BUILD_SUCCESS_HEADLINE,
      failureHeadline: OPENCODE_BUILD_FAILURE_HEADLINE,
      previewLink: "Preview",
      viewChangesLink: "View changes",
      technicalDetailsSummary: "Details",
      keepBuildingCta: "Keep building",
      laneLabel: "OpenCode build",
      discardPreviewLabel: "Discard preview",
      startOverLabel: "Start over",
      defaultPreviewError: "Preview failed.",
      defaultLaunchError: "Build failed.",
      failureFallbackMessage: "The build did not complete.",
      snapshotIdLabel: "Snapshot id:",
      outcomeLabel: "Outcome:",
    },
    preview: async () => makePreview(),
    launch: launchFn,
    changedPathsLine: (n) => (n === 1 ? "1 file changed" : `${n} files changed`),
    runningHeadline: OPENCODE_BUILD_RUNNING_HEADLINE,
    runningNote: OPENCODE_BUILD_RUNNING_NOTE,
    normieFailMessageForStatusReason: normieFailMessageForOpencode,
    pollIntervalMs: 0,
  };
}

async function renderAndApprove(launchFn: () => Promise<OpencodeBuildLaunchPayload>) {
  const config = buildTestConfig(launchFn);
  render(
    <ManagedProviderBuildApprovalPanel
      projectId="project.opencode-1"
      userPrompt="Add a docstring to main."
      config={config}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /preview/i }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /approve build/i })).not.toBeNull(),
  );

  const checkbox = document.querySelector(
    '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
  ) as HTMLInputElement;
  fireEvent.click(checkbox);

  return screen.getByRole("button", { name: /approve build/i }) as HTMLButtonElement;
}

beforeEach(() => {
  pollMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OpenCode async launch → running → polling", () => {
  it("transitions to 'running' phase and shows running headline when launch returns control_plane_status=running", async () => {
    pollMock.mockResolvedValue(makeRun("running", "opencode:running"));

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_RUNNING_HEADLINE)).not.toBeNull());

    const panel = document.querySelector(
      '[data-hww-coding-plan="opencode-build-approval"]',
    ) as HTMLElement;
    expect(panel.getAttribute("data-phase")).toBe("running");
  });

  it("polls fetchControlPlaneRun and transitions to 'succeeded' on run.status=succeeded", async () => {
    pollMock.mockResolvedValueOnce(makeRun("running", "opencode:running")).mockResolvedValueOnce(
      makeRun("succeeded", "opencode:snapshot_emitted", {
        output_ref: {
          snapshot_id: "snap_xyz",
          preview_url: "https://snapshots.example.test/p/xyz",
          changed_paths_count: 2,
        },
      }),
    );

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_SUCCESS_HEADLINE)).not.toBeNull());

    expect(pollMock).toHaveBeenCalledWith(RUN_ID);
    expect(screen.getByRole("link", { name: /preview/i })).toHaveAttribute(
      "href",
      "https://snapshots.example.test/p/xyz",
    );
  });

  it("transitions to 'failed' with normie message on run.status=failed opencode:timeout", async () => {
    pollMock.mockResolvedValueOnce(
      makeRun("failed", "opencode:timeout", {
        error_summary: "internal: asyncio.TimeoutError after 270s",
      }),
    );

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_FAILURE_HEADLINE)).not.toBeNull());

    const expectedMsg = normieFailMessageForOpencode("opencode:timeout");
    expect(expectedMsg).not.toBeNull();
    expect(screen.getByText(expectedMsg!)).toBeTruthy();

    // Raw internal error must NOT be shown.
    expect(screen.queryByText(/asyncio\.TimeoutError/)).toBeNull();
    expect(screen.queryByText(/internal:/)).toBeNull();
  });

  it("transitions to 'failed' with normie message on opencode:session_no_completion", async () => {
    pollMock.mockResolvedValueOnce(makeRun("failed", "opencode:session_no_completion"));

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_FAILURE_HEADLINE)).not.toBeNull());
    const msg = normieFailMessageForOpencode("opencode:session_no_completion");
    expect(screen.getByText(msg!)).toBeTruthy();
  });

  it("retries poll on network error", async () => {
    pollMock
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce(makeRun("succeeded", "opencode:snapshot_emitted"));

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(
      () => expect(screen.queryByText(OPENCODE_BUILD_SUCCESS_HEADLINE)).not.toBeNull(),
      { timeout: 5000 },
    );
    expect(pollMock).toHaveBeenCalledTimes(2);
  });

  it("does NOT enter running phase and does NOT call fetchControlPlaneRun when launch is synchronous (ok:true)", async () => {
    const launchBtn = await renderAndApprove(async () => makeSyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_SUCCESS_HEADLINE)).not.toBeNull());

    expect(pollMock).not.toHaveBeenCalled();
  });

  it("shows 'Start over' button in failed state so user can retry from scratch", async () => {
    pollMock.mockResolvedValueOnce(makeRun("failed", "opencode:runner_error"));

    const launchBtn = await renderAndApprove(async () => makeAsyncLaunch());
    fireEvent.click(launchBtn);

    await waitFor(() => expect(screen.queryByText(OPENCODE_BUILD_FAILURE_HEADLINE)).not.toBeNull());

    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  });
});

describe("normieFailMessageForOpencode", () => {
  it("returns normie copy for all known terminal failure status_reasons", () => {
    const knownFailureReasons = [
      "opencode:timeout",
      "opencode:session_no_completion",
      "opencode:runner_error",
      "opencode:permission_denied",
      "opencode:output_requires_review",
      "opencode:workspace_setup_failed",
      "opencode:serve_unavailable",
      "opencode:provider_not_configured",
    ];
    for (const reason of knownFailureReasons) {
      const msg = normieFailMessageForOpencode(reason);
      expect(msg, `${reason} should have a normie message`).not.toBeNull();
      const lower = msg!.toLowerCase();
      expect(lower).not.toContain("opencode:");
      expect(lower).not.toContain("asyncio");
      expect(lower).not.toContain("traceback");
    }
  });

  it("returns null for unknown or null reason", () => {
    expect(normieFailMessageForOpencode(null)).toBeNull();
    expect(normieFailMessageForOpencode(undefined)).toBeNull();
    expect(normieFailMessageForOpencode("unknown:reason")).toBeNull();
  });
});
