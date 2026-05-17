import { describe, expect, it } from "vitest";
import {
  DELETION_POLICY_LABELS,
  EXTERNAL_NETWORK_POLICY_LABELS,
  MODEL_SOURCE_LABELS,
  PERMISSION_PRESET_LABELS,
  REVIEW_MODE_LABELS,
  TASK_KIND_LABELS,
  formatIntentTagsForDisplay,
  type PermissionPreset,
} from "../builderStudioLabels";

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

const FORBIDDEN_PROVIDER_IDS = [
  "opencode_cli",
  "factory_droid_build",
  "factory_droid_audit",
  "claude_agent",
  "claude_code",
  "cursor_cloud",
];

describe("PERMISSION_PRESET_LABELS", () => {
  it("has a non-empty user-friendly label for every preset", () => {
    for (const preset of PRESETS) {
      const label = PERMISSION_PRESET_LABELS[preset];
      expect(typeof label).toBe("string");
      expect(label.trim().length).toBeGreaterThan(0);
    }
  });

  it("never exposes raw provider ids in any label value", () => {
    const allLabels = [
      ...Object.values(PERMISSION_PRESET_LABELS),
      ...Object.values(MODEL_SOURCE_LABELS),
      ...Object.values(REVIEW_MODE_LABELS),
      ...Object.values(DELETION_POLICY_LABELS),
      ...Object.values(EXTERNAL_NETWORK_POLICY_LABELS),
      ...Object.values(TASK_KIND_LABELS),
    ];
    for (const label of allLabels) {
      const lower = label.toLowerCase();
      for (const forbidden of FORBIDDEN_PROVIDER_IDS) {
        expect(lower).not.toContain(forbidden);
      }
    }
  });

  it("locks the readonly_analyst label", () => {
    expect(PERMISSION_PRESET_LABELS.readonly_analyst).toBe("Read-only Analyst");
  });
});

describe("formatIntentTagsForDisplay", () => {
  it("trims surrounding whitespace", () => {
    expect(formatIntentTagsForDisplay(["  games  ", "phaser"])).toEqual(["games", "phaser"]);
  });

  it("lowercases entries", () => {
    expect(formatIntentTagsForDisplay(["Games", "PHASER"])).toEqual(["games", "phaser"]);
  });

  it("dedupes after normalization", () => {
    expect(formatIntentTagsForDisplay(["games", "Games", "GAMES "])).toEqual(["games"]);
  });

  it("drops empty entries", () => {
    expect(formatIntentTagsForDisplay(["", "   ", "ui"])).toEqual(["ui"]);
  });
});
