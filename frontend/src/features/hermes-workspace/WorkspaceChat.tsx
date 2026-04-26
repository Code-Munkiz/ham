import * as React from "react";
import { workspaceChatAdapter } from "./workspaceAdapters";

/**
 * Placeholder: stream wiring via `postChatStream` + workspaceChatAdapter in a follow-up commit.
 */
export function WorkspaceChat() {
  return (
    <div className="flex h-full min-h-0 flex-col p-4 sm:p-6">
      <div className="mb-3 shrink-0">
        <h2 className="text-sm font-semibold text-white/90">Workspace chat</h2>
        <p className="mt-0.5 text-[12px] text-white/42">
          Adapter status: {workspaceChatAdapter.description}
        </p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/50 p-6 text-center">
        <p className="max-w-sm text-[13px] leading-relaxed text-white/55">
          Outbound send will use HAM <span className="font-mono text-white/60">postChatStream</span> only
          — not the upstream Node stream entrypoint (forbidden in this client).
        </p>
      </div>
    </div>
  );
}
