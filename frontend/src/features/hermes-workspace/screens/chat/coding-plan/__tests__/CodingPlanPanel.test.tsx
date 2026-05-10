import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CodingPlanPanel } from "../CodingPlanPanel";

const previewMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    previewCodingConductor: (...args: Parameters<typeof mod.previewCodingConductor>) =>
      previewMock(...args),
  };
});

beforeEach(() => {
  previewMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CodingPlanPanel", () => {
  it("submits the trimmed prompt and renders the resulting card", async () => {
    previewMock.mockResolvedValue({
      kind: "coding_conductor_preview",
      preview_id: "p-1",
      task_kind: "audit",
      task_confidence: 0.85,
      chosen: {
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
      },
      candidates: [
        {
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
        },
      ],
      blockers: [],
      recommendation_reason: "Read-only audit; no risk to the repository.",
      requires_approval: true,
      approval_kind: "confirm",
      project: {
        found: true,
        project_id: "p1",
        build_lane_enabled: false,
        has_github_repo: false,
      },
      is_operator: false,
    });

    render(<CodingPlanPanel initialPrompt=" Audit the persistence layer.  " projectId="p1" />);

    const submit = screen.getByText("Plan with coding agents", { selector: "button" });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(previewMock).toHaveBeenCalledWith({
        user_prompt: "Audit the persistence layer.",
        project_id: "p1",
      });
    });

    await waitFor(() => {
      expect(document.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull();
    });
    const headline = document.querySelector('[data-hww-coding-plan="headline"]')!.textContent ?? "";
    expect(headline).toContain("Read-only audit");
  });

  it("renders error copy on rejected fetch", async () => {
    previewMock.mockRejectedValue(new Error("Auth required"));

    render(<CodingPlanPanel initialPrompt="Audit the API." />);

    const submit = screen.getByText("Plan with coding agents", { selector: "button" });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(document.querySelector("[data-hww-coding-plan-error]")?.textContent).toContain(
        "Auth required",
      );
    });
    expect(document.querySelector('[data-hww-coding-plan="card"]')).toBeNull();
  });

  it("blocks submit when prompt is empty", () => {
    render(<CodingPlanPanel />);
    const submit = screen.getByText("Plan with coding agents", {
      selector: "button",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });
});
