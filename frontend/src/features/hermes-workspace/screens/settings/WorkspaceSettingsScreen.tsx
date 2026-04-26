import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { UnifiedSettings, type SettingsSubSectionId } from "@/components/workspace/UnifiedSettings";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import { resolveWorkspaceSettingsView, settingsSectionToWorkspaceUrlSlug } from "./workspaceSettingsNavData";
import { WorkspaceSettingsBridgePanel } from "./WorkspaceSettingsBridgePanel";
import { WorkspaceSettingsSideNav } from "./WorkspaceSettingsSideNav";

/**
 * Hermes-shaped settings: upstream-style section nav + mobile pills, still backed by HAM
 * `UnifiedSettings` (no new transport). Bridge rows explain gaps where upstream UI exists
 * but HAM has no full equivalent yet.
 */
export function WorkspaceSettingsScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const view = resolveWorkspaceSettingsView(tabParam);

  React.useEffect(() => {
    const raw = (tabParam ?? "").trim();
    if (raw !== view.slug) {
      setSearchParams({ tab: view.slug }, { replace: true });
    }
  }, [tabParam, view.slug, setSearchParams]);

  const onSubSegmentChange = (id: SettingsSubSectionId) => {
    setSearchParams({ tab: settingsSectionToWorkspaceUrlSlug(id) }, { replace: true });
  };

  return (
    <div className="hww-settings h-full min-h-0 overflow-hidden" style={HWS_PARITY_THEME}>
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col border-b border-white/[0.06] bg-[#050505] md:flex-row md:border-b-0">
        <WorkspaceSettingsSideNav activeSlug={view.slug} className="shrink-0 border-b border-white/[0.06] bg-[#060b10] px-3 py-2 md:max-w-[min(16rem,36vw)] md:border-b-0 md:border-r md:py-4" />
        <div className="min-h-0 min-w-0 flex-1">
          {view.kind === "unified" ? (
            <UnifiedSettings
              activeSubSegment={view.section}
              onSubSegmentChange={onSubSegmentChange}
              variant="page"
              hideInternalNav
            />
          ) : (
            <WorkspaceSettingsBridgePanel bridgeKey={view.key} />
          )}
        </div>
      </div>
    </div>
  );
}
