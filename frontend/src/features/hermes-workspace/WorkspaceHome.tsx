import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Orbit } from "lucide-react";

export function WorkspaceHome() {
  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center overflow-y-auto p-6 sm:p-10">
      <div className="w-full max-w-md space-y-5 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-[#0a1218]/80 shadow-[0_12px_40px_rgba(0,0,0,0.35)]">
          <Orbit className="h-7 w-7 text-[#ffb27a]/90" strokeWidth={1.25} />
        </div>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-white/95">Workspace (lift)</h1>
          <p className="text-sm leading-relaxed text-white/45">
            This namespaced area will host the adapted Hermes Workspace experience. HAM providers,
            API, and auth stay the same; only the UI is lifted here.
          </p>
        </div>
        <Link
          to="/workspace/chat"
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#c45c12]/40 bg-gradient-to-b from-[#1a120a]/60 to-[#0f0c09]/50 px-5 py-3 text-sm font-medium text-white/90 transition-colors hover:border-[#c45c12]/55 hover:from-[#1a120a]/80"
        >
          Go to workspace chat
          <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
        </Link>
        <p className="text-[11px] text-white/32">
          Set <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-white/50">
            VITE_ENABLE_HERMES_WORKSPACE=true
          </code>{" "}
          in <code className="font-mono">frontend/.env.local</code> to use this area.
        </p>
      </div>
    </div>
  );
}
