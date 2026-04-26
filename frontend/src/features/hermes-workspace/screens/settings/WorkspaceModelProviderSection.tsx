import * as React from "react";
import { ApiKeysPanel, ContextAndMemoryPanel } from "@/components/workspace/UnifiedSettings";

/**
 * Repomix `HermesConfigSection` under `section=hermes`: “Model & Provider” + context.
 * HAM: Cursor / OpenRouter credentials + context engine snapshot.
 */
export function WorkspaceModelProviderSection() {
  return (
    <div className="space-y-10">
      <section className="rounded-2xl border border-white/[0.08] bg-black/25 p-5 md:p-6">
        <h2 className="text-base font-semibold text-[#e8eef8]">Model &amp; provider</h2>
        <p className="mt-1 text-[12px] text-white/40">
          Provider credentials and routing (matches upstream “Model & Provider” / Hermes config scope).
        </p>
        <div className="mt-6">
          <ApiKeysPanel />
        </div>
      </section>
      <section className="rounded-2xl border border-white/[0.08] bg-black/25 p-5 md:p-6">
        <h3 className="text-sm font-semibold text-white/85">Context &amp; memory</h3>
        <p className="mt-1 text-[12px] text-white/40">Live snapshot from the Ham context engine for this workspace.</p>
        <div className="mt-4">
          <ContextAndMemoryPanel />
        </div>
      </section>
    </div>
  );
}
