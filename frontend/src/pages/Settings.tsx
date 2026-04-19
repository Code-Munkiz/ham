import * as React from "react";
import { useSearchParams } from "react-router-dom";
import {
  UnifiedSettings,
  normalizeSettingsTabParam,
  type SettingsSubSectionId,
} from "../components/workspace/UnifiedSettings";

export default function Settings() {
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
    <div className="h-full bg-[#050505] overflow-hidden">
      <UnifiedSettings
        activeSubSegment={activeSubSegment}
        onSubSegmentChange={onSubSegmentChange}
        variant="page"
        showSubNav={false}
      />
    </div>
  );
}
