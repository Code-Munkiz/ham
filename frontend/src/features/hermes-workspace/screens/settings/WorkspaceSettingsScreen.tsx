import * as React from "react";
import { useSearchParams } from "react-router-dom";
import {
  UnifiedSettings,
  normalizeSettingsTabParam,
  type SettingsSubSectionId,
} from "@/components/workspace/UnifiedSettings";

/**
 * Namespaced settings: same surface as `/settings` but under `/workspace/settings`
 * so mobile + shell stay in Workspace chrome.
 */
export function WorkspaceSettingsScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeSubSegment = normalizeSettingsTabParam(tabParam);

  React.useEffect(() => {
    const canonical = normalizeSettingsTabParam(tabParam);
    if (tabParam !== canonical) {
      setSearchParams({ tab: canonical }, { replace: true });
    }
  }, [tabParam, setSearchParams]);

  const onSubSegmentChange = (id: SettingsSubSectionId) => {
    setSearchParams({ tab: id }, { replace: true });
  };

  return (
    <div className="hww-settings h-full min-h-0 overflow-hidden bg-[#050505]">
      <UnifiedSettings
        activeSubSegment={activeSubSegment}
        onSubSegmentChange={onSubSegmentChange}
        variant="page"
      />
    </div>
  );
}
