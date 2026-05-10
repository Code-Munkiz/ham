import { describe, expect, it } from "vitest";

import {
  CODING_PLAN_NO_LAUNCH_FOOTER,
  FORBIDDEN_CARD_TOKENS,
  approvalCopyForCard,
  confidenceBadgeForCard,
  emptyStateHeadlineForCard,
  isLaunchableInThisPhase,
  outputKindCopyForCard,
  providerLabelForCard,
  taskKindDisplayForCard,
} from "../codingPlanCardCopy";
import type {
  CodingConductorOutputKind,
  CodingConductorPreviewPayload,
  CodingConductorProviderKind,
} from "@/lib/ham/api";

const PROVIDERS: CodingConductorProviderKind[] = [
  "no_agent",
  "factory_droid_audit",
  "factory_droid_build",
  "cursor_cloud",
  "claude_code",
];

const OUTPUTS: CodingConductorOutputKind[] = ["answer", "report", "pull_request", "mission"];

function makePayload(
  overrides: Partial<CodingConductorPreviewPayload> = {},
): CodingConductorPreviewPayload {
  return {
    kind: "coding_conductor_preview",
    preview_id: "preview-fixture",
    task_kind: "explain",
    task_confidence: 0.9,
    chosen: null,
    candidates: [],
    blockers: [],
    recommendation_reason: "fixture reason",
    requires_approval: false,
    approval_kind: "none",
    project: {
      found: false,
      project_id: null,
      build_lane_enabled: false,
      has_github_repo: false,
    },
    is_operator: false,
    ...overrides,
  };
}

describe("codingPlanCardCopy", () => {
  it("returns a non-empty product label for every provider kind", () => {
    for (const p of PROVIDERS) {
      const label = providerLabelForCard(p);
      expect(label.length).toBeGreaterThan(0);
      // The label must never name internal workflow ids or secrets.
      const lower = label.toLowerCase();
      for (const token of FORBIDDEN_CARD_TOKENS) {
        expect(lower).not.toContain(token);
      }
    }
  });

  it("returns user-friendly output-kind copy for every kind", () => {
    for (const k of OUTPUTS) {
      const copy = outputKindCopyForCard(k);
      expect(copy.length).toBeGreaterThan(0);
      expect(copy.toLowerCase()).not.toContain("safe_edit_low");
    }
  });

  it("approvalCopyForCard distinguishes none / confirm / pr-confirm", () => {
    expect(approvalCopyForCard("none")).not.toBe(approvalCopyForCard("confirm"));
    expect(approvalCopyForCard("confirm")).not.toBe(approvalCopyForCard("confirm_and_accept_pr"));
    expect(approvalCopyForCard("confirm_and_accept_pr").toLowerCase()).toContain("pull request");
  });

  it("confidenceBadgeForCard buckets coarsely", () => {
    expect(confidenceBadgeForCard(0.95)).toBe("high");
    expect(confidenceBadgeForCard(0.65)).toBe("medium");
    expect(confidenceBadgeForCard(0.2)).toBe("low");
  });

  it("taskKindDisplayForCard handles known + unknown ids", () => {
    expect(taskKindDisplayForCard("audit")).toBe("Audit");
    expect(taskKindDisplayForCard("__not_a_real_kind__").length).toBeGreaterThan(0);
  });

  it("emptyStateHeadlineForCard reflects chosen null + unknown task", () => {
    const noChosen = makePayload({ chosen: null });
    expect(emptyStateHeadlineForCard(noChosen).toLowerCase()).toContain("no coding agent");
    const unsure = makePayload({ chosen: null, task_kind: "unknown" });
    expect(emptyStateHeadlineForCard(unsure).toLowerCase()).toContain("isn't sure");
  });

  it("isLaunchableInThisPhase always returns false (preview-only invariant)", () => {
    expect(isLaunchableInThisPhase(null)).toBe(false);
    expect(
      isLaunchableInThisPhase({
        provider: "factory_droid_audit",
        label: "Read-only audit",
        available: true,
        reason: "x",
        blockers: [],
        confidence: 0.9,
        output_kind: "report",
        requires_operator: false,
        requires_confirmation: true,
        will_modify_code: false,
        will_open_pull_request: false,
      }),
    ).toBe(false);
  });

  it("CODING_PLAN_NO_LAUNCH_FOOTER mentions no action launched + later step", () => {
    const lower = CODING_PLAN_NO_LAUNCH_FOOTER.toLowerCase();
    expect(lower).toContain("no action has been launched yet");
    expect(lower).toContain("later step");
  });
});
