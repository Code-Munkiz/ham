/**
 * Command Center — API-side, read-only Hermes + HAM broker snapshot (Path B). No live JSON-RPC / WS claims.
 */
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Cpu,
  Layers,
  MessageSquare,
  Orbit,
  RefreshCw,
  Server,
  Shield,
  Terminal,
  Wifi,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HermesOperatorConnectionStrip } from "@/components/hermes/HermesOperatorConnectionStrip";
import { fetchModelsCatalog, fetchHermesGatewaySnapshot, type HermesGatewaySnapshot } from "@/lib/ham/api";
import type { HermesGatewayExternalRunner } from "@/lib/ham/hermesGateway";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { primaryChatPath } from "@/features/hermes-workspace/workspaceFlags";

type TabId =
  | "overview"
  | "runtime"
  | "models"
  | "commands"
  | "skills"
  | "plugins"
  | "mcp"
  | "sessions"
  | "runners"
  | "diagnostics";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "runtime", label: "Hermes Runtime" },
  { id: "models", label: "Models & Providers" },
  { id: "commands", label: "Commands / Menu" },
  { id: "skills", label: "Skills" },
  { id: "plugins", label: "Plugins" },
  { id: "mcp", label: "MCP / Tools" },
  { id: "sessions", label: "Sessions / Activity" },
  { id: "runners", label: "External Runners" },
  { id: "diagnostics", label: "Diagnostics" },
];

const TAB_QUERY_VALUES = new Set<string>(TABS.map((t) => t.id));

function partitionModelCatalog(items: ModelCatalogItem[]) {
  return {
    openrouter: items.filter((i) => i.provider === "openrouter"),
    cursor: items.filter((i) => i.provider === "cursor"),
  };
}

function deriveItemBadges(item: ModelCatalogItem, catalog: ModelCatalogPayload): string[] {
  const out: string[] = [];
  if (item.provider === "cursor") {
    out.push("Display only");
    return out;
  }
  if (item.provider === "openrouter") {
    if (item.supports_chat) {
      out.push("Chat-capable");
      out.push("Available");
    } else {
      out.push("Inactive");
      out.push("Disabled");
      const dr = (item.disabled_reason || "").toLowerCase();
      if (dr.includes("key") || dr.includes("not set") || dr.includes("plausible")) out.push("Auth required");
      if (catalog.gateway_mode !== "openrouter") out.push("Gateway mode mismatch");
    }
  }
  return [...new Set(out)];
}

function modeExplanation(gw: string): { title: string; body: string } {
  if (gw === "openrouter") {
    return {
      title: "OpenRouter mode",
      body: "Model selection is available for HAM chat. Selected model_id is validated server-side against the catalog.",
    };
  }
  if (gw === "http") {
    return {
      title: "HTTP (Hermes gateway) mode",
      body: "HAM chat is routed to the configured Hermes HTTP gateway. The upstream model is controlled by server env/config, not the browser selector. Per-request model_id is not applied in this mode.",
    };
  }
  if (gw === "mock") {
    return {
      title: "Mock mode",
      body: "Mock mode does not use a real model.",
    };
  }
  return {
    title: "Gateway mode",
    body: "See HERMES_GATEWAY_MODE and docs/HERMES_GATEWAY_CONTRACT.md.",
  };
}

function ModelBadge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "good" | "warn" | "neutral" | "mute" }) {
  return (
    <span
      className={cn(
        "text-[7px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded border",
        tone === "good" && "border-emerald-500/40 text-emerald-400/90",
        tone === "warn" && "border-amber-500/40 text-amber-400/90",
        tone === "mute" && "border-white/12 text-white/40",
        tone === "neutral" && "border-white/15 text-white/55",
      )}
    >
      {children}
    </span>
  );
}

