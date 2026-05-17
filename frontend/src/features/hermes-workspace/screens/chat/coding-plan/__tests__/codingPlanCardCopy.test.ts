import { describe, expect, it } from "vitest";

import {
  CODING_PLAN_NO_LAUNCH_FOOTER,
  FACTORY_DROID_BUILD_MANAGED_LABEL,
  FORBIDDEN_CARD_TOKENS,
  OPENCODE_PREFERRED_CTA,
  OPENCODE_PREFERRED_HINT,
  OPENCODE_PREFERRED_LOADING,
  approvalCopyForCard,
  builderLabelForCandidate,
  cardLabelForCandidate,
  claudeAgentStatusCopy,
  confidenceBadgeForCard,
  emptyStateHeadlineForCard,
  isLaunchableInThisPhase,
  outputKindCopyForCard,
  planDescriptionForCard,
  providerLabelForCard,
  shouldShowOpenCodeAffordance,
  taskKindDisplayForCard,
} from "../codingPlanCardCopy";
import type {
  CodingConductorCandidate,
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
  "claude_agent",
  "opencode_cli",
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

  it("cardLabelForCandidate switches to managed copy when will_open_pull_request is false", () => {
    const managed = cardLabelForCandidate({
      provider: "factory_droid_build",
      will_open_pull_request: false,
    });
    expect(managed).toBe(FACTORY_DROID_BUILD_MANAGED_LABEL);

    const githubPr = cardLabelForCandidate({
      provider: "factory_droid_build",
      will_open_pull_request: true,
    });
    expect(githubPr).toBe("Low-risk pull request");
  });

  it("cardLabelForCandidate falls back to per-provider label for non-build providers", () => {
    expect(cardLabelForCandidate({ provider: "no_agent", will_open_pull_request: false })).toBe(
      "Conversational answer",
    );
    expect(cardLabelForCandidate({ provider: "cursor_cloud", will_open_pull_request: true })).toBe(
      "Cursor pull request",
    );
  });

  it("CODING_PLAN_NO_LAUNCH_FOOTER mentions no action launched + later step", () => {
    const lower = CODING_PLAN_NO_LAUNCH_FOOTER.toLowerCase();
    expect(lower).toContain("no action has been launched yet");
    expect(lower).toContain("later step");
  });
});

const PREFERRED_USER_FACING_BANNED = [
  "opencode_cli",
  "factory_droid",
  "output_target",
  "controlplanerun",
  "/api/",
  "safe_edit_low",
  "workflow_id",
  "registry_revision",
  "https://",
  "http://",
] as const;

function makeCandidate(over: Partial<CodingConductorCandidate> = {}): CodingConductorCandidate {
  return {
    provider: "factory_droid_build",
    label: "Low-risk pull request",
    available: true,
    reason: "Low-risk pull request with a minimal diff.",
    blockers: [],
    confidence: 0.8,
    output_kind: "pull_request",
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    will_open_pull_request: true,
    ...over,
  };
}

describe("OpenCode preferred-provider affordance copy", () => {
  it("locks exact string values", () => {
    expect(OPENCODE_PREFERRED_CTA).toBe("Try with OpenCode");
    expect(OPENCODE_PREFERRED_HINT).toBe(
      "Build it in a managed workspace instead of opening a pull request.",
    );
    expect(OPENCODE_PREFERRED_LOADING).toBe("Switching to OpenCode…");
  });

  it("CTA never contains banned user-facing tokens", () => {
    const lower = OPENCODE_PREFERRED_CTA.toLowerCase();
    for (const token of PREFERRED_USER_FACING_BANNED) {
      expect(lower).not.toContain(token);
    }
    for (const token of FORBIDDEN_CARD_TOKENS) {
      expect(lower).not.toContain(token);
    }
  });

  it("hint never contains banned user-facing tokens", () => {
    const lower = OPENCODE_PREFERRED_HINT.toLowerCase();
    for (const token of PREFERRED_USER_FACING_BANNED) {
      expect(lower).not.toContain(token);
    }
    for (const token of FORBIDDEN_CARD_TOKENS) {
      expect(lower).not.toContain(token);
    }
  });

  it("loading copy never contains banned user-facing tokens", () => {
    const lower = OPENCODE_PREFERRED_LOADING.toLowerCase();
    for (const token of PREFERRED_USER_FACING_BANNED) {
      expect(lower).not.toContain(token);
    }
    for (const token of FORBIDDEN_CARD_TOKENS) {
      expect(lower).not.toContain(token);
    }
  });
});

