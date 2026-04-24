/**
 * HAM Shop — read-only discovery for skills, runtime inventory, capability directory.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import { Orbit, ShoppingBag } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchCapabilityDirectoryCapabilities,
  fetchCapabilityDirectoryIndex,
  fetchHermesRuntimeInventory,
  fetchHermesSkillsCapabilities,
  fetchHermesSkillsCatalog,
  fetchHermesSkillsInstalled,
  type CapabilityDirectoryCapabilitiesResponse,
  type CapabilityDirectoryIndexResponse,
  type HermesRuntimeInventory,
  type HermesSkillsCapabilities,
  type HermesSkillsCatalogResponse,
  type HermesSkillsInstalledResponse,
} from "@/lib/ham/api";
import { CapabilityDirectoryPanel } from "@/components/skills/CapabilityDirectoryPanel";
import { ShopOverviewSection } from "@/components/shop/ShopOverviewSection";
import { ShopSkillsSection } from "@/components/shop/ShopSkillsSection";
import { ShopRuntimeSection } from "@/components/shop/ShopRuntimeSections";
import { ShopTemplatesSection } from "@/components/shop/ShopTemplatesSection";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "skills", label: "Skills" },
  { id: "tools", label: "Tools" },
  { id: "mcp", label: "MCP" },
  { id: "plugins", label: "Plugins" },
  { id: "bundles", label: "Bundles" },
  { id: "templates", label: "Templates" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function HamShop() {
  const [tab, setTab] = React.useState<TabId>("overview");

  const [catalog, setCatalog] = React.useState<HermesSkillsCatalogResponse | null>(null);
  const [catalogErr, setCatalogErr] = React.useState<string | null>(null);
  const [live, setLive] = React.useState<HermesSkillsInstalledResponse | null>(null);
  const [liveErr, setLiveErr] = React.useState<string | null>(null);
  const [inventory, setInventory] = React.useState<HermesRuntimeInventory | null>(null);
  const [inventoryErr, setInventoryErr] = React.useState<string | null>(null);
  const [invLoading, setInvLoading] = React.useState(true);
  const [capIndex, setCapIndex] = React.useState<CapabilityDirectoryIndexResponse | null>(null);
  const [capIndexErr, setCapIndexErr] = React.useState<string | null>(null);
  const [capCaps, setCapCaps] = React.useState<CapabilityDirectoryCapabilitiesResponse | null>(null);
  const [capCapsErr, setCapCapsErr] = React.useState<string | null>(null);
  const [skillsCaps, setSkillsCaps] = React.useState<HermesSkillsCapabilities | null>(null);
  const [skillsCapsErr, setSkillsCapsErr] = React.useState<string | null>(null);
  const [bootLoading, setBootLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setBootLoading(true);
      setCatalogErr(null);
      setLiveErr(null);
      setInventoryErr(null);
      setCapIndexErr(null);
      setCapCapsErr(null);
      setSkillsCapsErr(null);
      setInvLoading(true);

      const results = await Promise.allSettled([
        fetchHermesSkillsCatalog(),
        fetchHermesSkillsInstalled(),
        fetchHermesRuntimeInventory(),
        fetchCapabilityDirectoryIndex(),
        fetchCapabilityDirectoryCapabilities(),
        fetchHermesSkillsCapabilities(),
      ]);
      if (cancelled) return;

      const errMsg = (reason: unknown) =>
        reason instanceof Error ? reason.message : String(reason);

      if (results[0].status === "fulfilled") setCatalog(results[0].value);
      else {
        setCatalog(null);
        setCatalogErr(errMsg(results[0].reason));
      }

      if (results[1].status === "fulfilled") setLive(results[1].value);
      else {
        setLive(null);
        setLiveErr(errMsg(results[1].reason));
      }

      if (results[2].status === "fulfilled") setInventory(results[2].value);
      else {
        setInventory(null);
        setInventoryErr(errMsg(results[2].reason));
      }
      setInvLoading(false);

      if (results[3].status === "fulfilled") setCapIndex(results[3].value);
      else {
        setCapIndex(null);
        setCapIndexErr(errMsg(results[3].reason));
      }

      if (results[4].status === "fulfilled") setCapCaps(results[4].value);
      else {
        setCapCaps(null);
        setCapCapsErr(errMsg(results[4].reason));
      }

      if (results[5].status === "fulfilled") setSkillsCaps(results[5].value);
      else {
        setSkillsCaps(null);
        setSkillsCapsErr(errMsg(results[5].reason));
      }

      setBootLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-hidden text-white/90">
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="shrink-0 border-b border-white/5 px-8 pt-8 pb-4 max-w-6xl mx-auto w-full space-y-4">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
              <ShoppingBag className="h-5 w-5 text-[#FF6B00]" />
            </div>
            <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">
              Workspace / Shop
            </span>
          </div>
          <h1 className="text-4xl font-black text-[#FF6B00] italic tracking-tighter uppercase leading-none">
            Shop
          </h1>
          <p className="text-sm font-bold text-white/30 max-w-3xl uppercase tracking-widest leading-relaxed">
            Read-only discovery across Hermes runtime skills, CLI inventory, and the static capability
            directory.{" "}
            <Link to="/hermes" className="text-[#FF6B00]/80 hover:underline">
              View diagnostics
            </Link>{" "}
            for deeper redacted CLI output.
          </p>
          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-[11px] text-cyan-100/85 leading-relaxed max-w-3xl">
            <span className="font-black uppercase tracking-wider text-[10px]">No execution</span> — this
            surface does not install, apply, or run anything. It only reflects API-visible catalog and
            inventory data.
          </div>
        </div>

        <div className="shrink-0 px-8 max-w-6xl mx-auto w-full flex flex-wrap gap-2 border-b border-white/5 pb-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "text-[9px] font-black uppercase tracking-[0.2em] px-4 py-2.5 rounded-lg border transition-colors",
                tab === t.id
                  ? "border-[#FF6B00]/50 bg-[#FF6B00]/15 text-[#FF6B00]"
                  : "border-white/10 text-white/40 hover:text-white/60 hover:border-white/20",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto scrollbar-hide px-8 py-6 max-w-6xl mx-auto w-full">
          {bootLoading ? (
            <p className="text-xs font-bold uppercase tracking-widest text-white/40 mb-6">Loading shop data…</p>
          ) : null}

          {!bootLoading && tab === "overview" ? (
            <ShopOverviewSection
              catalog={catalog}
              catalogErr={catalogErr}
              live={live}
              liveErr={liveErr}
              inventory={inventory}
              inventoryErr={inventoryErr}
              capIndex={capIndex}
              capIndexErr={capIndexErr}
              skillsCaps={skillsCaps}
              skillsCapsErr={skillsCapsErr}
            />
          ) : null}

          {!bootLoading && tab === "skills" ? (
            <ShopSkillsSection catalog={catalog} catalogErr={catalogErr} live={live} liveErr={liveErr} />
          ) : null}

          {!bootLoading && tab === "tools" ? (
            <ShopRuntimeSection inventory={inventory} loading={invLoading} error={inventoryErr} slice="tools" />
          ) : null}
          {!bootLoading && tab === "mcp" ? (
            <ShopRuntimeSection inventory={inventory} loading={invLoading} error={inventoryErr} slice="mcp" />
          ) : null}
          {!bootLoading && tab === "plugins" ? (
            <ShopRuntimeSection
              inventory={inventory}
              loading={invLoading}
              error={inventoryErr}
              slice="plugins"
            />
          ) : null}

          {!bootLoading && tab === "bundles" ? (
            <div className="space-y-4">
              <p className="text-[11px] text-white/45 max-w-2xl">
                Bundle cards and detail are read-only.{" "}
                <Link to="/hermes" className="text-[#FF6B00]/90 font-semibold hover:underline inline-flex items-center gap-1">
                  <Orbit className="h-3.5 w-3.5" />
                  View diagnostics
                </Link>{" "}
                for full runtime inventory context.
              </p>
              <CapabilityDirectoryPanel />
            </div>
          ) : null}

          {!bootLoading && tab === "templates" ? (
            <ShopTemplatesSection
              index={capIndex}
              indexErr={capIndexErr}
              capabilities={capCaps}
              capabilitiesErr={capCapsErr}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
