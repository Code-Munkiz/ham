import * as React from "react";
import { UnifiedSettings, SettingsSubSectionId } from "../components/workspace/UnifiedSettings";

export default function Settings() {
  const [activeSubSegment, setActiveSubSegment] = React.useState<SettingsSubSectionId>("api-keys");

  return (
    <div className="h-full bg-[#050505] overflow-hidden">
      <UnifiedSettings 
        activeSubSegment={activeSubSegment}
        onSubSegmentChange={setActiveSubSegment}
        variant="page"
      />
    </div>
  );
}
