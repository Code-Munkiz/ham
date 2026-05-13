import { describe, expect, it } from "vitest";

import { managedBuildChangedPathsLine } from "../codingPlanCardCopy";

describe("managedBuildChangedPathsLine", () => {
  it("formats counts for users", () => {
    expect(managedBuildChangedPathsLine(0)).toBe("No files changed");
    expect(managedBuildChangedPathsLine(1)).toBe("1 file changed");
    expect(managedBuildChangedPathsLine(3)).toBe("3 files changed");
  });

  it("returns empty for invalid counts", () => {
    expect(managedBuildChangedPathsLine(NaN)).toBe("");
    expect(managedBuildChangedPathsLine(-1)).toBe("");
  });
});
