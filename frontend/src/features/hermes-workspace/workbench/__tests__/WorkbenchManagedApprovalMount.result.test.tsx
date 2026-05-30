/**
 * Result / status / action consolidation in the right pane (Milestone 2).
 *
 * The managed build approval engine (relocated into the workbench right pane
 * via WorkbenchManagedApprovalMount) already owns the SuccessSummary +
 * failed/startOver result surface. These tests lock the consolidation
 * contract: the succeeded and failed lifecycle, the open + revise/retry
 * actions, the SmokePreflightError + OpenCode normie failure mapping, the full
 * preview→approval→building→completed lifecycle and the failure→retry loop —
 * all in the right-pane subtree, with chat holding only a concise pointer (no
 * duplicated result dashboard, no second approve/launch control) and no
 * Builder Studio task-launch surface.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorkbenchManagedApprovalMount } from "../WorkbenchManagedApprovalMount";
import { CodingPlanCard } from "@/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard";
import {
  FORBIDDEN_CARD_TOKENS,
  normieFailMessageForOpencode,
} from "@/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy";
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
import {
  assertManagedBuildSmokePreflight,
  SmokePreflightError,
} from "@/lib/ham/managedBuildSmokePreflight";

const previewDroidMock = api.previewDroidBuild as unknown as ReturnType<typeof vi.fn>;
const launchDroidMock = api.launchDroidBuild as unknown as ReturnType<typeof vi.fn>;
const previewOpencodeMock = api.previewOpencodeBuild as unknown as ReturnType<typeof vi.fn>;
const launchOpencodeMock = api.launchOpencodeBuild as unknown as ReturnType<typeof vi.fn>;
const pollMock = api.fetchControlPlaneRun as unknown as ReturnType<typeof vi.fn>;
const preflightMock = assertManagedBuildSmokePreflight as unknown as ReturnType<typeof vi.fn>;

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const PREVIEW_URL = "https://snapshots.example.test/p/abc";

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

/** Every data-hww-coding-plan node the SuccessSummary / panel is allowed to expose. */
const ALLOWED_SUCCESS_NODES = new Set([
  "managed-build-approval",
  "managed-build-headline",
  "managed-build-success-actions",
  "managed-build-preview-url",
  "managed-build-view-changes-url",
  "managed-build-changed-count",
  "managed-build-technical-details",
  "managed-build-snapshot-id",
  "managed-build-neutral-outcome",
  "managed-build-done",
]);

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
      preview_url: PREVIEW_URL,
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

function chatCardRoot(scope: HTMLElement): HTMLElement {
  return scope.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
}

function droidPanel(): HTMLElement {
  return document.querySelector('[data-hww-coding-plan="managed-build-approval"]') as HTMLElement;
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

/** Drive the right-pane Droid panel preview→approve→launch with the supplied launch payload. */
async function driveDroidToLaunch(launch: DroidBuildLaunchPayload, prompt = "Tidy README.") {
  previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
  launchDroidMock.mockResolvedValueOnce(launch);
  const view = render(
    <WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt={prompt} />,
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
  previewOpencodeMock.mockReset();
  launchOpencodeMock.mockReset();
  pollMock.mockReset();
  preflightMock.mockReset();
  preflightMock.mockResolvedValue({
    host: "ham-test.vercel.app",
    statusUrl: "https://ham-test.vercel.app/api/status",
    version: "0.1.0",
    runCount: 0,
    traceContext: "test;o=1",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Result consolidation — succeeded state (VAL-RESULT-001/002/003/008)", () => {
  it("VAL-RESULT-001: succeeded renders in the right pane reusing SuccessSummary", async () => {
    await driveDroidToLaunch(makeDroidLaunch());
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());

    const panel = droidPanel();
    expect(panel).not.toBeNull();
    expect(panel.getAttribute("data-phase")).toBe("succeeded");
    // The success surface is the reused SuccessSummary, inside the right pane.
    const root = rightPaneRoot();
    expect(root).not.toBeNull();
    expect(
      root.querySelector('[data-hww-coding-plan="managed-build-success-actions"]'),
    ).not.toBeNull();
    expect(root.contains(panel)).toBe(true);
  });

  it("VAL-RESULT-002: succeeded exposes open (preview link) + revise/retry (Keep building reset)", async () => {
    await driveDroidToLaunch(makeDroidLaunch());
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());

    const previewLink = droidPanel().querySelector(
      '[data-hww-coding-plan="managed-build-preview-url"]',
    ) as HTMLAnchorElement;
    expect(previewLink).not.toBeNull();
    expect(previewLink.getAttribute("href")).toBe(PREVIEW_URL);

    // "Keep building" resets the panel back to idle (revise/retry affordance).
    const keepBuilding = screen.getByRole("button", { name: /keep building/i });
    fireEvent.click(keepBuilding);
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("idle"));
    expect(screen.getByRole("button", { name: /prepare build/i })).toBeTruthy();
  });

  it("VAL-RESULT-003: succeeded exposes only known SuccessSummary action nodes (no new mechanics)", async () => {
    await driveDroidToLaunch(makeDroidLaunch());
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());

    const nodes = Array.from(
      droidPanel().querySelectorAll<HTMLElement>("[data-hww-coding-plan]"),
    ).map((el) => el.getAttribute("data-hww-coding-plan"));
    expect(nodes.length).toBeGreaterThan(0);
    for (const name of nodes) {
      expect(ALLOWED_SUCCESS_NODES.has(name ?? ""), `unexpected success node ${name}`).toBe(true);
    }
    // No approve/launch control survives into the succeeded state.
    expect(
      droidPanel().querySelector('[data-hww-coding-plan="managed-build-launch-cta"]'),
    ).toBeNull();
    expect(
      droidPanel().querySelector('[data-hww-coding-plan="managed-build-approve-checkbox"]'),
    ).toBeNull();
  });

  it("VAL-RESULT-008: succeeded copy leaks no build-kit/provider internals", async () => {
    await driveDroidToLaunch(makeDroidLaunch());
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());
    assertNoForbiddenTokens(rightPaneRoot());
  });
});

