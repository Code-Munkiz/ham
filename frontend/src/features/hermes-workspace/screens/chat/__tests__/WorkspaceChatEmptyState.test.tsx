import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  BUILDER_EXAMPLE_PROMPTS,
  BUILDER_FIRST_RUN_HEADLINE,
  builderOnboardingCopyLooksSafe,
} from "@/lib/ham/builderFirstRunOnboarding";
import { WorkspaceChatEmptyState } from "../WorkspaceChatEmptyState";

describe("WorkspaceChatEmptyState", () => {
  it("renders builder first-run onboarding copy and examples", () => {
    render(<WorkspaceChatEmptyState onExamplePromptSelect={vi.fn()} />);

    expect(screen.getByTestId("hww-chat-empty-headline")).toHaveTextContent(
      BUILDER_FIRST_RUN_HEADLINE,
    );
    expect(screen.getByTestId("hww-chat-empty-subheadline")).toHaveTextContent(
      /app, website, dashboard, or tool/i,
    );
    expect(screen.getByText(/preview you can refine/i)).toBeInTheDocument();
    expect(screen.getByTestId("hww-chat-empty-examples")).toBeInTheDocument();
    for (const example of BUILDER_EXAMPLE_PROMPTS) {
      expect(screen.getByText(example.label)).toBeInTheDocument();
    }
  });

  it("clicking an example calls back with the full prompt", () => {
    const onExamplePromptSelect = vi.fn();
    render(<WorkspaceChatEmptyState onExamplePromptSelect={onExamplePromptSelect} />);

    fireEvent.click(screen.getByText("Simple task tracker"));
    expect(onExamplePromptSelect).toHaveBeenCalledWith("Create a simple task tracker.");
  });

  it("keeps operator jargon out of rendered onboarding copy", () => {
    render(<WorkspaceChatEmptyState onExamplePromptSelect={vi.fn()} />);
    const dom = screen.getByTestId("hww-chat-empty-state").textContent || "";
    expect(builderOnboardingCopyLooksSafe(dom)).toBe(true);
    expect(dom).not.toMatch(/conductor/i);
    expect(dom).not.toMatch(/ControlPlaneRun/i);
  });
});
