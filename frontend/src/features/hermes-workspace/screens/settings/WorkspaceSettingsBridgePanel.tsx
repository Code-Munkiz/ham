import * as React from "react";
import { fetchModelsCatalog } from "@/lib/ham/api";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import type { WorkspaceSettingsBridgeSectionId } from "./workspaceSettingsNavData";
import { Switch } from "@/components/ui/switch";
import {
  WorkspaceSettingsCapabilityBadge,
  WorkspaceSettingsFieldRow,
  WorkspaceSettingsReadOnlyCard,
  WorkspaceSettingsSectionHeader,
  WorkspaceSettingsUnavailableNote,
} from "./workspaceSettingsReadOnlyChrome";

type WorkspaceSettingsBridgePanelProps = {
  section: WorkspaceSettingsBridgeSectionId;
};

function formatYesNo(v: boolean | undefined): string {
  if (v === true) return "Yes";
  if (v === false) return "No";
  return "—";
}

function useModelsCatalog() {
  const [catalog, setCatalog] = React.useState<ModelCatalogPayload | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    fetchModelsCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load catalog");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return { catalog, err };
}

function useOsColorScheme(): string {
  const [scheme, setScheme] = React.useState<string>(() =>
    typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  );
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setScheme(mq.matches ? "dark" : "light");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return scheme;
}

