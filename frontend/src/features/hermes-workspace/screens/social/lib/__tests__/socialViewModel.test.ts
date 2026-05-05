/**
 * Phase C.1 baseline test: pure view-model helpers that translate raw
 * provider snapshots into product-facing labels for the Social cockpit.
 *
 * These functions are the "product truth" boundary — UI components rely
 * on the exact strings/enum values returned here, so we lock the most
 * stable surfaces with deterministic fixtures. No DOM, no network.
 *
 * We deliberately keep fixture surface narrow: each test builds the
 * minimal sub-shape the function actually reads (cast to the imported
 * type so we still get type-checking on the shape we touch).
 */
import { describe, expect, it } from "vitest";
import type {
  DiscordCapabilities,
  SocialPersona,
  TelegramCapabilities,
  XProviderStatus,
} from "@/features/hermes-workspace/adapters/socialAdapter";
import {
  derivePersonaProductStatus,
  derivePostingFrequencyProduct,
  deriveReplyVolumeProduct,
  discordPostingFrequencyProduct,
  discordReplyVolumeProduct,
  fourModeToProduct,
  mapCoreReadiness,
  telegramPostingFrequencyProduct,
  telegramReplyVolumeProduct,
} from "@/features/hermes-workspace/screens/social/lib/socialViewModel";

// ---- fixtures -------------------------------------------------------------

function xStatus(overrides: {
  broadcast_lane_enabled?: boolean;
  reactive_lane_enabled?: boolean;
  caps?: Partial<XProviderStatus["cap_cooldown_summary"]>;
}): XProviderStatus {
  const baseCaps: XProviderStatus["cap_cooldown_summary"] = {
    broadcast_daily_cap: 5,
    broadcast_daily_used: 0,
    broadcast_daily_remaining: 5,
    broadcast_per_run_cap: 2,
    broadcast_min_spacing_minutes: 30,
    reactive_max_replies_per_15m: 4,
    reactive_max_replies_per_hour: 12,
    reactive_max_replies_per_user_per_day: 1,
    reactive_max_replies_per_thread_per_day: 1,
    reactive_min_seconds_between_replies: 60,
    reactive_batch_max_replies_per_run: 3,
  };
  return {
    provider_id: "x",
    label: "X",
    overall_readiness: "ready",
    readiness_reasons: [],
    emergency_stop: { enabled: false },
    dry_run_defaults: {
      global_dry_run: false,
      controller_dry_run: false,
      reactive_dry_run: false,
      reactive_batch_dry_run: false,
    },
    broadcast_lane: {
      enabled: overrides.broadcast_lane_enabled ?? true,
      controller_enabled: true,
      live_controller_enabled: false,
      dry_run_available: true,
      live_configured: true,
      execution_allowed_now: false,
      reasons: [],
    },
    reactive_lane: {
      enabled: overrides.reactive_lane_enabled ?? true,
      inbox_discovery_enabled: true,
      dry_run_enabled: true,
      live_canary_enabled: false,
      batch_enabled: false,
      reasons: [],
    },
    last_autonomous_post: null,
    last_reactive_reply: null,
    cap_cooldown_summary: { ...baseCaps, ...overrides.caps },
    paths: {
      execution_journal_path: "",
      audit_log_path: "",
    },
    read_only: false,
    mutation_attempted: false,
  };
}

function persona(overrides: Partial<SocialPersona> = {}): SocialPersona {
  return {
    persona_id: "test",
    version: 1,
    display_name: "Test Persona",
    short_bio: "",
    mission: "",
    values: [],
    tone_rules: [],
    platform_adaptations: {},
    prohibited_content: [],
    safety_boundaries: [],
    example_replies: [],
    example_announcements: [],
    refusal_examples: [],
    persona_digest: "",
    read_only: false,
    mutation_attempted: false,
    ...overrides,
  };
}

const TG_CAPS_OFF: TelegramCapabilities = {
  provider_id: "telegram",
  bot_token_present: false,
  allowed_users_configured: false,
  home_channel_configured: false,
  test_group_configured: false,
  telegram_mode: "unset",
  hermes_gateway_base_url_present: false,
  hermes_gateway_status_path_present: false,
  hermes_gateway_runtime_state: "unknown",
  telegram_platform_state: "not_reported",
  readiness: "setup_required",
  missing_requirements: [],
  recommended_next_steps: [],
  polling_supported: false,
  webhook_supported: false,
  groups_supported: false,
  topics_supported: false,
  media_supported: false,
  voice_supported: false,
  inbound_available: false,
  preview_available: false,
  live_message_available: false,
  live_apply_available: false,
  activity_apply_available: false,
  reactive_reply_apply_available: false,
  read_only: false,
  mutation_attempted: false,
};

const DISCORD_CAPS_OFF: DiscordCapabilities = {
  provider_id: "discord",
  bot_token_present: false,
  allowed_users_or_roles_configured: false,
  guild_or_channel_configured: false,
  dms_supported: false,
  channels_supported: false,
  threads_supported: false,
  slash_commands_supported: false,
  media_supported: false,
  voice_supported: false,
  inbound_available: false,
  preview_available: false,
  live_message_available: false,
  live_apply_available: false,
  read_only: false,
  mutation_attempted: false,
};