describe("Result consolidation — recoverable failure (VAL-RESULT-004/005/006/008)", () => {
  it("VAL-RESULT-004: recoverable launch failure renders plain-language message + Start over retry", async () => {
    await driveDroidToLaunch(
      makeDroidLaunch({
        ok: false,
        control_plane_status: null,
        output_ref: null,
        error_summary: "Something interrupted the build. No version was saved.",
      }),
    );
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("failed"));

    const errorNode = droidPanel().querySelector(
      '[data-hww-coding-plan="managed-build-error"]',
    ) as HTMLElement;
    expect(errorNode).not.toBeNull();
    expect((errorNode.textContent || "").trim().length).toBeGreaterThan(0);

    const retry = screen.getByRole("button", { name: /start over/i });
    fireEvent.click(retry);
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("idle"));
    assertNoForbiddenTokens(rightPaneRoot());
  });

  it("VAL-RESULT-005: SmokePreflightError surfaces friendly `${code}: ${message}` + Start over", async () => {
    preflightMock.mockReset();
    preflightMock.mockRejectedValueOnce(
      new SmokePreflightError(
        "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED",
        "The HAM backend could not be reached from this page.",
      ),
    );
    render(<WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />);

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("failed"));

    const errorNode = droidPanel().querySelector(
      '[data-hww-coding-plan="managed-build-error"]',
    ) as HTMLElement;
    expect(errorNode.textContent).toContain(
      "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED: The HAM backend could not be reached from this page.",
    );
    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  });

  it("VAL-RESULT-006: OpenCode poll→failed renders normie mapping, hides raw internals", async () => {
    previewOpencodeMock.mockResolvedValueOnce(makeOpencodePreview());
    launchOpencodeMock.mockResolvedValueOnce(makeOpencodeAsyncLaunch());
    pollMock.mockResolvedValue(
      makeRun("failed", "opencode:timeout", {
        error_summary: "internal: asyncio.TimeoutError after 270s",
      }),
    );

    render(
      <WorkbenchManagedApprovalMount
        payload={opencodePayload()}
        userPrompt="Add a docstring to main."
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewOpencodeMock).toHaveBeenCalledTimes(1));
    const checkbox = document.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    const normie = normieFailMessageForOpencode("opencode:timeout");
    expect(normie).not.toBeNull();
    await waitFor(() => expect(screen.queryByText(normie!)).not.toBeNull(), { timeout: 7000 });

    const oc = document.querySelector(
      '[data-hww-coding-plan="opencode-build-approval"]',
    ) as HTMLElement;
    expect(oc.getAttribute("data-phase")).toBe("failed");
    const blob = (oc.textContent || "").toLowerCase();
    expect(blob).not.toContain("asyncio");
    expect(blob).not.toContain("internal:");
    expect(blob).not.toContain("opencode:");
  }, 12000);
});

