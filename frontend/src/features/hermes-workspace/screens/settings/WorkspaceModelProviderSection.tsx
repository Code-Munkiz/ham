import * as React from "react";
import { ApiKeysPanel, ContextAndMemoryPanel } from "@/components/workspace/UnifiedSettings";
import { fetchModelsCatalog } from "@/lib/ham/api";
import type { ModelCatalogPayload } from "@/lib/ham/types";

function OpenRouterChatModelsReference() {
  const [payload, setPayload] = React.useState<ModelCatalogPayload | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    void (async () => {
      try {
        const p = await fetchModelsCatalog();
        if (!cancelled) setPayload(p);
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load catalog");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <p className="mt-6 text-[12px] text-amber-200/80">
        Could not load the model catalog: {loadError}
      </p>
    );
  }

  if (!payload?.openrouter_chat_ready) return null;

  const chat = payload.items.filter((x) => x.supports_chat);
  const orMeta = payload.openrouter_catalog;

  return (
    <div id="openrouter-models" className="mt-8 scroll-mt-28">
      <h3 className="text-sm font-semibold text-white/90">OpenRouter chat models</h3>
      <p className="mt-1 text-[13px] leading-relaxed text-white/45">
        Browse chat-capable models your API exposes (OpenRouter public list is fetched server-side
        with a short cache). API keys are never sent to the browser.
      </p>
      {orMeta?.remote_fetch_failed ? (
        <p className="mt-2 text-[12px] leading-snug text-amber-200/85">
          The API could not refresh the OpenRouter model list just now. Tier shortcuts (Auto,
          Premium, …) still work; try again after checking API connectivity.
        </p>
      ) : null}
      <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-white/[0.08] bg-black/20">
        <table className="w-full text-left text-[12px]">
          <thead className="sticky top-0 z-[1] bg-[#050a0c] text-[10px] uppercase tracking-wide text-white/45">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Id</th>
              <th className="px-3 py-2 font-medium">Ctx</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.06] text-white/82">
            {chat.map((row) => (
              <tr key={row.id}>
                <td className="px-3 py-1.5 align-top">{row.label}</td>
                <td className="px-3 py-1.5 align-top font-mono text-[11px] text-white/55">
                  {row.id}
                </td>
                <td className="px-3 py-1.5 align-top tabular-nums text-white/55">
                  {row.context_length != null ? row.context_length.toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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
          Store Cursor and other provider credentials on the API; routing and models follow your Ham
          server settings.
        </p>
        <div className="mt-6">
          <ApiKeysPanel variant="workspace" />
        </div>
        <OpenRouterChatModelsReference />
      </section>
      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6">
        <h3 className="text-sm font-semibold text-white/90">Context &amp; memory</h3>
        <p className="mt-1 text-[13px] leading-relaxed text-white/45">
          Live snapshot from the context engine for this workspace root.
        </p>
        <div className="mt-4">
          <ContextAndMemoryPanel variant="workspace" />
        </div>
      </section>
    </div>
  );
}
