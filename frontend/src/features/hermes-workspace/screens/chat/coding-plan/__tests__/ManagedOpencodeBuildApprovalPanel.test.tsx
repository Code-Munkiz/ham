import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ManagedOpencodeBuildApprovalPanel } from "../ManagedOpencodeBuildApprovalPanel";
import { FORBIDDEN_CARD_TOKENS } from "../codingPlanCardCopy";
import type { OpencodeBuildLaunchPayload, OpencodeBuildPreviewPayload } from "@/lib/ham/api";

vi.mock("@/lib/ham/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/api")>("@/lib/ham/api");
  return {
    ...actual,
    previewOpencodeBuild: vi.fn(),
    launchOpencodeBuild: vi.fn(),
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

const previewMock = api.previewOpencodeBuild as unknown as ReturnType<typeof vi.fn>;
const launchMock = api.launchOpencodeBuild as unknown as ReturnType<typeof vi.fn>;

const EXTRA_BANNED = [
  "opencode_cli",
  "factory_droid",
  "output_target",
  "controlplanerun",
  "/api/",
  "ham_opencode_exec_token",
];

function makePreview(over: Partial<OpencodeBuildPreviewPayload> = {}): OpencodeBuildPreviewPayload {
  return {
    kind: "opencode_build_preview",
    project_id: "project.opencode-scoped",
    project_name: "Honey Ham",
    user_prompt: "Tidy README typos.",
    model: null,
    summary: "OpenCode will edit the project in a managed workspace.",
    proposal_digest: "a".repeat(64),
    base_revision: "opencode-v1",
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
    ...over,
  };
}

function makeLaunch(over: Partial<OpencodeBuildLaunchPayload> = {}): OpencodeBuildLaunchPayload {
  return {
    kind: "opencode_build_launch",
    project_id: "project.opencode-scoped",
    ok: true,
    ham_run_id: "11111111-2222-3333-4444-555555555555",
    control_plane_status: "succeeded",
    summary: "Snapshot captured.",
    error_summary: null,
    is_readonly: false,
    will_open_pull_request: false,
    requires_approval: true,
    output_target: "managed_workspace",
    output_ref: {
      snapshot_id: "snap_oc_abc",
      preview_url: "https://snapshots.example.test/p/oc",
      changed_paths_count: 2,
      neutral_outcome: "snapshot_published",
    },
    ...over,
  };
}

function assertNoBannedTokens(root: HTMLElement) {
  const blob = (root.textContent || "").toLowerCase();
  for (const token of FORBIDDEN_CARD_TOKENS) {
    expect(blob, `panel leaks ${token}`).not.toContain(token);
  }
  for (const token of EXTRA_BANNED) {
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

describe("ManagedOpencodeBuildApprovalPanel", () => {
  it("renders idle state with preview CTA", () => {
    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );
    expect(
      container.querySelector('[data-hww-coding-plan="opencode-build-approval"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-hww-coding-plan="opencode-build-preview-cta"]'),
    ).not.toBeNull();
  });

  it("preview button is disabled when prompt is empty", () => {
    render(<ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="" />);
    const btn = screen.getByRole("button", { name: /^preview$/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls preview endpoint with composer project id and trimmed prompt", async () => {
    previewMock.mockResolvedValueOnce(makePreview({ project_id: "project.opencode-scoped" }));

    render(
      <ManagedOpencodeBuildApprovalPanel
        projectId="project.opencode-scoped"
        userPrompt=" Wire tests. "
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));

    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));
    expect(previewMock.mock.calls[0]?.[0]).toMatchObject({
      project_id: "project.opencode-scoped",
      user_prompt: "Wire tests.",
    });
  });

  it("launch button stays disabled until preview succeeds AND checkbox is ticked", async () => {
    previewMock.mockResolvedValueOnce(makePreview());

    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));

    const launchBtn = (await screen.findByRole("button", {
      name: /approve and build/i,
    })) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(true);
    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("0");

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    expect(launchBtn.disabled).toBe(false);
    expect(launchBtn.getAttribute("data-launch-enabled")).toBe("1");
  });

  it("renders snapshot success fields after launch ok", async () => {
    previewMock.mockResolvedValueOnce(makePreview());
    launchMock.mockResolvedValueOnce(makeLaunch());

    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /approve and build/i }));
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));

    expect(screen.getByText("Saved version created")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Preview" })).toHaveAttribute(
      "href",
      "https://snapshots.example.test/p/oc",
    );
    expect(screen.getByRole("link", { name: "View changes" })).toHaveAttribute(
      "href",
      "https://snapshots.example.test/p/oc",
    );

    const launchArgs = launchMock.mock.calls[0]![0]!;
    expect(launchArgs).toMatchObject({
      project_id: "project.opencode-scoped",
      user_prompt: "Tidy README typos.",
      proposal_digest: "a".repeat(64),
      base_revision: "opencode-v1",
      confirmed: true,
    });
    expect(Object.prototype.hasOwnProperty.call(launchArgs, "accept_pr")).toBe(false);

    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="opencode-build-snapshot-id"]'),
      ).not.toBeNull(),
    );
    const snap = container.querySelector(
      '[data-hww-coding-plan="opencode-build-snapshot-id"]',
    )!.textContent;
    expect(snap).toContain("snap_oc_abc");
    expect(
      container.querySelector('[data-hww-coding-plan="opencode-build-changed-count"]')!.textContent,
    ).toContain("2 files changed");

    expect(screen.getByRole("button", { name: /keep building/i })).toBeTruthy();

    assertNoBannedTokens(container as unknown as HTMLElement);

    const blob = (container.textContent || "").toLowerCase();
    expect(blob).not.toContain("pull request you review");
    expect(blob).not.toContain("github.com");
  });

  it("renders failure state on launch ok=false (safe-block path)", async () => {
    previewMock.mockResolvedValueOnce(makePreview());
    launchMock.mockResolvedValueOnce(
      makeLaunch({
        ok: false,
        output_ref: null,
        control_plane_status: "failed",
        summary: "OpenCode proposed deleting files, so HAM stopped before saving this version.",
        error_summary: "output_requires_review: 1 file would be deleted: README.md",
      }),
    );

    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Trim docs." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /approve and build/i }));
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));

    expect(screen.getByText(/Build did not complete/i)).toBeTruthy();
    expect(
      container.querySelector('[data-hww-coding-plan="opencode-build-success-actions"]'),
    ).toBeNull();
    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  });

  it("surfaces friendly error when preview API throws", async () => {
    previewMock.mockRejectedValueOnce(new Error("HAM_PERMISSION_DENIED"));

    render(<ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />);

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));

    await waitFor(() => expect(screen.getByText(/HAM_PERMISSION_DENIED/)).toBeTruthy());
    expect(screen.getByRole("button", { name: /start over/i })).toBeTruthy();
  });

  it("reset returns the panel to idle", async () => {
    previewMock.mockResolvedValueOnce(makePreview());
    launchMock.mockResolvedValueOnce(makeLaunch());

    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Tidy README." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));

    const checkbox = container.querySelector(
      '[data-hww-coding-plan="opencode-build-approve-checkbox"] input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: /approve and build/i }));
    await waitFor(() => expect(launchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: /keep building/i }));
    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="opencode-build-preview-cta"]'),
      ).not.toBeNull(),
    );
  });

  it("test-id prefix is opencode-build everywhere", async () => {
    previewMock.mockResolvedValueOnce(makePreview());

    const { container } = render(
      <ManagedOpencodeBuildApprovalPanel projectId="p1" userPrompt="Hi." />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));
    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="opencode-build-approve-checkbox"]'),
      ).not.toBeNull(),
    );

    const all = Array.from(container.querySelectorAll("[data-hww-coding-plan]"));
    for (const el of all) {
      const v = el.getAttribute("data-hww-coding-plan") || "";
      expect(v.startsWith("opencode-build")).toBe(true);
    }
  });
});
