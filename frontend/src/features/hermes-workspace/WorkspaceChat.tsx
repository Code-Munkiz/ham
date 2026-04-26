import * as React from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Search } from "lucide-react";
import { workspaceChatAdapter } from "./workspaceAdapters";

/**
 * Placeholder: stream wiring via HAM `postChatStream` + `workspaceChatAdapter` in a follow-up commit.
 * Layout mirrors upstream “chat + session rail” without real data.
 */
export function WorkspaceChat() {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden md:flex-row">
      {/* Session rail (desktop) / compact block (mobile) */}
      <aside className="flex max-h-36 w-full shrink-0 flex-col border-b border-[color:var(--ham-workspace-line)] bg-[#040d12]/50 p-3 md:max-h-none md:w-56 md:border-b-0 md:border-r">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">
          This session
        </p>
        <div className="relative mb-2">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-white/30"
            strokeWidth={1.5}
          />
          <input
            type="search"
            readOnly
            placeholder="Message search…"
            className="hww-input w-full cursor-default rounded-md py-1.5 pl-7 text-[11px]"
            title="Tied to session transcript index in a later commit"
          />
        </div>
        <p className="text-[11px] leading-relaxed text-white/40">
          Session identity and history will use the same HAM session model as <span className="font-mono">/chat</span>.
        </p>
      </aside>

      {/* Main thread placeholder */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-[color:var(--ham-workspace-line)] bg-[#040d14]/50 px-4 py-3 md:px-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-white/50" strokeWidth={1.5} />
              <h2 className="text-sm font-semibold text-white/90">Workspace chat</h2>
            </div>
            <span className="hww-pill">Adapter: {workspaceChatAdapter.ready ? "on" : "off"}</span>
          </div>
          <p className="mt-1.5 text-[12px] text-white/42">{workspaceChatAdapter.description}</p>
        </header>

        <div className="flex min-h-0 flex-1 flex-col items-center justify-center p-4 sm:p-6">
          <div className="w-full max-w-md rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/50 p-5 text-center sm:p-6">
            <p className="text-[13px] leading-relaxed text-white/55">
              Composer and live stream will call HAM <span className="font-mono text-white/65">postChatStream</span> through{" "}
              <span className="font-mono text-white/55">workspaceChatAdapter</span> only — not upstream Node
              stream routes in the browser.
            </p>
            <p className="mt-3 text-[11px] text-white/35">
              On narrow viewports, use the menu control to open the full workspace nav.
            </p>
            <div className="mt-4 flex justify-center">
              <Link
                to="/workspace"
                className="text-[12px] font-medium text-[#ffb27a]/90 hover:text-[#ffc896]"
              >
                ← Back to workspace home
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
