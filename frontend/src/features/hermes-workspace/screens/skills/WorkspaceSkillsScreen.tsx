/**
 * Upstream: src/routes/skills.tsx + src/screens/skills/skills-screen.tsx
 * (header "Skills Browser", tabs Installed / Marketplace, grid cards, detail sheet).
 * Marketplace hub calls are not available in HAM — show the same empty/fallback pattern.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { workspaceSkillsAdapter, type WorkspaceSkill } from "../../adapters/skillsAdapter";

const BUILTIN = new Set(["ham-local-docs", "ham-local-plan"]);

type SkillsTab = "installed" | "marketplace";

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
  tab,
  actionId,
  emptyTitle,
  emptyDescription,
  onOpen,
  onInstall,
  onUninstall,
  onToggle,
}: {
  skills: SkillView[];
  loading: boolean;
  tab: SkillsTab;
  actionId: string | null;
  emptyTitle: string;
  emptyDescription: string;
  onOpen: (s: SkillView) => void;
  onInstall: (id: string) => void;
  onUninstall: (id: string) => void;
  onToggle: (id: string, en: boolean) => void;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: tab === "installed" ? 4 : 6 }).map((_, i) => (
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
            key={`${tab}-${skill.id}`}
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
                {skill.installed && tab === "installed" ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-[var(--theme-muted)]">On</span>
                    <Switch
                      checked={skill.enabled}
                      disabled={busy || !skill.installed}
                      onCheckedChange={(c) => onToggle(skill.id, c)}
                    />
                  </div>
                ) : null}
                {tab === "marketplace" && !skill.installed ? (
                  <Button size="sm" className="h-7 text-xs" disabled={busy} onClick={() => onInstall(skill.id)}>
                    Install
                  </Button>
                ) : null}
                {tab === "installed" && skill.installed ? (
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

export function WorkspaceSkillsScreen() {
  const [tab, setTab] = React.useState<SkillsTab>("installed");
  const [raw, setRaw] = React.useState<WorkspaceSkill[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [searchInput, setSearchInput] = React.useState("");
  const [actionId, setActionId] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<SkillView | null>(null);
  const [page, setPage] = React.useState(1);
  const pageSize = 30;

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

  return (
    <div className="hws-root min-h-full overflow-y-auto" style={{ color: "var(--theme-text)" }}>
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8">
        <header className="rounded-2xl border border-white/10 bg-black/20 p-4 backdrop-blur-md">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--theme-muted)]">
            Hermes Workspace Marketplace
          </p>
          <h1 className="text-balance text-2xl font-medium sm:text-3xl">Skills Browser</h1>
          <p className="mt-1 max-w-2xl text-pretty text-sm text-[var(--theme-muted)] sm:text-base">
            Install and manage skills stored by the HAM Skills API. Marketplace catalog search is shown for layout parity;
            inventory comes from your deployment only — no upstream hub calls from the browser.
          </p>
        </header>

        <section className="rounded-2xl border border-white/10 bg-black/20 p-3 backdrop-blur-md sm:p-4">
          <Tabs
            value={tab}
            onValueChange={(v) => {
              setTab(v as SkillsTab);
              setPage(1);
            }}
            className="w-full"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <TabsList className="w-full rounded-xl border border-white/10 bg-black/30 p-1 sm:w-auto">
                <TabsTrigger value="installed" className="flex-1 sm:min-w-[132px]">
                  Installed
                </TabsTrigger>
                <TabsTrigger value="marketplace" className="flex-1 sm:min-w-[140px]">
                  Marketplace
                </TabsTrigger>
              </TabsList>

              {tab === "installed" ? (
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={searchInput}
                    onChange={(e) => {
                      setSearchInput(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Search by name, tags, or description"
                    className="h-9 w-full min-w-0 rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-[var(--theme-text)] outline-none sm:min-w-[220px]"
                  />
                </div>
              ) : null}
            </div>

            {err ? (
              <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100/90">
                <p className="font-medium">Skills API unavailable</p>
                <p className="mt-1 whitespace-pre-wrap break-words leading-relaxed opacity-95">{err}</p>
              </div>
            ) : null}

            <TabsContent value="installed" className="mt-3 outline-none">
              <div className="mb-2 flex justify-end">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
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
              <SkillsGrid
                skills={paged}
                loading={loading}
                tab="installed"
                actionId={actionId}
                emptyTitle="No skills installed yet"
                emptyDescription="Add a custom skill or connect a skills catalog when your HAM API exposes one. Built-in entries appear when the API returns them."
                onOpen={setSelected}
                onInstall={(id) => void runAction("install", id)}
                onUninstall={(id) => void runAction("uninstall", id)}
                onToggle={(id, en) => void runAction("toggle", id, en)}
              />
            </TabsContent>

            <TabsContent value="marketplace" className="mt-3 space-y-3 outline-none">
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100/90">
                <p className="font-medium">Skills catalog is not available from this HAM API yet.</p>
                <p className="mt-1 text-xs leading-relaxed opacity-95">
                  There are no browser calls to an external Skills Hub. Use <strong>Installed</strong> for the catalog
                  returned by <code className="text-xs">/api/workspace/skills</code> on your deployment.
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <input
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search Skills Hub, GitHub, and local fallback"
                  className="h-10 w-full rounded-lg border border-white/10 bg-black/30 px-3 text-sm outline-none"
                />
                <div className="text-right text-xs text-[var(--theme-muted)]">Source: hams-local</div>
              </div>
              <SkillsGrid
                skills={[]}
                loading={false}
                tab="marketplace"
                actionId={null}
                emptyTitle="Search the Skills Hub"
                emptyDescription="Hub integration is not wired in this HAM build. Switch to Installed to manage local skills."
                onOpen={(_s) => undefined}
                onInstall={(_id) => undefined}
                onUninstall={(_id) => undefined}
                onToggle={(_id, _e) => undefined}
              />
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
        ) : null}
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
    </div>
  );
}
