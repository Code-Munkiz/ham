import * as React from "react";
import { WorkspaceTerminalView } from "./WorkspaceTerminalView";

export function WorkspaceTerminalScreen() {
  return (
    <div className="hww-term flex h-full min-h-0 flex-col text-[#e2eaf3]">
      <header className="shrink-0 border-b border-[color:var(--ham-workspace-line)] px-3 py-2 md:px-4">
        <h1 className="text-sm font-medium text-white/90 md:text-base">Terminal</h1>
        <p className="text-[11px] text-white/40 md:text-[12px]">Session output appears when a server bridge is available.</p>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">
        <WorkspaceTerminalView mode="page" />
      </div>
    </div>
  );
}
