/**
 * Hermes runtime skills — read-only catalog (Phase 1).
 * Distinct from Cursor operator skills under `.cursor/skills` (see Settings / chat control plane).
 */
import * as React from "react";
import {
  AlertTriangle,
  BookOpen,
  ChevronRight,
  Cpu,
  KeyRound,
  ListTree,
  Search,
  Settings2,
  Shield,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  fetchHermesSkillDetail,
  fetchHermesSkillsCapabilities,
  fetchHermesSkillsCatalog,
  fetchHermesSkillsTargets,
  postHermesSkillsInstallApply,
  postHermesSkillsInstallPreview,
  type HermesSkillCatalogEntry,
  type HermesSkillCatalogEntryDetail,
  type HermesSkillsCapabilities,
  type HermesSkillsCatalogResponse,
  type HermesSkillsInstallApplyResponse,
  type HermesSkillsInstallPreviewResponse,
  type HermesSkillsTargetsResponse,
} from "@/lib/ham/api";

function TrustBadge({ level }: { level: string }) {
  const muted =
    level === "community"
      ? "border-amber-500/40 text-amber-500/70 bg-amber-500/5"
      : level === "trusted"
        ? "border-blue-500/40 text-blue-400/80 bg-blue-500/5"
        : level === "official" || level === "builtin"
          ? "border-emerald-500/40 text-emerald-400/80 bg-emerald-500/5"
          : "border-white/15 text-white/50 bg-white/[0.03]";
  return (
    <span
      className={cn(
        "text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border",
        muted,
      )}
    >
      {level}
    </span>
  );
}