// ---- enum mapping helpers -------------------------------------------------

describe("fourModeToProduct", () => {
  it("rewrites 'Preview' to the product label 'Preview only'", () => {
    expect(fourModeToProduct("Preview")).toBe("Preview only");
  });

  it("passes through 'Off', 'Approval required' and 'Autopilot' unchanged", () => {
    expect(fourModeToProduct("Off")).toBe("Off");
    expect(fourModeToProduct("Approval required")).toBe("Approval required");
    expect(fourModeToProduct("Autopilot")).toBe("Autopilot");
  });
});

describe("mapCoreReadiness", () => {
  it("maps each readiness enum to its product-facing label", () => {
    expect(mapCoreReadiness("ready")).toBe("Ready");
    expect(mapCoreReadiness("setup_required")).toBe("Needs setup");
    expect(mapCoreReadiness("limited")).toBe("Limited");
    expect(mapCoreReadiness("blocked")).toBe("Blocked");
  });
});

// ---- X frequency / volume -------------------------------------------------

describe("derivePostingFrequencyProduct", () => {
  it("returns 'Off' when the broadcast lane is disabled", () => {
    expect(
      derivePostingFrequencyProduct(
        xStatus({ broadcast_lane_enabled: false }),
      ),
    ).toBe("Off");
  });

  it("returns 'Custom' when caps fall outside the standard band", () => {
    // broadcast_daily_cap <= 0 forces the 'custom' branch
    expect(
      derivePostingFrequencyProduct(
        xStatus({ caps: { broadcast_daily_cap: 0 } }),
      ),
    ).toBe("Custom");

    // per-run cap >3 also forces 'custom'
    expect(
      derivePostingFrequencyProduct(
        xStatus({ caps: { broadcast_per_run_cap: 5 } }),
      ),
    ).toBe("Custom");
  });

  it("returns a banded value (Low/Standard/High) when caps are within range", () => {
    // 0 used / 5 cap → ratio 0 → Low band
    const out = derivePostingFrequencyProduct(xStatus({}));
    expect(["Low", "Standard", "High"]).toContain(out);
  });
});

describe("deriveReplyVolumeProduct", () => {
  it("returns 'Off' when the reactive lane is disabled", () => {
    expect(
      deriveReplyVolumeProduct(
        xStatus({ reactive_lane_enabled: false }),
      ),
    ).toBe("Off");
  });

  it("returns 'Custom' when reply caps exceed the standard envelope", () => {
    expect(
      deriveReplyVolumeProduct(
        xStatus({ caps: { reactive_max_replies_per_hour: 100 } }),
      ),
    ).toBe("Custom");

    expect(
      deriveReplyVolumeProduct(
        xStatus({ caps: { reactive_min_seconds_between_replies: 1 } }),
      ),
    ).toBe("Custom");
  });

  it("returns 'Low' for tight, conservative caps", () => {
    expect(
      deriveReplyVolumeProduct(
        xStatus({
          caps: {
            reactive_max_replies_per_hour: 2,
            reactive_max_replies_per_15m: 1,
            reactive_batch_max_replies_per_run: 1,
            reactive_min_seconds_between_replies: 120,
          },
        }),
      ),
    ).toBe("Low");
  });
});

// ---- Telegram / Discord delegations --------------------------------------

describe("telegramPostingFrequencyProduct", () => {
  it("returns 'Off' for empty Telegram capabilities", () => {
    expect(telegramPostingFrequencyProduct(TG_CAPS_OFF)).toBe("Off");
  });
});

describe("telegramReplyVolumeProduct", () => {
  it("returns 'Off' when Telegram inbound is unavailable", () => {
    expect(telegramReplyVolumeProduct(TG_CAPS_OFF)).toBe("Off");
  });
});

describe("discordPostingFrequencyProduct", () => {
  it("returns 'Off' for empty Discord capabilities", () => {
    expect(discordPostingFrequencyProduct(DISCORD_CAPS_OFF)).toBe("Off");
  });
});

describe("discordReplyVolumeProduct", () => {
  it("always returns 'Off' (Discord replies are not yet available)", () => {
    expect(discordReplyVolumeProduct(DISCORD_CAPS_OFF)).toBe("Off");
  });
});

// ---- Persona status -------------------------------------------------------

describe("derivePersonaProductStatus", () => {
  it("flags voice as locked when the persona is read_only", () => {
    const status = derivePersonaProductStatus(persona({ read_only: true }));
    expect(status.voiceLocked).toBe(true);
    expect(status.headline).toBe("Test Persona");
    expect(status.detail).toMatch(/locked/i);
  });

  it("flags voice as unlocked otherwise", () => {
    const status = derivePersonaProductStatus(persona({ read_only: false }));
    expect(status.voiceLocked).toBe(false);
    expect(status.detail).not.toMatch(/locked/i);
  });
});
