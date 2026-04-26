import * as React from "react";
import { ApiKeysPanel, ContextAndMemoryPanel } from "@/components/workspace/UnifiedSettings";

/**
 * Repomix `HermesConfigSection` under `section=hermes`: “Model & Provider” + context.
 * HAM: Cursor / OpenRouter credentials + context engine snapshot.
 */
export function WorkspaceModelProviderSection() {
  return (
    <div className="space-y-10">
      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6">
        <h2 className="text-base font-semibold text-[#e8eef8]">Model &amp; provider</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">
          Store Cursor and other provider credentials on the API; routing and models follow your Ham server settings.
        </p>
        <div className="mt-6">
          <ApiKeysPanel variant="workspace" />
        </div>
      </section>
      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6">
        <h3 className="text-sm font-semibold text-white/90">Context &amp; memory</h3>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">Live snapshot from the context engine for this workspace root.</p>
        <div className="mt-4">
          <ContextAndMemoryPanel variant="workspace" />
        </div>
      </section>
    </div>
  );
}
