import { describe, expect, it } from "vitest";
import { validatePolicy, isPolicyValid } from "../policyValidate";
import type { SocialPolicyDoc } from "../policyTypes";

function baseDoc(): SocialPolicyDoc {
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

describe("validatePolicy", () => {
  it("accepts a clean default doc", () => {
    expect(validatePolicy(baseDoc()).ok).toBe(true);
    expect(isPolicyValid(baseDoc())).toBe(true);
  });

  it("rejects live_autonomy_armed=true unconditionally", () => {
    const doc = baseDoc();
    doc.live_autonomy_armed = true;
    doc.autopilot_mode = "armed"; // server would accept; editor still rejects
    const result = validatePolicy(doc);
    expect(result.ok).toBe(false);
    expect(result.issues.find((i) => i.path === "live_autonomy_armed")).toBeTruthy();
  });

  it("rejects out-of-bounds posting cap", () => {
    const doc = baseDoc();
    doc.providers.x.posting_caps.max_per_day = 51;
    const result = validatePolicy(doc);
    expect(result.ok).toBe(false);
    expect(
      result.issues.find((i) => i.path === "providers.x.posting_caps.max_per_day"),
    ).toBeTruthy();
  });

  it("rejects out-of-bounds reply cap", () => {
    const doc = baseDoc();
    doc.providers.telegram.reply_caps.max_per_hour = 1000;
    const result = validatePolicy(doc);
    expect(result.ok).toBe(false);
  });

  it("rejects unknown autopilot_mode literal", () => {
    const doc = baseDoc();
    (doc as unknown as { autopilot_mode: string }).autopilot_mode = "loose";
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects unknown provider mode literal", () => {
    const doc = baseDoc();
    (doc.providers.x as unknown as { posting_mode: string }).posting_mode = "yolo";
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects non-slug nature_tag", () => {
    const doc = baseDoc();
    doc.content_style.nature_tags = ["NotASlug"];
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects nature_tag with embedded raw numeric ID", () => {
    const doc = baseDoc();
    doc.content_style.nature_tags = ["chat-100123456789"];
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects duplicate posting_actions_allowed", () => {
    const doc = baseDoc();
    doc.providers.x.posting_actions_allowed = ["post", "post"];
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects target with unknown label", () => {
    const doc = baseDoc();
    doc.providers.telegram.targets = [
      { label: "rogue" as unknown as "home_channel", enabled: true },
    ];
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("accepts the two allowed target labels", () => {
    const doc = baseDoc();
    doc.providers.telegram.targets = [
      { label: "home_channel", enabled: true },
      { label: "test_group", enabled: false },
    ];
    expect(validatePolicy(doc).ok).toBe(true);
  });

  it("rejects safety_rules.min_relevance > 1", () => {
    const doc = baseDoc();
    doc.safety_rules.min_relevance = 1.5;
    expect(validatePolicy(doc).ok).toBe(false);
  });

  it("rejects null/undefined doc", () => {
    expect(validatePolicy(null).ok).toBe(false);
    expect(validatePolicy(undefined).ok).toBe(false);
  });
});
