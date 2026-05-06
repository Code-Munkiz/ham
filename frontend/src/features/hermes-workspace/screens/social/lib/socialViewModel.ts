import type {
  DiscordCapabilities,
  SocialMessagingProviderStatus,
  SocialPersona,
  SocialPreviewResponse,
  SocialProvider,
  SocialSnapshot,
  TelegramCapabilities,
  XCapabilities,
  XProviderStatus,
} from "../../../adapters/socialAdapter";

export type HamgomoonStatus = "Active" | "Paused" | "Needs setup";

export type FourMode = "Off" | "Preview" | "Approval required" | "Autopilot";

export type FrequencyBand = "Off" | "Low" | "Standard" | "High";

/** Product-facing mode labels (UI). Internal logic still uses `FourMode` (“Preview”). */
export type ProductMode = "Off" | "Preview only" | "Approval required" | "Autopilot";

export type ProductFrequency = "Off" | "Low" | "Standard" | "High" | "Custom";

export type ProductReplyVolume = "Off" | "Low" | "Standard" | "High" | "Custom";

export type ProductProviderReadiness =
  | "Ready"
  | "Needs setup"
  | "Limited"
  | "Blocked"
  | "Coming soon";

export function fourModeToProduct(mode: FourMode): ProductMode {
  if (mode === "Preview") return "Preview only";
  return mode;
}

function modeToFrequencyHeuristic(mode: FourMode): ProductFrequency {
  if (mode === "Off") return "Off";
  if (mode === "Preview") return "Low";
  if (mode === "Approval required") return "Standard";
  return "High";
}

function modeToReplyVolumeHeuristic(mode: FourMode): ProductReplyVolume {
  if (mode === "Off") return "Off";
  if (mode === "Preview") return "Low";
  if (mode === "Approval required") return "Standard";
  return "High";
}

export function mapCoreReadiness(
  r: "ready" | "limited" | "blocked" | "setup_required",
): ProductProviderReadiness {
  if (r === "ready") return "Ready";
  if (r === "setup_required") return "Needs setup";
  if (r === "limited") return "Limited";
  return "Blocked";
}

/** Combines catalog provider card with deep readiness for product copy. */
export function resolveProviderReadiness(
  snapshot: SocialSnapshot,
  channelId: "x" | "telegram" | "discord",
): ProductProviderReadiness {
  const card = snapshot.providers.find((p) => p.id === channelId);
  if (card?.coming_soon || card?.status === "coming_soon") return "Coming soon";
  if (card?.status === "blocked") return "Blocked";
  if (channelId === "x") {
    const deep = mapCoreReadiness(snapshot.xStatus.overall_readiness);
    if (card?.status === "setup_required") return "Needs setup";
    return deep;
  }
  if (channelId === "telegram") {
    const deep = mapCoreReadiness(snapshot.telegramStatus.overall_readiness);
    if (card?.status === "setup_required") return "Needs setup";
    return deep;
  }
  const deep = mapCoreReadiness(snapshot.discordStatus.overall_readiness);
  if (card?.status === "setup_required") return "Needs setup";
  return deep;
}

export function derivePostingFrequencyProduct(x: XProviderStatus): ProductFrequency {
  if (!x.broadcast_lane.enabled) return "Off";
  const cap = x.cap_cooldown_summary.broadcast_daily_cap;
  const spacing = x.cap_cooldown_summary.broadcast_min_spacing_minutes;
  const perRun = x.cap_cooldown_summary.broadcast_per_run_cap;
  const custom = cap <= 0 || perRun > 3 || spacing < 5 || spacing > 360;
  if (custom) return "Custom";
  return derivePostFrequencyBand(x);
}

export function deriveReplyVolumeProduct(x: XProviderStatus): ProductReplyVolume {
  if (!x.reactive_lane.enabled) return "Off";
  const h = x.cap_cooldown_summary.reactive_max_replies_per_hour;
  const m15 = x.cap_cooldown_summary.reactive_max_replies_per_15m;
  const batch = x.cap_cooldown_summary.reactive_batch_max_replies_per_run;
  const minSec = x.cap_cooldown_summary.reactive_min_seconds_between_replies;
  if (h > 60 || m15 > 20 || batch > 5 || minSec < 15) return "Custom";
  if (h <= 6 && m15 <= 2) return "Low";
  if (h <= 24 && m15 <= 8) return "Standard";
  return "High";
}

