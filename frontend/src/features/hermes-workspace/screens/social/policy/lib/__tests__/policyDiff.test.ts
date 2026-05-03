import { describe, expect, it } from "vitest";
import { diffPolicy, hasPolicyChanges } from "../policyDiff";
import type { SocialPolicyDoc } from "../policyTypes";

function doc(): SocialPolicyDoc {
  return {
    schema_version: 1,
    persona: { persona_id: "ham-canonical", persona_version: 1 },
    content_style: {
      tone: "warm",
      length_preference: "standard",
      emoji_policy: "sparingly",
      nature_tags: [],
    },
    safety_rules: {
      blocked_topics: [],
      block_links: true,
      min_relevance: 0.75,
      consecutive_failure_stop: 2,
      policy_rejection_stop: 10,
    },
    providers: {
      x: {
        provider_id: "x",
        posting_mode: "off",
        reply_mode: "off",
        posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
        reply_caps: {
          max_per_15m: 5,
          max_per_hour: 20,
          max_per_user_per_day: 3,
          max_per_thread_per_day: 5,
          min_seconds_between: 60,
          batch_max_per_run: 1,
        },
        posting_actions_allowed: [],
        targets: [],
      },
      telegram: {
        provider_id: "telegram",
        posting_mode: "off",
        reply_mode: "off",
        posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
        reply_caps: {
          max_per_15m: 5,
          max_per_hour: 20,
          max_per_user_per_day: 3,
          max_per_thread_per_day: 5,
          min_seconds_between: 60,
          batch_max_per_run: 1,
        },
        posting_actions_allowed: [],
        targets: [],
      },
      discord: {
        provider_id: "discord",
        posting_mode: "off",
        reply_mode: "off",
        posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
        reply_caps: {
          max_per_15m: 5,
          max_per_hour: 20,
          max_per_user_per_day: 3,
          max_per_thread_per_day: 5,
          min_seconds_between: 60,
          batch_max_per_run: 1,
        },
        posting_actions_allowed: [],
        targets: [],
      },
    },
    autopilot_mode: "off",
    live_autonomy_armed: false,
  };
}

describe("diffPolicy", () => {
  it("returns [] for equal documents", () => {
    expect(diffPolicy(doc(), doc())).toEqual([]);
    expect(hasPolicyChanges(doc(), doc())).toBe(false);
  });

  it("detects a single leaf change with the correct path", () => {
    const a = doc();
    const b = doc();
    b.providers.x.posting_mode = "preview";
    const out = diffPolicy(a, b);
    expect(out).toHaveLength(1);
    expect(out[0].path).toBe("providers.x.posting_mode");
    expect(out[0].before).toBe("off");
    expect(out[0].after).toBe("preview");
  });

  it("detects nested cap change with dot path", () => {
    const a = doc();
    const b = doc();
    b.providers.telegram.reply_caps.max_per_hour = 30;
    const out = diffPolicy(a, b);
    expect(out).toHaveLength(1);
    expect(out[0].path).toBe("providers.telegram.reply_caps.max_per_hour");
  });

  it("treats array reorder as a change at the array path", () => {
    const a = doc();
    const b = doc();
    b.providers.x.posting_actions_allowed = ["post"];
    const out = diffPolicy(a, b);
    expect(out).toHaveLength(1);
    expect(out[0].path).toBe("providers.x.posting_actions_allowed");
  });

  it("returns sentinel diff when one doc is null", () => {
    const out = diffPolicy(null, doc());
    expect(out).toHaveLength(1);
    expect(out[0].path).toBe("$");
  });

  it("hasPolicyChanges true when any leaf differs", () => {
    const a = doc();
    const b = doc();
    b.autopilot_mode = "manual_only";
    expect(hasPolicyChanges(a, b)).toBe(true);
  });
});