function CatalogRow({ item, catalog }: { item: ModelCatalogItem; catalog: ModelCatalogPayload }) {
  const badges = deriveItemBadges(item, catalog);
  return (
    <div className="rounded-lg border border-white/[0.06] bg-[#0a0a0a] p-3 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div>
          <p className="text-xs font-bold text-white">{item.label}</p>
          <p className="text-[9px] font-mono text-white/45 break-all">{item.id}</p>
        </div>
        <div className="flex flex-wrap gap-1 justify-end">
          {badges.map((b) => (
            <ModelBadge
              key={b}
              tone={b === "Chat-capable" || b === "Available" ? "good" : b === "Display only" || b === "Static fallback" ? "mute" : "warn"}
            >
              {b}
            </ModelBadge>
          ))}
        </div>
      </div>
      <div className="text-[9px] text-white/35 space-y-0.5">
        <p>
          <span className="text-white/25">supports_chat</span>{" "}
          <span className="font-mono text-white/60">{String(item.supports_chat)}</span>
        </p>
        <p>
          <span className="text-white/25">provider</span> {item.provider}
          {item.tag ? <span className="ml-2">· tag {item.tag}</span> : null}
        </p>
        {item.openrouter_model ? (
          <p>
            <span className="text-white/25">openrouter_model</span>{" "}
            <span className="font-mono text-white/50">{item.openrouter_model}</span>
          </p>
        ) : null}
        {item.disabled_reason ? (
          <p className="text-amber-200/70">
            <span className="text-white/25">disabled_reason</span> {item.disabled_reason}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function EffectiveModelStrip({
  catalog,
  httpModelsCountHint,
}: {
  catalog: ModelCatalogPayload;
  httpModelsCountHint: string | number | null | undefined;
}) {
  const gw = catalog.gateway_mode;
  const chatReady = isDashboardChatGatewayReady(catalog);
  const eff =
    gw === "openrouter"
      ? "Use Chat to pick a chat-capable tier; server maps catalog id → OpenRouter. Default follows HERMES_GATEWAY_MODEL / DEFAULT_MODEL when unset."
      : gw === "http"
        ? `Upstream model is config-controlled: ${catalog.http_chat_model_primary || "hermes-agent (typical default)"}${catalog.http_chat_model_fallback ? ` · fallback ${catalog.http_chat_model_fallback}` : ""} — not switchable from the browser.`
        : gw === "mock"
          ? "Mock assistant only — no real model."
          : "See gateway mode.";

  return (
    <div className="rounded-xl border border-[#FF6B00]/25 bg-[#FF6B00]/5 p-4 space-y-2">
      <p className="text-[9px] font-black uppercase tracking-[0.2em] text-[#FF6B00]/80">Effective model / gateway</p>
      <div className="text-[10px] text-white/50 space-y-1">
        <p>
          <span className="text-white/30">gateway_mode</span>{" "}
          <span className="font-mono text-white/80">{gw}</span>
        </p>
        <p>
          <span className="text-white/30">dashboard_chat_ready</span>{" "}
          {String(catalog.dashboard_chat_ready ?? "—")} · <span className="text-white/30">openrouter_chat_ready</span>{" "}
          {String(catalog.openrouter_chat_ready)} · <span className="text-white/30">http_chat_ready</span>{" "}
          {String(catalog.http_chat_ready ?? "—")}
        </p>
        <p>
          <span className="text-white/30">catalog source</span> {catalog.source}
        </p>
        <p className="text-white/65 leading-snug pt-1">{eff}</p>
        {gw === "http" && httpModelsCountHint != null && httpModelsCountHint !== "—" ? (
          <p className="text-white/40">
            Hermes <span className="font-mono">GET /v1/models</span> probe count:{" "}
            <span className="font-mono text-white/60">{String(httpModelsCountHint)}</span> (cosmetic list on v0.8.0 — not
            a HAM model selector)
          </p>
        ) : null}
        <p className="pt-1 flex flex-wrap items-center gap-2">
          <ModelBadge tone={chatReady ? "good" : "warn"}>
            {chatReady ? "Chat ready" : "Chat not ready"}
          </ModelBadge>
          {gw === "http" ? <ModelBadge tone="mute">Config-controlled</ModelBadge> : null}
        </p>
        <div className="pt-2">
          <Link
            to={primaryChatPath()}
            className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Open Chat
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "neutral" | "warn" | "bad";
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border p-4 bg-[#0a0a0a] border-white/[0.06]",
        tone === "warn" && "border-amber-500/30",
        tone === "bad" && "border-red-500/25",
      )}
    >
      <p className="text-[9px] font-black uppercase tracking-[0.2em] text-white/35">{label}</p>
      <p className="mt-2 text-2xl font-black text-white tabular-nums">{value}</p>
      {sub ? <p className="mt-1 text-[10px] text-white/40 leading-snug">{sub}</p> : null}
    </div>
  );
}

function degradedLabel(keys: string[]): string {
  if (!keys.length) return "Healthy";
  return `Degraded: ${keys.join(", ")}`;
}

function RunnerCard({ r }: { r: HermesGatewayExternalRunner }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#080808] p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold text-white">{r.label}</p>
          <p className="text-[10px] text-white/45 mt-1 leading-relaxed">{r.description}</p>
        </div>
        <span
          className={cn(
            "shrink-0 text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border",
            r.status === "ready"
              ? "border-emerald-500/40 text-emerald-400/90"
              : r.availability === "stub"
                ? "border-white/15 text-white/35"
                : "border-amber-500/35 text-amber-400/90",
          )}
        >
          {r.availability}
        </span>
      </div>
      <div className="flex flex-wrap gap-2 text-[9px] text-white/30 font-mono">
        <span>status={r.status}</span>
        {r.requires_tty ? <span className="text-amber-400/70">requires_tty</span> : null}
        {r.requires_auth ? <span>requires_auth</span> : null}
        <span>source={r.source}</span>
      </div>
      {r.warnings?.length ? (
        <ul className="text-[10px] text-amber-400/80 list-disc pl-4 space-y-0.5">
          {r.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function CommandCenter() {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("project_id")?.trim() || undefined;
  const tabFromUrl = searchParams.get("tab");

  const [tab, setTab] = React.useState<TabId>("overview");
  const [snap, setSnap] = React.useState<HermesGatewaySnapshot | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [catalog, setCatalog] = React.useState<ModelCatalogPayload | null>(null);
  const [catalogErr, setCatalogErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (tabFromUrl && TAB_QUERY_VALUES.has(tabFromUrl)) {
      setTab(tabFromUrl as TabId);
    }
  }, [tabFromUrl]);

  const load = React.useCallback(
    async (refresh: boolean) => {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      setErr(null);
      setCatalogErr(null);
      try {
        const [shot, cat] = await Promise.allSettled([
          fetchHermesGatewaySnapshot({ projectId, refresh }),
          fetchModelsCatalog(),
        ]);
        if (shot.status === "fulfilled") {
          setSnap(shot.value);
        } else {
          setErr(shot.reason instanceof Error ? shot.reason.message : "Failed to load snapshot");
          setSnap(null);
        }
        if (cat.status === "fulfilled") {
          setCatalog(cat.value);
        } else {
          setCatalogErr(
            cat.reason instanceof Error ? cat.reason.message : "Failed to load model catalog (GET /api/models)",
          );
          setCatalog(null);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId],
  );

  React.useEffect(() => {
    void load(false);
  }, [load]);

  React.useEffect(() => {
    const t = window.setInterval(() => void load(false), 30_000);
    return () => window.clearInterval(t);
  }, [load]);

  const hub = snap?.hermes_hub as Record<string, unknown> | undefined;
  const gwMode = hub ? String(hub.gateway_mode ?? "—") : "—";
  const dashChat = hub?.dashboard_chat as Record<string, string> | undefined;
  const httpGw = snap?.http_gateway as Record<string, unknown> | undefined;
  const inv = snap?.runtime_inventory as Record<string, unknown> | undefined;
  const skills = snap?.skills_installed as Record<string, unknown> | undefined;
  const cmds = snap?.commands_and_menus as Record<string, unknown> | undefined;
  const cliReport = snap?.hermes_version?.cli_report as Record<string, unknown> | undefined;

  return (
    <div className="h-full overflow-auto bg-[#050505] text-white">
      <div className="max-w-6xl mx-auto p-8 space-y-8 pb-20">
        <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 border-b border-white/[0.06] pb-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-[#FF6B00]">
              <Orbit className="h-5 w-5" />
              <span className="text-[10px] font-black uppercase tracking-[0.35em]">Command Center</span>
            </div>
            <h1 className="text-2xl font-black tracking-tight">Hermes + HAM</h1>
            <p className="text-xs text-white/45 max-w-xl leading-relaxed">
              <span className="text-white/55">API-side, read-only snapshot</span> (Path B): what the Ham API can see
              on its host—allowlisted CLI/config, optional upstream HTTP health, control-plane hints. This is not a
              desktop view; TTY / full Hermes menus are not exposed by the current HTTP surface—labels mark CLI-only
              or degraded.
            </p>
            {projectId ? (
              <p className="text-[10px] font-mono text-white/35">project_id={projectId}</p>
            ) : (
              <p className="text-[10px] text-white/30">
                Add <span className="font-mono">?project_id=…</span> for control-plane run summaries.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void load(true)}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-[10px] font-black uppercase tracking-widest hover:bg-white/[0.08] disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              Refresh
            </button>
            <Link
              to="/hermes"
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white/50 hover:text-[#FF6B00]"
            >
              Legacy hub
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </header>

        {loading && !snap ? (
          <p className="text-sm text-white/40">Loading snapshot…</p>
        ) : null}
        {err ? (
          <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200/90">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {err}
          </div>
        ) : null}

        {snap ? (
          <>
            {snap.operator_connection ? <HermesOperatorConnectionStrip snapshot={snap} /> : null}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard
                label="Gateway mode"
                value={gwMode}
                sub={dashChat?.short_label}
                tone={snap.degraded_capabilities?.includes("hermes_http_gateway") ? "warn" : "neutral"}
              />
              <StatCard
                label="Inventory freshness"
                value={snap.freshness.inventory_cached ? "Cached" : "Fresh"}
                sub={`TTL ${snap.ttl_seconds}s · build ${snap.freshness.build_latency_ms}ms`}
              />
              <StatCard
                label="Tools / plugins / MCP"
                value={`${snap.counts.tools_lines} / ${snap.counts.plugins} / ${snap.counts.mcp}`}
                sub="CLI/config-backed counts"
              />
              <StatCard
                label="Skills"
                value={`${snap.counts.skills_installed} live / ${snap.counts.skills_catalog} catalog`}
                sub="Live overlay may be remote_only"
              />
              <StatCard
                label="HAM runs (store)"
                value={snap.activity.ham_run_store_count ?? "—"}
                sub="CWD-scoped run store"
              />
              <StatCard
                label="Control-plane rows"
                value={snap.activity.control_plane_runs?.length ?? 0}
                sub={snap.activity.control_plane_error ?? "project-scoped when set"}
                tone={snap.activity.control_plane_error ? "warn" : "neutral"}
              />
              <StatCard
                label="HTTP gateway probe"
                value={String(httpGw?.status ?? "—")}
                sub={httpGw?.error ? String(httpGw.error) : "HERMES_GATEWAY_BASE_URL"}
                tone={httpGw?.status === "unreachable" ? "bad" : "neutral"}
              />
              <StatCard
                label="Capabilities"
                value={degradedLabel(snap.degraded_capabilities)}
                sub={`${snap.external_runners.filter((x) => x.availability !== "stub").length} non-stub runners`}
                tone={snap.degraded_capabilities.length ? "warn" : "neutral"}
              />
            </div>

            <nav className="flex flex-wrap gap-2">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-[10px] font-black uppercase tracking-widest border transition-colors",
                    tab === t.id
                      ? "border-[#FF6B00]/50 bg-[#FF6B00]/10 text-[#FF6B00]"
                      : "border-white/10 text-white/40 hover:text-white/70",
                  )}
                >
                  {t.label}
                </button>
              ))}
            </nav>

            <div className="rounded-2xl border border-white/[0.06] bg-[#080808] p-6 space-y-4 min-h-[240px]">
              {tab === "overview" && (
                <div className="space-y-4">
                  <p className="text-sm text-white/60 leading-relaxed">{dashChat?.summary}</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-xl border border-white/[0.08] bg-[#0a0a0a] px-4 py-3 text-[10px] font-black uppercase tracking-widest">
                    <Link to="/activity" className="text-[#FF6B00] hover:underline">
                      Open Activity stream
                    </Link>
                    <span className="text-white/15" aria-hidden>
                      ·
                    </span>
                    <Link to="/hermes" className="text-[#FF6B00] hover:underline">
                      Open Hermes details
                    </Link>
                    <span className="text-white/15" aria-hidden>
                      ·
                    </span>
                    <Link to="/shop" className="text-[#FF6B00] hover:underline">
                      Browse Capabilities
                    </Link>
                    <span className="text-white/15" aria-hidden>
                      ·
                    </span>
                    <Link to="/skills" className="text-[#FF6B00] hover:underline">
                      Skills catalog
                    </Link>
                  </div>
                  {catalog ? (
                    <div className="rounded-xl border border-white/[0.08] bg-[#0c0c0c] p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <div className="text-[10px] text-white/50">
                        <span className="text-white/30 uppercase tracking-widest font-black">Models</span>{" "}
                        <span className="font-mono text-white/75">{catalog.gateway_mode}</span>
                        {catalog.http_chat_model_primary ? (
                          <span className="ml-2 text-white/40">
                            · HTTP primary{" "}
                            <span className="font-mono text-white/60">{catalog.http_chat_model_primary}</span>
                          </span>
                        ) : null}
                        {catalog.source === "fallback" ? (
                          <span className="ml-2 inline-block align-middle">
                            <ModelBadge tone="warn">Static fallback</ModelBadge>
                          </span>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => setTab("models")}
                          className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
                        >
                          Models & Providers →
                        </button>
                        <Link
                          to={primaryChatPath()}
                          className="text-[9px] font-black uppercase tracking-widest text-white/40 hover:text-[#FF6B00]"
                        >
                          Open Chat
                        </Link>
                      </div>
                    </div>
                  ) : catalogErr ? (
                    <p className="text-[10px] text-amber-400/80">Model catalog: {catalogErr}</p>
                  ) : null}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="rounded-xl border border-white/[0.05] p-4 space-y-2">
                      <p className="text-[10px] font-black uppercase text-white/35 flex items-center gap-2">
                        <Shield className="h-3.5 w-3.5" /> Honest limits (v0.8.0)
                      </p>
                      <ul className="text-xs text-white/50 space-y-1 list-disc pl-4">
                        <li>No REST live menu or slash discovery — CLI / TTY.</li>
                        <li>JSON-RPC and WebSocket control are future placeholders only.</li>
                        <li>Snapshot omits raw CLI captures; use dedicated APIs if you need them.</li>
                      </ul>
                    </div>
                    <div className="rounded-xl border border-white/[0.05] p-4 space-y-2">
                      <p className="text-[10px] font-black uppercase text-white/35 flex items-center gap-2">
                        <Wifi className="h-3.5 w-3.5" /> SSE
                      </p>
                      <p className="text-xs text-white/50">
                        HAM exposes <span className="font-mono text-white/70">GET /api/hermes-gateway/stream</span>{" "}
                        for lightweight ticks. Full payload: snapshot poll or manual refresh.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {tab === "runtime" && (
                <div className="space-y-3 text-sm">
                  <p className="text-white/55">
                    Hermes CLI:{" "}
                    <span className="font-mono text-white/80">{String(cliReport?.status ?? "—")}</span> —{" "}
                    <span className="text-white/45">{String(cliReport?.version_line ?? "")}</span>
                  </p>
                  <p className="text-xs text-white/40">
                    Inventory available:{" "}
                    <strong className="text-white/70">{String(inv?.available ?? "—")}</strong> · mode{" "}
                    {String(inv?.mode ?? "—")}
                  </p>
                  <Link className="text-[#FF6B00] text-xs font-bold inline-flex items-center gap-1" to="/hermes">
                    Open Hermes details <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              )}

              {tab === "models" && (
                <div className="space-y-6 text-sm">
                  {catalogErr ? (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-amber-200/90 text-xs">
                      Could not load <span className="font-mono">GET /api/models</span>: {catalogErr}
                    </div>
                  ) : null}
                  {catalog ? (
                    <>
                      <EffectiveModelStrip
                        catalog={catalog}
                        httpModelsCountHint={httpGw?.models_count_hint as string | number | undefined}
                      />
                      {(() => {
                        const me = modeExplanation(catalog.gateway_mode);
                        return (
                          <div className="rounded-xl border border-white/[0.08] p-4 space-y-2 bg-[#0a0a0a]">
                            <p className="text-[9px] font-black uppercase tracking-widest text-white/35">
                              {me.title}
                            </p>
                            <p className="text-xs text-white/55 leading-relaxed">{me.body}</p>
                          </div>
                        );
                      })()}
                      <div className="rounded-xl border border-white/10 p-4 space-y-2 bg-[#0a0a0a]">
                        <p className="text-[9px] font-black uppercase text-amber-400/70">Hermes runtime (operator machine)</p>
                        <p className="text-xs text-white/45 leading-relaxed">
                          Current Hermes v0.8.0 does not expose a verified API for switching the local Hermes runtime
                          model from HAM. HAM does not change operator-side <span className="font-mono">config.yaml</span>{" "}
                          or CLI profiles from this UI.
                        </p>
                      </div>
                      <div className="space-y-2 text-[10px] text-white/40">
                        <p>
                          <span className="text-white/30">api/models snapshot</span>{" "}
                          <span className="font-mono">gateway_mode={catalog.gateway_mode}</span>
                          {catalog.http_chat_model_primary != null && catalog.http_chat_model_primary !== "" ? (
                            <span>
                              {" "}
                              · <span className="text-white/30">http_chat_model_primary</span>{" "}
                              <span className="font-mono text-white/55">{String(catalog.http_chat_model_primary)}</span>
                            </span>
                          ) : null}
                          {catalog.http_chat_model_fallback != null && catalog.http_chat_model_fallback !== "" ? (
                            <span>
                              {" "}
                              · <span className="text-white/30">http_chat_model_fallback</span>{" "}
                              <span className="font-mono text-white/55">{String(catalog.http_chat_model_fallback)}</span>
                            </span>
                          ) : null}
                        </p>
                      </div>
                      {(() => {
                        const { openrouter, cursor } = partitionModelCatalog(catalog.items);
                        return (
                          <div className="space-y-6">
                            <div>
                              <h3 className="text-[10px] font-black uppercase tracking-widest text-white/35 mb-2">
                                OpenRouter / HAM chat-capable rows
                              </h3>
                              <p className="text-[10px] text-white/35 mb-2">
                                Server validates <span className="font-mono">model_id</span> on{" "}
                                <span className="font-mono">POST /api/chat</span> when{" "}
                                <span className="font-mono">HERMES_GATEWAY_MODE=openrouter</span>.
                              </p>
                              <div className="space-y-2">
                                {openrouter.length ? (
                                  openrouter.map((it) => <CatalogRow key={it.id} item={it} catalog={catalog} />)
                                ) : (
                                  <p className="text-white/30 text-xs">No OpenRouter rows.</p>
                                )}
                              </div>
                            </div>
                            <div>
                              <h3 className="text-[10px] font-black uppercase tracking-widest text-white/35 mb-2">
                                Cursor API slugs (display only)
                              </h3>
                              <p className="text-[10px] text-white/35 mb-2">
                                Listed for product alignment. Dashboard chat is not Cursor-backed.                                 Source:{" "}
                                <span className="font-mono">{catalog.source}</span>
                                {catalog.source === "fallback" ? (
                                  <span className="ml-1.5 inline-block align-middle">
                                    <ModelBadge tone="warn">Static fallback</ModelBadge>
                                  </span>
                                ) : null}
                              </p>
                              <div className="space-y-2">
                                {cursor.length ? (
                                  cursor.map((it) => <CatalogRow key={it.id} item={it} catalog={catalog} />)
                                ) : (
                                  <p className="text-white/30 text-xs">No Cursor rows.</p>
                                )}
                              </div>
                            </div>
                            {catalog.gateway_mode === "http" ? (
                              <div className="rounded-xl border border-cyan-500/20 p-4 space-y-2">
                                <h3 className="text-[10px] font-black uppercase tracking-widest text-cyan-400/70">
                                  Hermes HTTP — server-controlled model
                                </h3>
                                <p className="text-xs text-white/50 leading-relaxed">
                                  Browser <span className="font-mono">model_id</span> is not applied. Upstream request uses{" "}
                                  <span className="font-mono">HERMES_GATEWAY_MODEL</span> on the API host (or Hermes
                                  default).
                                </p>
                                <p className="text-[10px] font-mono text-white/65">
                                  primary: {catalog.http_chat_model_primary || "— (see API env)"}
                                </p>
                                {catalog.http_chat_model_fallback ? (
                                  <p className="text-[10px] font-mono text-white/50">
                                    fallback: {catalog.http_chat_model_fallback}
                                  </p>
                                ) : null}
                                <div className="flex flex-wrap gap-1">
                                  <ModelBadge tone="mute">Config-controlled</ModelBadge>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })()}
                    </>
                  ) : !catalogErr ? (
                    <p className="text-white/40 text-sm">Loading model catalog…</p>
                  ) : null}
                </div>
              )}

              {tab === "commands" && (
                <div className="space-y-4">
                  <p className="text-sm text-white/55">{String((cmds?.hermes_slash_and_menus as { summary?: string })?.summary ?? "")}</p>
                  <div className="space-y-2">
                    {(Array.isArray((cmds?.ham_cli_guidance as unknown[])) ? (cmds?.ham_cli_guidance as { title: string; template: string; requires_tty: boolean }[]) : []).map((g) => (
                      <div
                        key={g.template}
                        className="rounded-lg border border-white/[0.06] p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
                      >
                        <div className="flex items-center gap-2">
                          <Terminal className="h-4 w-4 text-white/25" />
                          <span className="text-xs font-bold text-white/80">{g.title}</span>
                          {g.requires_tty ? (
                            <span className="text-[9px] uppercase text-amber-400/90">TTY</span>
                          ) : null}
                        </div>
                        <code className="text-[10px] font-mono text-[#FF6B00]/90 bg-black/40 px-2 py-1 rounded">
                          {g.template}
                        </code>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {tab === "skills" && (
                <div className="text-sm text-white/60 space-y-2">
                  <p>Live count: {String(skills?.live_count ?? "—")} · linked: {String(skills?.linked_count ?? "—")}</p>
                  <p>Status: {String(skills?.status ?? "—")}</p>
                  <Link to="/skills" className="text-[#FF6B00] text-xs font-bold inline-flex items-center gap-1">
                    Skills UI <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              )}

              {tab === "plugins" && (
                <div className="text-sm text-white/60 space-y-2">
                  <p>Plugin lines (snapshot): {snap.counts.plugins}</p>
                  <p className="text-xs text-white/40">Detailed list: GET /api/hermes-runtime/inventory (operator).</p>
                </div>
              )}

              {tab === "mcp" && (
                <div className="text-sm text-white/60 space-y-2">
                  <p>MCP entries (snapshot): {snap.counts.mcp}</p>
                  <p className="text-xs text-white/40 flex items-center gap-2">
                    <Wrench className="h-3.5 w-3.5" />
                    Config-sanitized servers may appear in inventory when CLI list is empty.
                  </p>
                </div>
              )}

              {tab === "sessions" && (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-3 text-xs">
                    <Link
                      to="/control-plane"
                      className="text-[#FF6B00] font-bold inline-flex items-center gap-1"
                    >
                      Control-plane runs <Layers className="h-3 w-3" />
                    </Link>
                    <Link to="/runs" className="text-[#FF6B00] font-bold inline-flex items-center gap-1">
                      HAM runs <Server className="h-3 w-3" />
                    </Link>
                    <Link to="/activity" className="text-[#FF6B00] font-bold inline-flex items-center gap-1">
                      Open Activity stream <Cpu className="h-3 w-3" />
                    </Link>
                  </div>
                  <ul className="space-y-2">
                    {(snap.activity.control_plane_runs ?? []).length === 0 ? (
                      <li className="text-white/40 text-sm">No control-plane rows for this project (or no project id).</li>
                    ) : (
                      (snap.activity.control_plane_runs as { ham_run_id: string; status: string; summary?: string }[]).map(
                        (row) => (
                          <li
                            key={row.ham_run_id}
                            className="rounded-lg border border-white/[0.06] px-3 py-2 text-xs font-mono text-white/70"
                          >
                            {row.status} · {row.summary ?? row.ham_run_id}
                          </li>
                        ),
                      )
                    )}
                  </ul>
                </div>
              )}

              {tab === "runners" && (
                <div className="grid md:grid-cols-2 gap-3">
                  {snap.external_runners.map((r) => (
                    <RunnerCard key={r.id} r={r} />
                  ))}
                </div>
              )}

              {tab === "diagnostics" && (
                <div className="space-y-4 text-sm">
                  <div>
                    <p className="text-[10px] font-black uppercase text-white/35 mb-2">Warnings</p>
                    {snap.warnings?.length ? (
                      <ul className="list-disc pl-4 text-amber-200/80 space-y-1">
                        {snap.warnings.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-white/40">None on this capture.</p>
                    )}
                  </div>
                  <div>
                    <p className="text-[10px] font-black uppercase text-white/35 mb-2 flex items-center gap-2">
                      <Boxes className="h-3.5 w-3.5" /> Future adapters (placeholders)
                    </p>
                    <ul className="space-y-2">
                      {snap.future_adapter_placeholders.map((p) => (
                        <li key={p.id} className="rounded-lg border border-white/[0.05] px-3 py-2 text-xs">
                          <span className="font-mono text-white/70">{p.id}</span> · {p.status}
                          {p.note ? <span className="block text-white/45 mt-1">{p.note}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