export function telegramPostingFrequencyProduct(cap: TelegramCapabilities): ProductFrequency {
  return modeToFrequencyHeuristic(telegramPostingMode(cap));
}

export function telegramReplyVolumeProduct(cap: TelegramCapabilities): ProductReplyVolume {
  return modeToReplyVolumeHeuristic(telegramReplyMode(cap));
}

export function discordPostingFrequencyProduct(cap: DiscordCapabilities): ProductFrequency {
  return modeToFrequencyHeuristic(discordPostingMode(cap));
}

export function discordReplyVolumeProduct(_cap: DiscordCapabilities): ProductReplyVolume {
  return "Off";
}

export type ChannelProductTruth = {
  channelId: "x" | "telegram" | "discord";
  readiness: ProductProviderReadiness;
  postingMode: ProductMode;
  replyMode: ProductMode;
  postingFrequency: ProductFrequency;
  replyVolume: ProductReplyVolume;
  autopilotLine: string;
  nextHint: string;
};

function channelNextHint(
  snapshot: SocialSnapshot,
  channelId: "x" | "telegram" | "discord",
): string {
  if (snapshot.xStatus.emergency_stop.enabled && channelId === "x") {
    return "Clear emergency stop before live X posting or replies.";
  }
  if (channelId === "x") {
    const first = snapshot.xSetupSummary.recommended_next_steps[0];
    if (snapshot.xStatus.overall_readiness === "setup_required" && first) return first;
    if (snapshot.xStatus.overall_readiness === "limited" && first) return first;
    if (snapshot.xSetupSummary.ready_for_dry_run)
      return "Run a broadcast preflight or inbox preview on X.";
    return "Finish X setup to unlock previews and sends.";
  }
  if (channelId === "telegram") {
    const first =
      snapshot.telegramStatus.recommended_next_steps[0] ||
      snapshot.telegramSetup.recommended_next_steps[0];
    if (snapshot.telegramStatus.overall_readiness === "setup_required" && first) return first;
    if (snapshot.telegramStatus.overall_readiness === "limited" && first) return first;
    if (snapshot.telegramCapabilities.preview_available)
      return "Preview a Telegram message or check inbox.";
    return "Finish Telegram bot and gateway setup.";
  }
  const first =
    snapshot.discordStatus.recommended_next_steps[0] ||
    snapshot.discordSetup.recommended_next_steps[0];
  if (snapshot.discordStatus.overall_readiness === "setup_required" && first) return first;
  return "Discord is preview-only for now; follow setup guidance.";
}

export function deriveChannelProductTruth(
  snapshot: SocialSnapshot,
  channelId: "x" | "telegram" | "discord",
): ChannelProductTruth {
  const readiness = resolveProviderReadiness(snapshot, channelId);
  if (channelId === "x") {
    const x = snapshot.xStatus;
    const caps = snapshot.xCapabilities;
    const postM = fourModeToProduct(xPostingMode(x, caps));
    const replyM = fourModeToProduct(xReplyMode(x, caps));
    const postAuto = postM === "Autopilot";
    const replyAuto = replyM === "Autopilot";
    let autopilotLine = "Posts and replies follow approval or preview gates.";
    if (postAuto && replyAuto)
      autopilotLine = "Posts and replies can run on autopilot within safety caps.";
    else if (postAuto)
      autopilotLine = "Posting can autopilot; replies still follow your reply mode.";
    else if (replyAuto)
      autopilotLine = "Replies can autopilot; posting still follows your posting mode.";
    return {
      channelId,
      readiness,
      postingMode: postM,
      replyMode: replyM,
      postingFrequency: derivePostingFrequencyProduct(x),
      replyVolume: deriveReplyVolumeProduct(x),
      autopilotLine,
      nextHint: channelNextHint(snapshot, channelId),
    };
  }
  if (channelId === "telegram") {
    const cap = snapshot.telegramCapabilities;
    const postM = fourModeToProduct(telegramPostingMode(cap));
    const replyM = fourModeToProduct(telegramReplyMode(cap));
    return {
      channelId,
      readiness,
      postingMode: postM,
      replyMode: replyM,
      postingFrequency: telegramPostingFrequencyProduct(cap),
      replyVolume: telegramReplyVolumeProduct(cap),
      autopilotLine:
        postM === "Autopilot" || replyM === "Autopilot"
          ? "Autopilot-style lanes are on where the API allows; confirmations still apply for live sends."
          : "Telegram uses previews first, then your confirmation path for live sends.",
      nextHint: channelNextHint(snapshot, channelId),
    };
  }
  const cap = snapshot.discordCapabilities;
  const postM = fourModeToProduct(discordPostingMode(cap));
  const replyM = fourModeToProduct(discordReplyMode(cap));
  return {
    channelId,
    readiness,
    postingMode: postM,
    replyMode: replyM,
    postingFrequency: discordPostingFrequencyProduct(cap),
    replyVolume: discordReplyVolumeProduct(cap),
    autopilotLine: "Discord messaging is not fully available yet.",
    nextHint: channelNextHint(snapshot, channelId),
  };
}

