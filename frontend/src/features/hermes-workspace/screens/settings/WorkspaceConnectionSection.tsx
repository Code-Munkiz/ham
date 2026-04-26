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
      <section className="rounded-2xl border border-white/[0.08] bg-black/30 p-5 shadow-sm md:p-6">
        <h2 className="text-base font-semibold leading-tight text-[#e8eef8]">Connection</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">
          This HAM web UI talks to your local Ham API through the dev proxy (
          <span className="font-mono text-white/55">VITE_HAM_API_PROXY_TARGET</span> in dev). There is no separate
          in-browser “gateway URL” or Hermes dashboard URL field here — those exist in upstream Hermes Workspace only.
        </p>
        <p className="mt-3 text-[12px] leading-relaxed text-white/35">
          For API keys and provider credentials, use{" "}
          <Link className="text-[#ffb27a] underline-offset-2 hover:underline" to="/workspace/settings?section=hermes">
            Model &amp; provider
          </Link>
          . For a provider grid experience similar to upstream, open{" "}
          <Link className="text-[#ffb27a] underline-offset-2 hover:underline" to="/workspace/settings/providers">
            Provider setup
          </Link>
          .
        </p>
      </section>

      <section className="rounded-2xl border border-white/[0.08] bg-black/25 p-5 md:p-6">
        <h3 className="text-sm font-semibold text-white/80">Environment (process, names only)</h3>
        <p className="mt-1 text-[12px] text-white/40">
          Upstream Connection copy references agent-side <span className="font-mono">.env</span>; in HAM the same
          variables are listed read-only here.
        </p>
        <div className="mt-4">
          <EnvironmentReadonlyPanel />
        </div>
      </section>
    </div>
  );
}