function CapabilityBanner({ caps }: { caps: HermesSkillsCapabilities | null }) {
  if (!caps) return null;
  const mode = caps.mode;
  const tone =
    mode === "local"
      ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-200/90"
      : mode === "remote_only"
        ? "border-amber-500/40 bg-amber-500/5 text-amber-100/90"
        : "border-white/10 bg-white/[0.03] text-white/60";
  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-2 text-[11px] font-bold leading-relaxed",
        tone,
      )}
    >
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
        {mode === "local" ? (
          <Shield className="h-4 w-4 shrink-0" />
        ) : (
          <AlertTriangle className="h-4 w-4 shrink-0" />
        )}
        Skills on this host — {mode}
      </div>
      <p className="opacity-90">
        {mode === "local" &&
          caps.shared_runtime_install_supported === true &&
          "This API host is co-located with Hermes home and the catalog source pin is configured. Phase 2a shared runtime install (Hermes skills only, not Cursor skills) is available from the detail panel."}
        {mode === "local" &&
          caps.shared_runtime_install_supported !== true &&
          "Hermes home is visible on this host, but shared runtime install is not enabled yet (see warnings — e.g. `HAM_HERMES_SKILLS_SOURCE_ROOT` and `.ham-hermes-agent-commit` matching the catalog pin)."}
        {mode === "remote_only" &&
          "This deployment is remote-only (`HAM_HERMES_SKILLS_MODE=remote_only`). You can browse the Hermes runtime catalog; installs are blocked — the API cannot mutate the operator's Hermes home."}
        {mode === "unsupported" &&
          "No local Hermes home found (install Hermes CLI or set `HERMES_HOME` / `HAM_HERMES_HOME`). Catalog still loads; installs are not available here."}
      </p>
      {caps.hermes_home_path_hint && (
        <p className="font-mono text-[10px] opacity-70 break-all">
          Path: {caps.hermes_home_path_hint}
        </p>
      )}
      {(caps.warnings?.length ?? 0) > 0 && (
        <ul className="list-disc pl-4 space-y-1 text-[10px] opacity-80">
          {caps.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function HermesSkills() {
  const [catalogMeta, setCatalogMeta] = React.useState<
    Pick<HermesSkillsCatalogResponse, "upstream" | "catalog_note" | "count"> | null
  >(null);
  const [catalog, setCatalog] = React.useState<HermesSkillCatalogEntry[]>([]);
  const [filter, setFilter] = React.useState("");
  const [caps, setCaps] = React.useState<HermesSkillsCapabilities | null>(null);
  const [targets, setTargets] = React.useState<HermesSkillsTargetsResponse | null>(
    null,
  );
  const [detail, setDetail] = React.useState<HermesSkillCatalogEntryDetail | null>(
    null,
  );
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [detailErr, setDetailErr] = React.useState<string | null>(null);
  const [installPreview, setInstallPreview] =
    React.useState<HermesSkillsInstallPreviewResponse | null>(null);
  const [installPreviewErr, setInstallPreviewErr] = React.useState<string | null>(null);
  const [installApplyErr, setInstallApplyErr] = React.useState<string | null>(null);
  const [installApplyOk, setInstallApplyOk] =
    React.useState<HermesSkillsInstallApplyResponse | null>(null);
  const [installToken, setInstallToken] = React.useState("");
  const [installBusy, setInstallBusy] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoadErr(null);
        const [c, cap, t] = await Promise.all([
          fetchHermesSkillsCatalog(),
          fetchHermesSkillsCapabilities(),
          fetchHermesSkillsTargets(),
        ]);
        if (cancelled) return;
        setCatalog(c.entries);
        setCatalogMeta({
          upstream: c.upstream,
          catalog_note: c.catalog_note,
          count: c.count,
        });
        setCaps(cap);
        setTargets(t);
      } catch (e) {
        if (!cancelled) {
          setLoadErr(e instanceof Error ? e.message : "Failed to load skills catalog");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredCatalog = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter(
      (e) =>
        e.catalog_id.toLowerCase().includes(q) ||
        e.display_name.toLowerCase().includes(q) ||
        e.summary.toLowerCase().includes(q) ||
        e.trust_level.toLowerCase().includes(q),
    );
  }, [catalog, filter]);

  const openDetail = async (entry: HermesSkillCatalogEntry) => {
    setPanelOpen(true);
    setDetail(null);
    setDetailErr(null);
    setInstallPreview(null);
    setInstallPreviewErr(null);
    setInstallApplyErr(null);
    setInstallApplyOk(null);
    setInstallToken("");
    try {
      const res = await fetchHermesSkillDetail(entry.catalog_id);
      setDetail(res.entry);
    } catch (e) {
      setDetailErr(e instanceof Error ? e.message : "Detail request failed");
    }
  };

  const canInstallShared = caps?.shared_runtime_install_supported === true;
  const applyWritesEnabled = caps?.skills_apply_writes_enabled === true;

  const runInstallPreview = async () => {
    if (!detail) return;
    setInstallBusy(true);
    setInstallPreviewErr(null);
    setInstallApplyErr(null);
    setInstallApplyOk(null);
    try {
      const p = await postHermesSkillsInstallPreview({
        catalog_id: detail.catalog_id,
        target: { kind: "shared" },
      });
      setInstallPreview(p);
    } catch (e) {
      setInstallPreview(null);
      setInstallPreviewErr(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setInstallBusy(false);
    }
  };

  const runInstallApply = async () => {
    if (!installPreview || !installToken.trim()) return;
    setInstallBusy(true);
    setInstallApplyErr(null);
    try {
      const out = await postHermesSkillsInstallApply(
        {
          catalog_id: installPreview.catalog_id,
          target: { kind: "shared" },
          proposal_digest: installPreview.proposal_digest,
          base_revision: installPreview.base_revision,
        },
        installToken,
      );
      setInstallApplyOk(out);
    } catch (e) {
      setInstallApplyErr(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setInstallBusy(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-hidden">
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 overflow-y-auto scrollbar-hide p-8 max-w-6xl mx-auto w-full space-y-8">
          <header className="space-y-4 border-b border-white/5 pb-8">
            <div className="flex items-center gap-4">
              <div className="p-2 bg-[#FF6B00]/10 rounded border border-[#FF6B00]/20">
                <Sparkles className="h-5 w-5 text-[#FF6B00]" />
              </div>
              <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">
                Workspace / Skills
              </span>
            </div>
            <h1 className="text-4xl font-black text-[#FF6B00] italic tracking-tighter uppercase leading-none">
              Skills
            </h1>
            <p className="text-sm font-bold text-white/30 max-w-2xl uppercase tracking-widest leading-relaxed">
              Hermes <span className="text-white/50">runtime</span> skills catalog (bundled + official optional; may include
              scripts). Separate from Cursor <span className="text-white/50">operator</span> docs in{" "}
              <code className="text-[#FF6B00]/80">.cursor/skills</code>. Phase 2a: shared-target install only when this API
              host reports install support (see banner).
            </p>
          </header>

          <CapabilityBanner caps={caps} />

          {catalogMeta?.upstream && (
            <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 text-[10px] font-mono text-white/45 space-y-1">
              <div className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/80">
                Catalog source (pinned)
              </div>
              <div>
                {catalogMeta.upstream.repo} @ {catalogMeta.upstream.commit.slice(0, 12)}…
              </div>
              <div className="text-white/30">
                {catalogMeta.count} skills in catalog
              </div>
            </div>
          )}

          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name, id, summary…"
              className="pl-10 bg-black/40 border-white/10 text-white text-xs h-10"
            />
          </div>

          {loadErr && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-red-200/90 text-sm">
              {loadErr}
            </div>
          )}

          {targets && targets.targets.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40 flex items-center gap-2">
                <ListTree className="h-4 w-4 text-[#FF6B00]" />
                Install targets (preview only)
              </h2>
              <p className="text-[10px] text-white/25 uppercase tracking-widest">
                Where Phase 2 installs could apply — CLI profiles on this machine only (not Ham bridge
                profiles or Cursor subagent rules).
              </p>
              <div className="flex flex-wrap gap-2">
                {targets.targets.map((t) => (
                  <span
                    key={`${t.kind}-${t.id}`}
                    className={cn(
                      "text-[9px] font-bold uppercase tracking-wider px-3 py-1.5 rounded border",
                      t.available
                        ? "border-white/10 text-white/50 bg-white/[0.02]"
                        : "border-white/5 text-white/25 bg-transparent line-through opacity-60",
                    )}
                    title={t.notes}
                  >
                    {t.label}
                  </span>
                ))}
              </div>
            </section>
          )}

          <section className="space-y-4">
            <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40">
              Catalog
              {filter.trim() ? (
                <span className="text-white/25 normal-case ml-2">
                  ({filteredCatalog.length} shown)
                </span>
              ) : null}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {filteredCatalog.map((entry) => (
                <button
                  key={entry.catalog_id}
                  type="button"
                  onClick={() => openDetail(entry)}
                  className="text-left group flex flex-col p-6 bg-[#0a0a0a] border border-white/5 hover:border-[#FF6B00]/40 transition-all rounded-xl"
                >
                  <div className="flex justify-between items-start gap-4 mb-4">
                    <div className="space-y-2 flex-1 min-w-0">
                      <h3 className="text-sm font-black uppercase tracking-wide text-[#FF6B00] truncate">
                        {entry.display_name}
                      </h3>
                      <p className="text-[10px] font-bold text-white/35 leading-relaxed line-clamp-3">
                        {entry.summary}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 text-white/20 group-hover:text-[#FF6B00] shrink-0" />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <TrustBadge level={entry.trust_level} />
                    {entry.has_scripts && (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-violet-500/40 text-violet-300/80 bg-violet-500/5 flex items-center gap-1">
                        <Terminal className="h-3 w-3" />
                        Scripts
                      </span>
                    )}
                    {entry.platforms.map((p) => (
                      <span
                        key={p}
                        className="text-[8px] font-mono text-white/25 border border-white/10 px-1.5 py-0.5 rounded"
                      >
                        {p}
                      </span>
                    ))}
                    {entry.required_environment_variables.length > 0 && (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-amber-500/30 text-amber-400/70 bg-amber-500/5 flex items-center gap-1">
                        <KeyRound className="h-3 w-3" />
                        Env
                      </span>
                    )}
                    {entry.config_keys.length > 0 && (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-cyan-500/30 text-cyan-400/70 bg-cyan-500/5 flex items-center gap-1">
                        <Settings2 className="h-3 w-3" />
                        Config
                      </span>
                    )}
                  </div>
                  <p className="mt-4 text-[9px] font-mono text-white/15 truncate">
                    {entry.catalog_id}
                  </p>
                </button>
              ))}
            </div>
          </section>
        </div>

        {/* Detail panel */}
        <div
          className={cn(
            "border-l border-white/5 bg-[#080808] flex flex-col transition-all duration-300 overflow-hidden",
            panelOpen ? "w-full max-w-md opacity-100" : "w-0 max-w-0 opacity-0 border-l-0",
          )}
        >
          {panelOpen && (
            <div className="flex flex-col h-full min-w-[320px]">
              <div className="flex items-center justify-between p-4 border-b border-white/5">
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
                  Skill detail
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setPanelOpen(false);
                    setInstallPreview(null);
                    setInstallPreviewErr(null);
                    setInstallApplyErr(null);
                    setInstallApplyOk(null);
                    setInstallToken("");
                  }}
                  className="p-2 rounded-lg text-white/30 hover:text-white hover:bg-white/5"
                  aria-label="Close panel"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
                {detailErr && (
                  <p className="text-red-400/90 text-xs">{detailErr}</p>
                )}
                {detail && (
                  <>
                    <h3 className="text-lg font-black text-[#FF6B00] uppercase tracking-tight">
                      {detail.display_name}
                    </h3>
                    <p className="text-white/40 text-xs leading-relaxed">{detail.summary}</p>
                    <div className="flex flex-wrap gap-2">
                      <TrustBadge level={detail.trust_level} />
                      <span className="text-[8px] font-mono text-white/30 border border-white/10 px-2 py-0.5 rounded">
                        {detail.source_kind}
                      </span>
                    </div>
                    <dl className="space-y-2 text-[11px]">
                      <div>
                        <dt className="text-white/25 uppercase text-[9px] font-black tracking-wider">
                          Source ref
                        </dt>
                        <dd className="font-mono text-white/50 break-all">{detail.source_ref}</dd>
                      </div>
                      <div>
                        <dt className="text-white/25 uppercase text-[9px] font-black tracking-wider">
                          Version / hash
                        </dt>
                        <dd className="font-mono text-white/50">
                          {detail.version_pin} ·{" "}
                          {detail.content_hash_sha256
                            ? `${detail.content_hash_sha256.slice(0, 16)}…`
                            : "—"}
                        </dd>
                      </div>
                    </dl>
                    {detail.detail.manifest_files.length > 0 && (
                      <div>
                        <p className="text-[9px] font-black uppercase text-white/30 mb-1 flex items-center gap-1">
                          <BookOpen className="h-3 w-3" />
                          Manifest
                        </p>
                        <ul className="font-mono text-[10px] text-white/40 space-y-1">
                          {detail.detail.manifest_files.map((f) => (
                            <li key={f}>{f}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {detail.detail.warnings.length > 0 && (
                      <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3 text-amber-100/80 text-xs space-y-1">
                        {detail.detail.warnings.map((w) => (
                          <p key={w}>{w}</p>
                        ))}
                      </div>
                    )}
                    {detail.detail.provenance_note && (
                      <p className="text-[11px] text-white/35 italic">{detail.detail.provenance_note}</p>
                    )}
                    <div className="pt-4 border-t border-white/5 space-y-3">
                      <p className="text-[9px] text-white/35 uppercase tracking-wider font-bold">
                        Hermes runtime install — target:{" "}
                        <span className="text-[#FF6B00]/90">shared</span> only (not Hermes CLI profiles
                        here; not Cursor skills).
                      </p>
                      <button
                        type="button"
                        disabled={!canInstallShared || installBusy}
                        onClick={() => void runInstallPreview()}
                        className={cn(
                          "w-full py-3 rounded-lg border text-[10px] font-black uppercase tracking-widest transition-colors",
                          canInstallShared && !installBusy
                            ? "bg-[#FF6B00]/20 border-[#FF6B00]/50 text-[#FF6B00] hover:bg-[#FF6B00]/30"
                            : "bg-white/5 border-white/10 text-white/25 cursor-not-allowed",
                        )}
                      >
                        {canInstallShared ? "Preview install (shared)" : "Install unavailable on this host"}
                      </button>
                      {!canInstallShared && caps && (
                        <p className="text-[9px] text-white/25 leading-relaxed">
                          The API must be co-located with Hermes home, not remote-only, and{" "}
                          <code className="text-white/40">HAM_HERMES_SKILLS_SOURCE_ROOT</code> must point at
                          a matching hermes-agent tree (see capabilities warnings).
                        </p>
                      )}
                      {installPreviewErr && (
                        <p className="text-[11px] text-red-300/90">{installPreviewErr}</p>
                      )}
                      {installPreview && (
                        <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3 space-y-2 text-[10px]">
                          <div className="font-black uppercase tracking-widest text-white/40">
                            Preview
                          </div>
                          <p className="text-white/55">
                            <span className="text-white/30">Trust / source:</span>{" "}
                            {String(installPreview.entry.trust_level ?? "—")} ·{" "}
                            {String(installPreview.entry.source_kind ?? "")}
                          </p>
                          <p className="font-mono text-white/45 break-all text-[9px]">
                            Config: {installPreview.config_path}
                          </p>
                          <p className="font-mono text-white/45 break-all text-[9px]">
                            Bundle: {installPreview.bundle_dest}
                          </p>
                          <div className="text-white/40 space-y-1">
                            <span className="text-white/30">external_dirs change:</span> +
                            {installPreview.config_diff.added.length} path(s)
                            {installPreview.config_diff.added.length > 0 && (
                              <ul className="list-disc pl-4 font-mono text-[9px] text-white/50">
                                {installPreview.config_diff.added.map((p) => (
                                  <li key={p}>{p}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                          {installPreview.warnings.length > 0 && (
                            <ul className="list-disc pl-4 text-amber-200/80 text-[9px]">
                              {installPreview.warnings.map((w) => (
                                <li key={w}>{w}</li>
                              ))}
                            </ul>
                          )}
                          <div className="pt-2 border-t border-white/5 space-y-2">
                            <label className="block text-[9px] font-black uppercase text-white/30">
                              HAM_SKILLS_WRITE_TOKEN (session only; not stored)
                            </label>
                            <Input
                              type="password"
                              autoComplete="off"
                              value={installToken}
                              onChange={(e) => setInstallToken(e.target.value)}
                              placeholder={
                                applyWritesEnabled ? "Paste server token…" : "Server apply disabled"
                              }
                              disabled={!applyWritesEnabled || installBusy}
                              className="bg-black/40 border-white/10 text-white text-xs h-9"
                            />
                            {!applyWritesEnabled && (
                              <p className="text-[9px] text-amber-200/70">
                                This server has no <code className="text-white/50">HAM_SKILLS_WRITE_TOKEN</code>{" "}
                                — apply cannot run until an operator sets it.
                              </p>
                            )}
                            <button
                              type="button"
                              disabled={
                                !applyWritesEnabled ||
                                !installToken.trim() ||
                                installBusy
                              }
                              onClick={() => void runInstallApply()}
                              className="w-full py-2.5 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-200/90 text-[10px] font-black uppercase tracking-widest disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              Apply install
                            </button>
                            {installApplyErr && (
                              <p className="text-[11px] text-red-300/90">{installApplyErr}</p>
                            )}
                            {installApplyOk && (
                              <div className="rounded border border-emerald-500/30 bg-emerald-500/5 p-2 text-emerald-100/90 text-[10px] space-y-1">
                                <p className="font-black uppercase tracking-wider">Applied</p>
                                <p className="font-mono break-all">audit: {installApplyOk.audit_id}</p>
                                <p className="font-mono break-all">backup: {installApplyOk.backup_id}</p>
                                <p className="font-mono break-all">
                                  new_revision: {installApplyOk.new_revision.slice(0, 16)}…
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}
                {!detail && !detailErr && (
                  <div className="flex items-center gap-2 text-white/30 text-xs">
                    <Cpu className="h-4 w-4 animate-pulse" />
                    Loading…
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
