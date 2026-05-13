import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { CodingPlanCard } from "../CodingPlanCard";
import { CLAUDE_AGENT_STATUS_COPY, claudeAgentStatusCopy } from "../codingPlanCardCopy";
import type { CodingConductorCandidate, CodingConductorPreviewPayload } from "@/lib/ham/api";

function candidate(over: Partial<CodingConductorCandidate> = {}): CodingConductorCandidate {
  return {
    provider: "claude_agent",
    label: "Claude Agent (preview)",
    available: false,
    reason: "Claude Agent is not configured yet.",
    blockers: [],
    confidence: 0.5,
    output_kind: "answer",
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: false,
    will_open_pull_request: false,
    ...over,
  };
}

function payload(over: Partial<CodingConductorPreviewPayload> = {}): CodingConductorPreviewPayload {
  return {
    kind: "coding_conductor_preview",
    preview_id: "preview-claude-agent",
    task_kind: "explain",
    task_confidence: 0.7,
    chosen: null,
    candidates: [],
    blockers: [],
    recommendation_reason: "fixture reason",
    requires_approval: false,
    approval_kind: "none",
    project: {
      found: true,
      project_id: "p-claude",
      build_lane_enabled: false,
      has_github_repo: false,
    },
    is_operator: false,
    ...over,
  };
}

describe("CodingPlanCard — claude_agent provider scaffold", () => {
  it("renders the claude_agent display name when chosen", () => {
    const chosen = candidate();
    const p = payload({
      chosen,
      candidates: [chosen],
      recommendation_reason: chosen.reason,
    });
    const { container } = render(<CodingPlanCard payload={p} />);
    const card = container.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
    expect(card.textContent).toContain("Claude Agent");
  });

  it("does not render any active approve/launch/preview button for claude_agent", () => {
    const chosen = candidate();
    const p = payload({
      chosen,
      candidates: [chosen],
      recommendation_reason: chosen.reason,
    });
    render(<CodingPlanCard payload={p} />);
    const buttons = screen.getAllByRole("button");
    for (const b of buttons) {
      const name = (b.textContent || "").toLowerCase();
      if (/(approve|launch|preview|run|start)/.test(name)) {
        expect((b as HTMLButtonElement).disabled).toBe(true);
      }
    }
  });

  it("never renders the managed-build approval panel for claude_agent", () => {
    const chosen = candidate();
    const p = payload({
      chosen,
      candidates: [chosen],
      recommendation_reason: chosen.reason,
      project: {
        found: true,
        project_id: "p-claude",
        build_lane_enabled: true,
        has_github_repo: false,
        output_target: "managed_workspace",
        has_workspace_id: true,
      },
    });
    const { container } = render(<CodingPlanCard payload={p} />);
    expect(container.querySelector('[data-hww-coding-plan="managed-build-approval"]')).toBeNull();
  });

  it("returns the disabled status copy from claudeAgentStatusCopy", () => {
    expect(claudeAgentStatusCopy("disabled")).toBe("Claude Agent is not configured yet.");
  });

  it("never includes env names or internal workflow ids in any status copy", () => {
    const banned = [
      "CLAUDE_AGENT_ENABLED",
      "ANTHROPIC_API_KEY",
      "HAM_",
      "safe_edit_low",
      "sk-ant",
      "https://",
      "http://",
    ];
    for (const value of Object.values(CLAUDE_AGENT_STATUS_COPY)) {
      for (const token of banned) {
        expect(value).not.toContain(token);
      }
    }
  });
});
