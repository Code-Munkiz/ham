import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { CodingPlanCard } from "../CodingPlanCard";
import {
  FORBIDDEN_CARD_TOKENS,
  OPENCODE_PREFERRED_CTA,
  OPENCODE_PREFERRED_HINT,
  OPENCODE_PREFERRED_LOADING,
} from "../codingPlanCardCopy";
import type { CodingConductorCandidate, CodingConductorPreviewPayload } from "@/lib/ham/api";

function candidate(over: Partial<CodingConductorCandidate> = {}): CodingConductorCandidate {
  return {
    provider: "factory_droid_audit",
    label: "Read-only audit",
    available: true,
    reason: "Read-only audit; no risk to the repository.",
    blockers: [],
    confidence: 0.85,
    output_kind: "report",
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
    preview_id: "preview-1",
    task_kind: "audit",
    task_confidence: 0.85,
    chosen: null,
    candidates: [],
    blockers: [],
    recommendation_reason: "x",
    requires_approval: true,
    approval_kind: "confirm",
    project: {
      found: true,
      project_id: "p1",
      build_lane_enabled: false,
      has_github_repo: false,
    },
    is_operator: false,
    ...over,
  };
}

function renderWithDigest(p: CodingConductorPreviewPayload) {
  const utils = render(<CodingPlanCard payload={p} />);
  const card = utils.container.querySelector('[data-hww-coding-plan="card"]') as HTMLElement;
  return { ...utils, card };
}

