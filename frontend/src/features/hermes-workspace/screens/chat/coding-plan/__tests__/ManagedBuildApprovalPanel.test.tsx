import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CodingPlanCard } from "../CodingPlanCard";
import { ManagedBuildApprovalPanel } from "../ManagedBuildApprovalPanel";
import { FORBIDDEN_CARD_TOKENS } from "../codingPlanCardCopy";
import type {
  CodingConductorCandidate,
  CodingConductorPreviewPayload,
  DroidBuildLaunchPayload,
  DroidBuildPreviewPayload,
} from "@/lib/ham/api";

vi.mock("@/lib/ham/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/api")>("@/lib/ham/api");
  return {
    ...actual,
    previewDroidBuild: vi.fn(),
    launchDroidBuild: vi.fn(),
  };
});

vi.mock("@/lib/ham/managedBuildSmokePreflight", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/managedBuildSmokePreflight")>(
    "@/lib/ham/managedBuildSmokePreflight",
  );
  return {
    ...actual,
    assertManagedBuildSmokePreflight: vi.fn(async () => ({
      host: "ham-nine-mu.vercel.app",
      statusUrl: "https://ham-nine-mu.vercel.app/api/status",
      version: "0.1.0",
      runCount: 0,
      traceContext: "test-trace;o=1",
    })),
  };
});

import * as api from "@/lib/ham/api";

const previewMock = api.previewDroidBuild as unknown as ReturnType<typeof vi.fn>;
const launchMock = api.launchDroidBuild as unknown as ReturnType<typeof vi.fn>;

function makePreview(over: Partial<DroidBuildPreviewPayload> = {}): DroidBuildPreviewPayload {
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

function makeLaunch(over: Partial<DroidBuildLaunchPayload> = {}): DroidBuildLaunchPayload {
  return {
    kind: "droid_build_launch",
    project_id: "project.app-f53b52",
    ok: true,
    ham_run_id: "11111111-2222-3333-4444-555555555555",
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

function managedConductorPayload(): CodingConductorPreviewPayload {
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

function assertNoForbiddenTokens(root: HTMLElement) {
  const blob = (root.textContent || "").toLowerCase();
  for (const token of FORBIDDEN_CARD_TOKENS) {
    expect(blob, `panel leaks ${token}`).not.toContain(token);
  }
}

beforeEach(() => {
  previewMock.mockReset();
  launchMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CodingPlanCard managed workspace branch", () => {
  it("does NOT render the managed panel when output_target is github_pr", () => {
    const p = managedConductorPayload();
    p.project.output_target = "github_pr";
    p.project.has_github_repo = true;
    p.project.has_workspace_id = false;
    const { container } = render(<CodingPlanCard payload={p} userPrompt="x" />);
    expect(container.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
    expect(container.querySelector('[data-hww-coding-plan="launch-cta-disabled"]')).not.toBeNull();
  });

  it("does NOT render the managed panel when chosen provider is not factory_droid_build", () => {
    const p = managedConductorPayload();
    p.chosen = candidate({ provider: "cursor_cloud", will_open_pull_request: true });
    p.candidates = [p.chosen];
    const { container } = render(<CodingPlanCard payload={p} userPrompt="x" />);
    expect(container.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
  });

  it("renders the managed panel for managed_workspace factory_droid_build", () => {
    const p = managedConductorPayload();
    const { container } = render(<CodingPlanCard payload={p} userPrompt="Tidy docs" />);
    expect(
      container.querySelector('[data-hww-coding-plan="managed-build-approval"]'),
    ).not.toBeNull();
    expect(container.querySelector('[data-hww-coding-plan="launch-cta-disabled"]')).toBeNull();
    assertNoForbiddenTokens(container as unknown as HTMLElement);
  });
});

describe("ManagedBuildApprovalPanel", () => {
  it("preview button is disabled when prompt is empty", () => {
    render(<ManagedBuildApprovalPanel projectId="p1" userPrompt="" />);
    const btn = screen.getByRole("button", { name: /preview this build/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls preview endpoint with composer project id and prompt", async () => {
    previewMock.mockResolvedValueOnce(makePreview({ project_id: "project.scoped-chat" }));

    render(
      <ManagedBuildApprovalPanel projectId="project.scoped-chat" userPrompt=" Wire tests. " />,
    );

    fireEvent.click(screen.getByRole("button", { name: /preview this build/i }));

    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));
    expect(previewMock.mock.calls[0]?.[0]).toMatchObject({
      project_id: "project.scoped-chat",
      user_prompt: "Wire tests.",
    });
  });

  it("launch button stays disabled until preview succeeds AND checkbox is ticked", async () => {
    previewMock.mockResolvedValueOnce(makePreview());

    const { container } = render(
      <ManagedBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /preview this build/i }));

    await waitFor(() => {
      expect(previewMock).toHaveBeenCalledTimes(1);
    });

    const launchBtn = (await screen.findByRole("button", {
      name: /approve and build/i,
    })) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(true);
    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("0");

    // Tick the approval checkbox.
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    expect(launchBtn.disabled).toBe(false);
    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("1");
  });

  it("renders snapshot success fields after launch ok", async () => {
    previewMock.mockResolvedValueOnce(makePreview());
    launchMock.mockResolvedValueOnce(makeLaunch());

    const { container } = render(
      <ManagedBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /preview this build/i }));
    await waitFor(() => {
      expect(previewMock).toHaveBeenCalledTimes(1);
    });
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /approve and build/i }));

    await waitFor(() => {
      expect(launchMock).toHaveBeenCalledTimes(1);
    });

    // Launch payload must use the previewed digest + accept_pr=true (back-compat).
    const launchArgs = launchMock.mock.calls[0]![0]!;
    expect(launchArgs).toMatchObject({
      project_id: "project.app-f53b52",
      user_prompt: "Tidy README typos.",
      proposal_digest: "a".repeat(64),
      base_revision: "rev-test",
      confirmed: true,
      accept_pr: true,
    });

    await waitFor(() => {
      expect(
        container.querySelector('[data-hww-coding-plan="managed-build-snapshot-id"]'),
      ).not.toBeNull();
    });
    const snap = container.querySelector(
      '[data-hww-coding-plan="managed-build-snapshot-id"]',
    )!.textContent;
    expect(snap).toContain("snap_abc");
    expect(
      container
        .querySelector('[data-hww-coding-plan="managed-build-preview-url"]')!
        .querySelector("a")!
        .getAttribute("href"),
    ).toBe("https://snapshots.example.test/p/abc");
    expect(
      container.querySelector('[data-hww-coding-plan="managed-build-changed-count"]')!.textContent,
    ).toContain("3");

    assertNoForbiddenTokens(container as unknown as HTMLElement);

    // No GitHub PR copy on the managed success path.
    const blob = (container.textContent || "").toLowerCase();
    expect(blob).not.toContain("pull request you review");
    expect(blob).not.toContain("github.com");
  });

  it("surfaces friendly error when preview API throws", async () => {
    previewMock.mockRejectedValueOnce(new Error("HAM_PERMISSION_DENIED"));

    render(<ManagedBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />);

    fireEvent.click(screen.getByRole("button", { name: /preview this build/i }));

    await waitFor(() => {
      expect(screen.getByText(/HAM_PERMISSION_DENIED/)).toBeTruthy();
    });
    // Retry CTA appears.
    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  });
});
