/**
 * HAM Workspace Skills: installed items from /api/workspace/skills/items; catalog tab uses
 * /api/workspace/skills/hermes-* (server-side vendored Hermes catalog + read-only live overlay, same
 * sources as /shop). No direct browser calls to external hubs.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import type { HermesSkillCatalogEntry, HermesSkillCatalogEntryDetail } from "@/lib/ham/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { workspaceSkillsAdapter, type WorkspaceSkill } from "../../adapters/skillsAdapter";

const BUILTIN = new Set(["ham-local-docs", "ham-local-plan"]);

type SkillView = {
  id: string;
  name: string;
  description: string;
  author: string;
  category: string;
  icon: string;
  installed: boolean;
  enabled: boolean;
  sourcePath: string;
};

function toView(s: WorkspaceSkill): SkillView {
  return {
    id: s.id,
    name: s.name,
    description: s.description,
    author: BUILTIN.has(s.id) ? "Catalog" : "Custom",
    category: BUILTIN.has(s.id) ? "Built-in" : "Workspace",
    icon: BUILTIN.has(s.id) ? "📚" : "🧩",
    installed: s.installed,
    enabled: s.enabled,
    sourcePath: s.id,
  };
}

function SkillsGrid({
  skills,
  loading,
  actionId,
  emptyTitle,
  emptyDescription,
  onOpen,
  onUninstall,
  onToggle,
}: {
  skills: SkillView[];
  loading: boolean;
  actionId: string | null;
  emptyTitle: string;
  emptyDescription: string;
  onOpen: (s: SkillView) => void;
  onUninstall: (id: string) => void;
  onToggle: (id: string, en: boolean) => void;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-[200px] animate-pulse rounded-2xl border border-white/10 bg-black/20"
          />
        ))}
      </div>
    );
  }

  if (skills.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/15 bg-black/20 px-4 py-8 text-center">
        <p className="text-sm font-medium text-[var(--theme-text)]">{emptyTitle}</p>
        <p className="mt-1 max-w-sm mx-auto text-xs text-[var(--theme-muted)]">{emptyDescription}</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {skills.map((skill) => {
        const busy = actionId === skill.id;
        return (
          <article
            key={skill.id}
            className="flex min-h-[200px] flex-col rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm backdrop-blur-sm"
          >
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="min-w-0 space-y-1">
                <div className="text-lg leading-none">{skill.icon}</div>
                <h3 className="truncate text-sm font-semibold text-[var(--theme-text)]">{skill.name}</h3>
                <p className="line-clamp-2 text-xs text-[var(--theme-muted)]">{skill.description}</p>
              </div>
            </div>
            <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3">
              <div className="text-[10px] text-[var(--theme-muted)]">
                {skill.author} · {skill.category}
              </div>
              <div className="flex items-center gap-2">
                {skill.installed ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-[var(--theme-muted)]">On</span>
                    <Switch
                      checked={skill.enabled}
                      disabled={busy || !skill.installed}
                      onCheckedChange={(c) => onToggle(skill.id, c)}
                    />
                  </div>
                ) : null}
                {skill.installed ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={busy || BUILTIN.has(skill.id)}
                    onClick={() => onUninstall(skill.id)}
                  >
                    Uninstall
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => onOpen(skill)}>
                  Details
                </Button>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function trustBadgeClass(level: string) {
  if (level === "community") return "border-amber-500/35 text-amber-200/75 bg-amber-500/5";
  if (level === "trusted") return "border-blue-500/40 text-blue-300/80 bg-blue-500/5";
  if (level === "official" || level === "builtin")
    return "border-emerald-500/40 text-emerald-300/80 bg-emerald-500/5";
  return "border-white/15 text-white/50 bg-white/[0.03]";
}

type TabKey = "installed" | "catalog";

export function WorkspaceSkillsScreen() {
  const [tab, setTab] = React.useState<TabKey>("installed");
  const [raw, setRaw] = React.useState<WorkspaceSkill[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [searchInput, setSearchInput] = React.useState("");
  const [actionId, setActionId] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<SkillView | null>(null);
  const [page, setPage] = React.useState(1);
  const pageSize = 30;

  const [catPayload, setCatPayload] = React.useState<Awaited<
    ReturnType<typeof workspaceSkillsAdapter.hermesStaticCatalog>
  >["data"]>(null);
  const [catLive, setCatLive] = React.useState<Awaited<
    ReturnType<typeof workspaceSkillsAdapter.hermesLiveOverlay>
  >["overlay"]>(null);
  const [catLoading, setCatLoading] = React.useState(false);
  const [catErr, setCatErr] = React.useState<string | null>(null);
  const [catalogSearch, setCatalogSearch] = React.useState("");
  const [catalogPage, setCatalogPage] = React.useState(1);
  const [hermesDetail, setHermesDetail] = React.useState<HermesSkillCatalogEntryDetail | null>(null);
  const [hermesDetailErr, setHermesDetailErr] = React.useState<string | null>(null);
  const [hermesDetailBusy, setHermesDetailBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr(null);
    const { skills, bridge } = await workspaceSkillsAdapter.list();
    if (bridge.status === "pending") {
      setErr(bridge.detail);
      setRaw([]);
    } else {
      setRaw(skills);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    if (tab !== "catalog") return;
    let cancelled = false;
    (async () => {
      setCatLoading(true);
      setCatErr(null);
      const [cRes, oRes] = await Promise.all([
        workspaceSkillsAdapter.hermesStaticCatalog(),
        workspaceSkillsAdapter.hermesLiveOverlay(),
      ]);
      if (cancelled) return;
      if (cRes.bridge.status === "pending") {
        setCatErr(cRes.bridge.detail);
        setCatPayload(null);
        setCatLive(null);
        setCatLoading(false);
        return;
      }
      setCatErr(null);
      setCatPayload(cRes.data);
      if (oRes.bridge.status === "ready") {
        setCatLive(oRes.overlay);
      } else {
        setCatLive(null);
      }
      setCatLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [tab]);

  const q = searchInput.trim().toLowerCase();
  const installedViews = React.useMemo(() => {
    let list = raw.map(toView);
    if (q) {
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.category.toLowerCase().includes(q),
      );
    }
    return list;
  }, [raw, q]);

  const paged = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return installedViews.slice(start, start + pageSize);
  }, [installedViews, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(installedViews.length / pageSize));

  const linkedCatalogIds = React.useMemo(() => {
    const s = new Set<string>();
    if (!catLive?.installations) return s;
    for (const row of catLive.installations) {
      if (row.resolution === "linked" && row.catalog_id) s.add(row.catalog_id);
    }
    return s;
  }, [catLive]);

  const catalogFiltered = React.useMemo(() => {
    const entries = catPayload?.entries ?? [];
    const cq = catalogSearch.trim().toLowerCase();
    if (!cq) return entries;
    return entries.filter(
      (e) =>
        e.catalog_id.toLowerCase().includes(cq) ||
        e.display_name.toLowerCase().includes(cq) ||
        e.summary.toLowerCase().includes(cq) ||
        e.trust_level.toLowerCase().includes(cq),
    );
  }, [catPayload, catalogSearch]);

  const catalogPaged = React.useMemo(() => {
    const start = (catalogPage - 1) * pageSize;
    return catalogFiltered.slice(start, start + pageSize);
  }, [catalogFiltered, catalogPage, pageSize]);

  const catalogTotalPages = Math.max(1, Math.ceil(catalogFiltered.length / pageSize));

  async function runAction(
    kind: "install" | "uninstall" | "toggle",
    id: string,
    enabled?: boolean,
  ) {
    setActionId(id);
    setErr(null);
    try {
      if (kind === "install") {
        const { error } = await workspaceSkillsAdapter.patch(id, { installed: true, enabled: true });
        if (error) setErr(error);
      } else if (kind === "uninstall") {
        if (BUILTIN.has(id)) {
          setErr("Built-in catalog entries cannot be uninstalled from this list.");
        } else {
          const { error } = await workspaceSkillsAdapter.remove(id);
          if (error) setErr(error);
        }
      } else {
        const { error } = await workspaceSkillsAdapter.patch(id, { enabled: enabled ?? true });
        if (error) setErr(error);
      }
      await load();
    } finally {
      setActionId(null);
    }
  }

  const openHermesDetail = async (e: HermesSkillCatalogEntry) => {
    setHermesDetailBusy(true);
    setHermesDetail(null);
    setHermesDetailErr(null);
    const { entry, error, bridge } = await workspaceSkillsAdapter.hermesStaticCatalogEntry(e.catalog_id);
    setHermesDetailBusy(false);
    if (bridge.status === "pending") {
      setHermesDetailErr(bridge.detail);
      return;
    }
    if (error || !entry) {
      setHermesDetailErr(error ?? "Failed to load details.");
      return;
    }
    setHermesDetail(entry);
  };

  return (
    <div className="hws-root min-h-full overflow-y-auto" style={{ color: "var(--theme-text)" }}>
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8">
        <header className="rounded-2xl border border-white/10 bg-black/20 p-4 backdrop-blur-md">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--theme-muted)]">Hermes Workspace</p>
          <h1 className="text-balance text-2xl font-medium sm:text-3xl">Skills Browser</h1>
          <p className="mt-1 max-w-2xl text-pretty text-sm text-[var(--theme-muted)] sm:text-base">
            <strong>Installed</strong> uses the workspace JSON store via{" "}
            <code className="text-xs opacity-80">/api/workspace/skills</code>. <strong>Catalog</strong> is the read-only
            Hermes static catalog and live install overlay (same data as the{" "}
            <Link to="/workspace/skills" className="text-emerald-400/90 underline-offset-2 hover:underline">
              Skills
            </Link>{" "}
            surface), server-side only.
          </p>
        </header>

        <section className="rounded-2xl border border-white/10 bg-black/20 p-3 backdrop-blur-md sm:p-4">
          <Tabs
            value={tab}
            onValueChange={(v) => {
              setTab(v as TabKey);
              setPage(1);
              setCatalogPage(1);
            }}
            className="w-full"
          >
            <TabsList className="mb-3 w-full justify-start rounded-xl border border-white/10 bg-black/30 p-1 sm:w-auto">
              <TabsTrigger value="installed" className="px-4">
                Installed
              </TabsTrigger>
              <TabsTrigger value="catalog" className="px-4">
                Catalog
              </TabsTrigger>
            </TabsList>

            <TabsContent value="installed" className="mt-0 space-y-3 outline-none">
              <p className="text-xs text-[var(--theme-muted)]">
                Workspace-local skills and toggles. Add custom entries or manage built-ins when present.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <input
                  value={searchInput}
                  onChange={(e) => {
                    setSearchInput(e.target.value);
                    setPage(1);
                  }}
                  placeholder="Search by name, tags, or description"
                  className="h-9 w-full min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-[var(--theme-text)] outline-none sm:max-w-md"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="shrink-0"
                  onClick={async () => {
                    const name = window.prompt("Custom skill name");
                    if (!name?.trim()) return;
                    setActionId("new");
                    const { error } = await workspaceSkillsAdapter.create(name.trim(), "");
                    setActionId(null);
                    if (error) setErr(error);
                    else void load();
                  }}
                >
                  Add custom skill
                </Button>
              </div>

              {err ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100/90">
                  <p className="font-medium">Skills API unavailable</p>
                  <p className="mt-1 whitespace-pre-wrap break-words leading-relaxed opacity-95">{err}</p>
                </div>
              ) : null}

              <SkillsGrid
                skills={paged}
                loading={loading}
                actionId={actionId}
                emptyTitle="No skills in this deployment yet"
                emptyDescription="Add a custom skill, or use built-ins from /api/workspace/skills on this host."
                onOpen={setSelected}
                onUninstall={(id) => void runAction("uninstall", id)}
                onToggle={(id, en) => void runAction("toggle", id, en)}
              />
            </TabsContent>

            <TabsContent value="catalog" className="mt-0 space-y-3 outline-none">
              <p className="text-xs text-[var(--theme-muted)]">
                Read-only Hermes runtime skills catalog. Installing on a remote host is not available from this browser;
                this view mirrors the Capabilities page catalog.
              </p>
              {catPayload?.upstream ? (
                <p className="text-[10px] text-[var(--theme-muted)]">
                  Static source:{" "}
                  <span className="font-mono text-[var(--theme-text)]/80">
                    {catPayload.upstream.repo} @ {String(catPayload.upstream.commit).slice(0, 12)}…
                  </span>{" "}
                  · {catPayload.count.toLocaleString()} entries
                </p>
              ) : null}
              {catLive ? (
                <p className="text-[10px] text-[var(--theme-muted)]">
                  Live overlay: status {catLive.status} · rows {catLive.live_count} · linked {catLive.linked_count} ·
                  catalog-only {catLive.catalog_only_count}
                </p>
              ) : null}

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                <input
                  value={catalogSearch}
                  onChange={(e) => {
                    setCatalogSearch(e.target.value);
                    setCatalogPage(1);
                  }}
                  placeholder="Filter by name, id, summary…"
                  className="h-9 w-full min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-[var(--theme-text)] outline-none sm:max-w-xl"
                />
                <div className="shrink-0 text-[10px] text-[var(--theme-muted)]">
                  Source: {catPayload?.source ?? "hermes_static_catalog"} · read-only
                </div>
              </div>

              {catErr && !catPayload ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100/90">
                  <p className="font-medium">Catalog unavailable</p>
                  <p className="mt-1 whitespace-pre-wrap break-words opacity-95">
                    {catErr} Use Capabilities in the main app to verify server catalog configuration.
                  </p>
                </div>
              ) : null}

              {catLoading ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-[180px] animate-pulse rounded-2xl border border-white/10 bg-black/20"
                    />
                  ))}
                </div>
              ) : catPayload ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {catalogPaged.map((e) => {
                    const st = catLive?.status;
                    const overlayBad =
                      st === "remote_only" || st === "unavailable" || st === "error";
                    const linked = linkedCatalogIds.has(e.catalog_id);
                    return (
                      <article
                        key={e.catalog_id}
                        className="flex min-h-[180px] flex-col rounded-2xl border border-white/10 bg-black/25 p-4"
                      >
                        <div className="min-w-0 space-y-1">
                          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--theme-text)]">
                            {e.display_name}
                          </h3>
                          <p className="line-clamp-3 text-xs text-[var(--theme-muted)]">{e.summary || "—"}</p>
                          <p className="pt-1 font-mono text-[10px] text-white/40">{e.catalog_id}</p>
                        </div>
                        <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-white/10 pt-3">
                          <span
                            className={`text-[8px] font-semibold uppercase tracking-wider rounded border px-1.5 py-0.5 ${trustBadgeClass(e.trust_level)}`}
                          >
                            {e.trust_level}
                          </span>
                          {overlayBad ? (
                            <span className="text-[8px] font-semibold uppercase tracking-wider rounded border border-white/20 text-white/45 px-1.5 py-0.5">
                              Unavailable
                            </span>
                          ) : linked ? (
                            <span className="text-[8px] font-semibold uppercase tracking-wider rounded border border-emerald-500/40 text-emerald-200/80 px-1.5 py-0.5">
                              Linked
                            </span>
                          ) : (
                            <span className="text-[8px] font-semibold uppercase tracking-wider rounded border border-white/15 text-white/40 px-1.5 py-0.5">
                              Catalog-only
                            </span>
                          )}
                        </div>
                        <div className="mt-2 flex justify-end">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-7 text-xs"
                            onClick={() => void openHermesDetail(e)}
                          >
                            View details
                          </Button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : null}

              {!catLoading && catPayload && catalogFiltered.length === 0 ? (
                <p className="text-center text-sm text-[var(--theme-muted)]">No catalog entries match this filter.</p>
              ) : null}
            </TabsContent>
          </Tabs>
        </section>

        {tab === "installed" ? (
          <footer className="flex flex-col gap-2 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-[var(--theme-muted)] tabular-nums sm:flex-row sm:items-center sm:justify-between">
            <span>{installedViews.length.toLocaleString()} total skills</span>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <Link to="/workspace/chat" className="text-emerald-400/90 underline-offset-2 hover:underline">
                Open workspace chat
              </Link>
              <span className="text-white/20">·</span>
              <Link to="/workspace/settings" className="text-emerald-400/90 underline-offset-2 hover:underline">
                Settings
              </Link>
            </div>
            <div className="flex items-center gap-2 sm:ml-0">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="min-w-[82px] text-center">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </footer>
        ) : (
          <footer className="flex flex-col gap-2 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-[var(--theme-muted)] tabular-nums sm:flex-row sm:items-center sm:justify-between">
            <span>{catalogFiltered.length.toLocaleString()} entries (filtered)</span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={catalogPage <= 1 || catLoading}
                onClick={() => setCatalogPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="min-w-[82px] text-center">
                {catalogPage} / {catalogTotalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={catalogPage >= catalogTotalPages || catLoading}
                onClick={() => setCatalogPage((p) => Math.min(catalogTotalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </footer>
        )}
      </div>

      {selected ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
          <div
            className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--theme-bg)] shadow-2xl"
            style={{ color: "var(--theme-text)" }}
          >
            <div className="border-b border-white/10 px-5 py-4">
              <h2 className="text-lg font-semibold">
                {selected.icon} {selected.name}
              </h2>
              <p className="mt-1 text-sm text-[var(--theme-muted)]">
                by {selected.author} · {selected.category}
              </p>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <p className="whitespace-pre-wrap text-sm text-neutral-200">{selected.description || "—"}</p>
              <p className="mt-4 text-xs text-[var(--theme-muted)]">
                Source: <code className="text-xs opacity-80">{selected.sourcePath}</code>
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t border-white/10 px-5 py-3">
              <Button type="button" size="sm" variant="secondary" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {hermesDetailBusy || hermesDetail || hermesDetailErr ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
          <div
            className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--theme-bg)] shadow-2xl"
            style={{ color: "var(--theme-text)" }}
          >
            <div className="border-b border-white/10 px-5 py-4">
              <h2 className="text-lg font-semibold">
                {hermesDetail ? hermesDetail.display_name : "Skill details"}
              </h2>
              {hermesDetail ? (
                <p className="mt-1 font-mono text-xs text-[var(--theme-muted)]">{hermesDetail.catalog_id}</p>
              ) : null}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">
              {hermesDetailBusy ? <p className="text-[var(--theme-muted)]">Loading…</p> : null}
              {hermesDetailErr ? <p className="text-amber-200/90">{hermesDetailErr}</p> : null}
              {hermesDetail ? (
                <div className="space-y-3">
                  <p className="whitespace-pre-wrap text-neutral-200">{hermesDetail.summary || "—"}</p>
                  {hermesDetail.platforms.length ? (
                    <p className="text-xs text-[var(--theme-muted)]">
                      Platforms: {hermesDetail.platforms.join(", ")}
                    </p>
                  ) : null}
                  {hermesDetail.detail ? (
                    <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs">
                      <p className="text-[var(--theme-muted)]">{hermesDetail.detail.provenance_note}</p>
                      {hermesDetail.detail.warnings.length ? (
                        <ul className="mt-2 list-disc pl-4 text-amber-200/80">
                          {hermesDetail.detail.warnings.map((w) => (
                            <li key={w}>{w}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 border-t border-white/10 px-5 py-3">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  setHermesDetail(null);
                  setHermesDetailErr(null);
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
