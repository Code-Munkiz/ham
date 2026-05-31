import * as React from "react";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import { WorkspaceBuilderPreferences } from "../builder-studio/WorkspaceBuilderPreferences";

const BUILDERS_HEADING = "Builders";
const BUILDERS_SUBTITLE =
  "Choose the builder HAM uses when you ask it to build. Work starts in chat.";

export default function WorkspaceBuildersSection() {
  const ctx = useHamWorkspace();
  const workspaceId =
    ctx.state.status === "ready" ? (ctx.state.activeWorkspaceId?.trim() ?? "") : "";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-white/90">{BUILDERS_HEADING}</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">{BUILDERS_SUBTITLE}</p>
      </div>
      <WorkspaceBuilderPreferences workspaceId={workspaceId} />
    </div>
  );
}
