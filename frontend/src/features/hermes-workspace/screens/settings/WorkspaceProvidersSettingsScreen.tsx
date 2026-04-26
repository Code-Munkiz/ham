import * as React from "react";
import { Link } from "react-router-dom";
import { ApiKeysPanel } from "@/components/workspace/UnifiedSettings";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import { getDefaultWorkspaceSettingsSection } from "./workspaceSettingsNavData";
import { WorkspaceSettingsSideNav } from "./WorkspaceSettingsSideNav";

/** repomix `src/routes/settings/providers.tsx` → `ProvidersScreen`. HAM: provider credentials = API keys path. */
export function WorkspaceProvidersSettingsScreen() {
  return (
    <div className="hww-settings h-full min-h-0 overflow-hidden" style={HWS_PARITY_THEME}>
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col border-b border-white/[0.06] bg-[#050505] md:flex-row md:border-b-0">
        <WorkspaceSettingsSideNav
          activeSection={getDefaultWorkspaceSettingsSection()}
          className="shrink-0 border-b border-white/[0.06] bg-[#060b10] px-3 py-2 md:max-w-[min(16rem,38vw)] md:border-b-0 md:border-r md:py-4"
        />
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
          <h1 className="text-lg font-semibold text-[#e8eef8]">Provider setup</h1>
          <p className="mt-1 max-w-2xl text-[13px] text-white/45">
            Upstream <span className="font-mono">/settings/providers</span> (
            <span className="font-mono">ProvidersScreen</span>). HAM uses the API keys / Cursor panel as the credential
            surface; discoverable provider lists are API-driven.
          </p>
          <p className="mt-2 text-[12px] text-white/35">
            Also see{" "}
            <Link className="text-[#ffb27a] underline-offset-2 hover:underline" to="/workspace/settings?section=hermes">
              Model &amp; provider
            </Link>
            .
          </p>
          <div className="mt-6 max-w-4xl rounded-2xl border border-white/[0.08] bg-black/25 p-5 md:p-6">
            <ApiKeysPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
