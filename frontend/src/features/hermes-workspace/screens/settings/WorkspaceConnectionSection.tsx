import * as React from "react";
import { Link } from "react-router-dom";
import { EnvironmentReadonlyPanel } from "@/components/workspace/UnifiedSettings";

/**
 * Repomix `ConnectionSection` in `src/routes/settings/index.tsx`: gateway + dashboard URLs.
 * HAM uses the Vite proxy to the Ham API only; we do not expose upstream-style gateway fields in the browser.
 * Process env **names** live here next to connection (upstream tips reference agent-side `.env`).
 */
export function WorkspaceConnectionSection() {
  return (
    <div className="space-y-8">
      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-none md:p-6">
        <h2 className="text-base font-semibold leading-tight text-[#e8eef8]">Connection</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">
          The workspace UI calls your Ham API. In local dev, the Vite proxy points at the API (see{" "}
          <span className="font-mono text-[12px] text-white/50">VITE_HAM_API_PROXY_TARGET</span>). There is no separate
          gateway or dashboard URL field in this build — that behavior matches upstream Hermes, not a second config layer
          in the browser.
        </p>
        <p className="mt-3 text-[13px] leading-relaxed text-white/40">
          Keys and providers:{" "}
          <Link
            className="text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
            to="/workspace/settings?section=hermes"
          >
            Model &amp; provider
          </Link>
          . Provider-focused layout:{" "}
          <Link
            className="text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
            to="/workspace/settings/providers"
          >
            Provider setup
          </Link>
          .
        </p>
      </section>

      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6">
        <h3 className="text-sm font-semibold text-white/90">Environment</h3>
        <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-white/40">
          Variable names the API process can read (read-only; same idea as a repo{" "}
          <span className="font-mono text-white/45">.env</span> in upstream docs). Values are not shown here.
        </p>
        <div className="mt-4">
          <EnvironmentReadonlyPanel variant="workspace" />
        </div>
      </section>
    </div>
  );
}