export function deriveAutopilotSummary(snapshot: SocialSnapshot): string {
  const x = snapshot.xStatus;
  const caps = snapshot.xCapabilities;
  const xPost = fourModeToProduct(xPostingMode(x, caps));
  const xReply = fourModeToProduct(xReplyMode(x, caps));
  const tgPost = fourModeToProduct(telegramPostingMode(snapshot.telegramCapabilities));
  const tgReply = fourModeToProduct(telegramReplyMode(snapshot.telegramCapabilities));
  if (snapshot.xStatus.emergency_stop.enabled) {
    return "Autopilot is effectively off for X while emergency stop is on.";
  }
  const xAuto = xPost === "Autopilot" || xReply === "Autopilot";
  const tgAuto = tgPost === "Autopilot" || tgReply === "Autopilot";
  if (xAuto && tgAuto) return "X and Telegram have autopilot-capable lanes where policy allows.";
  if (xAuto) return "X has autopilot-capable lanes; Telegram follows its own mode.";
  if (tgAuto) return "Telegram has autopilot-capable lanes; X follows its own mode.";
  return "No channel is in full autopilot for both posting and replies; previews and approvals still apply.";
}

export function deriveSafetyProductLines(snapshot: SocialSnapshot): string[] {
  const persona = snapshot.persona;
  const lines: string[] = ["Safety checks on"];
  if (persona.read_only) lines.push("Voice locked to the canonical persona");
  lines.push("Approval required for live sends");
  lines.push(
    snapshot.xStatus.emergency_stop.enabled
      ? "Emergency stop on (X sends paused)"
      : "Emergency stop off",
  );
  lines.push(
    snapshot.xCapabilities.live_apply_available
      ? "Live actions gated (operator token + confirmation)"
      : "Live actions gated on this host",
  );
  return lines;
}

export type PersonaProductStatus = {
  headline: string;
  detail: string;
  voiceLocked: boolean;
};

export function derivePersonaProductStatus(persona: SocialPersona): PersonaProductStatus {
  return {
    headline: persona.display_name,
    detail: persona.read_only
      ? "Voice is locked; edits happen outside this cockpit."
      : "Persona can be edited via your usual workflow.",
    voiceLocked: Boolean(persona.read_only),
  };
}

export function deriveNextRecommendedAction(snapshot: SocialSnapshot): string {
  if (snapshot.xStatus.emergency_stop.enabled) {
    return "Turn off emergency stop for X when you are ready for live sends again.";
  }
  const xFirst = snapshot.xSetupSummary.recommended_next_steps[0];
  const tgFirst =
    snapshot.telegramStatus.recommended_next_steps[0] ||
    snapshot.telegramSetup.recommended_next_steps[0];

  if (snapshot.telegramStatus.overall_readiness === "blocked") {
    return tgFirst || "Fix Telegram connection — open Channels → Telegram → Setup.";
  }
  if (snapshot.xStatus.overall_readiness === "blocked") {
    return xFirst || "Fix X credentials or operator readiness.";
  }
  if (snapshot.telegramStatus.overall_readiness === "setup_required") {
    return tgFirst || "Finish connecting Telegram (open Channels → Telegram → Setup).";
  }
  if (snapshot.xStatus.overall_readiness === "setup_required") {
    return xFirst || "Finish X setup (credentials and operator readiness).";
  }
  if (snapshot.telegramStatus.overall_readiness === "limited") {
    return tgFirst || "Improve Telegram connection health.";
  }
  if (snapshot.xStatus.overall_readiness === "limited") {
    return xFirst || "Review X limits or optional setup gaps.";
  }
  if (snapshot.discordStatus.overall_readiness === "setup_required") {
    const dFirst =
      snapshot.discordStatus.recommended_next_steps[0] ||
      snapshot.discordSetup.recommended_next_steps[0];
    return dFirst || "Complete Discord setup steps.";
  }
  return "Preview an X post or check Telegram inbox to see the next safe step.";
}

