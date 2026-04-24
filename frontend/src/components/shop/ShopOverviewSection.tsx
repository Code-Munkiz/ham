import * as React from "react";
import { Link } from "react-router-dom";
import { LayoutDashboard, Orbit, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  CapabilityDirectoryIndexResponse,
  HermesRuntimeInventory,
  HermesSkillsCapabilities,
  HermesSkillsCatalogResponse,
  HermesSkillsInstalledResponse,
} from "@/lib/ham/api";
import { inventoryAvailabilityLabel, staticCatalogLabel } from "./runtimeLabels";

export interface ShopOverviewSectionProps {
  catalog: HermesSkillsCatalogResponse | null;
  catalogErr: string | null;
  live: HermesSkillsInstalledResponse | null;
  liveErr: string | null;
  inventory: HermesRuntimeInventory | null;
  inventoryErr: string | null;
  capIndex: CapabilityDirectoryIndexResponse | null;
  capIndexErr: string | null;
  skillsCaps: HermesSkillsCapabilities | null;
  skillsCapsErr: string | null;
}

function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: "default" | "muted";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-white/10 bg-black/30 p-4 text-center",
        tone === "muted" && "opacity-80",
      )}
    >
      <div className="text-[22px] font-black text-white/90 tabular-nums">{value}</div>
      <div className="text-[8px] font-black uppercase tracking-widest text-white/35 mt-1">{label}</div>
      {sub ? <div className="text-[9px] text-white/30 mt-1 leading-snug">{sub}</div> : null}
    </div>
  );
}

function SourceChip({ children, variant }: { children: React.ReactNode; variant: "cyan" | "amber" | "neutral" }) {
  const cls =
    variant === "cyan"
      ? "border-cyan-500/35 text-cyan-200/85 bg-cyan-500/5"
      : variant === "amber"
        ? "border-amber-500/35 text-amber-200/85 bg-amber-500/5"
        : "border-white/15 text-white/45 bg-white/[0.03]";
  return (
    <span className={cn("text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border", cls)}>
      {children}
    </span>
  );
}

export function ShopOverviewSection({
  catalog,
  catalogErr,
  live,
  liveErr,
  inventory,
  inventoryErr,
  capIndex,
  capIndexErr,
  skillsCaps,
  skillsCapsErr,
}: ShopOverviewSectionProps) {
  const staticSkillCount = catalog?.count ?? "—";
  const liveSkillCount = live?.live_count ?? "—";
  const linked = live?.linked_count ?? "—";
  const liveOnly = live?.live_only_count ?? "—";
  const catalogOnly = live?.catalog_only_count ?? "—";

  const toolsStatus = inventory ? inventory.tools.status : "—";
  const mcpCount = inventory?.mcp.servers.length ?? 0;
  const pluginCount = inventory?.plugins.items.length ?? 0;
  const bundleCount = capIndex?.counts.bundles ?? "—";
  const templateCount = capIndex?.counts.profile_templates ?? "—";

  const applyDir = capIndex
    ? capIndex.apply_available_globally
      ? "Registry mutation flag on"
      : "Apply unavailable"
    : "—";
  const skillsMutate =
    skillsCaps?.skills_apply_writes_enabled === true ? "Config-backed" : "Read-only";

  return (
    <section className="space-y-6">
      <div className="rounded-xl border border-cyan-500/25 bg-cyan-500/5 p-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-cyan-200/90">
          <LayoutDashboard className="h-4 w-4 shrink-0" />
          Read-only discovery
        </div>
        <p className="text-[11px] text-cyan-100/80 leading-relaxed max-w-3xl">
          HAM Shop lists what the API can observe. Nothing here mutates Hermes, MCP, or project settings.
          There is no execution, install, or apply from this surface.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <SourceChip variant="neutral">Read-only</SourceChip>
          {capIndex && !capIndex.apply_available_globally ? (
            <SourceChip variant="amber">Apply unavailable</SourceChip>
          ) : null}
          {skillsCaps && skillsCaps.skills_apply_writes_enabled !== true ? (
            <SourceChip variant="neutral">Hermes skill writes off</SourceChip>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <Link
          to="/hermes"
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest px-4 py-2 rounded-lg border border-[#FF6B00]/40 bg-[#FF6B00]/10 text-[#FF6B00] hover:bg-[#FF6B00]/20"
        >
          <Orbit className="h-4 w-4" />
          View diagnostics
        </Link>
        <Link
          to="/skills"
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest px-4 py-2 rounded-lg border border-white/15 text-white/50 hover:text-white hover:bg-white/5"
        >
          <Sparkles className="h-4 w-4" />
          Manage Hermes skills (legacy operator surface)
        </Link>
      </div>

      {(catalogErr || liveErr || inventoryErr || capIndexErr || skillsCapsErr) && (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/35 bg-amber-500/5 px-4 py-3 text-[11px] text-amber-100/90 space-y-1"
        >
          <p className="font-black uppercase tracking-wider text-[10px]">Partial data</p>
          <ul className="list-disc pl-5 space-y-0.5 text-amber-100/80">
            {catalogErr ? <li>Catalog: {catalogErr}</li> : null}
            {liveErr ? <li>Live skills: {liveErr}</li> : null}
            {inventoryErr ? <li>Runtime inventory: {inventoryErr}</li> : null}
            {capIndexErr ? <li>Capability directory: {capIndexErr}</li> : null}
            {skillsCapsErr ? <li>Hermes skills capabilities: {skillsCapsErr}</li> : null}
          </ul>
        </div>
      )}

      <div>
        <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40 mb-3">Counts</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <StatCard label="Static skill catalog" value={staticSkillCount} sub="GET /api/hermes-skills/catalog" />
          <StatCard label="Live skill rows" value={liveSkillCount} sub="CLI overlay" />
          <StatCard label="Linked" value={linked} sub="Catalog ↔ live" />
          <StatCard label="Live-only" value={liveOnly} sub="CLI only" />
          <StatCard label="Catalog-only" value={catalogOnly} sub="Not linked" />
          <StatCard
            label="Tools (inventory)"
            value={inventory ? inventory.tools.toolsets.length : "—"}
            sub={`Status: ${toolsStatus}`}
          />
          <StatCard label="MCP servers (parsed)" value={inventory ? mcpCount : "—"} />
          <StatCard label="Plugins (parsed)" value={inventory ? pluginCount : "—"} />
          <StatCard label="Bundles" value={bundleCount} />
          <StatCard label="Profile templates (registry)" value={templateCount} />
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 space-y-3">
        <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40">Source hints</h2>
        <div className="flex flex-wrap gap-2 text-[10px] text-white/55">
          <span className="font-black uppercase tracking-wider text-white/35">Runtime inventory:</span>
          <SourceChip variant="neutral">{inventoryAvailabilityLabel(inventory)}</SourceChip>
          {inventory ? (
            <SourceChip variant="neutral">{staticCatalogLabel(inventory.skills.static_catalog)}</SourceChip>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] text-white/55">
          <span className="font-black uppercase tracking-wider text-white/35">Capability directory:</span>
          <SourceChip variant="neutral">{capIndex ? "Static catalog" : "Unavailable"}</SourceChip>
          <SourceChip variant={capIndex?.apply_available_globally ? "cyan" : "amber"}>{applyDir}</SourceChip>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] text-white/55">
          <span className="font-black uppercase tracking-wider text-white/35">Hermes skill API writes:</span>
          <SourceChip variant="neutral">{skillsCaps ? skillsMutate : "Unavailable"}</SourceChip>
        </div>
      </div>
    </section>
  );
}