describe("shouldShowOpenCodeAffordance", () => {
  it("true when opencode is an available non-chosen candidate", () => {
    const chosen = makeCandidate({ provider: "factory_droid_build" });
    const opencode = makeCandidate({
      provider: "opencode_cli",
      label: "OpenCode managed workspace build",
      output_kind: "pull_request",
      will_open_pull_request: false,
    });
    expect(
      shouldShowOpenCodeAffordance(makePayload({ chosen, candidates: [chosen, opencode] })),
    ).toBe(true);
  });

  it("false when opencode candidate is blocked", () => {
    const chosen = makeCandidate({ provider: "factory_droid_build" });
    const opencode = makeCandidate({
      provider: "opencode_cli",
      available: false,
      blockers: ["Managed workspace is not enabled for this project."],
    });
    expect(
      shouldShowOpenCodeAffordance(makePayload({ chosen, candidates: [chosen, opencode] })),
    ).toBe(false);
  });

  it("false when opencode is already the chosen provider", () => {
    const chosen = makeCandidate({ provider: "opencode_cli" });
    expect(shouldShowOpenCodeAffordance(makePayload({ chosen, candidates: [chosen] }))).toBe(false);
  });

  it("false when no opencode candidate is present", () => {
    const chosen = makeCandidate({ provider: "factory_droid_build" });
    expect(shouldShowOpenCodeAffordance(makePayload({ chosen, candidates: [chosen] }))).toBe(false);
  });
});

describe("builderLabelForCandidate", () => {
  it("returns a non-empty normie label for every provider", () => {
    for (const p of PROVIDERS) {
      const label = builderLabelForCandidate({ provider: p });
      expect(label.length).toBeGreaterThan(0);
      const lower = label.toLowerCase();
      for (const token of FORBIDDEN_CARD_TOKENS) {
        expect(lower).not.toContain(token);
      }
    }
  });

  it("maps known providers to expected labels", () => {
    expect(builderLabelForCandidate({ provider: "opencode_cli" })).toBe("Open Builder");
    expect(builderLabelForCandidate({ provider: "claude_agent" })).toBe(
      "Premium Reasoning Builder",
    );
    expect(builderLabelForCandidate({ provider: "factory_droid_build" })).toBe(
      "Controlled Builder",
    );
    expect(builderLabelForCandidate({ provider: "cursor_cloud" })).toBe("Connected Repo Builder");
  });
});

describe("planDescriptionForCard", () => {
  it("returns answer copy for output_kind=answer", () => {
    const desc = planDescriptionForCard({
      output_kind: "answer",
      will_modify_code: false,
      will_open_pull_request: false,
    });
    expect(desc.toLowerCase()).toContain("without");
    expect(desc.toLowerCase()).not.toContain("pull request");
  });

  it("returns report copy for output_kind=report", () => {
    const desc = planDescriptionForCard({
      output_kind: "report",
      will_modify_code: false,
      will_open_pull_request: false,
    });
    expect(desc.toLowerCase()).toContain("read-only");
  });

  it("returns PR copy when will_open_pull_request is true", () => {
    const desc = planDescriptionForCard({
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: true,
    });
    expect(desc.toLowerCase()).toContain("pull request");
  });

  it("returns snapshot copy when will_modify_code but no PR", () => {
    const desc = planDescriptionForCard({
      output_kind: "mission",
      will_modify_code: true,
      will_open_pull_request: false,
    });
    expect(desc.toLowerCase()).toContain("version");
    expect(desc.toLowerCase()).not.toContain("pull request");
  });
});

describe("CLAUDE_AGENT_STATUS_COPY", () => {
  it("returns a non-empty string for every readiness state", () => {
    const states = [
      "disabled",
      "not_configured",
      "sdk_missing",
      "runner_unavailable",
      "configured",
    ] as const;
    for (const s of states) {
      expect(claudeAgentStatusCopy(s).length).toBeGreaterThan(0);
    }
  });
});