export function deriveWhatHamCanDoNow(snapshot: SocialSnapshot): string[] {
  const lines: string[] = [];
  if (snapshot.xStatus.emergency_stop.enabled) {
    lines.push("Review X status and drafts only — live X sends stay paused.");
  } else {
    if (snapshot.xSetupSummary.ready_for_dry_run)
      lines.push("Preview X broadcasts and scan the reply inbox.");
    if (
      snapshot.xSetupSummary.ready_for_confirmed_live_reply &&
      snapshot.xCapabilities.reactive_reply_apply_available
    ) {
      lines.push("Send a confirmed X reply when you have an approved preview.");
    }
    if (
      snapshot.xSetupSummary.ready_for_broadcast &&
      snapshot.xCapabilities.broadcast_apply_available
    ) {
      lines.push("Send a confirmed X post when you have an approved preview.");
    }
  }
  if (snapshot.telegramCapabilities.preview_available)
    lines.push("Draft and preview Telegram outbound messages.");
  if (snapshot.telegramCapabilities.inbound_available)
    lines.push("Inspect Telegram inbox and suggested replies.");
  const discord = snapshot.providers.find((p: SocialProvider) => p.id === "discord");
  if (discord && !discord.coming_soon) lines.push("Check Discord setup and preview-only guidance.");
  return lines.length ? lines : ["Complete channel setup, then refresh status."];
}

export function deriveWhatNeedsSetup(snapshot: SocialSnapshot): string[] {
  const lines: string[] = [];
  for (const p of snapshot.providers) {
    if (!["x", "telegram", "discord"].includes(p.id)) continue;
    if (p.coming_soon || p.status === "coming_soon") {
      lines.push(`${p.label}: coming soon.`);
      continue;
    }
    if (p.status === "setup_required")
      lines.push(`${p.label}: finish setup before full operation.`);
    if (p.status === "blocked") lines.push(`${p.label}: blocked — see readiness messages.`);
  }
  if (snapshot.xStatus.overall_readiness === "setup_required") {
    const s = snapshot.xSetupSummary.recommended_next_steps[0];
    if (s) lines.push(`X: ${s}`);
  }
  if (snapshot.telegramStatus.overall_readiness === "setup_required") {
    const s = snapshot.telegramStatus.recommended_next_steps[0];
    if (s) lines.push(`Telegram: ${s}`);
  }
  return lines.length ? lines : ["No blocking setup items reported."];
}

export type ContentStyle = "Updates" | "Announcements" | "Campaign posts";

export function deriveHamgomoonStatus(snapshot: SocialSnapshot): HamgomoonStatus {
  if (snapshot.xStatus.emergency_stop.enabled) return "Paused";
  const core = snapshot.providers.filter((p) => ["x", "telegram", "discord"].includes(p.id));
  if (core.some((p) => p.status !== "active")) return "Needs setup";
  return "Active";
}

function fourModeFromLanes(opts: {
  laneOn: boolean;
  previewOk: boolean;
  liveOk: boolean;
  autopilotOk: boolean;
}): FourMode {
  if (!opts.laneOn) return "Off";
  if (!opts.previewOk && !opts.liveOk) return "Off";
  if (opts.previewOk && !opts.liveOk) return "Preview";
  if (opts.liveOk && opts.autopilotOk) return "Autopilot";
  return "Approval required";
}

