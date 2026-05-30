/**
 * Phase 4 cleanup guards for the right-pane approval/status/result relocation.
 *
 * Locks the cleanup contract once the approval engine has moved to the right
 * pane:
 *  - the chat strip no longer mounts the full approval engine or any
 *    running/success/failure result UI (VAL-CLEAN-001);
 *  - CodingPlanCard, if rendered, is a minimal pointer with no approve
 *    checkbox and no launch CTA (VAL-CLEAN-002);
 *  - a no-internals leakage guard covers the relocated right-pane surface
 *    across its states (architecture §6 / FORBIDDEN_BUILD_REGISTRY_TOKENS)
 *    (VAL-CLEAN-003);
 *  - the completion checkpoint doc exists and summarizes the required points
 *    (VAL-CLEAN-005).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
} from "@/lib/ham/api";

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
const pollMock = api.fetchControlPlaneRun as unknown as ReturnType<typeof vi.fn>;

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

// Mirror of FORBIDDEN_BUILD_REGISTRY_TOKENS used by the relocated-surface
// suites (WorkspaceWorkbench.test.tsx / WorkbenchManagedApprovalMount.test.tsx)
// — architecture §6 forbidden build-kit internals.
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

function assertNoForbiddenTokens(node: HTMLElement) {
  const blob = (node.textContent || "").toLowerCase();
  for (const token of FORBIDDEN_CARD_TOKENS) {
    expect(blob, `relocated surface leaks ${token}`).not.toContain(token);
  }
  for (const token of FORBIDDEN_BUILD_REGISTRY_TOKENS) {
    expect(blob, `relocated surface leaks build-registry token ${token}`).not.toContain(token);
  }
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

function rightPaneRoot(): HTMLElement {
  return document.querySelector('[data-testid="hww-right-pane-approval"]') as HTMLElement;
}

function droidPanel(): HTMLElement {
  return document.querySelector('[data-hww-coding-plan="managed-build-approval"]') as HTMLElement;
}

async function driveDroidToLaunch(launch: DroidBuildLaunchPayload) {
  previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
  launchDroidMock.mockResolvedValueOnce(launch);
  const view = render(
    <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />,
  );

  fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
  await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
  const checkbox = document.querySelector(
    '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
  ) as HTMLInputElement;
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
  await waitFor(() => expect(launchDroidMock).toHaveBeenCalledTimes(1));
  return view;
}

beforeEach(() => {
  previewDroidMock.mockReset();
  launchDroidMock.mockReset();
  pollMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VAL-CLEAN-001: chat no longer duplicates approval/status/result", () => {
  it("does not mount the managed/opencode approval engine in the chat card", () => {
    const { container } = render(
      <CodingPlanCard payload={droidPayload()} userPrompt="Tidy README." />,
    );
    const card = container.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
    expect(card).not.toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();
  });

  it("does not duplicate running/success/failure result UI inside the chat card", () => {
    const { container } = render(
      <CodingPlanCard payload={droidPayload()} userPrompt="Tidy README." />,
    );
    const card = container.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
    for (const sel of [
      "managed-build-success-actions",
      "managed-build-preview-url",
      "managed-build-changed-count",
      "managed-build-error",
      "managed-build-retry",
      "managed-build-done",
      "opencode-build-success-actions",
      "opencode-build-error",
      "opencode-build-retry",
    ]) {
      expect(card.querySelector(`[data-hww-coding-plan="${sel}"]`), `chat leaks ${sel}`).toBeNull();
    }
  });
});

describe("VAL-CLEAN-002: CodingPlanCard is a minimal right-pane pointer only", () => {
  it("renders the pointer copy and no approve checkbox / launch CTA", () => {
    const { container } = render(
      <CodingPlanCard payload={droidPayload()} userPrompt="Tidy README." />,
    );
    const card = container.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
    const pointer = card.querySelector('[data-hww-coding-plan="right-pane-pointer"]');
    expect(pointer).not.toBeNull();
    expect(pointer!.textContent).toContain("Preview is ready on the right");

    // No approval/launch surface survives in chat.
    expect(card.querySelector('input[type="checkbox"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan$="-approve-checkbox"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="launch-cta-disabled"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="no-launch-footer"]')).toBeNull();
    for (const b of Array.from(card.querySelectorAll("button"))) {
      const name = (b.textContent || "").toLowerCase();
      expect(/approve build|prepare build|launch/.test(name)).toBe(false);
    }
  });
});

describe("VAL-CLEAN-003: leakage guard on the relocated right-pane surface", () => {
  it("emits no FORBIDDEN_BUILD_REGISTRY_TOKENS across idle → preview → approve → succeeded", async () => {
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidLaunch());
    const { container } = render(
      <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />,
    );

    // idle
    assertNoForbiddenTokens(rightPaneRoot());

    // previewed
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
    assertNoForbiddenTokens(rightPaneRoot());

    // approved → launching → succeeded
    const checkbox = container.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    assertNoForbiddenTokens(rightPaneRoot());

    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(launchDroidMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());
    assertNoForbiddenTokens(rightPaneRoot());
  });

  it("emits no FORBIDDEN_BUILD_REGISTRY_TOKENS in the recoverable failure state", async () => {
    await driveDroidToLaunch(
      makeDroidLaunch({
        ok: false,
        control_plane_status: null,
        output_ref: null,
        error_summary: "Something interrupted the build. No version was saved.",
      }),
    );
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("failed"));
    assertNoForbiddenTokens(rightPaneRoot());
  });
});

describe("VAL-CLEAN-005: completion checkpoint doc exists and summarizes required points", () => {
  const DOC_PATH = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../../../../../../docs/build-kit-registry-v2/RIGHT_PANE_APPROVAL_STATUS_COMPLETION_CHECKPOINT.md",
  );

  it("the checkpoint markdown file exists", () => {
    expect(fs.existsSync(DOC_PATH)).toBe(true);
  });

  it("references every required summary point", () => {
    const text = fs.readFileSync(DOC_PATH, "utf8").toLowerCase();
    const required = [
      "status shell",
      "approval relocated",
      "result",
      "actions consolidated",
      "chat cleaned up",
      "preserved",
      "proposal_digest",
      "base_revision",
      "builder studio",
      "build-kit internals",
      "tests",
      "claude",
      "cursor",
      "follow-up",
    ];
    for (const phrase of required) {
      expect(text, `checkpoint doc is missing "${phrase}"`).toContain(phrase);
    }
  });
});
