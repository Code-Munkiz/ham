import { describe, expect, it } from "vitest";
import {
  BUILDER_EXAMPLE_PROMPTS,
  BUILDER_FIRST_RUN_HEADLINE,
  BUILDER_FIRST_RUN_PREVIEW_NOTE,
  BUILDER_FIRST_RUN_SUBHEADLINE,
  builderOnboardingCopyLooksSafe,
} from "@/lib/ham/builderFirstRunOnboarding";

describe("builderFirstRunOnboarding", () => {
  it("defines builder-first headline and helper copy", () => {
    expect(BUILDER_FIRST_RUN_HEADLINE).toBe("What do you want to build?");
    expect(BUILDER_FIRST_RUN_SUBHEADLINE).toMatch(/app, website, dashboard, or tool/i);
    expect(BUILDER_FIRST_RUN_PREVIEW_NOTE).toMatch(/preview you can refine/i);
  });

  it("ships three example prompts for first-run users", () => {
    expect(BUILDER_EXAMPLE_PROMPTS).toHaveLength(3);
    expect(BUILDER_EXAMPLE_PROMPTS.map((row) => row.prompt)).toEqual([
      "Build a landing page for my newsletter.",
      "Create a simple task tracker.",
      "Make a portfolio site with a contact form.",
    ]);
  });

  it("flags internal operator jargon in user-facing copy", () => {
    expect(builderOnboardingCopyLooksSafe(BUILDER_FIRST_RUN_HEADLINE)).toBe(true);
    expect(builderOnboardingCopyLooksSafe("Use the conductor runner for ControlPlaneRun")).toBe(
      false,
    );
    expect(builderOnboardingCopyLooksSafe("project_id abc safe_edit_low")).toBe(false);
  });
});
