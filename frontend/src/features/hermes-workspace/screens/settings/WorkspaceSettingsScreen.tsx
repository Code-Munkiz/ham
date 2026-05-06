import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DesktopBundlePanel } from "@/components/settings/DesktopBundlePanel";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import {
  getDefaultWorkspaceSettingsSection,
  parseWorkspaceSettingsSection,
  type UpstreamSettingsNavId,
} from "./workspaceSettingsNavData";
import {
  WorkspaceSettingsCapabilityBadge,
  WorkspaceSettingsReadOnlyCard,
  WorkspaceSettingsSectionHeader,
} from "./workspaceSettingsReadOnlyChrome";
import { WorkspaceSettingsBridgePanel } from "./WorkspaceSettingsBridgePanel";
import { WorkspaceSettingsSideNav } from "./WorkspaceSettingsSideNav";
import { WorkspaceConnectionSection } from "./WorkspaceConnectionSection";
import { WorkspaceConnectedToolsSection } from "./WorkspaceConnectedToolsSection";
import { WorkspaceModelProviderSection } from "./WorkspaceModelProviderSection";

/**
 * `src/routes/settings/index.tsx`: `?section=<SettingsNavId>`, default `hermes` (not connection).
 * MCP is not section-only upstream — use `/workspace/settings/mcp`.
 */
export function WorkspaceSettingsScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const section = parseWorkspaceSettingsSection(
    searchParams.get("section"),
    searchParams.get("tab"),
  );

  React.useEffect(() => {
    const rawS = searchParams.get("section");
    const rawT = searchParams.get("tab");
    const next = parseWorkspaceSettingsSection(rawS, rawT);
    if (rawT != null || !rawS || rawS !== next) {
      setSearchParams({ section: next }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const main = (() => {
    const s: UpstreamSettingsNavId = section;
    switch (s) {
      case "connection":
        return <WorkspaceConnectionSection />;
      case "tools":
        return <WorkspaceConnectedToolsSection />;
      case "hermes":
        return <WorkspaceModelProviderSection />;
      case "display": {
        return (
          <div className="space-y-6">
            <p className="text-[13px] leading-relaxed text-white/45">
              Upstream <span className="text-white/70">Display</span> maps to Hermes UI density and
              related toggles. In HAM, the local desktop / Hermes bundle surface is closest to that
              intent.
            </p>
            <DesktopBundlePanel />
          </div>
        );
      }
      case "agent":
      case "routing":
      case "voice":
      case "appearance":
      case "chat":
      case "notifications":
      case "language":
        return <WorkspaceSettingsBridgePanel section={s} />;
      case "mcp":
        return (
          <WorkspaceSettingsReadOnlyCard>
            <WorkspaceSettingsSectionHeader
              title="MCP servers"
              subtitle="Upstream uses a dedicated MCP route. HAM mirrors that with a full MCP tools page; this section entry is a shortcut — server installation and writes stay on that screen."
              badge={
                <WorkspaceSettingsCapabilityBadge>
                  Managed in MCP page
                </WorkspaceSettingsCapabilityBadge>
              }
            />
            <p className="mt-4 text-[13px] leading-relaxed text-white/45">
              Open{" "}
              <Link
                className="text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
                to="/workspace/settings/mcp"
              >
                MCP servers
              </Link>{" "}
              for tools, extensions, and allowlisted configuration (read-only vs low-risk flows per
              HAM policy).
            </p>
          </WorkspaceSettingsReadOnlyCard>
        );
      default:
        return <WorkspaceModelProviderSection />;
    }
  })();

  return (
    <div className="hww-settings h-full min-h-0 overflow-hidden" style={HWS_PARITY_THEME}>
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col border-b border-white/[0.06] bg-[#050505] md:flex-row md:border-b-0">
        <WorkspaceSettingsSideNav
          activeSection={section}
          className="shrink-0 border-b border-white/[0.06] bg-[#060b10] px-3 py-2 md:max-w-[min(16rem,38vw)] md:border-b-0 md:border-r md:py-4"
        />
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6">{main}</div>
      </div>
    </div>
  );
}
