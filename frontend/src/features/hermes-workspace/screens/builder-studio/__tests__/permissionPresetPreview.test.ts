import { describe, expect, it } from "vitest";
import type { PermissionPreset } from "../builderStudioLabels";
import { permissionPresetPreview } from "../permissionPresetPreview";

const PRESETS: PermissionPreset[] = [
  "safe_docs",
  "app_build",
  "bug_fix",
  "refactor",
  "game_build",
  "test_write",
  "readonly_analyst",
  "custom",
];

describe("permissionPresetPreview", () => {
  it("returns the locked summary for safe_docs", () => {
    expect(permissionPresetPreview("safe_docs")).toBe(
      "Can edit docs only. Cannot delete. No network. Asks before changes.",
    );
  });

  it("returns the locked summary for app_build", () => {
    expect(permissionPresetPreview("app_build")).toBe(
      "Can build and edit. Deletes need review. May ask for shell and install.",
    );
  });

  it("returns the locked summary for bug_fix", () => {
    expect(permissionPresetPreview("bug_fix")).toBe(
      "Can edit existing files. Won't add new dirs. Deletes need review.",
    );
  });

  it("returns the locked summary for refactor", () => {
    expect(permissionPresetPreview("refactor")).toBe(
      "Can edit and create. No shell or network. Deletes need review.",
    );
  });

  it("returns the locked summary for game_build", () => {
    expect(permissionPresetPreview("game_build")).toBe(
      "Can build and edit. Deletes need review. May ask for shell and install. No network.",
    );
  });

  it("returns the locked summary for test_write", () => {
    expect(permissionPresetPreview("test_write")).toBe(
      "Can edit tests only. Cannot delete. May ask for shell.",
    );
  });

  it("returns the locked summary for readonly_analyst", () => {
    expect(permissionPresetPreview("readonly_analyst")).toBe(
      "Read only. Cannot edit, create, or delete. Always asks.",
    );
  });

  it("returns the locked summary for custom", () => {
    expect(permissionPresetPreview("custom")).toBe(
      "Advanced. Same safety floor as App Builder (deletes need review), with your scopes added.",
    );
  });

  it("mentions delete posture for every preset", () => {
    for (const preset of PRESETS) {
      const summary = permissionPresetPreview(preset).toLowerCase();
      expect(summary).toMatch(/delete/);
    }
  });

  it("locks readonly_analyst as the most restrictive (Read only, no edit)", () => {
    const summary = permissionPresetPreview("readonly_analyst");
    expect(summary).toContain("Read only");
    expect(summary.toLowerCase()).not.toContain(" can edit");
  });
});
