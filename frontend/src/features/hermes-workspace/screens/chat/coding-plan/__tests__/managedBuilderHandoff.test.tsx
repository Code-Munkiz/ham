/**
 * Selected-builder handoff: backend `builder` metadata for a ready managed
 * builder (OpenCode / Factory Droid) is recognized and synthesized into the
 * existing managed-approval payload, which drives the right-pane mount to the
 * matching approval surface. No duplicate approval component; no launch here.
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

import {
  FORBIDDEN_CARD_TOKENS,
  managedHandoffPreviewPayload,
  readManagedBuilderHandoff,
  shouldShowManagedBuildApproval,
  shouldShowOpencodeBuildApproval,
} from "../codingPlanCardCopy";
import { WorkbenchManagedApprovalMount } from "@/features/hermes-workspace/workbench/WorkbenchManagedApprovalMount";

// Mock the launch surface so nothing can hit the network on interaction; the
// idle render under test does not call these.
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

describe("readManagedBuilderHandoff", () => {
  it("returns key + label for a ready OpenCode handoff", () => {
    expect(
      readManagedBuilderHandoff({
        builder_handoff_required: true,
        selected_builder_state: "ready",
        selected_builder_key: "opencode",
        selected_builder_label: "OpenCode",
      }),
    ).toEqual({ key: "opencode", label: "OpenCode" });
  });

  it("returns key + label for a ready Factory Droid handoff", () => {
    expect(
      readManagedBuilderHandoff({
        builder_handoff_required: true,
        selected_builder_state: "ready",
        selected_builder_key: "factory_droid",
        selected_builder_label: "Factory Droid",
      }),
    ).toEqual({ key: "factory_droid", label: "Factory Droid" });
  });

  it("returns null when no handoff is required", () => {
    expect(readManagedBuilderHandoff(null)).toBeNull();
    expect(readManagedBuilderHandoff(undefined)).toBeNull();
    expect(readManagedBuilderHandoff({ selected_builder_state: "choose" })).toBeNull();
  });

  it("returns null for unsupported builders or not-ready states", () => {
    for (const key of ["cursor", "claude", "hermes_agent", "internal_scaffold", "nonsense"]) {
      expect(
        readManagedBuilderHandoff({
          builder_handoff_required: true,
          selected_builder_state: "ready",
          selected_builder_key: key,
        }),
      ).toBeNull();
    }
    expect(
      readManagedBuilderHandoff({
        builder_handoff_required: true,
        selected_builder_state: "setup_required",
        selected_builder_key: "opencode",
      }),
    ).toBeNull();
  });
});

describe("managedHandoffPreviewPayload drives the right managed approval predicate", () => {
  it("OpenCode handoff payload satisfies the OpenCode approval predicate only", () => {
    const payload = managedHandoffPreviewPayload("opencode", "proj.x");
    expect(shouldShowOpencodeBuildApproval(payload)).toBe(true);
    expect(shouldShowManagedBuildApproval(payload)).toBe(false);
    expect(payload.project.project_id).toBe("proj.x");
    expect(payload.project.output_target).toBe("managed_workspace");
  });

  it("Factory Droid handoff payload satisfies the Droid approval predicate only", () => {
    const payload = managedHandoffPreviewPayload("factory_droid", "proj.y");
    expect(shouldShowManagedBuildApproval(payload)).toBe(true);
    expect(shouldShowOpencodeBuildApproval(payload)).toBe(false);
    expect(payload.chosen?.will_open_pull_request).toBe(false);
  });
});

describe("WorkbenchManagedApprovalMount renders the matching surface for a handoff", () => {
  it("opens the OpenCode managed approval panel for an OpenCode handoff", () => {
    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={managedHandoffPreviewPayload("opencode", "proj.x")}
        userPrompt="build me a tetris game"
      />,
    );
    expect(
      container.querySelector('[data-hww-coding-plan="opencode-build-approval"]'),
    ).not.toBeNull();
    expect(container.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
  });

  it("opens the Droid managed approval panel for a Factory Droid handoff", () => {
    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={managedHandoffPreviewPayload("factory_droid", "proj.y")}
        userPrompt="build me a tetris game"
      />,
    );
    expect(
      container.querySelector('[data-hww-coding-plan="managed-build-approval"]'),
    ).not.toBeNull();
    expect(container.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();
  });

  it("does not leak forbidden internals in the rendered surface", () => {
    const { container } = render(
      <WorkbenchManagedApprovalMount
        payload={managedHandoffPreviewPayload("opencode", "proj.x")}
        userPrompt="build me a tetris game"
      />,
    );
    const blob = (container.textContent || "").toLowerCase();
    for (const token of FORBIDDEN_CARD_TOKENS) {
      expect(blob, `right pane leaks ${token}`).not.toContain(token);
    }
  });
});
