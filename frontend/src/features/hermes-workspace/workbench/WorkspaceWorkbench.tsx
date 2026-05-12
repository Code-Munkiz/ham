/**
 * HAM-native command-center workbench (right pane on /workspace/chat).
 * Preview / Share / Publish remain placeholders until product wiring lands.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Database,
  Eye,
  FileCode,
  FolderOpen,
  MoreHorizontal,
  Plus,
  Send,
  Settings2,
  Share2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  type BuilderImportJobRecord,
  type BuilderProjectSourceRecord,
  type BuilderSourceSnapshotRecord,
  listBuilderImportJobs,
  listBuilderProjectSources,
  listBuilderSourceSnapshots,
} from "@/lib/ham/api";
import { cn } from "@/lib/utils";
import { ProjectSourceIntakeDialog } from "./ProjectSourceIntakeDialog";
import { WorkbenchProjectSettingsPanel } from "./WorkbenchProjectSettingsPanel";

export type WorkspaceWorkbenchProps = {
  /** Binds embedded settings/deep-links to the active Ham project from chat routing. */
  projectId?: string | null;
  workspaceId?: string | null;
};

export type WorkspaceWorkbenchTabId = "preview" | "code" | "database" | "storage" | "settings";

const TABS: Array<{ id: WorkspaceWorkbenchTabId; label: string; icon: typeof Eye }> = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "code", label: "Code", icon: FileCode },
  { id: "database", label: "Database", icon: Database },
  { id: "storage", label: "Project source", icon: FolderOpen },
  { id: "settings", label: "Settings", icon: Settings2 },
];

export function WorkspaceWorkbench({
  projectId = null,
  workspaceId = null,
}: WorkspaceWorkbenchProps) {
  const [activeTab, setActiveTab] = React.useState<WorkspaceWorkbenchTabId>("preview");
  const [projectSourceOpen, setProjectSourceOpen] = React.useState(false);
  const [sourceRefreshKey, setSourceRefreshKey] = React.useState(0);
  const tabStripRef = React.useRef<HTMLDivElement | null>(null);
  const [workbenchTabBarMode, setWorkbenchTabBarMode] = React.useState<"labeled" | "icons">(
    "labeled",
  );

  React.useLayoutEffect(() => {
    const el = tabStripRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const apply = () => {
      const w = Math.round(el.getBoundingClientRect().width);
      if (!w) return;
      setWorkbenchTabBarMode(w < 420 ? "icons" : "labeled");
    };
    const ro = new ResizeObserver(() => apply());
    ro.observe(el);
    apply();
    return () => ro.disconnect();
  }, []);

  return (
    <aside
      data-testid="hww-workbench"
      className={cn(
        "flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden",
        "border-white/[0.08] bg-[#040d14]/92 shadow-[inset_1px_0_0_0_rgba(255,255,255,0.04)]",
        "border-t md:border-t-0 md:border-l",
      )}
      aria-label="Workspace workbench"
    >
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] px-2.5 py-2">
        <div
          ref={tabStripRef}
          data-hww-workbench-tab-strip
          data-hww-workbench-tab-density={workbenchTabBarMode}
          className="flex min-w-0 flex-1 flex-wrap gap-1 overflow-hidden"
        >
          {TABS.map((tab) => {
            const active = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                data-testid={`hww-workbench-tab-${tab.id}`}
                data-active={active ? "true" : "false"}
                aria-label={tab.label}
                title={tab.label}
                onClick={() => {
                  setActiveTab(tab.id);
                }}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30",
                  active
                    ? "bg-emerald-500/15 text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(16,185,129,0.25),0_0_16px_rgba(16,185,129,0.08)]"
                    : "text-white/45 hover:bg-white/[0.06] hover:text-white/75",
                )}
              >
                <Icon className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
                {workbenchTabBarMode === "labeled" ? (
                  <span className="select-none">{tab.label}</span>
                ) : null}
              </button>
            );
          })}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled
            className="h-8 gap-1 px-2 text-[11px] text-white/35"
            title="Sharing is not available in this build"
            data-testid="hww-workbench-share"
          >
            <Share2 className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
            <span className="hidden lg:inline">Share</span>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled
            className="h-8 gap-1 px-2 text-[11px] text-white/35"
            title="Publish is not available in this build"
            data-testid="hww-workbench-publish"
          >
            <Send className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
            <span className="hidden lg:inline">Publish</span>
          </Button>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-white/55 hover:text-white/90"
                aria-label="More workbench actions"
                data-testid="hww-workbench-more"
              >
                <MoreHorizontal className="h-4 w-4" strokeWidth={1.5} aria-hidden />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                className="z-50 min-w-[12rem] rounded-lg border border-white/[0.1] bg-[#07141c] p-1 text-[11px] text-white/88 shadow-xl"
                sideOffset={6}
                align="end"
              >
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Download ZIP — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Version history — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Make a copy — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item asChild className="rounded outline-none">
                  <a
                    href="https://github.com/Code-Munkiz/ham/blob/main/README.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block px-2 py-1.5 text-[#7dd3fc] hover:bg-white/[0.06]"
                  >
                    View docs (GitHub)
                  </a>
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>

      <div
        data-testid={`hww-workbench-panel-${activeTab}`}
        className="hww-scroll min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-3"
      >
        {activeTab === "preview" ? <WorkbenchPreviewPanel /> : null}
        {activeTab === "code" ? (
          <WorkbenchCodePanel onAddProjectSource={() => setProjectSourceOpen(true)} />
        ) : null}
        {activeTab === "database" ? <WorkbenchDatabasePanel /> : null}
        {activeTab === "storage" ? (
          <WorkbenchStoragePanel
            workspaceId={workspaceId}
            projectId={projectId}
            refreshKey={sourceRefreshKey}
            onAddProjectSource={() => setProjectSourceOpen(true)}
          />
        ) : null}
        {activeTab === "settings" ? <WorkbenchProjectSettingsPanel projectId={projectId} /> : null}
      </div>
      <ProjectSourceIntakeDialog
        open={projectSourceOpen}
        onOpenChange={setProjectSourceOpen}
        projectId={projectId}
        workspaceId={workspaceId}
        onZipImported={() => {
          setSourceRefreshKey((prev) => prev + 1);
        }}
      />
    </aside>
  );
}

