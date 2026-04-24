import * as React from "react";
import { ClipboardCopy } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  CapabilityDirectoryCapabilitiesResponse,
  CapabilityDirectoryIndexResponse,
  CapabilityDirectoryRecord,
} from "@/lib/ham/api";

export interface ShopTemplatesSectionProps {
  index: CapabilityDirectoryIndexResponse | null;
  indexErr: string | null;
  capabilities: CapabilityDirectoryCapabilitiesResponse | null;
  capabilitiesErr: string | null;
}

function TrustBadge({ tier }: { tier: string }) {
  const muted =
    tier === "first_party"
      ? "border-emerald-500/40 text-emerald-400/80 bg-emerald-500/5"
      : tier === "verified_org"
        ? "border-blue-500/40 text-blue-400/80 bg-blue-500/5"
        : "border-white/15 text-white/50 bg-white/[0.03]";
  return (
    <span
      className={cn(
        "text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border",
        muted,
      )}
    >
      {tier.replace(/_/g, " ")}
    </span>
  );
}

export function ShopTemplatesSection({
  index,
  indexErr,
  capabilities,
  capabilitiesErr,
}: ShopTemplatesSectionProps) {
  const templates = React.useMemo(() => {
    const rows = capabilities?.capabilities ?? [];
    return rows.filter((r) => r.kind === "profile_template");
  }, [capabilities]);

  const registryCount = index?.counts.profile_templates;

  const copyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {(indexErr || capabilitiesErr) && (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/35 bg-amber-500/5 px-4 py-3 text-[11px] text-amber-100/90"
        >
          {indexErr ? <p>Index: {indexErr}</p> : null}
          {capabilitiesErr ? <p>Capabilities: {capabilitiesErr}</p> : null}
        </div>
      )}

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 space-y-2">
        <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-[#FF6B00]/90">
          Profile templates
        </h2>
        <p className="text-[11px] text-white/45 leading-relaxed">
          Registry count:{" "}
          <span className="text-white/80 font-semibold tabular-nums">
            {registryCount ?? "—"}
          </span>
          . Rows below come from{" "}
          <span className="font-mono text-white/55">GET /api/capability-directory/capabilities</span>{" "}
          when the backend includes <span className="font-mono text-white/55">profile_template</span>{" "}
          kinds.
        </p>
        {index?.apply_available_globally === false ? (
          <p className="text-[10px] font-black uppercase tracking-widest text-cyan-200/80 border border-cyan-500/25 bg-cyan-500/5 rounded-lg p-2">
            Apply unavailable (directory flag)
          </p>
        ) : null}
      </div>

      {templates.length === 0 ? (
        <p className="text-[11px] text-white/35">
          {capabilities
            ? "No profile_template rows returned on the capabilities list — see registry count above."
            : "Capabilities list not loaded."}
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {templates.map((t: CapabilityDirectoryRecord) => (
            <article
              key={t.id}
              className="flex flex-col p-6 bg-[#0a0a0a] border border-white/5 rounded-xl space-y-3"
            >
              <div className="space-y-1">
                <h3 className="text-sm font-black uppercase tracking-wide text-[#FF6B00]">{t.display_name}</h3>
                <p className="text-[10px] font-bold text-white/35 leading-relaxed line-clamp-4">{t.summary}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <TrustBadge tier={t.trust_tier} />
                <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/15 text-white/40">
                  Read-only
                </span>
                <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/10 text-white/35">
                  Static catalog
                </span>
              </div>
              <div className="flex flex-wrap gap-2 mt-auto pt-2 border-t border-white/5">
                <button
                  type="button"
                  onClick={() => void copyId(t.id)}
                  className="text-[9px] font-black uppercase tracking-widest px-3 py-2 rounded-lg border border-white/15 text-white/50 hover:text-white hover:bg-white/5 flex items-center gap-1.5"
                >
                  <ClipboardCopy className="h-3 w-3" />
                  Copy ID
                </button>
              </div>
              <p className="text-[9px] font-mono text-white/15 truncate">{t.id}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
