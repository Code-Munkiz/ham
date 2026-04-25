import * as React from "react";
import {
  BookOpen,
  Bookmark,
  ChevronRight,
  Cpu,
  KeyRound,
  Search,
  Settings2,
  Terminal,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  fetchCapabilityLibrary,
  fetchHermesSkillDetail,
  postCapabilityLibrarySave,
  type HermesSkillCatalogEntry,
  type HermesSkillCatalogEntryDetail,
  type HermesSkillsCatalogResponse,
  type HermesSkillsInstalledResponse,
} from "@/lib/ham/api";
import { basenameOnly } from "./displayRedact";

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

function ShopSkillOverlayBadge({
  catalogId,
  live,
  linkedCatalogIds,
}: {
  catalogId: string;
  live: HermesSkillsInstalledResponse | null;
  linkedCatalogIds: Set<string>;
}) {
  if (!live) {
    return (
      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/15 text-white/40">
        Static catalog
      </span>
    );
  }
  const st = live.status;
  if (st === "remote_only" || st === "unavailable") {
    return (
      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/20 text-white/45">
        Unavailable
      </span>
    );
  }
  if (st === "error") {
    return (
      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-amber-500/35 text-amber-200/80">
        Unavailable
      </span>
    );
  }
  if (linkedCatalogIds.has(catalogId)) {
    return (
      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-emerald-500/40 text-emerald-300/85 bg-emerald-500/5">
        Live local
      </span>
    );
  }
  return (
    <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/15 text-white/40">
      Catalog-only
    </span>
  );
}

export interface ShopSkillsSectionProps {
  catalog: HermesSkillsCatalogResponse | null;
  catalogErr: string | null;
  live: HermesSkillsInstalledResponse | null;
  liveErr: string | null;
  /** Registered project for saving refs to the capability library. */
  projectId?: string | null;
  libraryWriteToken?: string;
  /** Current library revision (from GET /capability-library/library); updated after save. */
  libraryRevisionRef?: React.MutableRefObject<string | null>;
  onAfterLibrarySave?: (newRevision: string) => void;
}