function assertNoForbiddenTokens(node: HTMLElement) {
  const blob = node.textContent?.toLowerCase() ?? "";
  for (const token of FORBIDDEN_CARD_TOKENS) {
    expect(blob, `card leaks ${token}`).not.toContain(token);
  }
  // Also lock against runner URL leakage and PII-shaped patterns.
  expect(blob).not.toMatch(/https?:\/\//);
}

describe("CodingPlanCard", () => {
  it("sanitizes unknown project blocker copy for user-facing conductor text", () => {
    const p = payload({
      blockers: ["Unknown project_id 'project.app-f53b52'. Pick an existing project."],
      chosen: null,
      candidates: [],
    });
    renderWithDigest(p);
    const ul = screen
      .getByRole("region")
      .querySelector('[data-hww-coding-plan="response-blockers"]');
    expect(ul).toBeTruthy();
    expect((ul as HTMLElement).textContent?.toLowerCase()).not.toContain("unknown project_id");
    expect((ul as HTMLElement).textContent ?? "").toMatch(/Choose or create a project/i);
  });

  it("renders chosen provider label and recommendation reason", () => {
    const chosen = candidate({
      provider: "cursor_cloud",
      label: "Cursor pull request",
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: true,
      reason: "Repo-wide context; opens a pull request you review.",
    });
    const p = payload({
      task_kind: "refactor",
      chosen,
      candidates: [chosen],
      recommendation_reason: chosen.reason,
      approval_kind: "confirm",
    });

    const { card } = renderWithDigest(p);

    expect(card.querySelector('[data-hww-coding-plan="headline"]')!.textContent).toContain(
      "Cursor pull request",
    );
    const reason =
      card.querySelector('[data-hww-coding-plan="recommendation-reason"]')!.textContent ?? "";
    expect(reason.toLowerCase()).toContain("pull request");
  });

  it("renders blockers safely without leaking env names or workflow ids", () => {
    const blocked = candidate({
      provider: "factory_droid_build",
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: true,
      available: false,
      blockers: [
        "Build lane is disabled for this project. A workspace operator must enable it in Settings.",
        "This project has no GitHub repository configured.",
      ],
      reason: "Low-risk pull request with a minimal diff.",
    });
    const p = payload({
      task_kind: "typo_only",
      chosen: null,
      candidates: [blocked],
      blockers: ["Pick a project before launching a build."],
      recommendation_reason: "Multiple candidates are blocked; pick one to see how to unblock it.",
      approval_kind: "none",
    });

    const { card } = renderWithDigest(p);

    // Response-level blockers are surfaced.
    expect(card.querySelector('[data-hww-coding-plan="response-blockers"]')!.textContent).toContain(
      "Pick a project",
    );

    // Sanitisation lock.
    assertNoForbiddenTokens(card);
  });

  it("toggles alternatives and renders safe alternative labels", () => {
    const cursor = candidate({
      provider: "cursor_cloud",
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: true,
      reason: "Repo-wide context; opens a pull request you review.",
    });
    const noAgent = candidate({
      provider: "no_agent",
      output_kind: "answer",
      will_modify_code: false,
      will_open_pull_request: false,
      reason: "Conversational; no repository work needed.",
      requires_confirmation: false,
    });
    const p = payload({
      task_kind: "refactor",
      chosen: cursor,
      candidates: [cursor, noAgent],
      recommendation_reason: cursor.reason,
    });

    const { card } = renderWithDigest(p);

    // Alternatives drawer is collapsed by default.
    expect(card.querySelector('[data-hww-coding-plan="alternatives"]')).toBeNull();

    const toggle = card.querySelector(
      '[data-hww-coding-plan="alternatives-toggle"]',
    ) as HTMLButtonElement;
    expect(toggle).not.toBeNull();
    fireEvent.click(toggle);

    const drawer = card.querySelector('[data-hww-coding-plan="alternatives"]');
    expect(drawer).not.toBeNull();
    // "Conversational answer" label appears for the no_agent fallback.
    expect(drawer!.textContent).toContain("Conversational answer");
    assertNoForbiddenTokens(card);
  });

  it("renders safe fallback when chosen is null and task is unknown", () => {
    const noAgent = candidate({
      provider: "no_agent",
      output_kind: "answer",
      will_modify_code: false,
      will_open_pull_request: false,
      reason: "Conversational; no repository work needed.",
      requires_confirmation: false,
      confidence: 0.4,
    });
    const p = payload({
      task_kind: "unknown",
      task_confidence: 0.4,
      chosen: null,
      candidates: [noAgent],
      recommendation_reason: "I'm not sure which path is best for this request.",
      approval_kind: "none",
    });

    const { card } = renderWithDigest(p);
    const headline = card.querySelector('[data-hww-coding-plan="headline"]')!.textContent ?? "";
    expect(headline.toLowerCase()).toContain("isn't sure");
    assertNoForbiddenTokens(card);
  });

  it("never renders an active launch button (preview-only invariant)", () => {
    const chosen = candidate({
      provider: "factory_droid_audit",
      output_kind: "report",
      reason: "Read-only audit; no risk to the repository.",
    });
    const p = payload({ chosen, candidates: [chosen] });

    const { card } = renderWithDigest(p);

    const cta = card.querySelector(
      '[data-hww-coding-plan="launch-cta-disabled"]',
    ) as HTMLButtonElement;
    expect(cta).not.toBeNull();
    expect(cta.disabled).toBe(true);
    expect(cta.getAttribute("aria-disabled")).toBe("true");
    expect(cta.getAttribute("data-launch-enabled")).toBe("0");

    // Footer pins the no-launch promise.
    const footer =
      card.querySelector('[data-hww-coding-plan="no-launch-footer"]')!.textContent ?? "";
    expect(footer.toLowerCase()).toContain("no action has been launched yet");
  });

  it("does not render any element with name suggesting an active approve/launch action", () => {
    const chosen = candidate();
    const p = payload({ chosen, candidates: [chosen] });
    render(<CodingPlanCard payload={p} />);
    // Any button whose accessible name resembles a launch action must be disabled.
    const buttons = screen.getAllByRole("button");
    for (const b of buttons) {
      const name = (b.textContent || "").toLowerCase();
      if (/(approve|launch|run|start)/.test(name)) {
        expect((b as HTMLButtonElement).disabled).toBe(true);
      }
    }
  });
});

describe("CodingPlanCard OpenCode preferred-provider affordance", () => {
  function fdBuildChosen() {
    return candidate({
      provider: "factory_droid_build",
      label: "Low-risk pull request",
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: true,
      reason: "Low-risk pull request with a minimal diff.",
    });
  }

  function opencodeAvailable() {
    return candidate({
      provider: "opencode_cli",
      label: "OpenCode managed workspace build",
      output_kind: "pull_request",
      will_modify_code: true,
      will_open_pull_request: false,
      reason: "Build inside a managed workspace snapshot.",
    });
  }

  it("renders affordance when OpenCode is an available alternative and a callback is supplied", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });
    const onPreferProvider = vi.fn();

    const { container } = render(
      <CodingPlanCard payload={p} onPreferProvider={onPreferProvider} />,
    );
    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement | null;
    expect(cta).not.toBeNull();
    expect(cta!.textContent).toContain(OPENCODE_PREFERRED_CTA);
    const wrap = container.querySelector('[data-hww-coding-plan="opencode-affordance"]');
    expect(wrap?.textContent).toContain(OPENCODE_PREFERRED_HINT);
  });

  it("hides affordance when OpenCode candidate is blocked", () => {
    const chosen = fdBuildChosen();
    const blocked = candidate({
      provider: "opencode_cli",
      available: false,
      blockers: ["Managed workspace is not enabled for this project."],
    });
    const p = payload({ chosen, candidates: [chosen, blocked] });
    const { container } = render(<CodingPlanCard payload={p} onPreferProvider={vi.fn()} />);
    expect(container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]')).toBeNull();
  });

  it("hides affordance when OpenCode is already chosen", () => {
    const chosenOc = candidate({
      provider: "opencode_cli",
      output_kind: "pull_request",
      will_open_pull_request: false,
    });
    const p = payload({ chosen: chosenOc, candidates: [chosenOc] });
    const { container } = render(<CodingPlanCard payload={p} onPreferProvider={vi.fn()} />);
    expect(container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]')).toBeNull();
  });

  it("hides affordance when OpenCode is not in candidates", () => {
    const chosen = fdBuildChosen();
    const p = payload({ chosen, candidates: [chosen] });
    const { container } = render(<CodingPlanCard payload={p} onPreferProvider={vi.fn()} />);
    expect(container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]')).toBeNull();
  });

  it("hides affordance when onPreferProvider prop is not provided", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });
    const { container } = render(<CodingPlanCard payload={p} />);
    expect(container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]')).toBeNull();
  });

  it("clicking the CTA calls onPreferProvider('opencode_cli') exactly once", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });
    const onPreferProvider = vi.fn();

    const { container } = render(
      <CodingPlanCard payload={p} onPreferProvider={onPreferProvider} />,
    );
    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement;
    fireEvent.click(cta);
    expect(onPreferProvider).toHaveBeenCalledTimes(1);
    expect(onPreferProvider).toHaveBeenCalledWith("opencode_cli");
  });

  it("shows busy copy and disables the CTA while preferringProvider is opencode_cli", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });

    const { container } = render(
      <CodingPlanCard payload={p} onPreferProvider={vi.fn()} preferringProvider="opencode_cli" />,
    );
    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement;
    expect(cta.disabled).toBe(true);
    expect(cta.getAttribute("aria-busy")).toBe("true");
    expect(cta.textContent).toContain(OPENCODE_PREFERRED_LOADING);
  });

  it("preserves the never-renders-active-launch-button invariant", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });
    render(<CodingPlanCard payload={p} onPreferProvider={vi.fn()} />);
    const buttons = screen.getAllByRole("button");
    for (const b of buttons) {
      const name = (b.textContent || "").toLowerCase();
      if (/(approve|launch|run|start)/.test(name)) {
        expect((b as HTMLButtonElement).disabled).toBe(true);
      }
    }
  });

  it("affordance rendered text never contains banned user-facing tokens", () => {
    const chosen = fdBuildChosen();
    const opencode = opencodeAvailable();
    const p = payload({ chosen, candidates: [chosen, opencode] });
    const { container } = render(<CodingPlanCard payload={p} onPreferProvider={vi.fn()} />);
    const wrap = container.querySelector(
      '[data-hww-coding-plan="opencode-affordance"]',
    ) as HTMLElement;
    expect(wrap).not.toBeNull();
    const lower = wrap.textContent?.toLowerCase() ?? "";
    for (const token of FORBIDDEN_CARD_TOKENS) {
      expect(lower).not.toContain(token);
    }
    const extra = [
      "opencode_cli",
      "factory_droid",
      "output_target",
      "controlplanerun",
      "/api/",
      "https://",
      "http://",
    ];
    for (const token of extra) {
      expect(lower).not.toContain(token);
    }
  });
});