export function derivePostFrequencyBand(x: XProviderStatus): FrequencyBand {
  if (!x.broadcast_lane.enabled) return "Off";
  const cap = x.cap_cooldown_summary.broadcast_daily_cap;
  const used = x.cap_cooldown_summary.broadcast_daily_used;
  if (cap <= 0) return "Standard";
  const ratio = used / cap;
  if (ratio < 0.25) return "Low";
  if (ratio < 0.65) return "Standard";
  return "High";
}

export function telegramPostingMode(cap: TelegramCapabilities): FourMode {
  if (!cap.preview_available && !cap.live_message_available && !cap.activity_apply_available)
    return "Off";
  if (cap.preview_available && !cap.live_apply_available) return "Preview";
  if (cap.live_apply_available) return "Approval required";
  return "Preview";
}

export function telegramReplyMode(cap: TelegramCapabilities): FourMode {
  if (!cap.inbound_available) return "Off";
  if (!cap.reactive_reply_apply_available) return "Preview";
  return "Approval required";
}

export function discordPostingMode(cap: DiscordCapabilities): FourMode {
  if (!cap.preview_available) return "Off";
  return "Preview";
}

export function discordReplyMode(_cap: DiscordCapabilities): FourMode {
  return "Off";
}

export function deriveContentStyle(persona: SocialPersona): ContentStyle {
  const ann = persona.example_announcements?.length ?? 0;
  if (ann >= 4) return "Campaign posts";
  if (ann >= 1) return "Announcements";
  return "Updates";
}

export function xPostingMode(x: XProviderStatus, caps: XCapabilities): FourMode {
  return fourModeFromLanes({
    laneOn: x.broadcast_lane.enabled,
    previewOk: x.broadcast_lane.dry_run_available,
    liveOk: caps.broadcast_apply_available && x.broadcast_lane.live_configured,
    autopilotOk:
      x.broadcast_lane.live_controller_enabled &&
      x.broadcast_lane.execution_allowed_now &&
      !x.dry_run_defaults.global_dry_run,
  });
}

export function xReplyMode(x: XProviderStatus, caps: XCapabilities): FourMode {
  return fourModeFromLanes({
    laneOn: x.reactive_lane.enabled,
    previewOk: x.reactive_lane.dry_run_enabled,
    liveOk: caps.reactive_reply_apply_available || caps.reactive_batch_apply_available,
    autopilotOk:
      x.reactive_lane.batch_enabled &&
      x.reactive_lane.live_canary_enabled &&
      !x.dry_run_defaults.reactive_dry_run,
  });
}

export type ChannelSafetyHints = {
  voiceLocked: boolean;
  approvalRequired: boolean;
  emergencyStop: boolean;
  noLinksUnlessEnabled: boolean;
  noFinancialAdvice: boolean;
  noBuySellLanguage: boolean;
};

export function personaSafetyHints(persona: SocialPersona): ChannelSafetyHints {
  const blob = [...persona.prohibited_content, ...persona.safety_boundaries, ...persona.tone_rules]
    .join(" ")
    .toLowerCase();
  return {
    voiceLocked: Boolean(persona.read_only),
    approvalRequired: true,
    emergencyStop: false,
    noLinksUnlessEnabled: /\b(link|url|http)\b/.test(blob),
    noFinancialAdvice: /\b(financial advice|investment advice|not financial advice)\b/.test(blob),
    noBuySellLanguage: /\b(buy|sell|price|token|coin|crypto|stock)\b/.test(blob),
  };
}

export function xSafetyHints(x: XProviderStatus, persona: SocialPersona): ChannelSafetyHints {
  const base = personaSafetyHints(persona);
  return {
    ...base,
    emergencyStop: x.emergency_stop.enabled,
  };
}

export function telegramSafetyHints(
  status: SocialMessagingProviderStatus,
  persona: SocialPersona,
): ChannelSafetyHints {
  const base = personaSafetyHints(persona);
  return { ...base, emergencyStop: false };
}

export function discordSafetyHints(persona: SocialPersona): ChannelSafetyHints {
  return { ...personaSafetyHints(persona), emergencyStop: false };
}

