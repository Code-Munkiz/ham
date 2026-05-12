import { describe, expect, it } from "vitest";

import { sanitizeConductorUserFacingLine } from "@/lib/ham/conductorUiMessaging";

describe("sanitizeConductorUserFacingLine", () => {
  it("replaces unknown project_id copy without leaking raw ids", () => {
    const raw = "Unknown project_id 'project.app-f53b52'. Pick an existing project.";
    expect(sanitizeConductorUserFacingLine(raw).toLowerCase()).not.toContain("unknown project_id");
    expect(sanitizeConductorUserFacingLine(raw)).toContain("Choose or create a project");
  });

  it("passes unrelated message through unchanged", () => {
    expect(sanitizeConductorUserFacingLine("Build lane disabled.")).toBe("Build lane disabled.");
  });
});
