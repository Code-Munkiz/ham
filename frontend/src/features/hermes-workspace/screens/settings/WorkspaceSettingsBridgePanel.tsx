import * as React from "react";
import { fetchModelsCatalog } from "@/lib/ham/api";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import type { WorkspaceSettingsBridgeSectionId } from "./workspaceSettingsNavData";
import {
  WorkspaceSettingsCapabilityBadge,
  WorkspaceSettingsFieldRow,
  WorkspaceSettingsReadOnlyCard,
  WorkspaceSettingsSectionHeader,
  WorkspaceSettingsUnavailableNote,
} from "./workspaceSettingsReadOnlyChrome";
import { WorkspaceVoiceBridgeSection } from "./WorkspaceVoiceBridgeSection";

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

    case "voice":
      return <WorkspaceVoiceBridgeSection catalog={catalog} />;

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
