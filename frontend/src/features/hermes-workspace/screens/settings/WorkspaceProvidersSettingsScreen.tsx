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
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-white/45">
            Add and rotate API keys the same way as upstream “providers”: credentials are stored and validated on the Ham
            API; the list of models and options comes from the server.
          </p>
          <p className="mt-2 text-[13px] text-white/40">
            Related:{" "}
            <Link
              className="text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
              to="/workspace/settings?section=hermes"
            >
              Model &amp; provider
            </Link>{" "}
            for the full key + context layout.
          </p>
          <div className="mt-6 max-w-4xl">
            <ApiKeysPanel variant="workspace" />
          </div>
        </div>
      </div>
    </div>
  );
}