describe("Chat outcome summary only — no result dashboard duplicated (VAL-RESULT-007)", () => {
  it("VAL-RESULT-007: after success in the right pane, chat shows a concise pointer and no SuccessSummary nodes", async () => {
    const payload = droidPayload();
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(makeDroidLaunch());
    const { container } = render(
      <>
        <CodingPlanCard payload={payload} userPrompt="Tidy README." />
        <WorkbenchManagedApprovalMount payload={payload} userPrompt="Tidy README." />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(previewDroidMock).toHaveBeenCalledTimes(1));
    const checkbox = document.querySelector(
      '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());

    const card = chatCardRoot(container);
    expect(card).not.toBeNull();
    // Concise pointer only.
    expect(card.textContent).toContain("Preview is ready on the right");
    // No SuccessSummary surface duplicated in chat.
    expect(card.querySelector('[data-hww-coding-plan="managed-build-success-actions"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="managed-build-preview-url"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="managed-build-changed-count"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
  });
});

describe("Cross-area lifecycle flows (VAL-CROSS-001..004)", () => {
  it("VAL-CROSS-001: full lifecycle idle→previewed→running→succeeded plays out in the right pane", async () => {
    const payload = opencodePayload();
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
      <>
        <CodingPlanCard payload={payload} userPrompt="Add a docstring to main." />
        <WorkbenchManagedApprovalMount payload={payload} userPrompt="Add a docstring to main." />
      </>,
    );
    const oc = () =>
      document.querySelector('[data-hww-coding-plan="opencode-build-approval"]') as HTMLElement;

    expect(oc().getAttribute("data-phase")).toBe("idle");

    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(oc().getAttribute("data-phase")).toBe("previewed"));

    const checkbox = document.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));

    await waitFor(() => expect(oc().getAttribute("data-phase")).toBe("running"));
    await waitFor(() => expect(oc().getAttribute("data-phase")).toBe("succeeded"), {
      timeout: 7000,
    });
    expect(screen.queryByText("Saved version created")).not.toBeNull();

    // Every phase node lived in the right pane; chat only ever had the pointer.
    expect(rightPaneRoot().contains(oc())).toBe(true);
    const card = chatCardRoot(container);
    expect(card.textContent).toContain("Preview is ready on the right");
    expect(card.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();
  }, 12000);

  it("VAL-CROSS-002: failure→retry loop (failed→idle→previewed) works through the right pane", async () => {
    previewDroidMock.mockResolvedValue(makeDroidPreview());
    launchDroidMock.mockResolvedValueOnce(
      makeDroidLaunch({
        ok: false,
        control_plane_status: null,
        output_ref: null,
        error_summary: "The build did not complete.",
      }),
    );
    render(<WorkbenchManagedApprovalMount payload={droidPayload()} userPrompt="Tidy README." />);

    // preview → approve → launch (fails)
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("previewed"));
    fireEvent.click(
      document.querySelector(
        '[data-hww-coding-plan="managed-build-approve-checkbox"] input[type="checkbox"]',
      ) as HTMLInputElement,
    );
    fireEvent.click(screen.getByRole("button", { name: /approve build/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("failed"));

    // Start over → idle
    fireEvent.click(screen.getByRole("button", { name: /start over/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("idle"));

    // Prepare build again → previewed (recovers entirely in the right pane)
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("previewed"));
    expect(previewDroidMock).toHaveBeenCalledTimes(2);
  });

  it("VAL-CROSS-003: single source of truth — ≤1 approve checkbox/launch CTA, right pane only", async () => {
    const payload = droidPayload();
    previewDroidMock.mockResolvedValueOnce(makeDroidPreview());
    const { container } = render(
      <>
        <CodingPlanCard payload={payload} userPrompt="Tidy README." />
        <WorkbenchManagedApprovalMount payload={payload} userPrompt="Tidy README." />
      </>,
    );

    const card = chatCardRoot(container);

    const countCheckbox = () =>
      document.querySelectorAll('[data-hww-coding-plan$="-approve-checkbox"]').length;
    const countLaunch = () =>
      document.querySelectorAll('[data-hww-coding-plan$="-launch-cta"]').length;

    // idle phase
    expect(countCheckbox()).toBeLessThanOrEqual(1);
    expect(countLaunch()).toBeLessThanOrEqual(1);

    // previewed phase: exactly the single right-pane controls, none in chat
    fireEvent.click(screen.getByRole("button", { name: /prepare build/i }));
    await waitFor(() => expect(droidPanel().getAttribute("data-phase")).toBe("previewed"));
    expect(countCheckbox()).toBe(1);
    expect(countLaunch()).toBe(1);
    expect(card.querySelector('[data-hww-coding-plan$="-approve-checkbox"]')).toBeNull();
    expect(card.querySelector('[data-hww-coding-plan$="-launch-cta"]')).toBeNull();
    expect(
      rightPaneRoot().querySelector('[data-hww-coding-plan="managed-build-approve-checkbox"]'),
    ).not.toBeNull();
    // Exactly one approval panel root document-wide.
    expect(document.querySelectorAll('[data-hww-coding-plan$="-approval"]').length).toBe(1);
  });

  it("VAL-CROSS-004: no Builder Studio task-launch surface in the relocated flow", async () => {
    await driveDroidToLaunch(makeDroidLaunch());
    await waitFor(() => expect(screen.queryByText("Saved version created")).not.toBeNull());

    const root = rightPaneRoot();
    expect((root.textContent || "").toLowerCase()).not.toContain("builder studio");
    expect(root.querySelector('[data-testid*="builder-studio"]')).toBeNull();
    expect(
      screen.queryByRole("button", { name: /builder studio|launch task|start task/i }),
    ).toBeNull();
  });
});
