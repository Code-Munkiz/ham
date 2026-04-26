import * as React from "react";
import { LocalMachineConnectCta } from "../../components/LocalMachineConnectCta";
import { isLocalRuntimeConfigured } from "../../adapters/localRuntime";
import { WorkspaceTerminalView } from "./WorkspaceTerminalView";

export function WorkspaceTerminalScreen() {
  const [hasLocal, setHasLocal] = React.useState(() => isLocalRuntimeConfigured());

  React.useEffect(() => {
    const sync = () => setHasLocal(isLocalRuntimeConfigured());
    window.addEventListener("hww-local-runtime-changed", sync);
    return () => window.removeEventListener("hww-local-runtime-changed", sync);
  }, []);

  if (!hasLocal) {
    return (
      <div className="hww-term flex h-full min-h-0 flex-col text-[#e2eaf3]">
        <header className="shrink-0 border-b border-[color:var(--ham-workspace-line)] px-3 py-2 md:px-4">
          <h1 className="text-sm font-medium text-white/90 md:text-base">Terminal</h1>
          <p className="text-[11px] text-white/40 md:text-[12px]">Connect to run a shell on this computer through the HAM local API.</p>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-3 md:p-4">
          <p className="mb-2 text-[13px] text-white/70">Connect this machine to open a local terminal.</p>
          <LocalMachineConnectCta
            variant="card"
            onSuccess={() => setHasLocal(true)}
            showOpenFiles
            showOpenSettings
          />
        </div>
      </div>
    );
  }

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
