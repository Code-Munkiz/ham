import { describe, expect, it } from "vitest";

import {
  OPENCODE_BUILD_APPROVAL_BODY,
  OPENCODE_BUILD_APPROVAL_CHECKBOX,
  OPENCODE_BUILD_APPROVAL_HEADLINE,
  OPENCODE_BUILD_FAILURE_HEADLINE,
  OPENCODE_BUILD_KEEP_BUILDING_CTA,
  OPENCODE_BUILD_LAUNCH_BUSY,
  OPENCODE_BUILD_LAUNCH_CTA,
  OPENCODE_BUILD_NO_PR_NOTE,
  OPENCODE_BUILD_PREVIEW_BUSY,
  OPENCODE_BUILD_PREVIEW_CTA,
  OPENCODE_BUILD_PREVIEW_LINK,
  OPENCODE_BUILD_SUCCESS_HEADLINE,
  OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY,
  OPENCODE_BUILD_VIEW_CHANGES_LINK,
  opencodeBuildChangedPathsLine,
} from "../codingPlanCardCopy";

const ALL_STRINGS = [
  OPENCODE_BUILD_APPROVAL_HEADLINE,
  OPENCODE_BUILD_APPROVAL_BODY,
  OPENCODE_BUILD_APPROVAL_CHECKBOX,
  OPENCODE_BUILD_PREVIEW_CTA,
  OPENCODE_BUILD_PREVIEW_BUSY,
  OPENCODE_BUILD_LAUNCH_CTA,
  OPENCODE_BUILD_LAUNCH_BUSY,
  OPENCODE_BUILD_SUCCESS_HEADLINE,
  OPENCODE_BUILD_FAILURE_HEADLINE,
  OPENCODE_BUILD_NO_PR_NOTE,
  OPENCODE_BUILD_PREVIEW_LINK,
  OPENCODE_BUILD_VIEW_CHANGES_LINK,
  OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY,
  OPENCODE_BUILD_KEEP_BUILDING_CTA,
];

const BANNED_TOKENS = [
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
  "ham_opencode_exec_token",
];

describe("OpenCode managed build copy", () => {
  it("locks user-facing strings", () => {
    expect(OPENCODE_BUILD_APPROVAL_HEADLINE).toBe("Review OpenCode build");
    expect(OPENCODE_BUILD_APPROVAL_CHECKBOX).toContain("OpenCode");
    expect(OPENCODE_BUILD_PREVIEW_CTA).toBe("Preview");
    expect(OPENCODE_BUILD_PREVIEW_BUSY).toBe("Previewing…");
    expect(OPENCODE_BUILD_LAUNCH_CTA).toBe("Approve and build");
    expect(OPENCODE_BUILD_LAUNCH_BUSY).toBe("Building…");
    expect(OPENCODE_BUILD_SUCCESS_HEADLINE).toBe("Saved version created");
    expect(OPENCODE_BUILD_FAILURE_HEADLINE).toBe("Build did not complete");
    expect(OPENCODE_BUILD_NO_PR_NOTE.toLowerCase()).toContain("never open a pull request");
    expect(OPENCODE_BUILD_KEEP_BUILDING_CTA).toBe("Keep building");
    expect(OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY).toBe("Details");
  });

  it("never embeds banned identifier tokens in user-facing copy", () => {
    for (const s of ALL_STRINGS) {
      const lower = s.toLowerCase();
      for (const banned of BANNED_TOKENS) {
        expect(lower, `${s} contains banned token ${banned}`).not.toContain(banned);
      }
    }
  });

  it("formats changed-path counts", () => {
    expect(opencodeBuildChangedPathsLine(0)).toBe("No files changed");
    expect(opencodeBuildChangedPathsLine(1)).toBe("1 file changed");
    expect(opencodeBuildChangedPathsLine(4)).toBe("4 files changed");
    expect(opencodeBuildChangedPathsLine(NaN)).toBe("");
    expect(opencodeBuildChangedPathsLine(-2)).toBe("");
  });
});