export function ShopSkillsSection({
  catalog,
  catalogErr,
  live,
  liveErr,
  projectId = null,
  libraryWriteToken = "",
  libraryRevisionRef,
  onAfterLibrarySave,
}: ShopSkillsSectionProps) {
  const [filter, setFilter] = React.useState("");
  const [detail, setDetail] = React.useState<HermesSkillCatalogEntryDetail | null>(null);
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [detailErr, setDetailErr] = React.useState<string | null>(null);
  const [libSaveErr, setLibSaveErr] = React.useState<string | null>(null);
  const [libSaveBusy, setLibSaveBusy] = React.useState<string | null>(null);

  const entries = catalog?.entries ?? [];

  const linkedCatalogIds = React.useMemo(() => {
    const s = new Set<string>();
    if (!live?.installations) return s;
    for (const row of live.installations) {
      if (row.resolution === "linked" && row.catalog_id) s.add(row.catalog_id);
    }
    return s;
  }, [live]);

  const filtered = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    let rows = entries;
    if (q) {
      rows = rows.filter(
        (e) =>
          e.catalog_id.toLowerCase().includes(q) ||
          e.display_name.toLowerCase().includes(q) ||
          e.summary.toLowerCase().includes(q) ||
          e.trust_level.toLowerCase().includes(q),
      );
    }
    return rows;
  }, [entries, filter]);

  const liveOnlyRows = React.useMemo(
    () => live?.installations?.filter((r) => r.resolution === "live_only") ?? [],
    [live],
  );

  const openDetail = async (entry: HermesSkillCatalogEntry) => {
    setPanelOpen(true);
    setDetail(null);
    setDetailErr(null);
    try {
      const res = await fetchHermesSkillDetail(entry.catalog_id);
      setDetail(res.entry);
    } catch (e) {
      setDetailErr(e instanceof Error ? e.message : "Detail request failed");
    }
  };

  const saveToLibrary = async (entry: HermesSkillCatalogEntry) => {
    if (!projectId || !libraryWriteToken.trim()) {
      setLibSaveErr("Set a project in the URL (?project_id=…) and paste the write token (My library tab).");
      return;
    }
    setLibSaveErr(null);
    setLibSaveBusy(entry.catalog_id);
    try {
      const lib = await fetchCapabilityLibrary(projectId);
      const out = await postCapabilityLibrarySave(
        projectId,
        {
          ref: `hermes:${entry.catalog_id}`,
          notes: "",
          base_revision: lib.revision,
        },
        libraryWriteToken.trim(),
      );
      if (libraryRevisionRef) libraryRevisionRef.current = out.new_revision;
      onAfterLibrarySave?.(out.new_revision);
    } catch (e) {
      setLibSaveErr(e instanceof Error ? e.message : "Save to library failed");
    } finally {
      setLibSaveBusy(null);
    }
  };

  return (
    <div className="flex flex-1 min-h-0 gap-0">
      <div className="flex-1 overflow-y-auto scrollbar-hide space-y-6 pr-2">
        {catalogErr ? (
          <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-red-200/90 text-sm">
            {catalogErr}
          </div>
        ) : null}

        {catalog?.upstream ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 text-[10px] font-mono text-white/45 space-y-1">
            <div className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/80">
              Static catalog source (pinned)
            </div>
            <div>
              {catalog.upstream.repo} @ {catalog.upstream.commit.slice(0, 12)}…
            </div>
            <div className="text-white/30">{catalog.count} entries</div>
          </div>
        ) : null}

        {live ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 text-[10px] text-white/55 space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/80">
              Live overlay (read-only)
            </div>
            <p className="leading-relaxed">
              <span className="text-white/35">Live rows:</span> {live.live_count}
              <span className="text-white/25 mx-2">·</span>
              <span className="text-white/35">Linked:</span> {live.linked_count}
              <span className="text-white/25 mx-2">·</span>
              <span className="text-white/35">Live-only:</span> {live.live_only_count}
              <span className="text-white/25 mx-2">·</span>
              <span className="text-white/35">Catalog-only:</span> {live.catalog_only_count}
            </p>
            {(live.warnings?.length ?? 0) > 0 ? (
              <ul className="list-disc pl-4 text-amber-100/85 text-[10px] space-y-0.5">
                {live.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {liveErr ? (
          <p className="text-[10px] text-amber-200/80">Live overlay could not load: {liveErr}</p>
        ) : null}
        {libSaveErr ? (
          <p className="text-[10px] text-red-300/80 max-w-2xl" role="alert">
            {libSaveErr}
          </p>
        ) : null}

        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by name, id, summary…"
            className="pl-10 bg-black/40 border-white/10 text-white text-xs h-10"
          />
        </div>

        <section className="space-y-4">
          <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40">
            Catalog
            {filter.trim() ? (
              <span className="text-white/25 normal-case ml-2">({filtered.length} shown)</span>
            ) : null}
          </h2>
          {filtered.length === 0 ? (
            <p className="text-[11px] text-white/35">No catalog entries match this filter.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {filtered.map((entry) => (
                <div
                  key={entry.catalog_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => void openDetail(entry)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void openDetail(entry);
                    }
                  }}
                  className="text-left group flex flex-col p-6 bg-[#0a0a0a] border border-white/5 hover:border-[#FF6B00]/40 transition-all rounded-xl cursor-pointer"
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
                    <ShopSkillOverlayBadge
                      catalogId={entry.catalog_id}
                      live={live}
                      linkedCatalogIds={linkedCatalogIds}
                    />
                    <TrustBadge level={entry.trust_level} />
                    {entry.has_scripts ? (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-violet-500/40 text-violet-300/80 bg-violet-500/5 flex items-center gap-1">
                        <Terminal className="h-3 w-3" />
                        Scripts
                      </span>
                    ) : null}
                    {entry.required_environment_variables.length > 0 ? (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-amber-500/30 text-amber-400/70 bg-amber-500/5 flex items-center gap-1">
                        <KeyRound className="h-3 w-3" />
                        Env keys
                      </span>
                    ) : null}
                    {entry.config_keys.length > 0 ? (
                      <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-cyan-500/30 text-cyan-400/70 bg-cyan-500/5 flex items-center gap-1">
                        <Settings2 className="h-3 w-3" />
                        Config keys
                      </span>
                    ) : null}
                    {projectId ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void saveToLibrary(entry);
                        }}
                        disabled={!libraryWriteToken.trim() || libSaveBusy === entry.catalog_id}
                        className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-[#FF6B00]/40 text-[#FF6B00]/90 bg-[#FF6B00]/5 flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed hover:border-[#FF6B00]/60"
                      >
                        <Bookmark className="h-3 w-3" />
                        {libSaveBusy === entry.catalog_id ? "Saving…" : "Save to My Library"}
                      </button>
                    ) : null}
                  </div>
                  <p className="mt-4 text-[9px] font-mono text-white/15 truncate">{entry.catalog_id}</p>
                  <span className="mt-2 text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/80">
                    View details
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {liveOnlyRows.length > 0 ? (
          <section className="space-y-3 pb-8">
            <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40">Live-only</h2>
            <p className="text-[10px] text-white/30 uppercase tracking-widest max-w-2xl leading-relaxed">
              Rows from the CLI that did not link to a catalog id.{" "}
              <span className="text-[8px] font-black px-2 py-0.5 rounded border border-white/15 text-white/45">
                Live-only
              </span>
            </p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-white/55 font-mono">
              {liveOnlyRows.slice(0, 48).map((r) => (
                <li
                  key={r.name}
                  className="rounded border border-white/10 bg-white/[0.02] px-3 py-2 flex flex-wrap gap-x-2 gap-y-1"
                >
                  <span className="text-white/75">{r.name}</span>
                  <span className="text-white/35 text-[10px]">
                    {r.hermes_source}/{r.hermes_trust}
                  </span>
                </li>
              ))}
            </ul>
            {liveOnlyRows.length > 48 ? (
              <p className="text-[10px] text-white/35">+{liveOnlyRows.length - 48} more…</p>
            ) : null}
          </section>
        ) : null}
      </div>

      <div
        className={cn(
          "border-l border-white/5 bg-[#080808] flex flex-col transition-all duration-300 overflow-hidden shrink-0",
          panelOpen ? "w-full max-w-md opacity-100" : "w-0 max-w-0 opacity-0 border-l-0",
        )}
      >
        {panelOpen ? (
          <div className="flex flex-col h-full min-w-[320px]">
            <div className="flex items-center justify-between p-4 border-b border-white/5">
              <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
                Inspect skill
              </span>
              <button
                type="button"
                onClick={() => setPanelOpen(false)}
                className="p-2 rounded-lg text-white/30 hover:text-white hover:bg-white/5"
                aria-label="Close panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
              {detailErr ? <p className="text-red-400/90 text-xs">{detailErr}</p> : null}
              {detail ? (
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
                        {detail.content_hash_sha256 ? `${detail.content_hash_sha256.slice(0, 16)}…` : "—"}
                      </dd>
                    </div>
                  </dl>
                  {detail.detail.manifest_files.length > 0 ? (
                    <div>
                      <p className="text-[9px] font-black uppercase text-white/30 mb-1 flex items-center gap-1">
                        <BookOpen className="h-3 w-3" />
                        Manifest (names only)
                      </p>
                      <ul className="font-mono text-[10px] text-white/40 space-y-1">
                        {detail.detail.manifest_files.map((f) => (
                          <li key={f}>{basenameOnly(f)}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {detail.detail.warnings.length > 0 ? (
                    <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3 text-amber-100/80 text-xs space-y-1">
                      {detail.detail.warnings.map((w) => (
                        <p key={w}>{w}</p>
                      ))}
                    </div>
                  ) : null}
                  {detail.detail.provenance_note ? (
                    <p className="text-[11px] text-white/35 italic">{detail.detail.provenance_note}</p>
                  ) : null}
                  <p className="text-[10px] text-white/35 border-t border-white/5 pt-3">
                    Changes to Hermes runtime skills use the legacy operator surface — not from Shop.
                  </p>
                </>
              ) : null}
              {!detail && !detailErr ? (
                <div className="flex items-center gap-2 text-white/30 text-xs">
                  <Cpu className="h-4 w-4 animate-pulse" />
                  Loading…
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
