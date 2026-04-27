import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Layers, MessageSquare, PanelLeft } from "lucide-react";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";

export function WorkspaceHome() {
  const logoSrc = hamWorkspaceLogoUrl();
  return (
    <div className="hww-home flex h-full min-h-0 flex-col overflow-y-auto p-4 sm:p-6 md:p-8">
      <div className="mx-auto w-full max-w-3xl">
        <div className="mb-8 flex flex-col items-center text-center sm:mb-10">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-[#0a1218]/85 shadow-[0_16px_48px_rgba(0,0,0,0.4)]">
            <img
              src={logoSrc}
              alt=""
              className="h-12 w-12 object-contain"
              width={48}
              height={48}
            />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white/95 sm:text-3xl">
            Dashboard
          </h1>
          <p className="mt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/32">
            HAM's Workspace
          </p>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/45">
            Operator-facing workspace: chat, files, skills, and settings share the same HAM API and local runtime;
            some sections are still staging placeholders.
          </p>
        </div>

        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/60 p-4 text-left">
            <PanelLeft className="mb-2 h-4 w-4 text-white/40" strokeWidth={1.5} />
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/50">
              Sessions
            </p>
            <p className="mt-1 text-[12px] text-white/38">
              Search and list will bind to the HAM session adapter.
            </p>
          </div>
          <Link
            to="/workspace/chat"
            className="group rounded-xl border border-[#c45c12]/35 bg-gradient-to-b from-[#1a120a]/50 to-[#0f0c09]/40 p-4 text-left transition-colors hover:border-[#c45c12]/5 hover:from-[#1a120a]/70"
          >
            <MessageSquare className="mb-2 h-4 w-4 text-[#ffb27a]/80" strokeWidth={1.5} />
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/60 group-hover:text-white/80">
              Chat
            </p>
            <p className="mt-1 text-[12px] text-white/40 group-hover:text-white/55">
              Open the workspace chat surface (stream wiring next).
            </p>
          </Link>
          <div className="rounded-xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/60 p-4 text-left">
            <Layers className="mb-2 h-4 w-4 text-white/40" strokeWidth={1.5} />
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-white/50">Surface map</p>
            <p className="mt-1 text-[12px] text-white/38">
              Main + Knowledge nav items in the rail are present; most routes are UI placeholders until
              their adapters are shipped.
            </p>
          </div>
        </div>

        <div className="flex justify-center">
          <Link
            to="/workspace/chat"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/12 bg-white/[0.04] px-5 py-2.5 text-sm font-medium text-white/88 transition-colors hover:border-white/18 hover:bg-white/[0.07]"
          >
            Continue to workspace chat
            <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
          </Link>
        </div>
      </div>
    </div>
  );
}
