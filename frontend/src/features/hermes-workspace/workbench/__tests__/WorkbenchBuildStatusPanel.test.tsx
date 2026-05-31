import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { FORBIDDEN_USER_COPY_PATTERN } from "@/lib/ham/workbenchPreviewMessages";
import {
  WorkbenchBuildStatusPanel,
  buildStatusFromGenerationPhase,
  buildStatusFromManagedPhase,
  type WorkbenchBuildStatusValue,
} from "../WorkbenchBuildStatusPanel";

const ALLOWED_COPY = [
  "Preparing preview…",
  "Preview ready",
  "Ready to build",
  "Building…",
  "Preview updated",
  "Build completed",
  "Checking latest status…",
  "Something needs attention",
] as const;

const STATE_COPY: Array<[WorkbenchBuildStatusValue, (typeof ALLOWED_COPY)[number]]> = [
  ["preparing-preview", "Preparing preview…"],
  ["preview-ready", "Preview ready"],
  ["ready-to-build", "Ready to build"],
  ["building", "Building…"],
  ["preview-updated", "Preview updated"],
  ["build-completed", "Build completed"],
  ["checking", "Checking latest status…"],
  ["attention", "Something needs attention"],
];

// Mirror of FORBIDDEN_BUILD_REGISTRY_TOKENS used by WorkspaceWorkbench.test.tsx.
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

describe("WorkbenchBuildStatusPanel", () => {
  it("renders a single build-status shell with a stable test id", () => {
    render(<WorkbenchBuildStatusPanel status="ready-to-build" />);
    expect(screen.getAllByTestId("hww-build-status-shell")).toHaveLength(1);
  });

  it("shows 'Preview ready' for the preview-ready state", () => {
    render(<WorkbenchBuildStatusPanel status="preview-ready" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent("Preview ready");
  });

  it("shows 'Ready to build' for the ready-to-build state", () => {
    render(<WorkbenchBuildStatusPanel status="ready-to-build" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent("Ready to build");
  });

  it("shows 'Building…' for the building state", () => {
    render(<WorkbenchBuildStatusPanel status="building" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent("Building…");
  });

  it("shows 'Preview updated' for the preview-updated state", () => {
    render(<WorkbenchBuildStatusPanel status="preview-updated" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent("Preview updated");
  });

  it("shows 'Build completed' for the completed state", () => {
    render(<WorkbenchBuildStatusPanel status="build-completed" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent("Build completed");
  });

  it("shows 'Something needs attention' for the attention state", () => {
    render(<WorkbenchBuildStatusPanel status="attention" />);
    expect(screen.getByTestId("hww-build-status-shell")).toHaveTextContent(
      "Something needs attention",
    );
  });

  it("renders exactly one allowed lifecycle phrase per state and nothing outside the set", () => {
    for (const [status, copy] of STATE_COPY) {
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status} />);
      const shell = screen.getByTestId("hww-build-status-shell");
      const text = shell.textContent ?? "";
      expect(text).toContain(copy);
      for (const other of ALLOWED_COPY) {
        if (other !== copy) {
          expect(text).not.toContain(other);
        }
      }
      unmount();
    }
  });

  it("is presentational — no approve/prepare/launch controls", () => {
    for (const [status] of STATE_COPY) {
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status} />);
      const shell = screen.getByTestId("hww-build-status-shell");
      expect(within(shell).queryByRole("button")).toBeNull();
      expect(within(shell).queryByRole("checkbox")).toBeNull();
      expect(
        within(shell).queryByRole("button", { name: /approve|prepare build|launch/i }),
      ).toBeNull();
      unmount();
    }
  });

  it("does not nest a managed approval panel root", () => {
    for (const [status] of STATE_COPY) {
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status} />);
      const shell = screen.getByTestId("hww-build-status-shell");
      expect(shell.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
      expect(shell.querySelector('[data-hww-coding-plan="opencode-build-approval"]')).toBeNull();
      unmount();
    }
  });

  it("never leaks build-registry internals in any state", () => {
    for (const [status] of STATE_COPY) {
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status} />);
      const text = (screen.getByTestId("hww-build-status-shell").textContent ?? "").toLowerCase();
      for (const token of FORBIDDEN_BUILD_REGISTRY_TOKENS) {
        expect(text).not.toContain(token);
      }
      unmount();
    }
  });

  it("never matches the forbidden runner/infra copy pattern in any state", () => {
    for (const [status] of STATE_COPY) {
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status} />);
      const text = screen.getByTestId("hww-build-status-shell").textContent ?? "";
      expect(FORBIDDEN_USER_COPY_PATTERN.test(text)).toBe(false);
      unmount();
    }
  });
});

describe("buildStatusFromManagedPhase", () => {
  it("maps the managed build lifecycle to plain-language status values", () => {
    expect(buildStatusFromManagedPhase("previewing")).toBe("preparing-preview");
    expect(buildStatusFromManagedPhase("previewed")).toBe("preview-ready");
    expect(buildStatusFromManagedPhase("launching")).toBe("building");
    expect(buildStatusFromManagedPhase("running")).toBe("building");
    expect(buildStatusFromManagedPhase("succeeded")).toBe("build-completed");
    expect(buildStatusFromManagedPhase("failed")).toBe("attention");
  });

  it("returns null for idle so the preview-iframe phase remains the source of truth", () => {
    expect(buildStatusFromManagedPhase("idle")).toBeNull();
  });

  it("every non-idle phase renders an allowed plain-language phrase", () => {
    const phases = [
      "previewing",
      "previewed",
      "launching",
      "running",
      "succeeded",
      "failed",
    ] as const;
    for (const phase of phases) {
      const status = buildStatusFromManagedPhase(phase);
      expect(status).not.toBeNull();
      const { unmount } = render(<WorkbenchBuildStatusPanel status={status!} />);
      const text = screen.getByTestId("hww-build-status-shell").textContent ?? "";
      expect(ALLOWED_COPY.some((copy) => text.includes(copy))).toBe(true);
      expect(FORBIDDEN_USER_COPY_PATTERN.test(text)).toBe(false);
      unmount();
    }
  });
});

describe("buildStatusFromGenerationPhase", () => {
  it("maps the Builder Happy Path scaffold lifecycle to plain-language status", () => {
    expect(buildStatusFromGenerationPhase("preparing")).toBe("preparing-preview");
    expect(buildStatusFromGenerationPhase("generating")).toBe("building");
    expect(buildStatusFromGenerationPhase("interrupted")).toBe("checking");
  });

  it("returns null for idle/ready so the preview phase takes over", () => {
    expect(buildStatusFromGenerationPhase("idle")).toBeNull();
    expect(buildStatusFromGenerationPhase("ready")).toBeNull();
  });

  it("interrupted maps to a recoverable status, never the failure 'attention' copy", () => {
    const status = buildStatusFromGenerationPhase("interrupted");
    expect(status).toBe("checking");
    render(<WorkbenchBuildStatusPanel status={status!} />);
    const text = screen.getByTestId("hww-build-status-shell").textContent ?? "";
    expect(text).toContain("Checking latest status…");
    expect(text).not.toContain("Something needs attention");
    expect(FORBIDDEN_USER_COPY_PATTERN.test(text)).toBe(false);
  });
});