export function WorkspaceSettingsBridgePanel({ section }: WorkspaceSettingsBridgePanelProps) {
  const { catalog, err } = useModelsCatalog();
  const osScheme = useOsColorScheme();

  const chatModels =
    catalog?.items.filter((i) => i.supports_chat && !i.disabled_reason).length ?? null;
  const totalModels = catalog?.items.length ?? null;

  switch (section) {
    case "agent":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Agent behavior"
            subtitle="Upstream Hermes configures instruction budgets, tools, and agent defaults in HermesConfigSection (activeView agent). HAM can chat through the configured gateway, but persisting Hermes-style agent policy from this UI is not wired."
            badge={<WorkspaceSettingsCapabilityBadge tone="amber">Hermes bridge required</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            <WorkspaceSettingsFieldRow
              label="Writable agent policy"
              value="Unavailable"
              hint="Requires a writable Hermes runtime config bridge. Current HAM runtime exposes chat and context via the API host — not agent policy saves from the browser."
            />
            {catalog ? (
              <>
                <WorkspaceSettingsFieldRow
                  label="Gateway mode (HAM API)"
                  value={catalog.gateway_mode || "—"}
                  hint="From GET /api/models — informational only."
                />
                <WorkspaceSettingsFieldRow
                  label="Dashboard chat ready"
                  value={formatYesNo(isDashboardChatGatewayReady(catalog))}
                />
              </>
            ) : err ? (
              <WorkspaceSettingsUnavailableNote>Could not load HAM API snapshot: {err}</WorkspaceSettingsUnavailableNote>
            ) : (
              <WorkspaceSettingsFieldRow label="HAM API snapshot" value="Loading…" />
            )}
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    case "routing":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Smart routing"
            subtitle="Upstream Hermes maps model routing and fallbacks in HermesConfigSection (activeView routing). HAM resolves models and gateway paths on the server; this view summarizes what the HAM API reports — it does not change routing policy."
            badge={<WorkspaceSettingsCapabilityBadge>Read-only</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            {catalog ? (
              <>
                <WorkspaceSettingsFieldRow label="Gateway mode" value={catalog.gateway_mode || "—"} />
                <WorkspaceSettingsFieldRow
                  label="OpenRouter chat ready"
                  value={formatYesNo(catalog.openrouter_chat_ready)}
                />
                <WorkspaceSettingsFieldRow label="HTTP gateway ready" value={formatYesNo(catalog.http_chat_ready)} />
                <WorkspaceSettingsFieldRow
                  label="HTTP primary model"
                  value={catalog.http_chat_model_primary ?? "—"}
                  hint="When gateway_mode is http — configured on the API host."
                />
                <WorkspaceSettingsFieldRow
                  label="HTTP fallback model"
                  value={catalog.http_chat_model_fallback ?? "—"}
                />
                <WorkspaceSettingsFieldRow
                  label="Catalog entries"
                  value={totalModels != null ? String(totalModels) : "—"}
                />
                <WorkspaceSettingsFieldRow
                  label="Chat-capable models (unblocked)"
                  value={chatModels != null ? String(chatModels) : "—"}
                />
              </>
            ) : err ? (
              <WorkspaceSettingsUnavailableNote>
                Could not load routing snapshot from the HAM API: {err}. Smart routing detail is unavailable until the
                models endpoint responds.
              </WorkspaceSettingsUnavailableNote>
            ) : (
              <WorkspaceSettingsFieldRow label="HAM API snapshot" value="Loading…" />
            )}
            <p className="mt-4 text-[11px] text-white/35">
              Routing policy changes are not available in this workspace UI; they remain on the Ham server configuration.
            </p>
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    case "voice": {
      const ttsRow = (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <span className="shrink-0 text-[13px] text-white/65">TTS Provider</span>
          <select
            disabled
            className="h-8 w-full max-w-xs cursor-not-allowed rounded-lg border border-white/[0.1] bg-white/[0.04] px-2.5 text-[12px] text-white/45 outline-none sm:max-w-sm"
            aria-label="TTS provider (read-only)"
            value="edge"
          >
            <option value="edge">Edge TTS</option>
            <option value="elevenlabs">ElevenLabs</option>
            <option value="openai_tts">OpenAI TTS</option>
            <option value="neutts">NeuTTS</option>
          </select>
        </div>
      );
      const sttRows = (
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <span className="shrink-0 text-[13px] text-white/65">Enable STT</span>
            <Switch checked={false} disabled className="opacity-50" aria-label="Enable STT (read-only)" />
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <span className="shrink-0 text-[13px] text-white/65">STT Provider</span>
            <select
              disabled
              className="h-8 w-full max-w-xs cursor-not-allowed rounded-lg border border-white/[0.1] bg-white/[0.04] px-2.5 text-[12px] text-white/45 outline-none sm:max-w-sm"
              aria-label="STT provider (read-only)"
              value="openai"
            >
              <option value="local">Local (Whisper)</option>
              <option value="openai">OpenAI transcription (server)</option>
            </select>
          </div>
        </div>
      );
      return (
        <WorkspaceSettingsReadOnlyCard>
          <div className="mb-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">Settings</p>
          </div>
          <WorkspaceSettingsSectionHeader
            title="Voice"
            subtitle="Text-to-speech and speech-to-text."
            badge={<WorkspaceSettingsCapabilityBadge>Read-only</WorkspaceSettingsCapabilityBadge>}
          />
          <p className="mt-4 text-[12px] leading-relaxed text-white/50">
            Voice settings are read-only until the HAM runtime config bridge is wired. Chat dictation in the workspace
            composer uses <span className="font-mono text-white/65">POST /api/chat/transcribe</span> when the API host
            sets <span className="font-mono text-white/65">HAM_TRANSCRIPTION_*</span> (OpenAI transcription). This is
            not a &quot;Local (Whisper)&quot; path in the Ham stack as shown in upstream. Text-to-speech is not active
            on the main Ham API process (<span className="font-mono text-white/65">/api/tts</span> is not mounted in
            <span className="font-mono text-white/65"> server.py</span>).
          </p>
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-white/[0.1] bg-white/[0.02] px-4 py-3 shadow-sm">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-emerald-500/85">
                Text-to-Speech
              </p>
              {ttsRow}
            </div>
            <div className="rounded-xl border border-white/[0.1] bg-white/[0.02] px-4 py-3 shadow-sm">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-emerald-500/85">
                Speech-to-Text
              </p>
              {sttRows}
            </div>
          </div>
          {catalog ? (
            <p className="mt-4 text-[11px] text-white/35">
              Text chat gateway: {isDashboardChatGatewayReady(catalog) ? "ready" : "not ready"} (GET /api/models) —
              unrelated to TTS.
            </p>
          ) : null}
        </WorkspaceSettingsReadOnlyCard>
      );
    }

    case "appearance":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Appearance"
            subtitle="Upstream uses WorkspaceThemePicker and workspace accent controls. HAM workspace chrome follows the main app theme; a dedicated workspace-only theme editor is not wired."
            badge={<WorkspaceSettingsCapabilityBadge>Partial (local signal)</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            <WorkspaceSettingsFieldRow
              label="OS color scheme preference"
              value={osScheme}
              hint="Read from the browser only — not a persisted HAM workspace setting."
            />
            <WorkspaceSettingsFieldRow
              label="Workspace theme override"
              value="Unavailable"
              hint="Requires Hermes-style theme persistence or HAM UI preference storage — not implemented in this PR."
            />
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    case "chat":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Chat"
            subtitle="Upstream ChatDisplaySection controls tool messages, reasoning blocks, composer width, and enter-key behavior. Those preferences are not split into this workspace settings screen in HAM yet."
            badge={<WorkspaceSettingsCapabilityBadge tone="amber">Hermes bridge required</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            <WorkspaceSettingsFieldRow
              label="Chat display preferences"
              value="Unavailable"
              hint="Use the main chat experience; granular display toggles are not exposed here."
            />
            {catalog ? (
              <WorkspaceSettingsFieldRow
                label="Composer catalog source"
                value={catalog.source || "—"}
                hint="From GET /api/models."
              />
            ) : null}
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    case "notifications":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Notifications"
            subtitle="Upstream toggles alerts, usage thresholds, and smart suggestions. HAM uses different server-side notification channels; there is no Hermes-parity notification matrix in this UI yet."
            badge={<WorkspaceSettingsCapabilityBadge tone="amber">Not wired</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            <WorkspaceSettingsFieldRow
              label="Workspace notification settings"
              value="Unavailable"
              hint="No browser-writable notification policy endpoint is connected for this screen."
            />
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    case "language":
      return (
        <WorkspaceSettingsReadOnlyCard>
          <WorkspaceSettingsSectionHeader
            title="Language"
            subtitle="Upstream exposes locale labels and setLocale. HAM dashboard language is not switched from this workspace settings page."
            badge={<WorkspaceSettingsCapabilityBadge tone="amber">Not wired</WorkspaceSettingsCapabilityBadge>}
          />
          <div className="mt-6">
            <WorkspaceSettingsFieldRow
              label="Locale"
              value="Unavailable"
              hint="Requires a HAM locale preference API or Hermes runtime bridge — not implemented for this screen."
            />
            <WorkspaceSettingsFieldRow
              label="Browser language"
              value={typeof navigator !== "undefined" ? navigator.language || "—" : "—"}
              hint="Informational only — not used as the app locale."
            />
          </div>
        </WorkspaceSettingsReadOnlyCard>
      );

    default: {
      const _exhaustive: never = section;
      return _exhaustive;
    }
  }
}
