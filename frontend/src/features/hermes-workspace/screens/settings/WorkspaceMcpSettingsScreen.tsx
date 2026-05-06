import * as React from "react";
import { ToolsAndExtensionsPanel } from "@/components/workspace/UnifiedSettings";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import { getDefaultWorkspaceSettingsSection } from "./workspaceSettingsNavData";
import { WorkspaceSettingsSideNav } from "./WorkspaceSettingsSideNav";

/** repomix `src/routes/settings/mcp.tsx` → `McpSettingsScreen`; HAM maps to tools/extensions surface. */
export function WorkspaceMcpSettingsScreen() {
  return (
    <div className="hww-settings h-full min-h-0 overflow-hidden" style={HWS_PARITY_THEME}>
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col border-b border-white/[0.06] bg-[#050505] md:flex-row md:border-b-0">
        <WorkspaceSettingsSideNav
          activeSection={getDefaultWorkspaceSettingsSection()}
          className="shrink-0 border-b border-white/[0.06] bg-[#060b10] px-3 py-2 md:max-w-[min(16rem,38vw)] md:border-b-0 md:border-r md:py-4"
        />
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
          <h1 className="text-lg font-semibold text-[#e8eef8]">MCP Servers</h1>
          <p className="mt-1 max-w-2xl text-[13px] text-white/45">
            Upstream file route <span className="font-mono text-white/50">/settings/mcp</span> (
            <span className="font-mono">McpSettingsScreen</span> in repomix). HAM reuses the tools
            &amp; extensions surface; no new transport.
          </p>
          <div className="mt-6 max-w-4xl">
            <ToolsAndExtensionsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
