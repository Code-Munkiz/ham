/**
 * Hermes Workspace Voice settings — persisted via GET/PATCH `/api/workspace/voice-settings`.
 * Layout follows upstream Voice / Text-to-Speech cards (see repomix SSOT); behavior is HAM-native.
 */
import * as React from "react";
import { Loader2, Volume2 } from "lucide-react";
import { hamApiFetch } from "@/lib/ham/api";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  WorkspaceSettingsCapabilityBadge,
  WorkspaceSettingsFieldRow,
  WorkspaceSettingsReadOnlyCard,
  WorkspaceSettingsSectionHeader,
  WorkspaceSettingsUnavailableNote,
} from "./workspaceSettingsReadOnlyChrome";
import { useVoiceWorkspaceSettingsOptional } from "../../voice/VoiceWorkspaceSettingsContext";

type Props = {
  catalog: ModelCatalogPayload | null;
};

export function WorkspaceVoiceBridgeSection({ catalog }: Props) {
  const vs = useVoiceWorkspaceSettingsOptional();
  const [testingTts, setTestingTts] = React.useState(false);
  const [testErr, setTestErr] = React.useState<string | null>(null);

  if (!vs) {
    return (
      <WorkspaceSettingsReadOnlyCard>
        <WorkspaceSettingsUnavailableNote>
          Voice settings require the workspace shell (VoiceWorkspaceSettingsProvider).
        </WorkspaceSettingsUnavailableNote>
      </WorkspaceSettingsReadOnlyCard>
    );
  }

  const { payload, loading, error, saving, saveError, updateVoiceSettings } = vs;

  if (loading && !payload) {
    return (
      <WorkspaceSettingsReadOnlyCard>
        <div className="flex items-center gap-2 text-[13px] text-white/55">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading voice settings…
        </div>
      </WorkspaceSettingsReadOnlyCard>
    );
  }

  if (error || !payload) {
    return (
      <WorkspaceSettingsReadOnlyCard>
        <WorkspaceSettingsUnavailableNote>
          Could not load voice settings: {error ?? "unknown error"}
        </WorkspaceSettingsUnavailableNote>
      </WorkspaceSettingsReadOnlyCard>
    );
  }

  const { settings, capabilities } = payload;
  const ttsCap = capabilities.tts;
  const sttCap = capabilities.stt;
  const canPlayTts =
    settings.tts.enabled &&
    ttsCap.available &&
    (ttsCap.providers.find((p) => p.id === "edge")?.available ?? false);

  const runTestVoice = async () => {
    setTestErr(null);
    setTestingTts(true);
    try {
      const res = await hamApiFetch("/api/tts/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: "HAM workspace voice test.",
          voice: settings.tts.voice,
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      await audio.play();
      audio.onended = () => URL.revokeObjectURL(url);
    } catch (e) {
      setTestErr(e instanceof Error ? e.message : "Playback failed");
    } finally {
      setTestingTts(false);
    }
  };

  return (
    <WorkspaceSettingsReadOnlyCard>
      <div className="mb-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35">Settings</p>
      </div>
      <WorkspaceSettingsSectionHeader
        title="Voice"
        subtitle="Text-to-speech and speech-to-text — saved on the Ham API."
        badge={<WorkspaceSettingsCapabilityBadge tone="ok">HAM API</WorkspaceSettingsCapabilityBadge>}
      />
      <p className="mt-4 text-[12px] leading-relaxed text-white/50">
        Preferences persist via{" "}
        <span className="font-mono text-white/65">GET/PATCH /api/workspace/voice-settings</span>. Chat dictation uses{" "}
        <span className="font-mono text-white/65">POST /api/chat/transcribe</span> when the API host sets{" "}
        <span className="font-mono text-white/65">HAM_TRANSCRIPTION_*</span> — there is no local Whisper path in Ham.
        Text-to-speech uses <span className="font-mono text-white/65">POST /api/tts/generate</span> (Edge engine on the
        server). <span className="font-mono text-white/65">HAM_TTS_ENABLED=0</span> disables synthesis globally regardless
        of these toggles.
      </p>

      {saveError ? (
        <p className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[12px] text-red-200/90">
          {saveError}
        </p>
      ) : null}

      <div className="mt-6 space-y-4">
        <div className="rounded-xl border border-white/[0.1] bg-white/[0.02] px-4 py-3 shadow-sm">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-emerald-500/85">
            Text-to-Speech
          </p>
          <div className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Enable TTS</span>
              <Switch
                checked={settings.tts.enabled}
                disabled={saving}
                onCheckedChange={(v) => void updateVoiceSettings({ tts: { enabled: v } })}
                aria-label="Enable text-to-speech"
              />
            </div>
            <WorkspaceSettingsFieldRow
              label="Route availability"
              value={ttsCap.available ? "Available" : "Not available"}
              hint={
                ttsCap.available
                  ? "HAM exposes synthesis unless HAM_TTS_ENABLED=0 on the server. Health does not guarantee Microsoft accepts every request."
                  : "TTS disabled on the API host (HAM_TTS_ENABLED=0 or equivalent)."
              }
            />
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Provider</span>
              <select
                className="h-8 w-full max-w-xs rounded-lg border border-white/[0.12] bg-white/[0.06] px-2.5 text-[12px] text-white/85 outline-none sm:max-w-sm"
                aria-label="TTS provider"
                value={settings.tts.provider}
                disabled={saving || !settings.tts.enabled}
                onChange={(e) =>
                  void updateVoiceSettings({ tts: { provider: e.target.value as "edge" } })
                }
              >
                {ttsCap.providers.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.available}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Voice</span>
              <select
                className="h-8 w-full max-w-xs rounded-lg border border-white/[0.12] bg-white/[0.06] px-2.5 text-[12px] text-white/85 outline-none sm:max-w-sm"
                aria-label="Edge neural voice"
                value={settings.tts.voice}
                disabled={saving || !settings.tts.enabled}
                onChange={(e) => void updateVoiceSettings({ tts: { voice: e.target.value } })}
              >
                {ttsCap.voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label} ({v.id})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={!canPlayTts || saving || testingTts}
                className="gap-1.5 border border-white/10 bg-white/[0.06] text-[12px] text-white/85 hover:bg-white/10"
                onClick={() => void runTestVoice()}
              >
                {testingTts ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Volume2 className="h-3.5 w-3.5" />
                )}
                Test voice
              </Button>
              <span className="text-[11px] text-white/45">
                {saving ? (
                  <>
                    <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
                    Saving…
                  </>
                ) : (
                  "Each toggle applies immediately via PATCH."
                )}
              </span>
            </div>
            {testErr ? <p className="text-[11px] text-red-300/90">{testErr}</p> : null}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.1] bg-white/[0.02] px-4 py-3 shadow-sm">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-emerald-500/85">
            Speech-to-Text
          </p>
          <div className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Enable STT in composer</span>
              <Switch
                checked={settings.stt.enabled}
                disabled={saving}
                onCheckedChange={(v) => void updateVoiceSettings({ stt: { enabled: v } })}
                aria-label="Enable speech-to-text for chat dictation"
              />
            </div>
            <WorkspaceSettingsFieldRow
              label="Runtime available"
              value={sttCap.available ? "Yes" : "No"}
              hint={
                sttCap.available
                  ? "HAM_TRANSCRIPTION_PROVIDER=openai and API key set on the server."
                  : sttCap.reason === "not_configured"
                    ? "Transcription not configured on the API host — dictation is disabled until configured."
                    : "Transcription not configured on the API host — dictation will fail until configured."
              }
            />
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Provider</span>
              <select
                className="h-8 w-full max-w-xs rounded-lg border border-white/[0.12] bg-white/[0.06] px-2.5 text-[12px] text-white/85 outline-none sm:max-w-sm"
                aria-label="STT provider"
                value={settings.stt.provider}
                disabled={saving || !settings.stt.enabled}
                onChange={(e) =>
                  void updateVoiceSettings({ stt: { provider: e.target.value as "openai" } })
                }
              >
                {sttCap.providers.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.available}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <span className="shrink-0 text-[13px] text-white/65">Dictation mode</span>
              <select
                className="h-8 w-full max-w-xs rounded-lg border border-white/[0.12] bg-white/[0.06] px-2.5 text-[12px] text-white/85 outline-none sm:max-w-sm"
                aria-label="Dictation mode"
                value={settings.stt.mode}
                disabled={saving || !settings.stt.enabled}
                onChange={(e) =>
                  void updateVoiceSettings({
                    stt: { mode: e.target.value as "auto" | "live" | "record" },
                  })
                }
              >
                <option value="record">Record then transcribe</option>
                <option value="live">Dictate live</option>
                <option value="auto">Auto dictation</option>
              </select>
            </div>
            <p className="text-[11px] text-white/45">
              Record mode is the default and most reliable path. Live and Auto remain optional.
            </p>
          </div>
        </div>
      </div>

      {catalog ? (
        <p className="mt-4 text-[11px] text-white/35">
          Text chat gateway: {isDashboardChatGatewayReady(catalog) ? "ready" : "not ready"} (GET /api/models) —
          unrelated to Voice persistence.
        </p>
      ) : null}
    </WorkspaceSettingsReadOnlyCard>
  );
}