/** Human-readable excerpt from journal-ish records; avoids default JSON in primary UI. */
export function formatLooseRecordSummary(record: Record<string, unknown> | null): string | null {
  if (!record) return null;
  const keys = [
    "text",
    "message_text",
    "content",
    "body",
    "summary",
    "title",
    "output",
    "tweet_text",
    "reply_text",
  ];
  for (const k of keys) {
    const v = record[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return null;
}

export function operatingModeSummary(snapshot: SocialSnapshot): string {
  const st = deriveHamgomoonStatus(snapshot);
  if (st === "Paused")
    return "Emergency stop is on — sending is paused until you turn it off in runtime config.";
  if (st === "Needs setup")
    return "One or more channels still need setup before Ham can run at full strength.";
  return "Ham is running with previews first, confirmed sends second, and voice locked to the canonical persona.";
}

export type SocialProductTruth = {
  hamStatus: HamgomoonStatus;
  autopilotSummary: string;
  safetyLines: string[];
  /** Short, non-technical summary of topics the voice avoids (from persona). */
  voiceBoundariesLine: string;
  persona: PersonaProductStatus;
  nextAction: string;
  canDoNow: string[];
  needsSetup: string[];
};

/** Product-facing line for Overview safety (blocked topics / refusals). */
export function deriveVoiceBoundariesOverviewLine(persona: SocialPersona): string {
  const blocked = personaBlockedTopicsSummary(persona, 4);
  if (blocked === "Covered in persona rules") {
    return "Ham avoids topics and requests defined in the full persona — open Persona for the refusal list.";
  }
  return `Examples of what Ham won’t say: ${blocked}`;
}

/** Telegram: governor.allowed — no timestamps; use in primary operate UI. */
export function telegramPacingProductPill(allowed: boolean): {
  label: string;
  tone: "ok" | "warn";
} {
  if (allowed) return { label: "Ready to continue", tone: "ok" };
  return { label: "Ham is pacing sends", tone: "warn" };
}

/** Telegram: stricter line when a live/approval step is in scope. */
export function telegramApprovalWindowProductPill(allowed: boolean): {
  label: string;
  tone: "ok" | "warn";
} {
  if (allowed) return { label: "Ready for operator approval", tone: "ok" };
  return { label: "Waiting for the next safe send window", tone: "warn" };
}

export function buildSocialProductTruth(snapshot: SocialSnapshot): SocialProductTruth {
  return {
    hamStatus: deriveHamgomoonStatus(snapshot),
    autopilotSummary: deriveAutopilotSummary(snapshot),
    safetyLines: deriveSafetyProductLines(snapshot),
    voiceBoundariesLine: deriveVoiceBoundariesOverviewLine(snapshot.persona),
    persona: derivePersonaProductStatus(snapshot.persona),
    nextAction: deriveNextRecommendedAction(snapshot),
    canDoNow: deriveWhatHamCanDoNow(snapshot),
    needsSetup: deriveWhatNeedsSetup(snapshot),
  };
}

/** Operator-facing line for X preview cards (no API field names). */
export function friendlyXPreviewStatus(preview: SocialPreviewResponse): {
  label: string;
  tone: "ok" | "warn" | "danger" | "muted";
} {
  if (preview.status === "blocked") return { label: "Held by safety", tone: "warn" };
  if (preview.status === "failed") return { label: "Needs attention", tone: "danger" };
  if (preview.proposal_digest) return { label: "Ready for your approval path", tone: "ok" };
  return { label: "Complete a preview first", tone: "muted" };
}

/** Telegram-style preview status for draft cards (no API field names in labels). */
export function friendlyDraftStatus(
  status: "completed" | "blocked" | "failed",
  hasProposalDigest: boolean,
): { label: string; tone: "ok" | "warn" | "danger" | "muted" } {
  if (status === "blocked") return { label: "Held by safety", tone: "warn" };
  if (status === "failed") return { label: "Needs attention", tone: "danger" };
  if (hasProposalDigest) return { label: "Ready for operator approval", tone: "ok" };
  return { label: "Needs preview", tone: "muted" };
}

export function personaBlockedTopicsSummary(persona: SocialPersona, maxItems = 4): string {
  const items = persona.prohibited_content.slice(0, maxItems);
  if (!items.length) return "Covered in persona rules";
  return items.join(" · ");
}