function MutedPanel({ children }: { children: React.ReactNode }) {
  return <div className="space-y-3 text-[12px] leading-relaxed text-white/70">{children}</div>;
}

function WorkbenchPreviewPanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">No preview yet.</p>
      <p className="text-white/55">
        Ask HAM to build or connect a project to generate a preview. Live site preview is not wired
        in this shell.
      </p>
    </MutedPanel>
  );
}

function AddProjectSourceButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      className="gap-1.5 text-[11px]"
      data-testid="hww-add-project-source"
      onClick={onClick}
    >
      <Plus className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
      Add project source
    </Button>
  );
}

function WorkbenchCodePanel({ onAddProjectSource }: { onAddProjectSource: () => void }) {
  return (
    <MutedPanel>
      <div className="flex flex-wrap items-center gap-2">
        <AddProjectSourceButton onClick={onAddProjectSource} />
      </div>
      <div className="grid min-h-[180px] gap-2 rounded-lg border border-white/[0.08] bg-black/25 md:grid-cols-2">
        <div className="border-b border-white/[0.06] p-2 md:border-b-0 md:border-r md:border-white/[0.06]">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Files</p>
          <p className="mt-2 text-white/45">Explorer placeholder — no repo mounted.</p>
        </div>
        <div className="p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Viewer</p>
          <p className="mt-2 text-white/45">Select a file to view source (not connected).</p>
        </div>
      </div>
      <p className="text-white/55">
        Use <span className="font-medium text-white/65">Add project source</span> to upload to your
        local workspace (when configured) or attach a file for chat. Open the{" "}
        <Link
          to="/workspace/files"
          className="font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
        >
          Files
        </Link>{" "}
        route to browse disk after uploads. Full project intake and automatic repo import are not
        connected here yet.
      </p>
    </MutedPanel>
  );
}

function WorkbenchDatabasePanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">Database</p>
      <p className="text-white/55">
        Connect a database to inspect schema, tables, and app data. Examples you might use later:
        Supabase, Neon, Firebase, BigQuery, Postgres. Connection flows are not available in this
        placeholder.
      </p>
    </MutedPanel>
  );
}

type WorkbenchStoragePanelProps = {
  workspaceId?: string | null;
  projectId?: string | null;
  refreshKey: number;
  onAddProjectSource: () => void;
};

function WorkbenchStoragePanel({
  workspaceId = null,
  projectId = null,
  refreshKey,
  onAddProjectSource,
}: WorkbenchStoragePanelProps) {
  const [sources, setSources] = React.useState<BuilderProjectSourceRecord[]>([]);
  const [snapshots, setSnapshots] = React.useState<BuilderSourceSnapshotRecord[]>([]);
  const [jobs, setJobs] = React.useState<BuilderImportJobRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setSources([]);
      setSnapshots([]);
      setJobs([]);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void (async () => {
      try {
        const [sourcesRes, snapshotsRes, jobsRes] = await Promise.all([
          listBuilderProjectSources(ws, pid),
          listBuilderSourceSnapshots(ws, pid),
          listBuilderImportJobs(ws, pid),
        ]);
        if (cancelled) return;
        setSources(sourcesRes.sources || []);
        setSnapshots(snapshotsRes.source_snapshots || []);
        setJobs(jobsRes.import_jobs || []);
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, projectId, refreshKey]);

  const latestJob = jobs[0] ?? null;
  const activeSource = sources.find((s) => s.active_snapshot_id) ?? null;
  const activeSnapshot =
    activeSource && activeSource.active_snapshot_id
      ? snapshots.find((s) => s.id === activeSource.active_snapshot_id) || null
      : null;

  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">Project source</p>
      {!workspaceId?.trim() || !projectId?.trim() ? (
        <p className="text-white/55">
          Select an active workspace and project in chat to manage source snapshots.
        </p>
      ) : null}
      {loading ? <p className="text-white/45">Loading source records…</p> : null}
      {loadError ? (
        <p className="text-amber-200/90" data-testid="hww-project-source-load-error">
          Could not load project source records: {loadError}
        </p>
      ) : null}
      {!loading &&
      !loadError &&
      workspaceId?.trim() &&
      projectId?.trim() &&
      sources.length === 0 ? (
        <p className="text-white/55" data-testid="hww-project-source-empty-state">
          No project source connected yet. Upload a ZIP to create your first source snapshot.
        </p>
      ) : null}
      {sources.length > 0 ? (
        <div className="rounded-lg border border-white/[0.08] bg-black/25 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Sources</p>
          <ul
            className="mt-2 space-y-1 text-[11px] text-white/75"
            data-testid="hww-project-source-list"
          >
            {sources.map((source) => (
              <li key={source.id}>
                {source.display_name || source.kind}{" "}
                <span className="text-white/45">
                  ({source.kind}, {source.status})
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {activeSnapshot ? (
        <p className="text-white/55" data-testid="hww-project-source-active-snapshot">
          Active snapshot: <span className="text-white/70">{activeSnapshot.id}</span> (
          {activeSnapshot.size_bytes.toLocaleString()} bytes)
        </p>
      ) : null}
      {latestJob ? (
        <p className="text-white/55" data-testid="hww-project-source-latest-job">
          Latest import:{" "}
          <span className="text-white/70">
            {latestJob.status} / {latestJob.phase}
          </span>
          {latestJob.error_code ? (
            <span className="text-amber-200/90">
              {" "}
              ({latestJob.error_code}: {latestJob.error_message})
            </span>
          ) : null}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2 pt-1">
        <AddProjectSourceButton onClick={onAddProjectSource} />
      </div>
    </MutedPanel>
  );
}
