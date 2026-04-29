import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import { Construction } from "lucide-react";

type WorkspacePlaceholderPageProps = {
  /** Page heading */
  title: string;
  /** Optional short note; defaults to deferred wiring copy */
  description?: string;
};

/**
 * Styling-only / IA placeholder for Hermes Workspace routes. No PTY, FS, or non-HAM client transports.
 */
export function WorkspacePlaceholderPage({ title, description }: WorkspacePlaceholderPageProps) {
  const { pathname } = useLocation();
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-4 sm:p-5 md:p-6">
      <div className="mx-auto w-full max-w-2xl">
        <div className="mb-5 flex items-start gap-3 rounded-2xl border border-[color:var(--ham-workspace-line)] bg-[#040d12]/50 p-4 sm:p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/30">
            <Construction className="h-5 w-5 text-[#ffb27a]/85" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-white/92">{title}</h1>
            <p className="mt-1.5 text-[13px] leading-relaxed text-white/50">
              {description ??
                "This surface is not wired to HAM runtime yet. No filesystem, terminal, or third-party direct calls in the browser — adapters come in later slices."}
            </p>
            <p className="mt-2 font-mono text-[10px] text-white/30">{pathname}</p>
          </div>
        </div>
        <p className="text-center text-[12px] text-white/40">
          <Link to="/workspace" className="text-[#ffb27a]/90 hover:text-[#ffc896]">
            ← Back to workspace dashboard
          </Link>
        </p>
      </div>
    </div>
  );
}
