/**
 * Hermes Gateway / Command Center — backend snapshot (Path B). No live JSON-RPC / WS claims.
 */
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Cpu,
  Layers,
  Orbit,
  RefreshCw,
  Server,
  Shield,
  Terminal,
  Wifi,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchHermesGatewaySnapshot, type HermesGatewaySnapshot } from "@/lib/ham/api";
import type { HermesGatewayExternalRunner } from "@/lib/ham/hermesGateway";

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

  const [tab, setTab] = React.useState<TabId>("overview");
  const [snap, setSnap] = React.useState<HermesGatewaySnapshot | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);

  const load = React.useCallback(
    async (refresh: boolean) => {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      setErr(null);
      try {
        const data = await fetchHermesGatewaySnapshot({ projectId, refresh });
        setSnap(data);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load snapshot");
        setSnap(null);
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
            <h1 className="text-2xl font-black tracking-tight">Hermes Gateway</h1>
            <p className="text-xs text-white/45 max-w-xl leading-relaxed">
              Backend-mediated snapshot (Path B): allowlisted CLI/config discovery, optional Hermes HTTP health,
              HAM control-plane summaries. No live Hermes TUI menu API on v0.8.0 — labels below state CLI-only or
              degraded honestly.
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
                    Open legacy hub for deep links <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              )}

              {tab === "models" && (
                <div className="space-y-3 text-sm text-white/60">
                  <p>
                    Dashboard chat gateway mode: <span className="text-white font-mono">{gwMode}</span>
                  </p>
                  <p>
                    Hermes <span className="font-mono">GET /v1/models</span> count hint (probe):{" "}
                    <span className="font-mono">{String(httpGw?.models_count_hint ?? "—")}</span>
                  </p>
                  <p className="text-xs text-amber-400/80">
                    Full composer catalog remains on <span className="font-mono">GET /api/models</span> (not
                    duplicated here).
                  </p>
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
                      Activity feed <Cpu className="h-3 w-3" />
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
