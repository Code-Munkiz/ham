import { describe, expect, it } from "vitest";

import {
  normieFailMessageForOpencode,
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
  OPENCODE_BUILD_RUNNING_HEADLINE,
  OPENCODE_BUILD_RUNNING_NOTE,
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
  OPENCODE_BUILD_RUNNING_HEADLINE,
  OPENCODE_BUILD_RUNNING_NOTE,
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
    expect(OPENCODE_BUILD_PREVIEW_CTA).toBe("Prepare build");
    expect(OPENCODE_BUILD_PREVIEW_BUSY).toBe("Preparing build…");
    expect(OPENCODE_BUILD_LAUNCH_CTA).toBe("Approve build");
    expect(OPENCODE_BUILD_LAUNCH_BUSY).toBe("Building…");
    expect(OPENCODE_BUILD_SUCCESS_HEADLINE).toBe("Saved version created");
    expect(OPENCODE_BUILD_FAILURE_HEADLINE).toBe("Build did not complete. No version was saved.");
    expect(OPENCODE_BUILD_NO_PR_NOTE.toLowerCase()).toContain("never open a pull request");
    expect(OPENCODE_BUILD_KEEP_BUILDING_CTA).toBe("Keep building");
    expect(OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY).toBe("Details");
    expect(OPENCODE_BUILD_RUNNING_HEADLINE).toBe("HAM is building with OpenCode");
    expect(OPENCODE_BUILD_RUNNING_NOTE).toContain("minutes");
  });

  it("never embeds banned identifier tokens in user-facing copy", () => {
    for (const s of ALL_STRINGS) {
      const lower = s.toLowerCase();
      for (const banned of BANNED_TOKENS) {
        expect(lower, `${s} contains banned token ${banned}`).not.toContain(banned);
      }
    }
  });

  it("running copy strings never contain banned tokens", () => {
    const runningStrings = [OPENCODE_BUILD_RUNNING_HEADLINE, OPENCODE_BUILD_RUNNING_NOTE];
    for (const s of runningStrings) {
      const lower = s.toLowerCase();
      for (const banned of BANNED_TOKENS) {
        expect(lower, `${s} contains banned token ${banned}`).not.toContain(banned);
      }
    }
  });

  it("normieFailMessageForOpencode returns non-null for known failure reasons", () => {
    const failures = [
      "opencode:timeout",
      "opencode:session_no_completion",
      "opencode:runner_error",
      "opencode:permission_denied",
      "opencode:output_requires_review",
    ];
    for (const reason of failures) {
      const msg = normieFailMessageForOpencode(reason);
      expect(msg, `${reason} should yield a message`).not.toBeNull();
      expect(msg!.length).toBeGreaterThan(10);
    }
  });

  it("normieFailMessageForOpencode returns null for unknown or falsy input", () => {
    expect(normieFailMessageForOpencode(null)).toBeNull();
    expect(normieFailMessageForOpencode(undefined)).toBeNull();
    expect(normieFailMessageForOpencode("")).toBeNull();
    expect(normieFailMessageForOpencode("unknown:reason")).toBeNull();
  });

  it("formats changed-path counts", () => {
    expect(opencodeBuildChangedPathsLine(0)).toBe("No files changed");
    expect(opencodeBuildChangedPathsLine(1)).toBe("1 file changed");
    expect(opencodeBuildChangedPathsLine(4)).toBe("4 files changed");
    expect(opencodeBuildChangedPathsLine(NaN)).toBe("");
    expect(opencodeBuildChangedPathsLine(-2)).toBe("");
  });
});
