import * as React from "react";
import { AlertTriangle, CheckCircle2, Circle, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  socialAdapter,
  type DiscordCapabilities,
  type SocialBroadcastApplyResponse,
  type SocialMessagingProviderStatus,
  type SocialMessagingSetupChecklist,
  type SocialPersona,
  type SocialReactiveBatchApplyResponse,
  type SocialReactiveReplyApplyResponse,
  type SocialPreviewKind,
  type SocialPreviewResponse,
  type SocialProvider,
  type SocialSnapshot,
  type TelegramCapabilities,
  type TelegramActivityApplyResponse,
  type TelegramActivityPreviewResponse,
  type TelegramActivityRunOncePreviewResponse,
  type TelegramInboundPreviewResponse,
  type TelegramMessageApplyResponse,
  type TelegramMessagePreviewResponse,
  type TelegramReactiveReplyApplyResponse,
  type TelegramReactiveRepliesPreviewResponse,
  type XCapabilities,
} from "../../adapters/socialAdapter";
import { WorkspaceSurfaceHeader, WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";
import { SOCIAL_COPY } from "./lib/socialCopy";
import {
  buildSocialProductTruth,
  deriveChannelProductTruth,
  deriveContentStyle,
  discordSafetyHints,
  formatLooseRecordSummary,
  friendlyDraftStatus,
  friendlyXPreviewStatus,
  operatingModeSummary,
  personaBlockedTopicsSummary,
  resolveProviderReadiness,
  telegramApprovalWindowProductPill,
  telegramPacingProductPill,
  telegramSafetyHints,
  type ProductProviderReadiness,
  xSafetyHints,
} from "./lib/socialViewModel";

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function TechnicalProofIntro() {
  return (
    <div className="col-span-full rounded-xl border border-amber-400/25 bg-amber-500/5 p-3 text-sm leading-relaxed text-amber-50/90">
      {SOCIAL_COPY.technicalProofWarning}
    </div>
  );
}

function humanTelegramChatLabel(chatType?: string | null): string {
  if (!chatType) return "Telegram conversation";
  const t = chatType.toLowerCase();
  if (t === "group" || t === "supergroup") return "Telegram group";
  if (t === "channel") return "Telegram channel";
  if (t === "private") return "Direct message";
  return `${titleCase(chatType)} chat`;
}

function friendlyApplyOutcome(record: Record<string, unknown> | null): { summary: string; statusLine: string | null } {
  if (!record) return { summary: "No result details were returned for this action.", statusLine: null };
  const statusRaw = record.status;
  const statusLine = typeof statusRaw === "string" ? `Status: ${titleCase(statusRaw)}` : null;
  const text = formatLooseRecordSummary(record);
  const summary =
    text ||
    (statusLine
      ? "Ham finished this step. Open Advanced technical proof if you need the full raw response."
      : "Ham finished this step.");
  return { summary, statusLine };
}

function FriendlyLiveOutcomeCard({ title, record }: { title: string; record: Record<string, unknown> | null }) {
  const { summary, statusLine } = friendlyApplyOutcome(record);
  return (
    <section className="rounded-2xl border border-white/10 bg-black/20 p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-white/85">{title}</h3>
      {statusLine ? <p className="mt-1 text-xs text-white/48">{statusLine}</p> : null}
      <p className="mt-3 text-sm leading-relaxed text-white/75">{summary}</p>
      <p className="mt-2 text-xs text-white/42">Full technical detail lives under Advanced technical proof.</p>
    </section>
  );
}

function statusTone(status: string): "ok" | "warn" | "danger" | "muted" {
  if (status === "active" || status === "ready") return "ok";
  if (status === "blocked") return "danger";
  if (status === "coming_soon") return "muted";
  return "warn";
}

function StatusPill({ label, tone = "muted" }: { label: string; tone?: "ok" | "warn" | "danger" | "muted" }) {
  const cls =
    tone === "ok"
      ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-100"
      : tone === "danger"
        ? "border-red-400/25 bg-red-500/10 text-red-100"
        : tone === "warn"
          ? "border-amber-400/25 bg-amber-500/10 text-amber-100"
          : "border-white/10 bg-white/[0.04] text-white/55";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", cls)}>
      {label}
    </span>
  );
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm">
      <span className="text-white/68">{label}</span>
      <StatusPill label={value ? "Yes" : "No"} tone={value ? "ok" : "muted"} />
    </div>
  );
}

type SocialSelection = "persona" | "x" | "telegram" | "discord";
type SocialSection = "overview" | "channels" | "persona" | "activity" | "setup";
type ChannelDetailTab = "operate" | "inbox" | "activity" | "setup" | "advanced";

const SOCIAL_SECTIONS: { id: SocialSection; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "channels", label: "Channels" },
  { id: "persona", label: "Persona" },
  { id: "activity", label: "Activity" },
  { id: "setup", label: "Setup" },
];

const CHANNEL_DETAIL_TABS: { id: ChannelDetailTab; label: string }[] = [
  { id: "operate", label: "Preview & send" },
  { id: "inbox", label: "Inbox" },
  { id: "activity", label: "Activity" },
  { id: "setup", label: "Setup" },
  { id: "advanced", label: "Advanced technical proof" },
];

function readinessLabel(status: string): string {
  if (status === "active" || status === "ready") return "Ready";
  if (status === "setup_required") return "Needs setup";
  if (status === "coming_soon") return "Coming soon";
  if (status === "blocked") return "Held by safety check";
  return "Limited";
}

function productReadinessTone(status: ProductProviderReadiness): "ok" | "warn" | "danger" | "muted" {
  if (status === "Ready") return "ok";
  if (status === "Coming soon") return "muted";
  if (status === "Blocked") return "danger";
  if (status === "Limited" || status === "Needs setup") return "warn";
  return "muted";
}

