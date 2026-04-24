import * as React from "react";
import { Link } from "react-router-dom";
import { Orbit } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HermesRuntimeInventory } from "@/lib/ham/api";
import { basenameOnly, redactPathLikeLine } from "./displayRedact";
import { cliTruth, configTruth } from "./runtimeLabels";

export interface ShopRuntimeSectionProps {
  inventory: HermesRuntimeInventory | null;
  loading: boolean;
  error: string | null;
  /** Which slice of inventory to render */
  slice: "tools" | "mcp" | "plugins";
}

export function ShopRuntimeSection({ inventory, loading, error, slice }: ShopRuntimeSectionProps) {
  if (loading) {
    return (
      <p className="text-xs font-bold uppercase tracking-widest text-white/40 py-6">Loading runtime inventory…</p>
    );
  }
  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
        {error}
      </div>
    );
  }
  if (!inventory) {
    return <p className="text-[11px] text-white/35 py-6">No inventory payload.</p>;
  }

  const inv = inventory;

  if (slice === "tools") {
    return (
      <div className="space-y-4 text-[11px] text-white/65 max-w-3xl">
        <div className="flex flex-wrap gap-2 items-center">
          <span
            className={cn(
              "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border",
              inv.available
                ? "border-emerald-500/40 text-emerald-200/90"
                : "border-white/20 text-white/50",
            )}
          >
            {cliTruth(inv, inv.tools.status)}
          </span>
          {inv.source.hermes_binary ? (
            <span className="text-[10px] font-mono text-white/45" title="CLI basename only">
              CLI: {basenameOnly(inv.source.hermes_binary)}
            </span>
          ) : (
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
              Hermes CLI not reported
            </span>
          )}
        </div>
        <p className="text-white/45">
          Co-located API:{" "}
          <span className="text-white/70">{inv.source.colocated ? "yes" : "no"}</span>
        </p>
        {inv.tools.warning ? <p className="text-amber-100/85">{inv.tools.warning}</p> : null}
        {(inv.tools.config_toolsets?.length ?? 0) > 0 ? (
          <p className="text-[10px] text-white/45">
            <span className="font-black uppercase tracking-wider text-white/35">Config-backed toolsets:</span>{" "}
            {inv.tools
              .config_toolsets!.slice(0, 16)
              .map((t) => redactPathLikeLine(t))
              .join(", ")}
            {inv.tools.config_toolsets!.length > 16
              ? ` +${inv.tools.config_toolsets!.length - 16} more`
              : ""}
          </p>
        ) : null}
        {inv.tools.toolsets.length > 0 ? (
          <ul className="list-disc pl-5 font-mono text-[10px] text-white/55 space-y-0.5">
            {inv.tools.toolsets.slice(0, 24).map((t) => (
              <li key={t}>{redactPathLikeLine(t)}</li>
            ))}
          </ul>
        ) : (
          <p className="text-white/45 italic">{inv.tools.summary_text || "(no toolsets parsed)"}</p>
        )}
        <div className="space-y-1 pt-3 border-t border-white/5">
          <div className="text-[10px] font-black uppercase tracking-widest text-white/40">
            Memory / context —{" "}
            <span className="text-white/55">{configTruth(String(inv.config.status ?? "missing"))}</span>
          </div>
          <p>
            Memory provider:{" "}
            <span className="font-mono text-white/55">{(inv.config.memory_provider as string) || "—"}</span>
          </p>
          <p>
            Context engine:{" "}
            <span className="font-mono text-white/55">{(inv.config.context_engine as string) || "—"}</span>
          </p>
        </div>
        <RuntimeFooter />
      </div>
    );
  }

  if (slice === "mcp") {
    return (
      <div className="space-y-4 text-[11px] text-white/65 max-w-3xl">
        <div className="text-[10px] font-black uppercase tracking-widest text-white/40">
          MCP — <span className="text-white/55">{cliTruth(inv, inv.mcp.status)}</span>
        </div>
        {inv.mcp.servers.length > 0 ? (
          <ul className="list-disc pl-5 space-y-0.5">
            {inv.mcp.servers.slice(0, 32).map((s, i) => (
              <li key={i} className="font-mono text-[10px]">
                {redactPathLikeLine(
                  s.text ?? `${s.name ?? "?"} (${s.transport ?? "unknown"})`,
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-white/45 italic">(empty)</p>
        )}
        {Array.isArray(inv.config.mcp_servers) && inv.config.mcp_servers.length > 0 ? (
          <p className="text-[10px] text-white/45">
            Config-backed MCP entries: {inv.config.mcp_servers.length} (names / transport only).
          </p>
        ) : null}
        <RuntimeFooter />
      </div>
    );
  }

  // plugins
  return (
    <div className="space-y-4 text-[11px] text-white/65 max-w-3xl">
      <div className="text-[10px] font-black uppercase tracking-widest text-white/40">
        Plugins — <span className="text-white/55">{cliTruth(inv, inv.plugins.status)}</span>
      </div>
      {inv.plugins.items.length > 0 ? (
        <ul className="list-disc pl-5 space-y-0.5">
          {inv.plugins.items.slice(0, 32).map((p, idx) => (
            <li key={`${idx}-${p.text.slice(0, 32)}`} className="font-mono text-[10px]">
              {redactPathLikeLine(p.text)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-white/45 italic">(empty)</p>
      )}
      <RuntimeFooter />
    </div>
  );
}

function RuntimeFooter() {
  return (
    <p className="text-[10px] text-white/35 pt-4 border-t border-white/5">
      Raw CLI dumps stay on{" "}
      <Link to="/hermes" className="text-[#FF6B00]/90 font-black uppercase tracking-wider hover:underline inline-flex items-center gap-1">
        <Orbit className="h-3 w-3" />
        View diagnostics
      </Link>
      .
    </p>
  );
}