function ProviderCard({
  provider,
  snapshot,
  selected = false,
  onSelect,
  lastActivity,
  primaryAction,
  warning,
}: {
  provider: SocialProvider;
  snapshot?: SocialSnapshot | null;
  selected?: boolean;
  onSelect?: () => void;
  lastActivity?: string;
  primaryAction?: string;
  warning?: string | null;
}) {
  const readinessProduct =
    snapshot && (provider.id === "x" || provider.id === "telegram" || provider.id === "discord")
      ? resolveProviderReadiness(snapshot, provider.id)
      : null;
  const readinessLabelText = readinessProduct ?? readinessLabel(provider.status);
  const tone = readinessProduct ? productReadinessTone(readinessProduct) : statusTone(provider.status);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "rounded-2xl border bg-black/25 p-4 text-left shadow-sm transition hover:border-white/25",
        selected ? "border-emerald-300/35" : "border-white/10",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-white/92">{provider.label}</div>
          <div className="mt-1 text-xs text-white/45">
            {provider.id === "x"
              ? "Ready for previews and confirmed actions."
              : provider.id === "telegram"
                ? "Ready for previews and confirmed actions."
                : provider.id === "discord"
                  ? "Setup guidance available. Messaging controls come later."
                  : "Future channel slot."}
          </div>
        </div>
        <StatusPill label={readinessLabelText} tone={tone} />
      </div>
      <div className="mt-4 space-y-2 text-sm">
        <div className="text-white/72">{lastActivity || "No recent activity reported."}</div>
        <div className="font-medium text-emerald-100">{primaryAction || "Open channel details"}</div>
        {warning ? <div className="rounded-lg border border-amber-400/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100/80">{warning}</div> : null}
      </div>
    </button>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-white/60">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function DetailsPanel({
  title,
  summary = SOCIAL_COPY.advancedDetailsSummary,
  children,
}: {
  title: string;
  summary?: string;
  children: React.ReactNode;
}) {
  return (
    <details className="rounded-2xl border border-white/10 bg-black/20 p-4 shadow-sm">
      <summary className="cursor-pointer list-none text-sm font-semibold uppercase tracking-[0.12em] text-white/60">
        {title}
        <span className="ml-2 text-xs font-normal normal-case tracking-normal text-white/38">{summary}</span>
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

function SectionTabs({
  selected,
  onSelect,
}: {
  selected: SocialSection;
  onSelect: (section: SocialSection) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/25 p-2">
      {SOCIAL_SECTIONS.map((section) => (
        <button
          key={section.id}
          type="button"
          onClick={() => onSelect(section.id)}
          className={cn(
            "rounded-xl px-3 py-2 text-sm font-medium transition",
            selected === section.id
              ? "bg-emerald-400/15 text-emerald-50"
              : "text-white/58 hover:bg-white/[0.06] hover:text-white/82",
          )}
        >
          {section.label}
        </button>
      ))}
    </div>
  );
}

function ChannelDetailTabs({
  selected,
  onSelect,
}: {
  selected: ChannelDetailTab;
  onSelect: (tab: ChannelDetailTab) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/25 p-2">
      {CHANNEL_DETAIL_TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onSelect(tab.id)}
          className={cn(
            "rounded-xl px-3 py-2 text-sm font-medium transition",
            selected === tab.id
              ? "bg-white/12 text-white"
              : "text-white/58 hover:bg-white/[0.06] hover:text-white/82",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function GlobalStatusStrip({ snapshot }: { snapshot: SocialSnapshot }) {
  const truth = buildSocialProductTruth(snapshot);
  const hamTone =
    truth.hamStatus === "Active" ? "ok" : truth.hamStatus === "Paused" ? "danger" : "warn";
  const core = ["x", "telegram", "discord"] as const;
  const readyCount = core.filter((id) => resolveProviderReadiness(snapshot, id) === "Ready").length;
  return (
    <div className="grid gap-2 rounded-2xl border border-white/10 bg-black/25 p-3 sm:grid-cols-2 xl:grid-cols-3">
      <StatusPill label={`Ham: ${truth.hamStatus}`} tone={hamTone} />
      <StatusPill
        label={`Providers ready: ${readyCount} / ${core.length}`}
        tone={readyCount === core.length ? "ok" : "warn"}
      />
      <StatusPill
        label={snapshot.xStatus.emergency_stop.enabled ? "Emergency stop on (X)" : "Emergency stop off"}
        tone={snapshot.xStatus.emergency_stop.enabled ? "danger" : "ok"}
      />
      <div className="col-span-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/78 sm:col-span-2 xl:col-span-3">
        <span className="text-white/45">Next · </span>
        {truth.nextAction}
      </div>
      <div className="col-span-full flex flex-wrap gap-2 text-xs text-white/52">
        {truth.safetyLines.map((line) => (
          <span key={line} className="rounded-lg border border-white/10 bg-black/25 px-2 py-1">
            {line}
          </span>
        ))}
      </div>
    </div>
  );
}

function SettingsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm">
      <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/50">{title}</h3>
      <div className="mt-3 space-y-1 text-sm">{children}</div>
    </section>
  );
}

function SettingsRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-white/5 py-2 last:border-0">
      <span className="text-white/55">{label}</span>
      <span className="max-w-[55%] text-right font-medium text-white/88">{value}</span>
    </div>
  );
}

function KeyValueGrid({ rows }: { rows: { label: string; value: React.ReactNode }[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {rows.map((row) => (
        <div key={row.label} className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">{row.label}</div>
          <div className="mt-1 break-words text-sm text-white/82">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

function RecordPreview({ record, emptyLabel }: { record: Record<string, unknown> | null; emptyLabel: string }) {
  if (!record) {
    return <p className="text-sm text-white/45">{emptyLabel}</p>;
  }
  return (
    <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/30 p-3 text-[11px] leading-relaxed text-white/70">
      {JSON.stringify(record, null, 2)}
    </pre>
  );
}

function CapabilityRows({ capabilities }: { capabilities: XCapabilities }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <BoolRow label="Inbox checks configured" value={capabilities.live_read_available} />
      <BoolRow label="Model preview configured" value={capabilities.live_model_available} />
      <BoolRow label="X post preview configured" value={capabilities.broadcast_dry_run_available} />
      <BoolRow label="Confirmed post sending configured" value={capabilities.broadcast_live_available} />
      <BoolRow label="X inbox checks configured" value={capabilities.reactive_inbox_discovery_available} />
      <BoolRow label="Reply preview configured" value={capabilities.reactive_dry_run_available} />
      <BoolRow label="One-reply confirmation configured" value={capabilities.reactive_reply_canary_available} />
      <BoolRow label="Reply batch preview configured" value={capabilities.reactive_batch_available} />
      <BoolRow label="Live actions require confirmation" value={capabilities.live_apply_available} />
      <BoolRow label="Status API available" value={capabilities.read_only} />
    </div>
  );
}

function MessagingCapabilityRows({ capabilities }: { capabilities: TelegramCapabilities | DiscordCapabilities }) {
  const sharedRows = [
    { label: "Bot token present", value: capabilities.bot_token_present },
    { label: "Inbox checks configured", value: capabilities.inbound_available },
    { label: "Previews configured", value: capabilities.preview_available },
    { label: "Confirmed message sending configured", value: capabilities.live_message_available },
    { label: "Live actions require confirmation", value: capabilities.live_apply_available },
    { label: "Confirmed activity sending configured", value: capabilities.provider_id === "telegram" ? capabilities.activity_apply_available : false },
    { label: "Status API available", value: capabilities.read_only },
  ];
  const providerRows =
    capabilities.provider_id === "telegram"
      ? [
          { label: "Allowed users configured", value: capabilities.allowed_users_configured },
          { label: "Home channel configured", value: capabilities.home_channel_configured },
          { label: "Polling supported", value: capabilities.polling_supported },
          { label: "Webhook supported", value: capabilities.webhook_supported },
          { label: "Groups supported", value: capabilities.groups_supported },
          { label: "Topics supported", value: capabilities.topics_supported },
          { label: "Media supported", value: capabilities.media_supported },
          { label: "Voice supported", value: capabilities.voice_supported },
        ]
      : [
          { label: "Allowed users or roles configured", value: capabilities.allowed_users_or_roles_configured },
          { label: "Guild or channel configured", value: capabilities.guild_or_channel_configured },
          { label: "DMs supported", value: capabilities.dms_supported },
          { label: "Channels supported", value: capabilities.channels_supported },
          { label: "Threads supported", value: capabilities.threads_supported },
          { label: "Slash commands supported", value: capabilities.slash_commands_supported },
          { label: "Media supported", value: capabilities.media_supported },
          { label: "Voice supported", value: capabilities.voice_supported },
        ];
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {[...providerRows, ...sharedRows].map((row) => (
        <BoolRow key={row.label} label={row.label} value={row.value} />
      ))}
    </div>
  );
}

function MessagingProviderPanel({
  status,
  capabilities,
  setup,
  activeTab,
  telegramPreview,
  telegramPreviewBusy = false,
  telegramPreviewError,
  onPreviewTelegram,
  telegramActivityPreview,
  telegramActivityPreviewBusy = false,
  telegramActivityPreviewError,
  onPreviewTelegramActivity,
  telegramActivityRunOncePreview,
  telegramActivityRunOncePreviewBusy = false,
  telegramActivityRunOncePreviewError,
  onPreviewTelegramActivityRunOnce,
  telegramInboundPreview,
  telegramInboundPreviewBusy = false,
  telegramInboundPreviewError,
  onPreviewTelegramInbound,
  telegramReactivePreview,
  telegramReactivePreviewBusy = false,
  telegramReactivePreviewError,
  onPreviewTelegramReactive,
  onOpenTelegramReactiveLiveConfirm,
  telegramReactiveLiveResult,
  telegramReactiveLiveError,
  onOpenTelegramActivityLiveConfirm,
  telegramActivityLiveResult,
  telegramActivityLiveError,
  onOpenTelegramLiveConfirm,
  telegramLiveResult,
  telegramLiveError,
}: {
  status: SocialMessagingProviderStatus;
  capabilities: TelegramCapabilities | DiscordCapabilities;
  setup: SocialMessagingSetupChecklist;
  activeTab: ChannelDetailTab;
  telegramPreview?: TelegramMessagePreviewResponse | null;
  telegramPreviewBusy?: boolean;
  telegramPreviewError?: string | null;
  onPreviewTelegram?: () => void;
  telegramActivityPreview?: TelegramActivityPreviewResponse | null;
  telegramActivityPreviewBusy?: boolean;
  telegramActivityPreviewError?: string | null;
  onPreviewTelegramActivity?: () => void;
  telegramActivityRunOncePreview?: TelegramActivityRunOncePreviewResponse | null;
  telegramActivityRunOncePreviewBusy?: boolean;
  telegramActivityRunOncePreviewError?: string | null;
  onPreviewTelegramActivityRunOnce?: () => void;
  telegramInboundPreview?: TelegramInboundPreviewResponse | null;
  telegramInboundPreviewBusy?: boolean;
  telegramInboundPreviewError?: string | null;
  onPreviewTelegramInbound?: () => void;
  telegramReactivePreview?: TelegramReactiveRepliesPreviewResponse | null;
  telegramReactivePreviewBusy?: boolean;
  telegramReactivePreviewError?: string | null;
  onPreviewTelegramReactive?: () => void;
  onOpenTelegramReactiveLiveConfirm?: (item: TelegramReactiveRepliesPreviewResponse["items"][number]) => void;
  telegramReactiveLiveResult?: TelegramReactiveReplyApplyResponse | null;
  telegramReactiveLiveError?: string | null;
  onOpenTelegramActivityLiveConfirm?: () => void;
  telegramActivityLiveResult?: TelegramActivityApplyResponse | null;
  telegramActivityLiveError?: string | null;
  onOpenTelegramLiveConfirm?: () => void;
  telegramLiveResult?: TelegramMessageApplyResponse | null;
  telegramLiveError?: string | null;
}) {
  const isTelegram = status.provider_id === "telegram";
  const telegramCapabilities = capabilities.provider_id === "telegram" ? capabilities : null;
  const canSendOneTelegramMessage = Boolean(
    telegramPreview?.proposal_digest && telegramCapabilities?.readiness === "ready" && telegramCapabilities.live_apply_available,
  );
  const canSendOneTelegramActivity = Boolean(
    telegramActivityPreview?.proposal_digest &&
      telegramActivityPreview?.governor.allowed &&
      telegramCapabilities?.readiness === "ready" &&
      telegramCapabilities?.activity_apply_available,
  );
  const telegramReactiveLiveCandidates = (telegramReactivePreview?.items || []).filter(
    (item) =>
      Boolean(item.proposal_digest) &&
      item.policy.allowed &&
      item.governor.allowed &&
      telegramCapabilities?.readiness === "ready" &&
      telegramCapabilities?.reactive_reply_apply_available,
  );
  const guidance = isTelegram
    ? {
        title: "Telegram setup guidance",
        productIntro: [
          "Connect a Telegram bot so Ham has a clear identity to speak as.",
          "Confirm a private test group and make sure Ham can read messages there and send only when you approve.",
          "Use previews in this cockpit first — nothing sends without your confirmation flow.",
        ],
        technicalIntro: [
          "BotFather is Telegram’s official tool to create the bot username and issue a secret token. Store that token only on the trusted runtime that runs your Ham bridge — never paste it here.",
          "Ham’s messaging bridge must be running and reachable in your environment so Telegram traffic can flow through approved paths.",
        ],
        checklist: [
          "Connect Telegram bot (via BotFather)",
          "Store bot credentials only on the trusted runtime",
          "Create or confirm a private test group",
          "Add the bot to the test group with the right permissions",
          "Optional: add an announcement channel for later trials",
          "Review privacy mode for how the bot sees messages",
          "Plan allowed users/chats for early trials",
          "Verify Ham can read messages and preview sends in this cockpit",
        ],
        warningTitle: "What not to paste",
        warnings: ["Bot token", "Raw environment files", "Screenshots containing secrets", "Authorization headers"],
        noteTitle: "Why Ham may not respond yet",
        noteProduct:
          "The bot can exist in Telegram before Ham is fully wired. Work the checklist, then refresh until previews succeed.",
        noteTechnical:
          "On the API host, Telegram token and bridge configuration must be present before confirmed sends. This panel never collects those secrets.",
      }
    : {
        title: "Discord setup guidance",
        productIntro: [
          "Connect a Discord bot from the Developer Portal so Ham has an application identity.",
          "Invite the bot to a private test server and pick channels for safe trials.",
          "Use previews here first; confirmed sends stay behind your approval flow.",
        ],
        technicalIntro: [
          "The Developer Portal issues a secret bot token. Store it only on the trusted runtime that runs your Ham bridge — never paste it here.",
          "Server and channel routing must be configured on that host so Ham can read and send only through approved paths.",
        ],
        checklist: [
          "Create Discord application and bot",
          "Store bot credentials only on the trusted runtime",
          "Create or confirm a private test server",
          "Invite the bot with appropriate (minimal) permissions",
          "Create test channels for previews",
          "Review required intents for reading and replying",
          "Plan server/channel routing for Ham",
          "Verify Ham can read messages and run previews in this cockpit",
        ],
        warningTitle: "Safety note",
        warnings: [
          "Do not grant Administrator casually",
          "Do not paste the bot token into chat or Git",
          "Keep the server private until readiness passes",
        ],
        noteTitle: "Why Ham may not respond yet",
        noteProduct:
          "The bot can exist in a server before Ham is fully wired. Complete the checklist and refresh until setup turns green.",
        noteTechnical:
          "Bot token and routing must be stored securely on the runtime host and the messaging bridge must be connected before confirmed sends.",
      };
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {activeTab === "advanced" ? <TechnicalProofIntro /> : null}
      {activeTab === "advanced" ? (
      <Panel title={`${status.label} runtime snapshot`}>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <StatusPill label={titleCase(status.overall_readiness)} tone={statusTone(status.overall_readiness)} />
            <StatusPill label={status.read_only ? "Status check" : "Actions available"} tone={status.read_only ? "ok" : "danger"} />
            <StatusPill label={status.live_apply_available ? "Live actions require confirmation" : "Setup required for live actions"} tone={status.live_apply_available ? "warn" : "ok"} />
            <StatusPill
              label={status.mutation_attempted ? "Tried to send" : "No send attempted"}
              tone={status.mutation_attempted ? "danger" : "ok"}
            />
            <StatusPill
              label={status.hermes_gateway.provider_runtime_state === "connected" ? "Local bot connected" : "Local bot not connected"}
              tone={status.hermes_gateway.provider_runtime_state === "connected" ? "ok" : "warn"}
            />
          </div>
          {status.readiness_reasons.length ? (
            <div className="flex flex-wrap gap-2">
              {status.readiness_reasons.map((reason) => (
                <StatusPill key={reason} label={titleCase(reason)} tone="warn" />
              ))}
            </div>
          ) : (
            <p className="text-sm text-white/55">No setup needs reported.</p>
          )}
          <p className="text-sm text-white/55">
            Technical connection snapshot for operators. Day-to-day settings are summarized in the cards above.
          </p>
        </div>
      </Panel>
      ) : null}

      {activeTab === "advanced" ? (
      <DetailsPanel title="Local bot connection" summary="Show gateway source, status path, and runtime details">
        <KeyValueGrid
          rows={[
            { label: "Runtime source", value: titleCase(status.hermes_gateway.source) },
            { label: "Gateway state", value: titleCase(status.hermes_gateway.gateway_state) },
            { label: "Channel runtime", value: titleCase(status.hermes_gateway.provider_runtime_state) },
            { label: "Gateway status known", value: status.hermes_gateway.status_file_available ? "Yes" : "Unknown" },
            { label: "Status file available", value: status.hermes_gateway.status_file_available ? "Yes" : "No" },
            { label: "Status path configured", value: status.hermes_gateway.status_path_configured ? "Yes" : "No" },
            { label: "Gateway base configured", value: status.hermes_gateway.base_url_configured ? "Yes" : "No" },
            { label: "Active agents", value: status.hermes_gateway.active_agents ?? "Unknown" },
          ]}
        />
        {status.hermes_gateway.error_message ? (
          <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
            {status.hermes_gateway.error_message}
          </p>
        ) : null}
      </DetailsPanel>
      ) : null}

      {telegramCapabilities && activeTab === "advanced" ? (
        <DetailsPanel title="Telegram setup details" summary="Runtime requirements, booleans, and readiness (technical)">
          <div className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <BoolRow label="Token present" value={Boolean(status.telegram_bot_token_present ?? telegramCapabilities.bot_token_present)} />
              <BoolRow label="Allowed users configured" value={Boolean(status.telegram_allowed_users_present ?? telegramCapabilities.allowed_users_configured)} />
              <BoolRow label="Home channel configured" value={Boolean(status.telegram_home_channel_configured ?? telegramCapabilities.home_channel_configured)} />
              <BoolRow label="Test group configured" value={Boolean(status.telegram_test_group_configured ?? telegramCapabilities.test_group_configured)} />
              <BoolRow label="Hermes gateway base URL present" value={Boolean(status.hermes_gateway_base_url_present ?? telegramCapabilities.hermes_gateway_base_url_present)} />
              <BoolRow label="Hermes gateway status path present" value={Boolean(status.hermes_gateway_status_path_present ?? telegramCapabilities.hermes_gateway_status_path_present)} />
            </div>
            <KeyValueGrid
              rows={[
                { label: "Telegram mode", value: titleCase(status.telegram_mode ?? telegramCapabilities.telegram_mode) },
                { label: "Hermes runtime state", value: titleCase(status.hermes_gateway_runtime_state ?? telegramCapabilities.hermes_gateway_runtime_state) },
                { label: "Telegram connection", value: titleCase(status.telegram_platform_state ?? telegramCapabilities.telegram_platform_state) },
                { label: "Readiness", value: titleCase(status.readiness ?? telegramCapabilities.readiness) },
              ]}
            />
            {(status.telegram_mode ?? telegramCapabilities.telegram_mode) === "polling_default" ? (
              <p className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm leading-relaxed text-white/62">
                Hermes uses polling locally when no Telegram webhook URL is configured.
              </p>
            ) : null}
            {!status.telegram_bot_token_present || !status.hermes_gateway_base_url_present ? (
              <p className="rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm leading-relaxed text-amber-100/80">
                Bot exists but runtime is not connected yet. Store the token securely, configure allowed chats/users, and validate the Hermes gateway before preview work.
              </p>
            ) : null}
            {(status.missing_requirements.length || telegramCapabilities.missing_requirements.length) ? (
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Missing requirements</h3>
                <div className="flex flex-wrap gap-2">
                  {(status.missing_requirements.length ? status.missing_requirements : telegramCapabilities.missing_requirements).map((item) => (
                    <StatusPill key={item} label={titleCase(item)} tone="warn" />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </DetailsPanel>
      ) : null}

      {telegramCapabilities && activeTab === "operate" ? (
        <Panel title="Telegram primary actions">
          <div className="space-y-4">
            <div className="space-y-2 text-sm leading-relaxed text-white/62">
              <p>Preview and review Telegram actions before any live send. Live actions still require approval and the existing confirmation flow.</p>
              <p>Voice is locked to the canonical HAMgomoon persona and targets remain masked.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusPill
                label={telegramCapabilities.readiness === "ready" ? "Setup ready" : "Setup needs attention"}
                tone={telegramCapabilities.readiness === "ready" ? "ok" : "warn"}
              />
              <StatusPill label={telegramCapabilities.preview_available ? "Previews ready" : "Setup required for previews"} tone={telegramCapabilities.preview_available ? "ok" : "warn"} />
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="border-white/15 bg-white/5 text-white/90"
              onClick={onPreviewTelegram}
              disabled={telegramPreviewBusy || !onPreviewTelegram}
            >
              {telegramPreviewBusy ? "Drafting..." : "Draft Telegram message"}
            </Button>
            {telegramPreviewError ? (
              <p className="rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                {telegramPreviewError}
              </p>
            ) : null}
            {telegramPreview ? <TelegramMessagePreviewCard preview={telegramPreview} /> : null}
            {telegramPreview?.proposal_digest ? (
              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-white/82">Approved Telegram message</h3>
                    <p className="mt-1 text-xs text-white/48">
                      This sends exactly one Telegram message to the configured test/home target. No batch. No retry.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill label="Preview locked" tone="ok" />
                    <StatusPill label={telegramCapabilities.live_apply_available ? "Ready for operator approval" : "Setup required before sending"} tone={telegramCapabilities.live_apply_available ? "ok" : "warn"} />
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  className="mt-3 bg-red-700 text-white hover:bg-red-600"
                  disabled={!canSendOneTelegramMessage || !onOpenTelegramLiveConfirm}
                  onClick={onOpenTelegramLiveConfirm}
                >
                  Send one Telegram message
                </Button>
                {!canSendOneTelegramMessage ? (
                  <p className="mt-2 text-xs text-white/42">
                    Preview required before sending. Also requires ready Telegram setup and the Social live apply token configured on the API host.
                  </p>
                ) : null}
              </div>
            ) : null}
            {telegramLiveError ? (
              <p className="rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                {telegramLiveError}
              </p>
            ) : null}
            {telegramLiveResult ? (
              <FriendlyLiveOutcomeCard
                title="Telegram message result"
                record={telegramLiveResult as unknown as Record<string, unknown>}
              />
            ) : null}
          </div>
        </Panel>
      ) : null}

      {telegramCapabilities && activeTab === "inbox" ? (
        <Panel title="Telegram inbox">
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white/82">Telegram inbox</h3>
                  <p className="mt-1 text-xs text-white/48">
                    Check locally captured inbound messages. No Telegram API call. No reply will be sent.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusPill label="Local transcript only" tone="ok" />
                  <StatusPill label="No send attempted" tone="ok" />
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="mt-3 border-white/15 bg-white/5 text-white/90"
                onClick={onPreviewTelegramInbound}
                disabled={telegramInboundPreviewBusy || !onPreviewTelegramInbound}
              >
                {telegramInboundPreviewBusy ? "Checking..." : "Check Telegram inbox"}
              </Button>
              {telegramInboundPreviewError ? (
                <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                  {telegramInboundPreviewError}
                </p>
              ) : null}
              {telegramInboundPreview ? <TelegramInboundPreviewCard preview={telegramInboundPreview} /> : null}
            </div>
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white/82">Suggested replies</h3>
                  <p className="mt-1 text-xs text-white/48">
                    Find reply opportunities from the local inbox. No Telegram message will be sent by this check.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusPill label="No send attempted" tone="ok" />
                  <StatusPill label="No model call" tone="ok" />
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="mt-3 border-white/15 bg-white/5 text-white/90"
                onClick={onPreviewTelegramReactive}
                disabled={telegramReactivePreviewBusy || !onPreviewTelegramReactive}
              >
                {telegramReactivePreviewBusy ? "Checking..." : "Preview Telegram replies"}
              </Button>
              {telegramReactivePreviewError ? (
                <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                  {telegramReactivePreviewError}
                </p>
              ) : null}
              {telegramReactivePreview ? <TelegramReactiveRepliesPreviewCard preview={telegramReactivePreview} /> : null}
              {telegramReactiveLiveCandidates.length ? (
                <div className="mt-3 space-y-3">
                  {telegramReactiveLiveCandidates.map((item) => (
                    <div key={`telegram-reactive-live-${item.inbound_id}`} className="rounded-xl border border-white/10 bg-black/20 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-white/82">Approved Telegram reply</h3>
                          <p className="mt-1 text-xs text-white/48">
                            This sends exactly one Telegram reply through the governed Social cockpit. No batch. No retry. No autonomous runner.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <StatusPill label={item.classification ? titleCase(item.classification) : "Candidate"} tone="ok" />
                          <StatusPill label="Preview locked" tone="ok" />
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        className="mt-3 bg-red-700 text-white hover:bg-red-600"
                        disabled={!onOpenTelegramReactiveLiveConfirm}
                        onClick={() => onOpenTelegramReactiveLiveConfirm?.(item)}
                      >
                        Send one approved reply
                      </Button>
                    </div>
                  ))}
                </div>
              ) : null}
              {telegramReactiveLiveError ? (
                <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                  {telegramReactiveLiveError}
                </p>
              ) : null}
              {telegramReactiveLiveResult ? (
                <FriendlyLiveOutcomeCard
                  title="Telegram reply result"
                  record={telegramReactiveLiveResult as unknown as Record<string, unknown>}
                />
              ) : null}
            </div>
          </div>
        </Panel>
      ) : null}

      {telegramCapabilities && activeTab === "activity" ? (
        <Panel title="Telegram activity & pacing">
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white/82">Preview Telegram activity</h3>
                  <p className="mt-1 text-xs text-white/48">
                    Preview one bounded activity post. No Telegram message will be sent by this action.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusPill label="Activity preview" tone="ok" />
                  <StatusPill label="No scheduler" tone="ok" />
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="mt-3 border-white/15 bg-white/5 text-white/90"
                onClick={onPreviewTelegramActivity}
                disabled={telegramActivityPreviewBusy || !onPreviewTelegramActivity}
              >
                {telegramActivityPreviewBusy ? "Drafting..." : "Draft Telegram activity"}
              </Button>
              {telegramActivityPreviewError ? (
                <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                  {telegramActivityPreviewError}
                </p>
              ) : null}
              {telegramActivityPreview ? <TelegramActivityPreviewCard preview={telegramActivityPreview} /> : null}
              <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-white/82">Check scheduled activity once</h3>
                    <p className="mt-1 text-xs text-white/48">
                      Preview only. No Telegram message will be sent. No scheduler will be started.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill label="One-time check" tone="ok" />
                    <StatusPill label="Preview only" tone="ok" />
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="mt-3 border-white/15 bg-white/5 text-white/90"
                  onClick={onPreviewTelegramActivityRunOnce}
                  disabled={telegramActivityRunOncePreviewBusy || !onPreviewTelegramActivityRunOnce}
                >
                  {telegramActivityRunOncePreviewBusy ? "Checking..." : "Check once"}
                </Button>
                {telegramActivityRunOncePreviewError ? (
                  <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                    {telegramActivityRunOncePreviewError}
                  </p>
                ) : null}
                {telegramActivityRunOncePreview ? <TelegramActivityRunOncePreviewCard preview={telegramActivityRunOncePreview} /> : null}
              </div>
              {canSendOneTelegramActivity ? (
                <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-white/82">Approved Telegram activity</h3>
                      <p className="mt-1 text-xs text-white/48">
                        This sends exactly one Telegram activity message to the configured test group. No batch. No retry. No scheduler.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <StatusPill
                        label={telegramApprovalWindowProductPill(telegramActivityPreview.governor.allowed).label}
                        tone={telegramApprovalWindowProductPill(telegramActivityPreview.governor.allowed).tone}
                      />
                      <StatusPill
                        label={telegramCapabilities.activity_apply_available ? "Ready for operator approval" : "Setup required before sending"}
                        tone={telegramCapabilities.activity_apply_available ? "ok" : "warn"}
                      />
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="mt-3 bg-red-700 text-white hover:bg-red-600"
                    disabled={!onOpenTelegramActivityLiveConfirm}
                    onClick={onOpenTelegramActivityLiveConfirm}
                  >
                    Send one Telegram activity
                  </Button>
                </div>
              ) : null}
              {telegramActivityLiveError ? (
                <p className="rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-sm text-amber-100/80">
                  {telegramActivityLiveError}
                </p>
              ) : null}
              {telegramActivityLiveResult ? (
                <FriendlyLiveOutcomeCard
                  title="Telegram activity result"
                  record={telegramActivityLiveResult as unknown as Record<string, unknown>}
                />
              ) : null}
            </div>
          </div>
        </Panel>
      ) : null}

      {telegramCapabilities && activeTab === "advanced" &&
      (telegramLiveResult || telegramReactiveLiveResult || telegramActivityLiveResult) ? (
        <DetailsPanel title="Live send payloads (raw JSON)" summary="Session apply responses">
          {telegramLiveResult ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Message send</h3>
              <RecordPreview record={telegramLiveResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramReactiveLiveResult ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Reply send</h3>
              <RecordPreview record={telegramReactiveLiveResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramActivityLiveResult ? (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Activity send</h3>
              <RecordPreview record={telegramActivityLiveResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
        </DetailsPanel>
      ) : null}

      {!telegramCapabilities && activeTab === "operate" ? (
        <Panel title="Discord actions">
          <div className="space-y-3 text-sm text-white/62">
            <p>Discord setup guidance is available in this cockpit right now. Messaging controls come later.</p>
            <StatusPill label="Setup guidance available" tone="ok" />
            <StatusPill label="Check setup" tone="warn" />
          </div>
        </Panel>
      ) : null}

      {activeTab === "setup" ? (
      <DetailsPanel title="Setup checklist" summary="Show channel setup steps and recommendations">
        <div className="space-y-2">
          {setup.items.map((item) => (
            <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-white/70">
                {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                {item.label}
              </div>
              <StatusPill label={item.ok ? "OK" : "Missing"} tone={item.ok ? "ok" : "warn"} />
            </div>
          ))}
        </div>
        {setup.recommended_next_steps.length ? (
          <div className="mt-4 space-y-2">
            {setup.recommended_next_steps.map((step) => (
              <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/62">
                {step}
              </div>
            ))}
          </div>
        ) : null}
      </DetailsPanel>
      ) : null}

      {activeTab === "setup" ? (
      <DetailsPanel title={guidance.title} summary="What to do before previews and sends">
        <div className="space-y-4">
          <div className="space-y-2">
            {guidance.productIntro.map((line) => (
              <p key={line} className="text-sm leading-relaxed text-white/72">
                {line}
              </p>
            ))}
          </div>
          <div className="rounded-lg border border-white/10 bg-black/20 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">{guidance.noteTitle}</h3>
            <p className="mt-2 text-sm leading-relaxed text-white/62">{guidance.noteProduct}</p>
          </div>
          <ChecklistGroup
            title="Setup checklist"
            rows={guidance.checklist.map((label) => ({
              id: `${status.provider_id}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
              label,
              ok: false,
            }))}
          />
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">{guidance.warningTitle}</h3>
            <TextList items={guidance.warnings} tone="warn" />
          </div>
          <DetailsPanel title={SOCIAL_COPY.setupHostTokenTechnicalTitle} summary={SOCIAL_COPY.setupHostTokenTechnicalSummary}>
            <div className="space-y-2">
              {guidance.technicalIntro.map((line) => (
                <p key={line} className="text-sm leading-relaxed text-white/55">
                  {line}
                </p>
              ))}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-amber-100/78">{guidance.noteTechnical}</p>
          </DetailsPanel>
        </div>
      </DetailsPanel>
      ) : null}

      {activeTab === "advanced" ? (
      <DetailsPanel title="Available actions" summary="Show raw capability switches">
        <MessagingCapabilityRows capabilities={capabilities} />
      </DetailsPanel>
      ) : null}

      {activeTab === "advanced" ? (
      <DetailsPanel title="Safety proof" summary="Show boundaries and no-secret guarantees">
        <div className="space-y-2 text-sm text-white/62">
            <p className="flex gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
            Telegram exposes preview-first actions. No Telegram or Discord send, confirmed-action, bot startup, or gateway process controls are exposed.
          </p>
          <p className="flex gap-2">
            <Circle className="mt-1 h-3 w-3 shrink-0 text-white/40" />
            Bot tokens, allowlists, raw channel IDs, and Hermes local paths are never displayed here.
          </p>
        </div>
      </DetailsPanel>
      ) : null}

      {telegramCapabilities &&
      activeTab === "advanced" &&
      (telegramPreview ||
        telegramInboundPreview ||
        telegramReactivePreview ||
        telegramActivityPreview ||
        telegramActivityRunOncePreview) ? (
        <DetailsPanel title="Recent Telegram previews (raw JSON)" summary="Latest preview responses for this session">
          {telegramPreview ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Message draft</h3>
              <RecordPreview record={telegramPreview as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramInboundPreview ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Inbox check</h3>
              <RecordPreview record={telegramInboundPreview as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramReactivePreview ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Reply suggestions</h3>
              <RecordPreview record={telegramReactivePreview as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramActivityPreview ? (
            <div className="mb-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Activity draft</h3>
              <RecordPreview record={telegramActivityPreview as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
          {telegramActivityRunOncePreview ? (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">One-time activity check</h3>
              <RecordPreview record={telegramActivityRunOncePreview as unknown as Record<string, unknown>} emptyLabel="No payload." />
            </div>
          ) : null}
        </DetailsPanel>
      ) : null}

      {telegramCapabilities &&
      activeTab === "advanced" &&
      (telegramActivityPreview ||
        telegramActivityRunOncePreview ||
        (telegramReactivePreview?.items?.length ?? 0) > 0) ? (
        <DetailsPanel title={SOCIAL_COPY.telegramPacingTechnicalTitle} summary={SOCIAL_COPY.telegramPacingTechnicalSummary}>
          {telegramActivityPreview ? (
            <div className="mb-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Activity draft preview</h3>
              {telegramActivityPreview.governor.next_allowed_send_time ? (
                <p className="text-sm text-white/60">
                  Next allowed send window:{" "}
                  <span className="font-mono text-xs">{telegramActivityPreview.governor.next_allowed_send_time}</span>
                </p>
              ) : null}
              {telegramActivityPreview.governor.reasons.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-white/65">
                  {telegramActivityPreview.governor.reasons.map((r) => (
                    <li key={r}>{titleCase(r)}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-white/45">No internal pacing reasons on this preview.</p>
              )}
            </div>
          ) : null}
          {telegramActivityRunOncePreview ? (
            <div className="mb-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">One-time activity check</h3>
              {telegramActivityRunOncePreview.governor.next_allowed_send_time ? (
                <p className="text-sm text-white/60">
                  Next allowed send window:{" "}
                  <span className="font-mono text-xs">{telegramActivityRunOncePreview.governor.next_allowed_send_time}</span>
                </p>
              ) : null}
              {telegramActivityRunOncePreview.governor.reasons.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-white/65">
                  {telegramActivityRunOncePreview.governor.reasons.map((r) => (
                    <li key={r}>{titleCase(r)}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-white/45">No internal pacing reasons on this check.</p>
              )}
            </div>
          ) : null}
          {telegramReactivePreview?.items?.length ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Suggested replies (pacing)</h3>
              <div className="space-y-3">
                {telegramReactivePreview.items.map((item) => (
                  <div key={item.inbound_id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                    <p className="text-xs text-white/45">Suggestion for one conversation</p>
                    {item.governor.reasons.length ? (
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-white/65">
                        {item.governor.reasons.map((r) => (
                          <li key={r}>{titleCase(r)}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-white/45">No internal pacing reasons for this row.</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </DetailsPanel>
      ) : null}
    </div>
  );
}

function TextList({ items, tone = "muted" }: { items: string[]; tone?: "muted" | "warn" }) {
  const cls = tone === "warn" ? "text-amber-100/78" : "text-white/62";
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item} className={cn("rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm", cls)}>
          {item}
        </div>
      ))}
    </div>
  );
}

function ExampleList({ examples }: { examples: { input?: string; output: string }[] }) {
  return (
    <div className="space-y-2">
      {examples.map((example, idx) => (
        <div key={`${example.output}-${idx}`} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
          {example.input ? <div className="text-xs font-semibold uppercase tracking-[0.12em] text-white/38">Input: {example.input}</div> : null}
          <div className="mt-1 leading-relaxed text-white/75">{example.output}</div>
        </div>
      ))}
    </div>
  );
}

function PersonaPanel({ persona }: { persona: SocialPersona }) {
  const adaptations = Object.entries(persona.platform_adaptations).filter(([key]) => ["x", "telegram", "discord"].includes(key));
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Canonical HAM persona">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <StatusPill label={persona.display_name} tone="ok" />
            <StatusPill label={`${persona.persona_id} v${persona.version}`} tone="muted" />
            <StatusPill label={persona.read_only ? "Voice locked" : "Editable"} tone={persona.read_only ? "ok" : "warn"} />
          </div>
          <p className="text-sm leading-relaxed text-white/65">{persona.short_bio}</p>
          <KeyValueGrid
            rows={[
              { label: "Mission", value: persona.mission },
              { label: "Tone summary", value: persona.tone_rules.slice(0, 2).join(" · ") || "—" },
            ]}
          />
        </div>
      </Panel>

      <DetailsPanel title="Digest protection" summary="Why previews and sends stay consistent">
        <div className="space-y-2 text-sm text-white/62">
          <p className="flex gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
            Ham’s voice is fingerprinted. If the persona changes after a preview, sends should stop until you preview again.
          </p>
          <p className="flex gap-2">
            <Circle className="mt-1 h-3 w-3 shrink-0 text-white/40" />
            The fingerprint is a digest checksum — you don’t need to manage it; it is proof the voice did not drift.
          </p>
          <details className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-white/45">
            <summary className="cursor-pointer text-white/55">Technical fingerprint prefix</summary>
            <p className="mt-2 font-mono text-[11px] text-white/55">{persona.persona_digest.slice(0, 16)}…</p>
          </details>
        </div>
      </DetailsPanel>

      <Panel title="Voice rules">
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Values</h3>
            <TextList items={persona.values} />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Tone</h3>
            <TextList items={persona.tone_rules} />
          </div>
        </div>
      </Panel>

      <Panel title="Platform adaptations">
        <div className="space-y-3">
          {adaptations.map(([key, adaptation]) => (
            <div key={key} className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill label={adaptation.label || titleCase(key)} tone="ok" />
                {adaptation.max_chars ? <StatusPill label={`${adaptation.max_chars} chars`} tone="muted" /> : null}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-white/65">{adaptation.style}</p>
              {adaptation.guidance.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {adaptation.guidance.map((item) => (
                    <StatusPill key={item} label={item} tone="muted" />
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Preview voice examples">
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Replies</h3>
            <ExampleList examples={persona.example_replies} />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Announcements</h3>
            <ExampleList examples={persona.example_announcements.map((output) => ({ output }))} />
          </div>
        </div>
      </Panel>

      <Panel title="What Ham will not say">
        <div className="space-y-4">
          <TextList items={persona.prohibited_content} tone="warn" />
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Refusal examples</h3>
            <ExampleList examples={persona.refusal_examples} />
          </div>
        </div>
      </Panel>

      <Panel title="Safety boundaries">
        <TextList items={persona.safety_boundaries} />
      </Panel>
    </div>
  );
}

function ChecklistGroup({
  title,
  rows,
}: {
  title: string;
  rows: { id: string; label: string; ok: boolean }[];
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.id} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-white/68">{row.label}</span>
            <StatusPill label={row.ok ? "Ready" : "Missing"} tone={row.ok ? "ok" : "warn"} />
          </div>
        ))}
      </div>
    </div>
  );
}

function LoadingCards() {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div key={idx} className="h-32 animate-pulse rounded-2xl border border-white/10 bg-black/25" />
      ))}
    </div>
  );
}

const PREVIEW_LABELS: Record<SocialPreviewKind, string> = {
  reactive_inbox: "Check X inbox",
  reactive_batch_dry_run: "Preview X replies",
  broadcast_preflight: "Draft X post",
};

const X_ACTION_COPY: Record<SocialPreviewKind, { button: string; description: string; busy: string }> = {
  broadcast_preflight: {
    button: "Draft X post",
    description: "Prepare one original X post. Nothing is sent.",
    busy: "Drafting...",
  },
  reactive_inbox: {
    button: "Check X inbox",
    description: "Find one safe reply opportunity. Nothing is sent.",
    busy: "Checking...",
  },
  reactive_batch_dry_run: {
    button: "Preview X replies",
    description: "Review multiple possible replies. Nothing is sent.",
    busy: "Checking...",
  },
};

const LIVE_REPLY_CONFIRMATION_PHRASE = "SEND ONE LIVE REPLY";
const LIVE_BATCH_CONFIRMATION_PHRASE = "SEND LIVE REACTIVE BATCH";
const LIVE_BROADCAST_CONFIRMATION_PHRASE = "SEND ONE LIVE POST";
const LIVE_TELEGRAM_CONFIRMATION_PHRASE = "SEND ONE TELEGRAM MESSAGE";
const LIVE_TELEGRAM_ACTIVITY_CONFIRMATION_PHRASE = "SEND ONE TELEGRAM ACTIVITY";
const LIVE_TELEGRAM_REACTIVE_REPLY_CONFIRMATION_PHRASE = "SEND ONE TELEGRAM REPLY";

function TelegramMessagePreviewCard({ preview }: { preview: TelegramMessagePreviewResponse }) {
  const draft = friendlyDraftStatus(preview.status, Boolean(preview.proposal_digest));
  return (
    <section className="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white/85">Draft Telegram message</h3>
          <p className="mt-1 text-xs text-white/48">Preview only. No Telegram message will be sent from this step.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={draft.label} tone={draft.tone} />
          <StatusPill label="Voice locked" tone="ok" />
          {preview.proposal_digest ? <StatusPill label="Draft locked" tone="ok" /> : null}
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Destination</div>
          <div className="mt-1 text-sm text-white/82">{titleCase(preview.target.kind)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Length</div>
          <div className="mt-1 text-sm text-white/82">{preview.message_preview.char_count} characters</div>
        </div>
      </div>
      {preview.message_preview.text ? (
        <div className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/75">
          {preview.message_preview.text}
        </div>
      ) : null}
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Why it’s paused</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-white/65">
            {[...preview.reasons, ...preview.warnings].map((line) => (
              <li key={line}>{titleCase(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview.recommended_next_steps.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Next step</p>
          {preview.recommended_next_steps.map((step) => (
            <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/62">
              {step}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TelegramActivityPreviewCard({ preview }: { preview: TelegramActivityPreviewResponse }) {
  const draft = friendlyDraftStatus(preview.status, Boolean(preview.proposal_digest));
  const pacing = telegramPacingProductPill(preview.governor.allowed);
  return (
    <section className="mt-3 rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white/85">Draft Telegram activity</h3>
          <p className="mt-1 text-xs text-white/48">Preview only. No Telegram message will be sent from this step.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={draft.label} tone={draft.tone} />
          <StatusPill label={pacing.label} tone={pacing.tone} />
          <StatusPill label="Voice locked" tone="ok" />
          {preview.proposal_digest ? <StatusPill label="Draft locked" tone="ok" /> : null}
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Destination</div>
          <div className="mt-1 text-sm text-white/82">{titleCase(preview.target.kind)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Length</div>
          <div className="mt-1 text-sm text-white/82">{preview.activity_preview.char_count} characters</div>
        </div>
      </div>
      {preview.activity_preview.text ? (
        <div className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/75">
          {preview.activity_preview.text}
        </div>
      ) : null}
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Notes</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-white/65">
            {[...preview.reasons, ...preview.warnings].map((line) => (
              <li key={`a-${line}`}>{titleCase(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function TelegramActivityRunOncePreviewCard({ preview }: { preview: TelegramActivityRunOncePreviewResponse }) {
  const draft = friendlyDraftStatus(preview.status, Boolean(preview.proposal_digest));
  const pacing = preview.governor.allowed
    ? { label: "Ready to preview", tone: "ok" as const }
    : { label: "Waiting for the next safe send window", tone: "warn" as const };
  return (
    <section className="mt-3 rounded-2xl border border-sky-400/20 bg-sky-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white/85">One-time activity check</h3>
          <p className="mt-1 text-xs text-white/48">Safe read-style check. No message is sent and no scheduler is started.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={draft.label} tone={draft.tone} />
          <StatusPill label="Preview only" tone="ok" />
          <StatusPill label="Voice locked" tone="ok" />
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Destination</div>
          <div className="mt-1 text-sm text-white/82">{titleCase(preview.target.kind)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Send spacing</div>
          <div className="mt-1 text-sm text-white/82">{pacing.label}</div>
        </div>
      </div>
      {preview.activity_preview.text ? (
        <div className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/75">
          {preview.activity_preview.text}
        </div>
      ) : null}
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Notes</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-white/65">
            {[...preview.reasons, ...preview.warnings].map((line) => (
              <li key={`ro-${line}`}>{titleCase(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview.recommended_next_steps.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Next step</p>
          {preview.recommended_next_steps.map((step) => (
            <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/62">
              {step}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TelegramInboundPreviewCard({ preview }: { preview: TelegramInboundPreviewResponse }) {
  const draft = friendlyDraftStatus(preview.status, false);
  return (
    <section className="mt-3 rounded-2xl border border-violet-400/20 bg-violet-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white/85">Telegram inbox</h3>
          <p className="mt-1 text-xs text-white/48">Local inbox snapshot. No outbound send.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={draft.label} tone={draft.tone} />
          <StatusPill
            label={preview.inbound_count ? `${preview.inbound_count} opportunit${preview.inbound_count === 1 ? "y" : "ies"}` : "Inbox quiet"}
            tone={preview.inbound_count ? "ok" : "muted"}
          />
          <StatusPill label="No send from this step" tone="ok" />
        </div>
      </div>
      {preview.items.length ? (
        <div className="mt-3 space-y-3">
          {preview.items.map((item) => (
            <div key={item.inbound_id} className="rounded-lg border border-white/10 bg-black/25 p-3">
              <div className="flex flex-wrap gap-2">
                <StatusPill label={item.repliable ? "Can reply" : "Cannot reply"} tone={item.repliable ? "ok" : "warn"} />
                <StatusPill label={item.already_answered ? "Already answered" : "Unanswered"} tone={item.already_answered ? "muted" : "ok"} />
                <StatusPill label={humanTelegramChatLabel(item.chat_type)} tone="muted" />
              </div>
              <p className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/75">{item.text}</p>
              {item.reasons.length ? (
                <div className="mt-3 space-y-1 text-sm text-white/60">
                  {item.reasons.map((reason) => (
                    <p key={`${item.inbound_id}-${reason}`}>• {titleCase(reason)}</p>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Notes</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-white/65">
            {[...preview.reasons, ...preview.warnings].map((line) => (
              <li key={line}>{titleCase(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview.recommended_next_steps.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Next step</p>
          {preview.recommended_next_steps.map((step) => (
            <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/62">
              {step}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TelegramReactiveRepliesPreviewCard({ preview }: { preview: TelegramReactiveRepliesPreviewResponse }) {
  const draft = friendlyDraftStatus(preview.status, false);
  return (
    <section className="mt-3 rounded-2xl border border-fuchsia-400/20 bg-fuchsia-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white/85">Suggested Telegram replies</h3>
          <p className="mt-1 text-xs text-white/48">Draft replies from your inbox. Nothing sends from this preview.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={draft.label} tone={draft.tone} />
          <StatusPill
            label={
              preview.reply_candidate_count
                ? `${preview.reply_candidate_count} suggestion${preview.reply_candidate_count === 1 ? "" : "s"}`
                : "No suggestions yet"
            }
            tone={preview.reply_candidate_count ? "ok" : "muted"}
          />
          <StatusPill label="No send from this step" tone="ok" />
        </div>
      </div>
      {preview.items.length ? (
        <div className="mt-3 space-y-3">
          {preview.items.map((item) => {
            const itemPacing = telegramPacingProductPill(item.governor.allowed);
            return (
            <div key={item.inbound_id} className="rounded-lg border border-white/10 bg-black/25 p-3">
              <div className="flex flex-wrap gap-2">
                <StatusPill label={titleCase(item.classification)} tone={item.policy.allowed ? "ok" : "warn"} />
                <StatusPill label={item.policy.allowed ? "Policy OK" : "Needs review"} tone={item.policy.allowed ? "ok" : "warn"} />
                <StatusPill label={itemPacing.label} tone={itemPacing.tone} />
                {item.proposal_digest ? <StatusPill label="Draft locked" tone="ok" /> : null}
              </div>
              <p className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/75">{item.inbound_text}</p>
              {item.reply_candidate_text ? (
                <p className="mt-3 rounded-lg border border-emerald-400/20 bg-emerald-500/10 p-3 text-sm leading-relaxed text-emerald-50/85">
                  {item.reply_candidate_text}
                </p>
              ) : null}
              {item.reasons.length ? (
                <div className="mt-3 space-y-1 text-sm text-white/60">
                  {item.reasons.map((reason) => (
                    <p key={`${item.inbound_id}-${reason}`}>• {titleCase(reason)}</p>
                  ))}
                </div>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : null}
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Notes</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-white/65">
            {[...preview.reasons, ...preview.warnings].map((line) => (
              <li key={`tr-${line}`}>{titleCase(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview.recommended_next_steps.length ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Next step</p>
          {preview.recommended_next_steps.map((step) => (
            <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/62">
              {step}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function PreviewResultCard({ preview }: { preview: SocialPreviewResponse }) {
  const st = friendlyXPreviewStatus(preview);
  const proposed = formatLooseRecordSummary(preview.result);
  const whyHeld =
    preview.reasons.length > 0
      ? preview.reasons.map((r) => titleCase(r)).join(" · ")
      : preview.warnings.length > 0
        ? preview.warnings.map((w) => titleCase(w)).join(" · ")
        : null;
  let nextStep = "Run the preview again after you address any setup notes above.";
  if (preview.status === "blocked") nextStep = "Adjust setup or persona rules, then run this preview again.";
  if (preview.status === "failed") nextStep = "Fix the issue described in the notes, refresh, and preview again.";
  if (preview.proposal_digest && preview.status === "completed") nextStep = "Use the send panel when you’re ready — the existing confirmation flow still applies.";

  return (
    <section className="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white/85">{PREVIEW_LABELS[preview.preview_kind]}</h2>
          <p className="mt-1 text-xs text-white/48">Preview only. No live X write.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={st.label} tone={st.tone} />
          <StatusPill label="Voice locked" tone="ok" />
          {preview.proposal_digest ? <StatusPill label="Draft locked" tone="ok" /> : null}
        </div>
      </div>
      <p className="mt-3 text-sm text-white/60">{X_ACTION_COPY[preview.preview_kind].description}</p>
      {proposed ? (
        <div className="mt-3 rounded-lg border border-white/10 bg-black/30 p-3 text-sm leading-relaxed text-white/80">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">Proposed text</p>
          <p className="mt-2">{proposed}</p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-white/45">No draft text was returned. Use Advanced technical proof if you need raw fields.</p>
      )}
      {whyHeld ? (
        <p className="mt-3 text-sm text-white/62">
          <span className="font-medium text-white/78">Why it’s paused: </span>
          {whyHeld}
        </p>
      ) : null}
      <p className="mt-3 text-sm text-white/62">
        <span className="font-medium text-white/78">Next step: </span>
        {nextStep}
      </p>
      <p className="mt-1 text-xs text-white/42">
        Voice fingerprinting still applies: if the persona changes after this preview, re-preview before any live send.
      </p>
    </section>
  );
}

function XActionCard({
  kind,
  busyKind,
  onPreview,
}: {
  kind: SocialPreviewKind;
  busyKind: SocialPreviewKind | null;
  onPreview: (kind: SocialPreviewKind) => void;
}) {
  const copy = X_ACTION_COPY[kind];
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <div className="space-y-2">
        <h3 className="text-base font-semibold text-white/90">{PREVIEW_LABELS[kind]}</h3>
        <p className="text-sm leading-relaxed text-white/58">{copy.description}</p>
      </div>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        className="mt-4 border-white/15 bg-white/5 text-white/90"
        onClick={() => onPreview(kind)}
        disabled={busyKind !== null}
      >
        {busyKind === kind ? copy.busy : copy.button}
      </Button>
    </div>
  );
}

function ConfiguredBehaviorPanel({ snapshot }: { snapshot: SocialSnapshot }) {
  const channels = (["x", "telegram", "discord"] as const).map((id) => {
    const t = deriveChannelProductTruth(snapshot, id);
    const label = id === "x" ? "X" : id === "telegram" ? "Telegram" : "Discord";
    return (
      <div key={id} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/72">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-white/88">{label}</span>
          <StatusPill label={t.readiness} tone={productReadinessTone(t.readiness)} />
        </div>
        <p className="mt-2 text-white/62">
          Posting <span className="text-white/85">{t.postingMode}</span> · cadence{" "}
          <span className="text-white/85">{t.postingFrequency}</span>
        </p>
        <p className="text-white/62">
          Replies <span className="text-white/85">{t.replyMode}</span> · volume{" "}
          <span className="text-white/85">{t.replyVolume}</span>
        </p>
        <p className="mt-2 text-xs text-white/48">{t.autopilotLine}</p>
      </div>
    );
  });
  return (
    <Panel title={SOCIAL_COPY.overviewProductSummary}>
      <div className="grid gap-2 md:grid-cols-3">{channels}</div>
      <p className="mt-3 text-xs text-white/45">{SOCIAL_COPY.overviewRhythm}</p>
    </Panel>
  );
}

function ProductChannelBanner({
  snapshot,
  channelId,
}: {
  snapshot: SocialSnapshot;
  channelId: "x" | "telegram" | "discord";
}) {
  const t = deriveChannelProductTruth(snapshot, channelId);
  const label = channelId === "x" ? "X" : channelId === "telegram" ? "Telegram" : "Discord";
  return (
    <section className="rounded-2xl border border-emerald-400/15 bg-emerald-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/55">{SOCIAL_COPY.channelProductSummary}</h3>
          <p className="mt-1 text-lg font-semibold text-white/92">{label}</p>
          <p className="mt-2 text-sm text-white/68">{t.autopilotLine}</p>
        </div>
        <StatusPill label={t.readiness} tone={productReadinessTone(t.readiness)} />
      </div>
      <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
          <div className="text-white/45">Posting</div>
          <div className="font-medium text-white/88">
            {t.postingMode} · {t.postingFrequency}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
          <div className="text-white/45">Replies</div>
          <div className="font-medium text-white/88">
            {t.replyMode} · {t.replyVolume}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 sm:col-span-2 lg:col-span-2">
          <div className="text-white/45">Next for this channel</div>
          <div className="font-medium text-white/82">{t.nextHint}</div>
        </div>
      </div>
    </section>
  );
}

export function WorkspaceSocialScreen() {
  const [snapshot, setSnapshot] = React.useState<SocialSnapshot | null>(null);
  const [selectedSection, setSelectedSection] = React.useState<SocialSection>("overview");
  const [selectedProvider, setSelectedProvider] = React.useState<SocialSelection>("x");
  const [channelTab, setChannelTab] = React.useState<ChannelDetailTab>("operate");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = React.useState<SocialPreviewKind | null>(null);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [previews, setPreviews] = React.useState<Partial<Record<SocialPreviewKind, SocialPreviewResponse>>>({});
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [confirmText, setConfirmText] = React.useState("");
  const [operatorToken, setOperatorToken] = React.useState("");
  const [liveBusy, setLiveBusy] = React.useState(false);
  const [liveError, setLiveError] = React.useState<string | null>(null);
  const [liveResult, setLiveResult] = React.useState<SocialReactiveReplyApplyResponse | null>(null);
  const [batchConfirmOpen, setBatchConfirmOpen] = React.useState(false);
  const [batchConfirmText, setBatchConfirmText] = React.useState("");
  const [batchOperatorToken, setBatchOperatorToken] = React.useState("");
  const [batchBusy, setBatchBusy] = React.useState(false);
  const [batchError, setBatchError] = React.useState<string | null>(null);
  const [batchResult, setBatchResult] = React.useState<SocialReactiveBatchApplyResponse | null>(null);
  const [broadcastConfirmOpen, setBroadcastConfirmOpen] = React.useState(false);
  const [broadcastConfirmText, setBroadcastConfirmText] = React.useState("");
  const [broadcastOperatorToken, setBroadcastOperatorToken] = React.useState("");
  const [broadcastBusy, setBroadcastBusy] = React.useState(false);
  const [broadcastError, setBroadcastError] = React.useState<string | null>(null);
  const [broadcastResult, setBroadcastResult] = React.useState<SocialBroadcastApplyResponse | null>(null);
  const [telegramPreviewBusy, setTelegramPreviewBusy] = React.useState(false);
  const [telegramPreviewError, setTelegramPreviewError] = React.useState<string | null>(null);
  const [telegramPreview, setTelegramPreview] = React.useState<TelegramMessagePreviewResponse | null>(null);
  const [telegramInboundPreviewBusy, setTelegramInboundPreviewBusy] = React.useState(false);
  const [telegramInboundPreviewError, setTelegramInboundPreviewError] = React.useState<string | null>(null);
  const [telegramInboundPreview, setTelegramInboundPreview] = React.useState<TelegramInboundPreviewResponse | null>(null);
  const [telegramReactivePreviewBusy, setTelegramReactivePreviewBusy] = React.useState(false);
  const [telegramReactivePreviewError, setTelegramReactivePreviewError] = React.useState<string | null>(null);
  const [telegramReactivePreview, setTelegramReactivePreview] = React.useState<TelegramReactiveRepliesPreviewResponse | null>(null);
  const [telegramReactiveConfirmOpen, setTelegramReactiveConfirmOpen] = React.useState(false);
  const [telegramReactiveConfirmText, setTelegramReactiveConfirmText] = React.useState("");
  const [telegramReactiveOperatorToken, setTelegramReactiveOperatorToken] = React.useState("");
  const [telegramReactiveLiveBusy, setTelegramReactiveLiveBusy] = React.useState(false);
  const [telegramReactiveLiveError, setTelegramReactiveLiveError] = React.useState<string | null>(null);
  const [telegramReactiveLiveResult, setTelegramReactiveLiveResult] = React.useState<TelegramReactiveReplyApplyResponse | null>(null);
  const [telegramReactiveSelected, setTelegramReactiveSelected] = React.useState<TelegramReactiveRepliesPreviewResponse["items"][number] | null>(null);
  const [telegramActivityPreviewBusy, setTelegramActivityPreviewBusy] = React.useState(false);
  const [telegramActivityPreviewError, setTelegramActivityPreviewError] = React.useState<string | null>(null);
  const [telegramActivityPreview, setTelegramActivityPreview] = React.useState<TelegramActivityPreviewResponse | null>(null);
  const [telegramActivityRunOncePreviewBusy, setTelegramActivityRunOncePreviewBusy] = React.useState(false);
  const [telegramActivityRunOncePreviewError, setTelegramActivityRunOncePreviewError] = React.useState<string | null>(null);
  const [telegramActivityRunOncePreview, setTelegramActivityRunOncePreview] = React.useState<TelegramActivityRunOncePreviewResponse | null>(null);
  const [telegramActivityConfirmOpen, setTelegramActivityConfirmOpen] = React.useState(false);
  const [telegramActivityConfirmText, setTelegramActivityConfirmText] = React.useState("");
  const [telegramActivityOperatorToken, setTelegramActivityOperatorToken] = React.useState("");
  const [telegramActivityLiveBusy, setTelegramActivityLiveBusy] = React.useState(false);
  const [telegramActivityLiveError, setTelegramActivityLiveError] = React.useState<string | null>(null);
  const [telegramActivityLiveResult, setTelegramActivityLiveResult] = React.useState<TelegramActivityApplyResponse | null>(null);
  const [telegramConfirmOpen, setTelegramConfirmOpen] = React.useState(false);
  const [telegramConfirmText, setTelegramConfirmText] = React.useState("");
  const [telegramOperatorToken, setTelegramOperatorToken] = React.useState("");
  const [telegramLiveBusy, setTelegramLiveBusy] = React.useState(false);
  const [telegramLiveError, setTelegramLiveError] = React.useState<string | null>(null);
  const [telegramLiveResult, setTelegramLiveResult] = React.useState<TelegramMessageApplyResponse | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const result = await socialAdapter.loadSnapshot();
    if (result.bridge.status === "pending") {
      setError(result.bridge.detail || result.error || "Social API needs attention.");
      setSnapshot(null);
    } else {
      setSnapshot(result.snapshot);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const runPreview = async (kind: SocialPreviewKind) => {
    setPreviewBusy(kind);
    setPreviewError(null);
    const result =
      kind === "reactive_inbox"
        ? await socialAdapter.previewInboxDiscovery()
        : kind === "reactive_batch_dry_run"
          ? await socialAdapter.previewReactiveBatchDryRun()
          : await socialAdapter.previewBroadcastPreflight();
    setPreviewBusy(null);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setPreviewError(detail || "Preview needs attention.");
      return;
    }
    setPreviews((prev) => ({ ...prev, [kind]: result.preview ?? undefined }));
  };

  const runTelegramPreview = async () => {
    setTelegramPreviewBusy(true);
    setTelegramPreviewError(null);
    const result = await socialAdapter.previewTelegramMessage();
    setTelegramPreviewBusy(false);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramPreviewError(detail || "Telegram preview needs attention.");
      return;
    }
    setTelegramPreview(result.preview);
    setTelegramLiveResult(null);
  };

  const runTelegramInboundPreview = async () => {
    setTelegramInboundPreviewBusy(true);
    setTelegramInboundPreviewError(null);
    const result = await socialAdapter.previewTelegramInbound();
    setTelegramInboundPreviewBusy(false);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramInboundPreviewError(detail || "Telegram inbox preview needs attention.");
      return;
    }
    setTelegramInboundPreview(result.preview);
  };

  const runTelegramReactivePreview = async () => {
    setTelegramReactivePreviewBusy(true);
    setTelegramReactivePreviewError(null);
    const result = await socialAdapter.previewTelegramReactiveReplies();
    setTelegramReactivePreviewBusy(false);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramReactivePreviewError(detail || "Telegram reply preview needs attention.");
      return;
    }
    setTelegramReactivePreview(result.preview);
    setTelegramReactiveLiveResult(null);
  };

  const sendOneTelegramReactiveReply = async () => {
    if (!telegramReactiveSelected?.proposal_digest) return;
    setTelegramReactiveLiveBusy(true);
    setTelegramReactiveLiveError(null);
    const result = await socialAdapter.sendOneTelegramReactiveReply({
      proposalDigest: telegramReactiveSelected.proposal_digest,
      confirmationPhrase: telegramReactiveConfirmText,
      inboundId: telegramReactiveSelected.inbound_id,
      operatorToken: telegramReactiveOperatorToken,
      clientRequestId: `social-ui-telegram-reactive-${Date.now()}`,
    });
    setTelegramReactiveLiveBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramReactiveLiveError(detail || "Telegram reply needs attention.");
      return;
    }
    setTelegramReactiveLiveResult(result.apply);
    setTelegramReactiveConfirmOpen(false);
    setTelegramReactiveConfirmText("");
    setTelegramReactiveOperatorToken("");
    setTelegramReactiveSelected(null);
    void load();
  };

  const runTelegramActivityPreview = async () => {
    setTelegramActivityPreviewBusy(true);
    setTelegramActivityPreviewError(null);
    const result = await socialAdapter.previewTelegramActivity({
      activityKind: "test_activity",
      clientRequestId: `social-ui-activity-${Date.now()}`,
    });
    setTelegramActivityPreviewBusy(false);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramActivityPreviewError(detail || "Telegram activity preview needs attention.");
      return;
    }
    setTelegramActivityPreview(result.preview);
    setTelegramActivityLiveResult(null);
  };

  const runTelegramActivityRunOncePreview = async () => {
    setTelegramActivityRunOncePreviewBusy(true);
    setTelegramActivityRunOncePreviewError(null);
    const result = await socialAdapter.previewTelegramActivityRunOnce({
      activityKind: "test_activity",
      clientRequestId: `social-ui-activity-run-once-${Date.now()}`,
    });
    setTelegramActivityRunOncePreviewBusy(false);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramActivityRunOncePreviewError(detail || "Telegram scheduled activity preview needs attention.");
      return;
    }
    setTelegramActivityRunOncePreview(result.preview);
  };

  const sendOneTelegramActivity = async () => {
    if (!telegramActivityPreview?.proposal_digest) return;
    setTelegramActivityLiveBusy(true);
    setTelegramActivityLiveError(null);
    const result = await socialAdapter.sendOneTelegramActivity({
      proposalDigest: telegramActivityPreview.proposal_digest,
      confirmationPhrase: telegramActivityConfirmText,
      operatorToken: telegramActivityOperatorToken,
      activityKind: telegramActivityPreview.activity_preview.activity_kind,
      clientRequestId: `social-ui-telegram-activity-${Date.now()}`,
    });
    setTelegramActivityLiveBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramActivityLiveError(detail || "Telegram live activity needs attention.");
      return;
    }
    setTelegramActivityLiveResult(result.apply);
    setTelegramActivityConfirmOpen(false);
    setTelegramActivityConfirmText("");
    setTelegramActivityOperatorToken("");
    void load();
  };

  const x = snapshot?.xStatus;
  const caps = snapshot?.xCapabilities;
  const setup = snapshot?.xSetupSummary;
  const selectedMessaging =
    selectedProvider === "telegram" && snapshot
      ? {
          status: snapshot.telegramStatus,
          capabilities: snapshot.telegramCapabilities,
          setup: snapshot.telegramSetup,
        }
      : selectedProvider === "discord" && snapshot
        ? {
            status: snapshot.discordStatus,
            capabilities: snapshot.discordCapabilities,
            setup: snapshot.discordSetup,
          }
        : null;
  const inboxPreview = previews.reactive_inbox;
  const batchPreview = previews.reactive_batch_dry_run;
  const broadcastPreview = previews.broadcast_preflight;
  const canSendOneLiveReply = Boolean(inboxPreview?.proposal_digest && caps?.reactive_reply_apply_available);
  const canSendLiveReactiveBatch = Boolean(batchPreview?.proposal_digest && caps?.reactive_batch_apply_available);
  const canSendOneLivePost = Boolean(broadcastPreview?.proposal_digest && caps?.broadcast_apply_available);
  const providerSummary = (provider: SocialProvider) => {
    if (provider.id === "x") {
      return {
        lastActivity: `Last post: ${snapshot?.xStatus.last_autonomous_post ? "found" : "none yet"} · Last reply: ${snapshot?.xStatus.last_reactive_reply ? "found" : "none yet"}`,
        primaryAction: deriveChannelProductTruth(snapshot!, "x").nextHint,
        warning: snapshot?.xStatus.emergency_stop.enabled
          ? "Emergency stop is on."
          : provider.status === "active"
            ? null
            : "Setup required before live sends.",
      };
    }
    if (provider.id === "telegram") {
      return {
        lastActivity: telegramInboundPreview
          ? `${telegramInboundPreview.inbound_count} inbox items found`
          : telegramReactivePreview
            ? `${telegramReactivePreview.reply_candidate_count} reply opportunities`
            : "No inbox check run yet.",
        primaryAction: deriveChannelProductTruth(snapshot!, "telegram").nextHint,
        warning: snapshot?.telegramStatus.readiness_reasons[0]
          ? titleCase(snapshot.telegramStatus.readiness_reasons[0])
          : null,
      };
    }
    if (provider.id === "discord") {
      return {
        lastActivity: "No live Discord activity yet.",
        primaryAction: deriveChannelProductTruth(snapshot!, "discord").nextHint,
        warning: "Live controls are not available yet.",
      };
    }
    return {
      lastActivity: "No activity reported.",
      primaryAction: "Open channel details",
      warning: provider.coming_soon ? "Coming soon." : null,
    };
  };

  const socialProductTruth = snapshot ? buildSocialProductTruth(snapshot) : null;

  const sendOneTelegramMessage = async () => {
    if (!telegramPreview?.proposal_digest) return;
    setTelegramLiveBusy(true);
    setTelegramLiveError(null);
    const result = await socialAdapter.sendOneTelegramMessage({
      proposalDigest: telegramPreview.proposal_digest,
      confirmationPhrase: telegramConfirmText,
      operatorToken: telegramOperatorToken,
      messageIntent: "test_message",
      clientRequestId: `social-ui-telegram-${Date.now()}`,
    });
    setTelegramLiveBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setTelegramLiveError(detail || "Telegram live message needs attention.");
      return;
    }
    setTelegramLiveResult(result.apply);
    setTelegramConfirmOpen(false);
    setTelegramConfirmText("");
    setTelegramOperatorToken("");
    void load();
  };

  const sendOneLiveReply = async () => {
    if (!inboxPreview?.proposal_digest) return;
    setLiveBusy(true);
    setLiveError(null);
    const result = await socialAdapter.sendOneLiveReply({
      proposalDigest: inboxPreview.proposal_digest,
      confirmationPhrase: confirmText,
      operatorToken,
      clientRequestId: `social-ui-${Date.now()}`,
    });
    setLiveBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setLiveError(detail || "Live reply needs attention.");
      return;
    }
    setLiveResult(result.apply);
    setConfirmOpen(false);
    setConfirmText("");
    setOperatorToken("");
    void load();
  };

  const sendLiveReactiveBatch = async () => {
    if (!batchPreview?.proposal_digest) return;
    setBatchBusy(true);
    setBatchError(null);
    const result = await socialAdapter.sendLiveReactiveBatch({
      proposalDigest: batchPreview.proposal_digest,
      confirmationPhrase: batchConfirmText,
      operatorToken: batchOperatorToken,
      clientRequestId: `social-ui-batch-${Date.now()}`,
    });
    setBatchBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setBatchError(detail || "Live reply batch needs attention.");
      return;
    }
    setBatchResult(result.apply);
    setBatchConfirmOpen(false);
    setBatchConfirmText("");
    setBatchOperatorToken("");
    void load();
  };

  const sendOneLivePost = async () => {
    if (!broadcastPreview?.proposal_digest) return;
    setBroadcastBusy(true);
    setBroadcastError(null);
    const result = await socialAdapter.sendOneLivePost({
      proposalDigest: broadcastPreview.proposal_digest,
      confirmationPhrase: broadcastConfirmText,
      operatorToken: broadcastOperatorToken,
      clientRequestId: `social-ui-broadcast-${Date.now()}`,
    });
    setBroadcastBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setBroadcastError(detail || "Live post needs attention.");
      return;
    }
    setBroadcastResult(result.apply);
    setBroadcastConfirmOpen(false);
    setBroadcastConfirmText("");
    setBroadcastOperatorToken("");
    void load();
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-y-auto p-3 md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        eyebrow="Social"
        title="HAMgomoon Social"
        subtitle="Operate autonomous social reach with previews first, confirmations second, and voice locked to Ham’s persona."
        actions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 gap-1.5 border-white/15 bg-white/5 text-white/90"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      <WorkspaceSurfaceStateCard
        title="Voice and safety are locked"
        description="HAMgomoon keeps your voice, channel settings, and confirmed sends aligned. Technical proof stays under Advanced technical proof."
        tone="neutral"
      />

      {error ? (
        <WorkspaceSurfaceStateCard
          title="Social API needs attention"
          description="The Social channel snapshot could not be loaded. Other workspace routes may still work."
          tone="amber"
          technicalDetail={error}
          primaryAction={
            <Button type="button" size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : null}

      {loading ? <LoadingCards /> : null}

      {!loading && snapshot ? (
        <>
          <GlobalStatusStrip snapshot={snapshot} />

          <SectionTabs
            selected={selectedSection}
            onSelect={(section) => {
              setSelectedSection(section);
              if (section === "channels" && selectedProvider === "persona") {
                setSelectedProvider("x");
              }
            }}
          />

          {selectedSection === "overview" || selectedSection === "channels" ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {snapshot.providers.map((provider) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                snapshot={snapshot}
                selected={selectedSection === "channels" && provider.id === selectedProvider}
                onSelect={() => {
                  if (provider.id === "x" || provider.id === "telegram" || provider.id === "discord") {
                    setSelectedSection("channels");
                    setSelectedProvider(provider.id);
                    setChannelTab("operate");
                  }
                }}
                {...providerSummary(provider)}
              />
            ))}
          </div>
          ) : null}

          {selectedSection === "overview" && socialProductTruth ? (
            <div className="grid gap-4 xl:grid-cols-3">
              <div className="xl:col-span-3">
                <ConfiguredBehaviorPanel snapshot={snapshot} />
              </div>

              <Panel title={SOCIAL_COPY.overviewNextAction}>
                <p className="text-sm leading-relaxed text-white/78">{socialProductTruth.nextAction}</p>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewHamStatus}>
                <div className="space-y-2 text-sm text-white/72">
                  <div className="flex flex-wrap gap-2">
                    <StatusPill
                      label={socialProductTruth.hamStatus}
                      tone={
                        socialProductTruth.hamStatus === "Active"
                          ? "ok"
                          : socialProductTruth.hamStatus === "Paused"
                            ? "danger"
                            : "warn"
                      }
                    />
                  </div>
                  <p>{operatingModeSummary(snapshot)}</p>
                </div>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewAutopilot}>
                <p className="text-sm leading-relaxed text-white/72">{socialProductTruth.autopilotSummary}</p>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewPersona}>
                <div className="space-y-2 text-sm text-white/72">
                  <p>
                    <span className="font-medium text-white/88">{socialProductTruth.persona.headline}</span>{" "}
                    <span className="text-white/45">
                      ({snapshot.persona.persona_id} v{snapshot.persona.version})
                    </span>
                  </p>
                  <p className="text-white/58">{snapshot.persona.short_bio}</p>
                  <p className="text-xs text-white/50">{socialProductTruth.persona.detail}</p>
                </div>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewSafety}>
                <ul className="list-inside list-disc space-y-1 text-sm text-white/65">
                  {socialProductTruth.safetyLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                <p className="mt-3 text-sm leading-relaxed text-white/60">{socialProductTruth.voiceBoundariesLine}</p>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewCanDoNow}>
                <ul className="list-inside list-disc space-y-1 text-sm text-white/62">
                  {socialProductTruth.canDoNow.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewNeedsSetup}>
                <ul className="list-inside list-disc space-y-1 text-sm text-white/62">
                  {socialProductTruth.needsSetup.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewAttention}>
                <div className="space-y-2 text-sm text-white/62">
                  {snapshot.providers.some((provider) => provider.status !== "active") ? (
                    snapshot.providers
                      .filter((provider) => provider.status !== "active")
                      .map((provider) => (
                        <div key={provider.id} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                          {provider.label}: {provider.status === "coming_soon" ? "planned" : "needs setup"}
                        </div>
                      ))
                  ) : (
                    <p>No channel setup needs reported.</p>
                  )}
                </div>
              </Panel>

              <Panel title={SOCIAL_COPY.overviewRecentActivity}>
                <div className="space-y-2 text-sm text-white/62">
                  <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                    Last X post: {formatLooseRecordSummary(snapshot.xStatus.last_autonomous_post) || "none captured yet"}
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                    Last X reply: {formatLooseRecordSummary(snapshot.xStatus.last_reactive_reply) || "none captured yet"}
                  </div>
                </div>
              </Panel>
            </div>
          ) : null}

          {selectedSection === "persona" ? <PersonaPanel persona={snapshot.persona} /> : null}

          {selectedSection === "channels" ? <ChannelDetailTabs selected={channelTab} onSelect={setChannelTab} /> : null}

          {selectedSection === "channels" && snapshot && selectedProvider === "x" && x && caps ? (
            <ProductChannelBanner snapshot={snapshot} channelId="x" />
          ) : null}
          {selectedSection === "channels" && snapshot && selectedProvider === "telegram" ? (
            <ProductChannelBanner snapshot={snapshot} channelId="telegram" />
          ) : null}
          {selectedSection === "channels" && snapshot && selectedProvider === "discord" ? (
            <ProductChannelBanner snapshot={snapshot} channelId="discord" />
          ) : null}

          {selectedSection === "channels" && snapshot && selectedProvider === "x" && x && caps ? (
            <div className="grid gap-3 md:grid-cols-3">
              <SettingsCard title={SOCIAL_COPY.channelPostingSettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "x")} />
                <SettingsRow label="Posting mode" value={deriveChannelProductTruth(snapshot, "x").postingMode} />
                <SettingsRow label="Posting frequency" value={deriveChannelProductTruth(snapshot, "x").postingFrequency} />
                <SettingsRow label="Autopilot (this channel)" value={deriveChannelProductTruth(snapshot, "x").autopilotLine} />
                <SettingsRow label="Content style" value={deriveContentStyle(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Daily caps and spacing from status">
                  <SettingsRow label="Max posts per day" value={String(x.cap_cooldown_summary.broadcast_daily_cap)} />
                  <SettingsRow label="Minimum spacing" value={`${x.cap_cooldown_summary.broadcast_min_spacing_minutes} min`} />
                  <SettingsRow label="Max posts per run" value={String(x.cap_cooldown_summary.broadcast_per_run_cap)} />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelReplySettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "x")} />
                <SettingsRow label="Reply mode" value={deriveChannelProductTruth(snapshot, "x").replyMode} />
                <SettingsRow label="Reply volume" value={deriveChannelProductTruth(snapshot, "x").replyVolume} />
                <SettingsRow label="Safe / blocked topics" value={personaBlockedTopicsSummary(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Reply caps from status">
                  <SettingsRow label="Max replies per 15m" value={String(x.cap_cooldown_summary.reactive_max_replies_per_15m)} />
                  <SettingsRow label="Max replies per hour" value={String(x.cap_cooldown_summary.reactive_max_replies_per_hour)} />
                  <SettingsRow label="Reply to mentions/comments" value={x.reactive_lane.inbox_discovery_enabled ? "Inbox checks on" : "Needs setup"} />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelSafetySettings}>
                {(() => {
                  const h = xSafetyHints(x, snapshot.persona);
                  return (
                    <>
                      <SettingsRow label="Voice locked" value={h.voiceLocked ? "Yes" : "No"} />
                      <SettingsRow label="Approval required for live sends" value={h.approvalRequired ? "Yes" : "No"} />
                      <SettingsRow label="Emergency stop" value={h.emergencyStop ? "On" : "Off"} />
                      <SettingsRow label="Links in posts" value={h.noLinksUnlessEnabled ? "Restricted unless voice allows" : "Standard"} />
                      <SettingsRow label="Financial advice" value={h.noFinancialAdvice ? "Not allowed" : "Standard"} />
                      <SettingsRow label="Buy/sell language" value={h.noBuySellLanguage ? "Limited by voice rules" : "Standard"} />
                      <SettingsRow label="Secrets in this UI" value="Not collected here" />
                    </>
                  );
                })()}
              </SettingsCard>
            </div>
          ) : null}

          {selectedSection === "channels" && snapshot && selectedProvider === "telegram" ? (
            <div className="grid gap-3 md:grid-cols-3">
              <SettingsCard title={SOCIAL_COPY.channelPostingSettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "telegram")} />
                <SettingsRow label="Posting mode" value={deriveChannelProductTruth(snapshot, "telegram").postingMode} />
                <SettingsRow label="Posting frequency" value={deriveChannelProductTruth(snapshot, "telegram").postingFrequency} />
                <SettingsRow label="Autopilot (this channel)" value={deriveChannelProductTruth(snapshot, "telegram").autopilotLine} />
                <SettingsRow label="Content style" value={deriveContentStyle(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Telegram pacing is enforced server-side">
                  <SettingsRow label="Pacing detail" value="See activity preview and server limits" />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelReplySettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "telegram")} />
                <SettingsRow label="Reply mode" value={deriveChannelProductTruth(snapshot, "telegram").replyMode} />
                <SettingsRow label="Reply volume" value={deriveChannelProductTruth(snapshot, "telegram").replyVolume} />
                <SettingsRow label="Safe / blocked topics" value={personaBlockedTopicsSummary(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Inbound and reply bounds">
                  <SettingsRow label="Max replies per run/hour" value="Bounded by Social limits" />
                  <SettingsRow label="Reply only to mentions/comments" value="Uses allowed chat policy" />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelSafetySettings}>
                {(() => {
                  const h = telegramSafetyHints(snapshot.telegramStatus, snapshot.persona);
                  return (
                    <>
                      <SettingsRow label="Voice locked" value={h.voiceLocked ? "Yes" : "No"} />
                      <SettingsRow label="Approval required for live sends" value={h.approvalRequired ? "Yes" : "No"} />
                      <SettingsRow label="Emergency stop" value={h.emergencyStop ? "On" : "Off"} />
                      <SettingsRow label="Links in posts" value={h.noLinksUnlessEnabled ? "Restricted unless voice allows" : "Standard"} />
                      <SettingsRow label="Financial advice" value={h.noFinancialAdvice ? "Not allowed" : "Standard"} />
                      <SettingsRow label="Buy/sell language" value={h.noBuySellLanguage ? "Limited by voice rules" : "Standard"} />
                      <SettingsRow label="Secrets in this UI" value="Not collected here" />
                    </>
                  );
                })()}
              </SettingsCard>
            </div>
          ) : null}

          {selectedSection === "channels" && snapshot && selectedProvider === "discord" ? (
            <div className="grid gap-3 md:grid-cols-3">
              <SettingsCard title={SOCIAL_COPY.channelPostingSettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "discord")} />
                <SettingsRow label="Posting mode" value={deriveChannelProductTruth(snapshot, "discord").postingMode} />
                <SettingsRow label="Posting frequency" value={deriveChannelProductTruth(snapshot, "discord").postingFrequency} />
                <SettingsRow label="Autopilot (this channel)" value={deriveChannelProductTruth(snapshot, "discord").autopilotLine} />
                <SettingsRow label="Content style" value={deriveContentStyle(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Discord limits">
                  <SettingsRow label="Max posts per day" value="—" />
                  <SettingsRow label="Minimum spacing" value="—" />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelReplySettings}>
                <SettingsRow label="Provider readiness" value={resolveProviderReadiness(snapshot, "discord")} />
                <SettingsRow label="Reply mode" value={deriveChannelProductTruth(snapshot, "discord").replyMode} />
                <SettingsRow label="Reply volume" value={deriveChannelProductTruth(snapshot, "discord").replyVolume} />
                <SettingsRow label="Safe / blocked topics" value={personaBlockedTopicsSummary(snapshot.persona)} />
                <DetailsPanel title={SOCIAL_COPY.channelPacingAdvanced} summary="Reply limits">
                  <SettingsRow label="Max replies per run/hour" value="—" />
                  <SettingsRow label="Reply only to mentions/comments" value="Not configured yet" />
                </DetailsPanel>
              </SettingsCard>
              <SettingsCard title={SOCIAL_COPY.channelSafetySettings}>
                {(() => {
                  const h = discordSafetyHints(snapshot.persona);
                  return (
                    <>
                      <SettingsRow label="Voice locked" value={h.voiceLocked ? "Yes" : "No"} />
                      <SettingsRow label="Approval required for live sends" value={h.approvalRequired ? "Yes" : "No"} />
                      <SettingsRow label="Emergency stop" value={h.emergencyStop ? "On" : "Off"} />
                      <SettingsRow label="Links in posts" value={h.noLinksUnlessEnabled ? "Restricted unless voice allows" : "Standard"} />
                      <SettingsRow label="Financial advice" value={h.noFinancialAdvice ? "Not allowed" : "Standard"} />
                      <SettingsRow label="Buy/sell language" value={h.noBuySellLanguage ? "Limited by voice rules" : "Standard"} />
                      <SettingsRow label="Secrets in this UI" value="Not collected here" />
                    </>
                  );
                })()}
              </SettingsCard>
            </div>
          ) : null}

          {selectedSection === "channels" && selectedMessaging ? (
            <MessagingProviderPanel
              status={selectedMessaging.status}
              capabilities={selectedMessaging.capabilities}
              setup={selectedMessaging.setup}
              activeTab={channelTab}
              telegramPreview={selectedProvider === "telegram" ? telegramPreview : null}
              telegramPreviewBusy={telegramPreviewBusy}
              telegramPreviewError={selectedProvider === "telegram" ? telegramPreviewError : null}
              onPreviewTelegram={selectedProvider === "telegram" ? () => void runTelegramPreview() : undefined}
              telegramInboundPreview={selectedProvider === "telegram" ? telegramInboundPreview : null}
              telegramInboundPreviewBusy={telegramInboundPreviewBusy}
              telegramInboundPreviewError={selectedProvider === "telegram" ? telegramInboundPreviewError : null}
              onPreviewTelegramInbound={selectedProvider === "telegram" ? () => void runTelegramInboundPreview() : undefined}
              telegramReactivePreview={selectedProvider === "telegram" ? telegramReactivePreview : null}
              telegramReactivePreviewBusy={telegramReactivePreviewBusy}
              telegramReactivePreviewError={selectedProvider === "telegram" ? telegramReactivePreviewError : null}
              onPreviewTelegramReactive={selectedProvider === "telegram" ? () => void runTelegramReactivePreview() : undefined}
              onOpenTelegramReactiveLiveConfirm={
                selectedProvider === "telegram"
                  ? (item) => {
                      setTelegramReactiveSelected(item);
                      setTelegramReactiveConfirmOpen(true);
                      setTelegramReactiveLiveError(null);
                    }
                  : undefined
              }
              telegramReactiveLiveResult={selectedProvider === "telegram" ? telegramReactiveLiveResult : null}
              telegramReactiveLiveError={selectedProvider === "telegram" ? telegramReactiveLiveError : null}
              telegramActivityPreview={selectedProvider === "telegram" ? telegramActivityPreview : null}
              telegramActivityPreviewBusy={telegramActivityPreviewBusy}
              telegramActivityPreviewError={selectedProvider === "telegram" ? telegramActivityPreviewError : null}
              onPreviewTelegramActivity={selectedProvider === "telegram" ? () => void runTelegramActivityPreview() : undefined}
              telegramActivityRunOncePreview={selectedProvider === "telegram" ? telegramActivityRunOncePreview : null}
              telegramActivityRunOncePreviewBusy={telegramActivityRunOncePreviewBusy}
              telegramActivityRunOncePreviewError={selectedProvider === "telegram" ? telegramActivityRunOncePreviewError : null}
              onPreviewTelegramActivityRunOnce={selectedProvider === "telegram" ? () => void runTelegramActivityRunOncePreview() : undefined}
              onOpenTelegramActivityLiveConfirm={
                selectedProvider === "telegram"
                  ? () => {
                      setTelegramActivityConfirmOpen(true);
                      setTelegramActivityLiveError(null);
                    }
                  : undefined
              }
              telegramActivityLiveResult={selectedProvider === "telegram" ? telegramActivityLiveResult : null}
              telegramActivityLiveError={selectedProvider === "telegram" ? telegramActivityLiveError : null}
              onOpenTelegramLiveConfirm={
                selectedProvider === "telegram"
                  ? () => {
                      setTelegramConfirmOpen(true);
                      setTelegramLiveError(null);
                    }
                  : undefined
              }
              telegramLiveResult={selectedProvider === "telegram" ? telegramLiveResult : null}
              telegramLiveError={selectedProvider === "telegram" ? telegramLiveError : null}
            />
          ) : null}

          {selectedSection === "channels" && selectedProvider === "x" && x && caps ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {channelTab === "operate" ? (
              <>
              <Panel title="X primary actions">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Preview the three safe X work modes first. Nothing is sent from these actions, and live controls still require the existing confirmation flow.
                  </p>
                  <div className="grid gap-3 lg:grid-cols-3">
                    <XActionCard
                      kind="broadcast_preflight"
                      busyKind={previewBusy}
                      onPreview={(kind) => void runPreview(kind)}
                    />
                    <XActionCard
                      kind="reactive_inbox"
                      busyKind={previewBusy}
                      onPreview={(kind) => void runPreview(kind)}
                    />
                    <XActionCard
                      kind="reactive_batch_dry_run"
                      busyKind={previewBusy}
                      onPreview={(kind) => void runPreview(kind)}
                    />
                  </div>
                  <p className="text-xs text-white/42">No live X write happens from these preview/check actions.</p>
                </div>
              </Panel>

              {previewError ? (
                <WorkspaceSurfaceStateCard
                  title="Preview needs attention"
                  description="A preview request needs attention. Status panels may still be available."
                  tone="amber"
                  technicalDetail={previewError}
                />
              ) : null}

              {Object.entries(previews).map(([kind, preview]) =>
                preview ? <PreviewResultCard key={kind} preview={preview} /> : null,
              )}
              </>
              ) : null}

              {setup && channelTab === "setup" ? (
              <>
                <DetailsPanel title="X setup" summary="Connections, readiness, and recommended steps">
                  <div className="space-y-4">
                    <div className="flex flex-wrap gap-2">
                      <StatusPill label={setup.provider_configured ? "Channel configured" : "Channel limited"} tone={setup.provider_configured ? "ok" : "warn"} />
                      <StatusPill label={titleCase(setup.overall_readiness)} tone={statusTone(setup.overall_readiness)} />
                    </div>
                    <ChecklistGroup
                      title="Required connections"
                      rows={[
                        { id: "x_read", label: "X read credential present", ok: Boolean(setup.required_connections.x_read_credential_present) },
                        { id: "x_write", label: "X write credential present", ok: Boolean(setup.required_connections.x_write_credential_present) },
                        { id: "xai", label: "xAI key present", ok: Boolean(setup.required_connections.xai_key_present) },
                        { id: "reactive_handle", label: "Reply handle configured", ok: Boolean(setup.required_connections.reactive_handle_configured) },
                        { id: "operator", label: "Operator token ready", ok: Boolean(setup.required_connections.operator_token_ready) },
                        { id: "emergency", label: "Emergency stop off", ok: Boolean(setup.required_connections.emergency_stop_disabled) },
                      ]}
                    />
                    <ChecklistGroup
                      title="Deployment checklist"
                      rows={[
                        { id: "dry_run", label: "Ready for previews", ok: setup.ready_for_dry_run },
                        { id: "live_reply", label: "Ready for confirmed live reply", ok: setup.ready_for_confirmed_live_reply },
                        { id: "batch", label: "Ready for reactive batch", ok: setup.ready_for_reactive_batch },
                        { id: "broadcast", label: "Ready for broadcast", ok: setup.ready_for_broadcast },
                      ]}
                    />
                    {setup.missing_requirement_ids.length ? (
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Missing requirements</h3>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {setup.missing_requirement_ids.map((id) => (
                            <StatusPill key={id} label={titleCase(id)} tone="warn" />
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </DetailsPanel>
              </>
              ) : null}

              {setup && channelTab === "advanced" ? (
              <>
                <DetailsPanel title="X setup identifiers (masked)" summary={SOCIAL_COPY.advancedDetailsSummary}>
                  <KeyValueGrid
                    rows={Object.entries(setup.safe_identifiers).map(([key, value]) => ({
                      label: titleCase(key),
                      value: value || "Not set",
                    }))}
                  />
                </DetailsPanel>
                <DetailsPanel title="Automation readiness" summary={SOCIAL_COPY.advancedDetailsSummary}>
                  <div className="space-y-4">
                    {Object.entries(setup.lane_readiness).map(([lane, data]) => (
                      <div key={lane} className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">{titleCase(lane)}</h3>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          {Object.entries(data)
                            .filter(([, value]) => typeof value === "boolean")
                            .map(([key, value]) => (
                              <BoolRow key={key} label={titleCase(key)} value={Boolean(value)} />
                            ))}
                        </div>
                        {Array.isArray(data.missing) && data.missing.length ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(data.missing as string[]).map((item) => (
                              <StatusPill key={item} label={titleCase(item)} tone="warn" />
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </DetailsPanel>
              </>
              ) : null}

              {setup && channelTab === "setup" ? (
                <DetailsPanel title="Setup guidance" summary="Show recommended next steps">
                  <div className="space-y-3 text-sm text-white/62">
                    <p>
                      Ask Ham to help configure this is a placeholder for a future guided setup flow. This panel is setup guidance:
                      no secret entry on this screen, no credential entry, and no configuration changes here.
                    </p>
                    <div className="space-y-2">
                      {setup.recommended_next_steps.map((step) => (
                        <div key={step} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                          {step}
                        </div>
                      ))}
                    </div>
                  </div>
                </DetailsPanel>
              ) : null}

              {channelTab === "operate" ? (
              <>
              <Panel title="Send approved reply">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Sends exactly one X reply from the latest reply check. If the voice changes, check replies again first.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill
                      label={inboxPreview?.proposal_digest ? "Preview locked" : "Preview required before sending"}
                      tone={inboxPreview?.proposal_digest ? "ok" : "warn"}
                    />
                    <StatusPill
                      label={caps.reactive_reply_apply_available ? "Ready for operator approval" : "Preview required before sending"}
                      tone={caps.reactive_reply_apply_available ? "ok" : "muted"}
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="bg-red-600 text-white hover:bg-red-500"
                    disabled={!canSendOneLiveReply}
                    onClick={() => {
                      setConfirmOpen(true);
                      setLiveError(null);
                    }}
                  >
                    Send one approved reply
                  </Button>
                  {!canSendOneLiveReply ? (
                    <p className="text-xs text-white/42">
                      Check replies first, then confirm that approved reply sending is available.
                    </p>
                  ) : null}
                </div>
              </Panel>

              {liveError ? (
                <WorkspaceSurfaceStateCard
                  title="Live reply needs attention"
                  description="The confirmed one-shot live reply did not run."
                  tone="amber"
                  technicalDetail={liveError}
                />
              ) : null}

              {liveResult ? (
                <FriendlyLiveOutcomeCard title="Approved reply result" record={liveResult as unknown as Record<string, unknown>} />
              ) : null}

              <Panel title="Send approved reply batch">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Sends multiple approved replies, capped by the reply limits. No retry. No post.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill
                      label={batchPreview?.proposal_digest ? "Preview locked" : "Preview required before sending"}
                      tone={batchPreview?.proposal_digest ? "ok" : "warn"}
                    />
                    <StatusPill
                      label={caps.reactive_batch_apply_available ? "Ready for operator approval" : "Preview required before sending"}
                      tone={caps.reactive_batch_apply_available ? "ok" : "muted"}
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="bg-red-700 text-white hover:bg-red-600"
                    disabled={!canSendLiveReactiveBatch}
                    onClick={() => {
                      setBatchConfirmOpen(true);
                      setBatchError(null);
                    }}
                  >
                    Send live reactive batch
                  </Button>
                  {!canSendLiveReactiveBatch ? (
                    <p className="text-xs text-white/42">
                      Preview multiple replies first, then confirm that batch sending is available.
                    </p>
                  ) : null}
                </div>
              </Panel>

              {batchError ? (
                <WorkspaceSurfaceStateCard
                  title="Live reply batch needs attention"
                  description="The confirmed live reply batch did not run."
                  tone="amber"
                  technicalDetail={batchError}
                />
              ) : null}

              {batchResult ? (
                <FriendlyLiveOutcomeCard title="Approved reply batch result" record={batchResult as unknown as Record<string, unknown>} />
              ) : null}

              <Panel title="Send approved post">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Sends exactly one original X post using the locked voice. No batch. No retry. No replies.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill
                      label={broadcastPreview?.proposal_digest ? "Preview locked" : "Preview required before sending"}
                      tone={broadcastPreview?.proposal_digest ? "ok" : "warn"}
                    />
                    <StatusPill
                      label={caps.broadcast_apply_available ? "Ready for operator approval" : "Preview required before sending"}
                      tone={caps.broadcast_apply_available ? "ok" : "muted"}
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="bg-red-800 text-white hover:bg-red-700"
                    disabled={!canSendOneLivePost}
                    onClick={() => {
                      setBroadcastConfirmOpen(true);
                      setBroadcastError(null);
                    }}
                  >
                    Send approved post
                  </Button>
                  {!canSendOneLivePost ? (
                    <p className="text-xs text-white/42">
                      Preview an X post first, then confirm that approved post sending is ready.
                    </p>
                  ) : null}
                </div>
              </Panel>

              {broadcastError ? (
                <WorkspaceSurfaceStateCard
                  title="Live post needs attention"
                  description="The confirmed one-shot live post did not run."
                  tone="amber"
                  technicalDetail={broadcastError}
                />
              ) : null}

              {broadcastResult ? (
                <FriendlyLiveOutcomeCard title="Approved post result" record={broadcastResult as unknown as Record<string, unknown>} />
              ) : null}
              </>
              ) : null}

              {channelTab === "advanced" ? (
              <>
              <TechnicalProofIntro />
              <Panel title="X status strip">
                <div className="mb-3 flex flex-wrap gap-2">
                  <StatusPill label={titleCase(x.overall_readiness)} tone={statusTone(x.overall_readiness)} />
                  <StatusPill label={x.read_only ? "Status check" : "Actions available"} tone={x.read_only ? "ok" : "danger"} />
                  <StatusPill
                    label={x.emergency_stop.enabled ? "Emergency stop on" : "Emergency stop off"}
                    tone={x.emergency_stop.enabled ? "danger" : "ok"}
                  />
                  <StatusPill
                    label={caps.live_apply_available ? "Live actions require confirmation" : "Preview required before sending"}
                    tone={caps.live_apply_available ? "danger" : "ok"}
                  />
                </div>
                {x.readiness_reasons.length ? (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-white/60">
                    {x.readiness_reasons.map((reason) => (
                      <li key={reason}>{titleCase(reason)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-white/55">No setup needs reported.</p>
                )}
              </Panel>

              <DetailsPanel title="X setup feature flags" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(snapshot.xSetup.feature_flags).map(([key, value]) => (
                    <BoolRow key={key} label={titleCase(key)} value={value} />
                  ))}
                </div>
              </DetailsPanel>

              <DetailsPanel title="Available actions" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <CapabilityRows capabilities={caps} />
              </DetailsPanel>

              <DetailsPanel title="Safety proof" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <div className="grid gap-2 sm:grid-cols-2">
                  <BoolRow label="Global preview mode" value={x.dry_run_defaults.global_dry_run} />
                  <BoolRow label="Controller preview mode" value={x.dry_run_defaults.controller_dry_run} />
                  <BoolRow label="Reply preview mode" value={x.dry_run_defaults.reactive_dry_run} />
                  <BoolRow label="Reply batch preview mode" value={x.dry_run_defaults.reactive_batch_dry_run} />
                </div>
              </DetailsPanel>

              <DetailsPanel title="Posting lane (advanced)" summary="Technical readiness for original posts">
                <KeyValueGrid
                  rows={[
                    { label: "Mode configured", value: x.broadcast_lane.enabled ? "Yes" : "No" },
                    { label: "Controller", value: x.broadcast_lane.controller_enabled ? "Configured" : "Waiting for setup" },
                    { label: "Live controller", value: x.broadcast_lane.live_controller_enabled ? "Configured" : "Waiting for setup" },
                    { label: "Preview", value: x.broadcast_lane.dry_run_available ? "Ready" : "Needs setup" },
                    { label: "Live configured", value: x.broadcast_lane.live_configured ? "Yes" : "No" },
                    { label: "Ready to send now", value: x.broadcast_lane.execution_allowed_now ? "Yes" : "No" },
                  ]}
                />
                {x.broadcast_lane.reasons.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {x.broadcast_lane.reasons.map((reason) => (
                      <StatusPill key={reason} label={titleCase(reason)} tone="warn" />
                    ))}
                  </div>
                ) : null}
              </DetailsPanel>

              <DetailsPanel title="Reply lane (advanced)" summary="Technical readiness for replies">
                <KeyValueGrid
                  rows={[
                    { label: "Mode configured", value: x.reactive_lane.enabled ? "Yes" : "No" },
                    { label: "Inbox discovery", value: x.reactive_lane.inbox_discovery_enabled ? "Configured" : "Waiting for setup" },
                    { label: "Preview", value: x.reactive_lane.dry_run_enabled ? "Ready" : "Needs setup" },
                    { label: "One-reply confirmation", value: x.reactive_lane.live_canary_enabled ? "Configured" : "Waiting for setup" },
                    { label: "Batch replies", value: x.reactive_lane.batch_enabled ? "Configured" : "Waiting for setup" },
                  ]}
                />
                {x.reactive_lane.reasons.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {x.reactive_lane.reasons.map((reason) => (
                      <StatusPill key={reason} label={titleCase(reason)} tone="warn" />
                    ))}
                  </div>
                ) : null}
              </DetailsPanel>

              <DetailsPanel title="Safety boundary" summary="Show frontend/API safety notes">
                <div className="space-y-2 text-sm text-white/62">
                  <p className="flex gap-2">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                    Frontend uses `hamApiFetch` against Social API endpoints and keeps live sends behind confirmation flows.
                  </p>
                  <p className="flex gap-2">
                    <Circle className="mt-1 h-3 w-3 shrink-0 text-white/40" />
                    Live posting, replies, and batch execution stay gated by locked previews, confirmation phrases, and operator authorization.
                  </p>
                </div>
              </DetailsPanel>

              <DetailsPanel title="Live apply payloads (raw JSON)" summary="Confirmed sends from this browser session">
                {liveResult || batchResult || broadcastResult ? (
                  <div className="space-y-3">
                    {liveResult ? (
                      <div>
                        <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">One reply apply</h3>
                        <RecordPreview record={liveResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
                      </div>
                    ) : null}
                    {batchResult ? (
                      <div>
                        <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Reply batch apply</h3>
                        <RecordPreview record={batchResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
                      </div>
                    ) : null}
                    {broadcastResult ? (
                      <div>
                        <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Post apply</h3>
                        <RecordPreview record={broadcastResult as unknown as Record<string, unknown>} emptyLabel="No payload." />
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-sm text-white/45">No live apply responses in this session yet.</p>
                )}
              </DetailsPanel>

              {Object.keys(previews).length ? (
                <DetailsPanel title="Recent X previews (raw JSON)" summary="Preflight payloads from this session">
                  <div className="space-y-3">
                    {(Object.entries(previews) as [SocialPreviewKind, SocialPreviewResponse | undefined][]).map(([kind, preview]) =>
                      preview ? (
                        <div key={kind}>
                          <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-white/45">{PREVIEW_LABELS[kind]}</h3>
                          <RecordPreview record={preview.result} emptyLabel="No preview payload." />
                        </div>
                      ) : null,
                    )}
                  </div>
                </DetailsPanel>
              ) : null}

              <DetailsPanel title="Delivery history" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <KeyValueGrid
                  rows={[
                    { label: "Path", value: snapshot.xJournal.journal_path },
                    { label: "Rows scanned", value: snapshot.xJournal.total_count_scanned },
                    { label: "Malformed", value: snapshot.xJournal.malformed_count },
                    { label: "Recent cap", value: snapshot.xJournal.bounds.max_recent_items },
                  ]}
                />
                <div className="mt-3">
                  <RecordPreview record={snapshot.xJournal.counts_by_execution_kind} emptyLabel="No journal counts yet." />
                </div>
                <div className="mt-3 space-y-2">
                  {snapshot.xJournal.recent_items.length ? (
                    snapshot.xJournal.recent_items.map((item, idx) => (
                      <RecordPreview key={idx} record={item} emptyLabel="No journal record." />
                    ))
                  ) : (
                    <p className="text-sm text-white/45">No recent journal items.</p>
                  )}
                </div>
              </DetailsPanel>

              <DetailsPanel title="Safety log" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <KeyValueGrid
                  rows={[
                    { label: "Path", value: snapshot.xAudit.audit_path },
                    { label: "Rows scanned", value: snapshot.xAudit.total_count_scanned },
                    { label: "Malformed", value: snapshot.xAudit.malformed_count },
                    { label: "Recent cap", value: snapshot.xAudit.bounds.max_recent_events },
                  ]}
                />
                <div className="mt-3">
                  <RecordPreview record={snapshot.xAudit.counts_by_event_type} emptyLabel="No audit counts yet." />
                </div>
                {snapshot.xAudit.latest_audit_ids.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {snapshot.xAudit.latest_audit_ids.map((id) => (
                      <StatusPill key={id} label={id} tone="muted" />
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 space-y-2">
                  {snapshot.xAudit.recent_events.length ? (
                    snapshot.xAudit.recent_events.map((event, idx) => (
                      <RecordPreview key={idx} record={event} emptyLabel="No audit event." />
                    ))
                  ) : (
                    <p className="text-sm text-white/45">No recent audit events.</p>
                  )}
                </div>
              </DetailsPanel>

              <DetailsPanel title="Latest post & reply (raw journal rows)" summary={SOCIAL_COPY.advancedDetailsSummary}>
                <RecordPreview record={x.last_autonomous_post} emptyLabel="No autonomous post in summary." />
                <div className="mt-3">
                  <RecordPreview record={x.last_reactive_reply} emptyLabel="No reactive reply in summary." />
                </div>
              </DetailsPanel>
              </>
              ) : null}

              {channelTab === "activity" ? (
              <>
              <Panel title="How hard Ham is working on X">
                <p className="text-sm leading-relaxed text-white/68">
                  Today Ham has used{" "}
                  <span className="text-white/85">
                    {x.cap_cooldown_summary.broadcast_daily_used} of {x.cap_cooldown_summary.broadcast_daily_cap}
                  </span>{" "}
                  post slots, with{" "}
                  <span className="text-white/85">{x.cap_cooldown_summary.broadcast_daily_remaining}</span> still available. Posts are
                  spaced at least {x.cap_cooldown_summary.broadcast_min_spacing_minutes} minutes apart. Reply pacing is capped per
                  quarter-hour, hour, user, and thread so bursts cannot slip through unnoticed.
                </p>
              </Panel>

              <Panel title="Latest post">
                {formatLooseRecordSummary(x.last_autonomous_post) ? (
                  <p className="text-sm leading-relaxed text-white/75">{formatLooseRecordSummary(x.last_autonomous_post)}</p>
                ) : (
                  <p className="text-sm text-white/45">No recent post text in the activity window.</p>
                )}
              </Panel>

              <Panel title="Latest reply">
                {formatLooseRecordSummary(x.last_reactive_reply) ? (
                  <p className="text-sm leading-relaxed text-white/75">{formatLooseRecordSummary(x.last_reactive_reply)}</p>
                ) : (
                  <p className="text-sm text-white/45">No recent reply text in the activity window.</p>
                )}
              </Panel>

              <Panel title="Deeper logs">
                <p className="text-sm text-white/58">
                  Delivery rows, safety counters, and full JSON snapshots stay under{" "}
                  <span className="text-white/78">Advanced technical proof</span> for this channel.
                </p>
              </Panel>
              </>
              ) : null}

              {channelTab === "setup" ? (
              <DetailsPanel title="Setup checklist" summary="Connection checks for this channel">
                <div className="space-y-2">
                  {snapshot.xSetup.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                        {item.label}
                      </div>
                      <StatusPill label={item.ok ? "OK" : "Missing"} tone={item.ok ? "ok" : "warn"} />
                    </div>
                  ))}
                </div>
              </DetailsPanel>
              ) : null}

            </div>
          ) : null}

          {selectedSection === "activity" ? (
            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title={SOCIAL_COPY.activityWhatHamDoing}>
                <div className="space-y-3 text-sm text-white/68">
                  <p>
                    Ham drafts and previews social messages with your persona. Confirmed sends only happen through the existing
                    approval flows on each channel.
                  </p>
                  <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">Last X post (summary)</p>
                    <p className="mt-2 text-white/75">
                      {formatLooseRecordSummary(snapshot.xJournal.latest_broadcast_post as Record<string, unknown> | null) ||
                        "Nothing recorded in this snapshot yet."}
                    </p>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">Last X reply (summary)</p>
                    <p className="mt-2 text-white/75">
                      {formatLooseRecordSummary(snapshot.xJournal.latest_reactive_reply as Record<string, unknown> | null) ||
                        "Nothing recorded in this snapshot yet."}
                    </p>
                  </div>
                </div>
              </Panel>
              <Panel title={SOCIAL_COPY.overviewRecentActivity}>
                <p className="text-sm leading-relaxed text-white/65">
                  This is a light view of recent X outcomes. For Telegram or Discord, run an inbox or preview on that channel —
                  suggestions appear in those flows, not as raw feeds here.
                </p>
              </Panel>
              <Panel title={SOCIAL_COPY.activityRecentSuggestions}>
                <p className="text-sm leading-relaxed text-white/65">
                  Open <span className="text-white/80">Channels</span>, pick X or Telegram, then run an inbox or draft preview.
                  Suggested replies and posts stay on those screens until you confirm or dismiss them.
                </p>
              </Panel>
              <Panel title={SOCIAL_COPY.activitySafetyRelevant}>
                <p className="text-sm leading-relaxed text-white/65">
                  When Ham holds something back, preview cards explain why in plain language. For full safety and audit payloads,
                  use <span className="text-white/80">Advanced technical proof</span> on the channel.
                </p>
              </Panel>
              <div className="col-span-full">
                <DetailsPanel title={SOCIAL_COPY.activityTelemetryDetailsTitle} summary={SOCIAL_COPY.activityTelemetryDetailsSummary}>
                  <div className="grid gap-2 text-sm text-white/60 sm:grid-cols-2">
                    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      Journal items in snapshot: {snapshot.xJournal.recent_items.length}
                    </div>
                    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      Recent safety events in snapshot: {snapshot.xAudit.recent_events.length}
                    </div>
                  </div>
                  <p className="mt-3 text-xs text-white/45">
                    Full JSON is under <span className="text-white/60">Channels → X → Advanced technical proof</span>.
                  </p>
                </DetailsPanel>
              </div>
            </div>
          ) : null}

          {selectedSection === "setup" ? (
            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title="Setup overview">
                <div className="space-y-2 text-sm text-white/62">
                  {snapshot.providers.map((provider) => (
                    <div key={`setup-${provider.id}`} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <span>{provider.label}</span>
                      <StatusPill
                        label={provider.configured ? "Configured" : provider.coming_soon ? "Planned" : "Needs setup"}
                        tone={provider.configured ? "ok" : provider.coming_soon ? "muted" : "warn"}
                      />
                    </div>
                  ))}
                </div>
              </Panel>
              <DetailsPanel title="X setup checklist" summary="Show required X setup checks">
                <div className="space-y-2">
                  {snapshot.xSetup.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                        {item.label}
                      </div>
                      <StatusPill label={item.ok ? "Ready" : "Missing"} tone={item.ok ? "ok" : "warn"} />
                    </div>
                  ))}
                </div>
              </DetailsPanel>
              <DetailsPanel title="Telegram setup checklist" summary="Show Telegram setup checks">
                <div className="space-y-2">
                  {snapshot.telegramSetup.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                        {item.label}
                      </div>
                      <StatusPill label={item.ok ? "Ready" : "Missing"} tone={item.ok ? "ok" : "warn"} />
                    </div>
                  ))}
                </div>
              </DetailsPanel>
              <DetailsPanel title="Discord setup checklist" summary="Show Discord setup checks">
                <div className="space-y-2">
                  {snapshot.discordSetup.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                        {item.label}
                      </div>
                      <StatusPill label={item.ok ? "Ready" : "Missing"} tone={item.ok ? "ok" : "warn"} />
                    </div>
                  ))}
                </div>
              </DetailsPanel>
            </div>
          ) : null}
        </>
      ) : null}

      {telegramConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="telegram-live-message-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="telegram-live-message-title" className="text-lg font-semibold">
              Confirmed live Telegram message
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one Telegram message to the configured test/home target. No batch. No retry.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={telegramConfirmText}
                  onChange={(event) => setTelegramConfirmText(event.target.value)}
                  placeholder={LIVE_TELEGRAM_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={telegramOperatorToken}
                  onChange={(event) => setTelegramOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="border-white/15 bg-white/5 text-white/85"
                onClick={() => setTelegramConfirmOpen(false)}
                disabled={telegramLiveBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                className="bg-red-700 text-white hover:bg-red-600"
                onClick={() => void sendOneTelegramMessage()}
                disabled={
                  telegramLiveBusy ||
                  telegramConfirmText.trim() !== LIVE_TELEGRAM_CONFIRMATION_PHRASE ||
                  !telegramOperatorToken.trim()
                }
              >
                {telegramLiveBusy ? "Sending..." : "Send one Telegram message"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {telegramReactiveConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="telegram-live-reactive-reply-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="telegram-live-reactive-reply-title" className="text-lg font-semibold">
              Confirmed live Telegram reply
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one Telegram reply through the governed Social cockpit. No batch. No retry. No autonomous runner.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={telegramReactiveConfirmText}
                  onChange={(event) => setTelegramReactiveConfirmText(event.target.value)}
                  placeholder={LIVE_TELEGRAM_REACTIVE_REPLY_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={telegramReactiveOperatorToken}
                  onChange={(event) => setTelegramReactiveOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="border-white/15 bg-white/5 text-white/85"
                onClick={() => setTelegramReactiveConfirmOpen(false)}
                disabled={telegramReactiveLiveBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                className="bg-red-700 text-white hover:bg-red-600"
                onClick={() => void sendOneTelegramReactiveReply()}
                disabled={
                  telegramReactiveLiveBusy ||
                  telegramReactiveConfirmText.trim() !== LIVE_TELEGRAM_REACTIVE_REPLY_CONFIRMATION_PHRASE ||
                  !telegramReactiveOperatorToken.trim() ||
                  !telegramReactiveSelected?.proposal_digest
                }
              >
                {telegramReactiveLiveBusy ? "Sending..." : "Send one Telegram reply"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {telegramActivityConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="telegram-live-activity-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="telegram-live-activity-title" className="text-lg font-semibold">
              Confirmed live Telegram activity
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one Telegram activity message to the configured test group. No batch. No retry. No scheduler.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={telegramActivityConfirmText}
                  onChange={(event) => setTelegramActivityConfirmText(event.target.value)}
                  placeholder={LIVE_TELEGRAM_ACTIVITY_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={telegramActivityOperatorToken}
                  onChange={(event) => setTelegramActivityOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="border-white/15 bg-white/5 text-white/85"
                onClick={() => setTelegramActivityConfirmOpen(false)}
                disabled={telegramActivityLiveBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                className="bg-red-700 text-white hover:bg-red-600"
                onClick={() => void sendOneTelegramActivity()}
                disabled={
                  telegramActivityLiveBusy ||
                  telegramActivityConfirmText.trim() !== LIVE_TELEGRAM_ACTIVITY_CONFIRMATION_PHRASE ||
                  !telegramActivityOperatorToken.trim()
                }
              >
                {telegramActivityLiveBusy ? "Sending..." : "Send one Telegram activity"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {confirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="social-live-reply-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="social-live-reply-title" className="text-lg font-semibold">
              Confirmed live X reply
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one live reply. No batch. No retry.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={confirmText}
                  onChange={(event) => setConfirmText(event.target.value)}
                  placeholder={LIVE_REPLY_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={operatorToken}
                  onChange={(event) => setOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
              <p className="text-xs text-white/40">
                The frontend sends only the proposal digest, confirmation phrase, and operator token. It never sends reply text.
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setConfirmOpen(false);
                  setConfirmText("");
                  setOperatorToken("");
                }}
                disabled={liveBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                className="bg-red-600 text-white hover:bg-red-500"
                onClick={() => void sendOneLiveReply()}
                disabled={liveBusy || confirmText !== LIVE_REPLY_CONFIRMATION_PHRASE || !operatorToken.trim()}
              >
                {liveBusy ? "Sending approved reply..." : "Send one approved reply"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {batchConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="social-live-batch-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="social-live-batch-title" className="text-lg font-semibold">
              Confirmed live reactive batch
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This may send multiple approved replies, capped by your configured reply limits. No retry. No broadcast post.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={batchConfirmText}
                  onChange={(event) => setBatchConfirmText(event.target.value)}
                  placeholder={LIVE_BATCH_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={batchOperatorToken}
                  onChange={(event) => setBatchOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
              <p className="text-xs text-white/40">
                The frontend sends only the batch proposal digest, confirmation phrase, and operator token. It never sends reply text or candidate bodies.
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setBatchConfirmOpen(false);
                  setBatchConfirmText("");
                  setBatchOperatorToken("");
                }}
                disabled={batchBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                className="bg-red-700 text-white hover:bg-red-600"
                onClick={() => void sendLiveReactiveBatch()}
                disabled={batchBusy || batchConfirmText !== LIVE_BATCH_CONFIRMATION_PHRASE || !batchOperatorToken.trim()}
              >
                {batchBusy ? "Sending live reactive batch..." : "Send live reactive batch"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {broadcastConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="social-live-broadcast-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="social-live-broadcast-title" className="text-lg font-semibold">
              Confirmed live X post
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one live original post. No batch. No retry. No replies.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={broadcastConfirmText}
                  onChange={(event) => setBroadcastConfirmText(event.target.value)}
                  placeholder={LIVE_BROADCAST_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={broadcastOperatorToken}
                  onChange={(event) => setBroadcastOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
              <p className="text-xs text-white/40">
                The frontend sends only the broadcast proposal digest, confirmation phrase, and operator token. It never sends post text or candidate bodies.
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setBroadcastConfirmOpen(false);
                  setBroadcastConfirmText("");
                  setBroadcastOperatorToken("");
                }}
                disabled={broadcastBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                className="bg-red-800 text-white hover:bg-red-700"
                onClick={() => void sendOneLivePost()}
                disabled={broadcastBusy || broadcastConfirmText !== LIVE_BROADCAST_CONFIRMATION_PHRASE || !broadcastOperatorToken.trim()}
              >
                {broadcastBusy ? "Sending approved post..." : "Send approved post"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
