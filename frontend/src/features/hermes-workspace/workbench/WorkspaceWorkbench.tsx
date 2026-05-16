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
  type BuilderActivityItem,
  type CloudRuntimeJob,
  type CloudRuntimeLifecycleStatus,
  type BuilderCloudRuntimeStatus,
  type BuilderImportJobRecord,
  type BuilderVisualEditRequest,
  type CreateBuilderVisualEditRequestPayload,
  type LocalRunProfilePayload,
  type LocalRunProfileResponse,
  type BuilderPreviewStatus,
  type BuilderWorkerCapability,
  type BuilderProjectSourceRecord,
  type BuilderSourceSnapshotRecord,
  createBuilderPreviewProxySession,
  createBuilderVisualEditRequest,
  deleteBuilderLocalRunProfile,
  deleteBuilderLocalPreview,
  getBuilderActivity,
  getBuilderCloudRuntime,
  getBuilderCloudRuntimeJobStatus,
  getBuilderLocalRunProfile,
  getBuilderPreviewStatus,
  getBuilderSnapshotFileContent,
  getBuilderWorkerCapabilities,
  listBuilderCloudRuntimeJobs,
  subscribeBuilderActivityStream,
  listBuilderVisualEditRequests,
  listBuilderImportJobs,
  listBuilderProjectSources,
  listBuilderSnapshotFiles,
  listBuilderSourceSnapshots,
  postBuilderSnapshotFileChat,
  postBuilderLocalPreview,
  requestBuilderCloudRuntime,
  saveBuilderLocalRunProfile,
} from "@/lib/ham/api";
import { sanitizeWorkbenchProjectAccessMessage } from "@/lib/ham/workbenchProjectMessages";
import { cn } from "@/lib/utils";
import { ProjectSourceIntakeDialog } from "./ProjectSourceIntakeDialog";
import { WorkbenchProjectSettingsPanel } from "./WorkbenchProjectSettingsPanel";

export type WorkspaceWorkbenchProps = {
  /** Binds embedded settings/deep-links to the active Ham project from chat routing. */
  projectId?: string | null;
  workspaceId?: string | null;
  /** Bumped from chat when builder scaffold runs so workbench refetches sources. */
  workbenchRefreshSignal?: number;
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
  workbenchRefreshSignal = 0,
}: WorkspaceWorkbenchProps) {
  const [activeTab, setActiveTab] = React.useState<WorkspaceWorkbenchTabId>("preview");
  const [projectSourceOpen, setProjectSourceOpen] = React.useState(false);
  const [sourceRefreshKey, setSourceRefreshKey] = React.useState(0);
  const [previewTabRefreshKey, setPreviewTabRefreshKey] = React.useState(0);
  const tabStripRef = React.useRef<HTMLDivElement | null>(null);
  const [workbenchTabBarMode, setWorkbenchTabBarMode] = React.useState<"labeled" | "icons">(
    "labeled",
  );

  React.useEffect(() => {
    if (workbenchRefreshSignal > 0) {
      setSourceRefreshKey((k) => k + 1);
    }
  }, [workbenchRefreshSignal]);

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
      <div className="relative z-[250] flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] px-2.5 py-2">
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
                  if (tab.id === "preview") {
                    setPreviewTabRefreshKey((k) => k + 1);
                  }
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
        {activeTab === "preview" ? (
          <WorkbenchPreviewPanel
            workspaceId={workspaceId}
            projectId={projectId}
            sourceRefreshKey={sourceRefreshKey}
            previewTabRefreshKey={previewTabRefreshKey}
          />
        ) : null}
        {activeTab === "code" ? (
          <WorkbenchCodePanel
            workspaceId={workspaceId}
            projectId={projectId}
            sourceRefreshKey={sourceRefreshKey}
            onAddProjectSource={() => setProjectSourceOpen(true)}
            onSnapshotUpdated={() => setSourceRefreshKey((prev) => prev + 1)}
          />
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

function isProjectNotFoundError(message: string | null): boolean {
  const text = (message || "").toLowerCase();
  return text.includes("unknown project_id") || text.includes("project_not_found");
}

function isSessionAuthInterruption(message: string | null): boolean {
  const text = (message || "").toLowerCase();
  return (
    text.includes("clerk_session_required") ||
    text.includes("ham_workspace_auth_required") ||
    text.includes("too many requests") ||
    text.includes("http 429") ||
    text.includes("session token") ||
    text.includes("signature has expired") ||
    /(^|\\b)401(\\b|$)/.test(text) ||
    text.includes("http 401")
  );
}

function sanitizePreviewFetchError(message: string | null): string | null {
  const raw = (message || "").trim();
  if (!raw) return null;
  if (/\b404\b/i.test(raw) || /HTTP\s*404/i.test(raw)) {
    return "Preview status is not available yet.";
  }
  if (
    /PREVIEW_PROXY_UPSTREAM_UNAVAILABLE/i.test(raw) ||
    /PREVIEW_PROXY_TIMEOUT/i.test(raw) ||
    /PREVIEW_PROXY_NOT_CONFIGURED/i.test(raw)
  ) {
    return "Preview is still warming up. HAM will keep retrying until it is ready.";
  }
  return raw;
}

function normalizePreviewUrl(preview: BuilderPreviewStatus | null): string | null {
  if (!preview || preview.status !== "ready") return null;
  const raw = (preview.preview_url || "").trim();
  if (!raw) return null;
  if (preview.mode === "local") return raw;
  if (/^https?:\/\//i.test(raw)) return null;
  const withoutSlash = raw.replace(/^\/+/, "");
  if (!withoutSlash) return null;
  if (withoutSlash.startsWith("api/")) return `/${withoutSlash}`;
  if (withoutSlash.startsWith("workspaces/")) return `/api/${withoutSlash}`;
  return null;
}

function WorkbenchPreviewPanel({
  workspaceId = null,
  projectId = null,
  sourceRefreshKey = 0,
  previewTabRefreshKey = 0,
}: {
  workspaceId?: string | null;
  projectId?: string | null;
  sourceRefreshKey?: number;
  previewTabRefreshKey?: number;
}) {
  const PREVIEW_AUTOPOLL_MS = 2500;
  const [preview, setPreview] = React.useState<BuilderPreviewStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [activity, setActivity] = React.useState<BuilderActivityItem[]>([]);
  const [activityError, setActivityError] = React.useState<string | null>(null);
  const [activityStreamState, setActivityStreamState] = React.useState<
    "live" | "reconnecting" | "offline"
  >("offline");
  const [workers, setWorkers] = React.useState<BuilderWorkerCapability[]>([]);
  const [workersError, setWorkersError] = React.useState<string | null>(null);
  const [previewUrlInput, setPreviewUrlInput] = React.useState("");
  const [submitBusy, setSubmitBusy] = React.useState(false);
  const [disconnectBusy, setDisconnectBusy] = React.useState(false);
  const [runProfile, setRunProfile] = React.useState<LocalRunProfileResponse | null>(null);
  const [runProfileBusy, setRunProfileBusy] = React.useState(false);
  const [runProfileError, setRunProfileError] = React.useState<string | null>(null);
  const [visualEditRequests, setVisualEditRequests] = React.useState<BuilderVisualEditRequest[]>(
    [],
  );
  const [visualEditInstruction, setVisualEditInstruction] = React.useState("");
  const [visualEditSelectorHints, setVisualEditSelectorHints] = React.useState("");
  const [visualEditRoute, setVisualEditRoute] = React.useState("/");
  const [visualEditModeActive, setVisualEditModeActive] = React.useState(false);
  const [visualEditTarget, setVisualEditTarget] = React.useState<{
    x: number;
    y: number;
    width: number;
    height: number;
    viewport_width: number;
    viewport_height: number;
    device_mode: "desktop" | "mobile";
  } | null>(null);
  const [visualEditBusy, setVisualEditBusy] = React.useState(false);
  const [visualEditError, setVisualEditError] = React.useState<string | null>(null);
  const [visualEditNotice, setVisualEditNotice] = React.useState<string | null>(null);
  const [cloudRuntime, setCloudRuntime] = React.useState<BuilderCloudRuntimeStatus | null>(null);
  const [cloudRuntimeError, setCloudRuntimeError] = React.useState<string | null>(null);
  const [cloudRuntimeJobBusy, setCloudRuntimeJobBusy] = React.useState(false);
  const [cloudRuntimeJobError, setCloudRuntimeJobError] = React.useState<string | null>(null);
  const [cloudRuntimeJobNotice, setCloudRuntimeJobNotice] = React.useState<string | null>(null);
  const [cloudRuntimeLatestJob, setCloudRuntimeLatestJob] = React.useState<CloudRuntimeJob | null>(
    null,
  );
  const [cloudRuntimeLifecycle, setCloudRuntimeLifecycle] =
    React.useState<CloudRuntimeLifecycleStatus | null>(null);
  const [previewProxySessionKey, setPreviewProxySessionKey] = React.useState<string | null>(null);
  const [previewProxySessionMinting, setPreviewProxySessionMinting] = React.useState(false);
  const [previewProxySessionError, setPreviewProxySessionError] = React.useState<string | null>(
    null,
  );
  const [runProfileForm, setRunProfileForm] = React.useState<LocalRunProfilePayload>({
    display_name: "Local run profile",
    working_directory: ".",
    dev_command: "npm run dev",
    install_command: "",
    build_command: "",
    test_command: "",
    expected_preview_url: "",
  });
  const [snapshots, setSnapshots] = React.useState<BuilderSourceSnapshotRecord[]>([]);
  const [previewViewport, setPreviewViewport] = React.useState<"desktop" | "mobile">("desktop");
  const [iframeProxyError, setIframeProxyError] = React.useState<string | null>(null);
  const [iframeReloadNonce, setIframeReloadNonce] = React.useState(0);
  const [authSessionRefreshing, setAuthSessionRefreshing] = React.useState(false);
  const previewAuthBackoffUntilRef = React.useRef(0);
  const activityDrivenPreviewRefreshAtRef = React.useRef(0);

  React.useEffect(() => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setSnapshots([]);
      return;
    }
    let cancelled = false;
    void listBuilderSourceSnapshots(ws, pid)
      .then((r) => {
        if (!cancelled) setSnapshots(r.source_snapshots || []);
      })
      .catch(() => {
        if (!cancelled) setSnapshots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, projectId, sourceRefreshKey]);

  const refreshActivity = React.useCallback(async () => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setActivity([]);
      setActivityError(null);
      return;
    }
    try {
      const activityPayload = await getBuilderActivity(ws, pid);
      setActivity(activityPayload.items || []);
      setActivityError(null);
    } catch (e) {
      setActivity([]);
      setActivityError(e instanceof Error ? e.message : String(e));
    }
  }, [workspaceId, projectId]);

  const refreshRunProfile = React.useCallback(async () => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setRunProfile(null);
      setRunProfileError(null);
      return;
    }
    try {
      const payload = await getBuilderLocalRunProfile(ws, pid);
      setRunProfile(payload);
      setRunProfileError(null);
      if (payload.profile) {
        const profile = payload.profile;
        setRunProfileForm({
          display_name: profile.display_name || "Local run profile",
          working_directory: profile.working_directory || ".",
          dev_command: (profile.dev_command_argv || []).join(" "),
          install_command: (profile.install_command_argv || []).join(" "),
          build_command: (profile.build_command_argv || []).join(" "),
          test_command: (profile.test_command_argv || []).join(" "),
          expected_preview_url: profile.expected_preview_url || "",
          source_snapshot_id: profile.source_snapshot_id || null,
          status: profile.status,
          metadata: profile.metadata || {},
        });
      }
    } catch (e) {
      setRunProfile(null);
      setRunProfileError(e instanceof Error ? e.message : String(e));
    }
  }, [workspaceId, projectId]);

  const refreshVisualEditRequests = React.useCallback(async () => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setVisualEditRequests([]);
      setVisualEditError(null);
      return;
    }
    try {
      const payload = await listBuilderVisualEditRequests(ws, pid);
      setVisualEditRequests(payload.visual_edit_requests || []);
      setVisualEditError(null);
    } catch (e) {
      setVisualEditRequests([]);
      setVisualEditError(e instanceof Error ? e.message : String(e));
    }
  }, [workspaceId, projectId]);

  const refreshWorkers = React.useCallback(async () => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setWorkers([]);
      setWorkersError(null);
      return;
    }
    try {
      const payload = await getBuilderWorkerCapabilities(ws, pid);
      setWorkers(payload.workers || []);
      setWorkersError(null);
    } catch (e) {
      setWorkers([]);
      setWorkersError(e instanceof Error ? e.message : String(e));
    }
  }, [workspaceId, projectId]);

  const refreshPreviewRuntimeStatus = React.useCallback(
    async (opts?: { includeLifecycle?: boolean; forceRefresh?: boolean }) => {
      const ws = workspaceId?.trim() || "";
      const pid = projectId?.trim() || "";
      if (!ws || !pid) {
        setPreview(null);
        setCloudRuntime(null);
        setCloudRuntimeLatestJob(null);
        setCloudRuntimeLifecycle(null);
        setAuthSessionRefreshing(false);
        previewAuthBackoffUntilRef.current = 0;
        return;
      }
      const forceRefresh = opts?.forceRefresh === true;
      if (!forceRefresh && previewAuthBackoffUntilRef.current > Date.now()) {
        return;
      }
      const includeLifecycle = opts?.includeLifecycle !== false;
      try {
        const previewPayload = await getBuilderPreviewStatus(ws, pid);
        const cloudPayload = await getBuilderCloudRuntime(ws, pid);
        const cloudJobsPayload = await listBuilderCloudRuntimeJobs(ws, pid);
        setPreview(previewPayload);
        setCloudRuntime(cloudPayload);
        const latestJob = cloudJobsPayload.jobs?.[0] || null;
        setCloudRuntimeLatestJob(latestJob);
        if (includeLifecycle && latestJob?.id) {
          const jobStatus = await getBuilderCloudRuntimeJobStatus(ws, pid, latestJob.id);
          setCloudRuntimeLifecycle(jobStatus.lifecycle);
        } else if (!latestJob) {
          setCloudRuntimeLifecycle(null);
        }
        setError(null);
        setAuthSessionRefreshing(false);
        previewAuthBackoffUntilRef.current = 0;
        setCloudRuntimeError(null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (isSessionAuthInterruption(msg)) {
          setAuthSessionRefreshing(true);
          previewAuthBackoffUntilRef.current = Date.now() + 4_000;
          setCloudRuntimeError("Session refreshing... re-establishing secure preview checks.");
          return;
        }
        setAuthSessionRefreshing(false);
        setError(msg);
        setPreview(null);
        setCloudRuntime(null);
        setCloudRuntimeLatestJob(null);
        setCloudRuntimeLifecycle(null);
        setCloudRuntimeError(msg);
      }
    },
    [workspaceId, projectId],
  );

  const refresh = React.useCallback(async () => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setPreview(null);
      setActivity([]);
      setCloudRuntimeLatestJob(null);
      setCloudRuntimeLifecycle(null);
      setError(null);
      setActivityError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await refreshPreviewRuntimeStatus({ includeLifecycle: true });
      await refreshActivity();
      await refreshRunProfile();
      await refreshVisualEditRequests();
      await refreshWorkers();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setPreview(null);
      setCloudRuntime(null);
      setCloudRuntimeLatestJob(null);
      setCloudRuntimeLifecycle(null);
      setCloudRuntimeError(msg);
    } finally {
      setLoading(false);
    }
  }, [
    workspaceId,
    projectId,
    refreshActivity,
    refreshRunProfile,
    refreshVisualEditRequests,
    refreshWorkers,
    refreshPreviewRuntimeStatus,
  ]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    const wsId = workspaceId?.trim() || "";
    const project = projectId?.trim() || "";
    if (!wsId || !project) {
      setActivityStreamState("offline");
      return;
    }
    setActivityStreamState("reconnecting");
    const sub = subscribeBuilderActivityStream(wsId, project, {
      onOpen: () => setActivityStreamState("live"),
      onActivity: (payload) => {
        setActivity(payload.items || []);
        setActivityError(null);
        setActivityStreamState("live");
        const shouldRefreshPreview =
          (payload.items || []).some((item) =>
            ["runtime_status", "preview_connected", "preview_error", "source_snapshot"].includes(
              item.kind,
            ),
          ) || (payload.items || []).length > 0;
        if (shouldRefreshPreview) {
          const now = Date.now();
          if (now - activityDrivenPreviewRefreshAtRef.current >= 1_200) {
            activityDrivenPreviewRefreshAtRef.current = now;
            void refreshPreviewRuntimeStatus({ includeLifecycle: false });
          }
        }
      },
      onHeartbeat: () => setActivityStreamState("live"),
      onError: () => {
        setActivityStreamState("offline");
        setActivityError((prev) => prev || "Live activity stream disconnected. Refresh manually.");
        void refreshActivity();
      },
    });
    return () => sub.close();
  }, [workspaceId, projectId, refreshActivity, refreshPreviewRuntimeStatus]);

  const previewUrl = normalizePreviewUrl(preview);
  const ws = workspaceId?.trim() || "";
  const pid = projectId?.trim() || "";
  const hasBackendSource = snapshots.length > 0 || Boolean(preview?.source_snapshot_id);
  let previewPhase:
    | "no_project"
    | "no_source"
    | "preparing"
    | "source_ready"
    | "starting"
    | "ready"
    | "error" = "no_source";
  if (!ws || !pid) {
    previewPhase = "no_project";
  } else if (iframeProxyError) {
    previewPhase = "starting";
  } else if (authSessionRefreshing) {
    previewPhase = "starting";
  } else if (preview?.status === "error") {
    previewPhase = "error";
  } else if (error) {
    previewPhase = "error";
  } else if (preview?.status === "ready" && previewUrl) {
    previewPhase = "ready";
  } else if (preview?.mode === "cloud" && preview?.status === "building") {
    previewPhase = "starting";
  } else if (preview?.mode === "cloud" && preview?.status === "waiting" && hasBackendSource) {
    previewPhase = "source_ready";
  } else if (preview?.status === "waiting") {
    previewPhase = "starting";
  } else if (hasBackendSource && preview?.status === "not_connected") {
    previewPhase = "source_ready";
  } else if (hasBackendSource && loading) {
    previewPhase = "starting";
  } else if (!hasBackendSource && loading) {
    previewPhase = "preparing";
  } else if (!hasBackendSource) {
    previewPhase = "no_source";
  } else {
    previewPhase = "source_ready";
  }
  const showConnectForm = Boolean(
    ws &&
    pid &&
    (preview?.status === "not_connected" ||
      preview?.status === "waiting" ||
      preview?.status === "error"),
  );
  const visualEditReady = Boolean(ws && pid && preview?.status === "ready" && previewUrl);
  const previewUrlKind: "local" | "cloud_proxy" | "unknown" =
    preview?.mode === "local" ? "local" : preview?.mode === "cloud" ? "cloud_proxy" : "unknown";
  React.useEffect(() => {
    if (!visualEditReady) {
      setVisualEditModeActive(false);
      setVisualEditTarget(null);
    }
  }, [visualEditReady]);
  const cloudRuntimeWorker =
    workers.find((row) => row.worker_kind === "cloud_runtime_worker") || null;
  const cloudRuntimeProviderStatus = (cloudRuntimeWorker?.status || "disabled").toLowerCase();
  const cloudRuntimeState = cloudRuntime?.status || "disabled";
  const cloudRuntimeRequestEnabled = [
    "dry_run_ready",
    "provider_ready",
    "provider_accepted",
  ].includes(cloudRuntimeState);
  const activeSourceSnapshotId =
    preview?.source_snapshot_id || cloudRuntime?.source_snapshot_id || snapshots[0]?.id || null;
  const cloudPreviewHealthy =
    preview?.mode === "cloud" && preview?.status === "ready" && preview?.health === "healthy";
  const cloudRetryEnabled =
    Boolean(ws && pid && activeSourceSnapshotId) &&
    cloudRuntimeRequestEnabled &&
    !cloudPreviewHealthy;
  const previewProxySessionCandidateKey =
    ws && pid && previewUrl && preview?.mode === "cloud" && preview?.status === "ready"
      ? [
          ws,
          pid,
          preview.runtime_session_id || "",
          preview.preview_endpoint_id || "",
          previewUrl,
        ].join("|")
      : null;
  const cloudPreviewProxyNeedsSession =
    preview?.mode === "cloud" && preview?.status === "ready" && Boolean(previewUrl);
  const canRenderPreviewIframe =
    preview?.status === "ready" &&
    Boolean(previewUrl) &&
    !iframeProxyError &&
    (!cloudPreviewProxyNeedsSession ||
      (previewProxySessionKey === previewProxySessionCandidateKey && !previewProxySessionError));
  const shouldAutoPollPreview =
    Boolean(ws && pid && !loading) &&
    ((preview?.status === "waiting" && hasBackendSource) ||
      preview?.status === "building" ||
      (preview?.status === "not_connected" && hasBackendSource) ||
      cloudRuntimeLatestJob?.status === "queued" ||
      Boolean(iframeProxyError) ||
      authSessionRefreshing ||
      cloudRuntimeLatestJob?.status === "running");

  React.useEffect(() => {
    if (!shouldAutoPollPreview) return;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      void refreshPreviewRuntimeStatus({ includeLifecycle: false });
    };
    tick();
    const intervalId = window.setInterval(tick, PREVIEW_AUTOPOLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    shouldAutoPollPreview,
    refreshPreviewRuntimeStatus,
    sourceRefreshKey,
    preview?.source_snapshot_id,
    preview?.runtime_session_id,
    cloudRuntimeLatestJob?.id,
  ]);

  React.useEffect(() => {
    if (!previewTabRefreshKey) return;
    void refreshPreviewRuntimeStatus({ includeLifecycle: false });
  }, [previewTabRefreshKey, refreshPreviewRuntimeStatus]);

  React.useEffect(() => {
    setIframeProxyError(null);
  }, [
    preview?.runtime_session_id,
    preview?.preview_endpoint_id,
    preview?.source_snapshot_id,
    previewUrl,
  ]);

  React.useEffect(() => {
    if (!iframeProxyError) return;
    if (preview?.status !== "ready" || !previewUrl) return;
    setIframeReloadNonce((n) => n + 1);
    setIframeProxyError(null);
  }, [iframeProxyError, preview?.status, previewUrl]);

  React.useEffect(() => {
    if (!cloudPreviewProxyNeedsSession || !previewProxySessionCandidateKey || !ws || !pid) {
      setPreviewProxySessionMinting(false);
      setPreviewProxySessionError(null);
      setPreviewProxySessionKey(null);
      return;
    }
    if (previewProxySessionKey === previewProxySessionCandidateKey) {
      return;
    }
    let cancelled = false;
    setPreviewProxySessionMinting(true);
    setPreviewProxySessionError(null);
    void createBuilderPreviewProxySession(ws, pid)
      .then(() => {
        if (!cancelled) {
          setPreviewProxySessionKey(previewProxySessionCandidateKey);
          setPreviewProxySessionError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setPreviewProxySessionKey(null);
          setPreviewProxySessionError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPreviewProxySessionMinting(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    cloudPreviewProxyNeedsSession,
    previewProxySessionCandidateKey,
    previewProxySessionKey,
    ws,
    pid,
  ]);
  const cloudRuntimeProviderCopy =
    cloudRuntimeState === "experiment_not_enabled"
      ? "Cloud runtime experiments are not enabled."
      : cloudRuntimeState === "config_missing"
        ? "Cloud runtime provider needs configuration before it can run."
        : cloudRuntimeState === "dry_run_ready"
          ? "Cloud runtime dry-run path is ready for safe experimentation."
          : cloudRuntimeState === "provider_ready" || cloudRuntimeState === "provider_accepted"
            ? "Cloud runtime experiment provider is ready."
            : "Cloud runtime experiments are disabled by default.";
  const cloudRuntimeReady =
    cloudRuntimeState === "provider_ready" || cloudRuntimeState === "provider_accepted";
  const cloudRuntimePrimaryCopy = cloudRuntimeReady
    ? "Cloud preview runtime is ready."
    : "Cloud preview runtime status is shown below.";
  const cloudRuntimeSecondaryCopy = cloudRuntimeReady
    ? "Generated apps can run in the hosted preview sandbox."
    : "Check status and setup hints below for this project.";
  const optionalWorkerIntroCopy =
    "Optional coding workers can be connected for extra workflows. They do not block cloud preview runtime.";
  const cloudPreviewDisconnected = [
    "disabled",
    "experiment_not_enabled",
    "config_missing",
  ].includes(cloudRuntimeState);
  const primaryState =
    previewPhase === "no_project" || previewPhase === "no_source"
      ? {
          title: "Tell HAM what to build.",
          subtitle: "Your app preview will appear here once HAM creates the first source.",
        }
      : previewPhase === "preparing"
        ? {
            title: "Preparing your project…",
            subtitle: "Hang tight while HAM sets up the first source snapshot.",
          }
        : previewPhase === "source_ready"
          ? {
              title:
                preview?.mode === "cloud"
                  ? preview?.message || "Preparing your cloud preview…"
                  : "Source is ready. Preparing preview…",
              subtitle:
                preview?.mode === "cloud"
                  ? cloudPreviewDisconnected
                    ? preview?.message || "Cloud preview is not configured in this environment."
                    : "Source files are visible in the Code tab. Your preview will load here when the environment is ready."
                  : cloudPreviewDisconnected
                    ? "Cloud preview is not connected in this environment."
                    : "Connect a local preview URL when your dev server is running, or open Advanced for diagnostics.",
            }
          : previewPhase === "starting"
            ? {
                title:
                  preview?.mode === "cloud" && preview?.message
                    ? preview.message
                    : "Starting preview environment…",
                subtitle:
                  preview?.mode === "cloud"
                    ? authSessionRefreshing
                      ? "Session refreshing... HAM will retry authenticated preview polling."
                      : "Source files are visible in the Code tab."
                    : activity[0]?.title
                      ? `Latest: ${activity[0].title}`
                      : "Provisioning or waiting for a preview URL.",
              }
            : previewPhase === "error"
              ? {
                  title: "Preview could not start.",
                  subtitle: "",
                }
              : { title: "", subtitle: "" };
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden text-[12px] leading-relaxed text-white/70">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="text-[11px]"
          data-testid="hww-preview-refresh"
          onClick={() => {
            void refresh();
          }}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh status"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="text-[11px]"
          data-testid="hww-preview-open-new-tab"
          disabled={!previewUrl}
          onClick={() => {
            if (previewUrl) window.open(previewUrl, "_blank", "noopener,noreferrer");
          }}
        >
          Open in new tab
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="text-[11px]"
          data-testid="hww-preview-disconnect"
          disabled={!ws || !pid || !preview || preview.status === "not_connected" || disconnectBusy}
          onClick={() => {
            if (!ws || !pid) return;
            setDisconnectBusy(true);
            setError(null);
            void deleteBuilderLocalPreview(ws, pid)
              .then((res) => {
                setPreview(res.preview_status);
                void refreshActivity();
              })
              .catch((e) => {
                setError(e instanceof Error ? e.message : String(e));
              })
              .finally(() => {
                setDisconnectBusy(false);
              });
          }}
        >
          {disconnectBusy ? "Disconnecting…" : "Disconnect preview"}
        </Button>
        <input
          type="text"
          readOnly
          value={previewUrl || ""}
          placeholder="Preview path / URL"
          title="Preview URL when connected"
          data-testid="hww-preview-path-bar"
          className="min-w-[10rem] flex-[1_1_8rem] rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/80 placeholder:text-white/35"
        />
        <div className="flex items-center overflow-hidden rounded-md border border-white/[0.12] bg-black/30">
          <button
            type="button"
            data-testid="hww-preview-viewport-desktop"
            onClick={() => setPreviewViewport("desktop")}
            className={cn(
              "px-2 py-1.5 text-[10px] font-medium uppercase tracking-wide outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30",
              previewViewport === "desktop"
                ? "bg-emerald-500/20 text-emerald-100"
                : "text-white/50 hover:bg-white/[0.06]",
            )}
          >
            Desktop
          </button>
          <button
            type="button"
            data-testid="hww-preview-viewport-mobile"
            onClick={() => setPreviewViewport("mobile")}
            className={cn(
              "px-2 py-1.5 text-[10px] font-medium uppercase tracking-wide outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30",
              previewViewport === "mobile"
                ? "bg-emerald-500/20 text-emerald-100"
                : "text-white/50 hover:bg-white/[0.06]",
            )}
          >
            Mobile
          </button>
        </div>
        <Button
          type="button"
          size="sm"
          variant={visualEditModeActive ? "default" : "secondary"}
          className="text-[11px]"
          data-testid="hww-visual-edit-toggle"
          disabled={!visualEditReady}
          title={
            visualEditReady ? "Capture a visual target from preview." : "Preview must be ready."
          }
          onClick={() => {
            if (!visualEditReady) return;
            setVisualEditNotice(null);
            setVisualEditError(null);
            setVisualEditModeActive((prev) => !prev);
            setVisualEditTarget(null);
          }}
        >
          {visualEditModeActive ? "Exit edit mode" : "Edit"}
        </Button>
      </div>
      {previewPhase !== "ready" ? (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="hww-preview-status-pills">
          <span className="rounded-full border border-white/[0.12] bg-black/35 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/60">
            {previewPhase.replaceAll("_", " ")}
          </span>
        </div>
      ) : null}
      {activity.length > 0 && previewPhase !== "ready" ? (
        <div
          data-testid="hww-preview-activity-compact"
          className="space-y-1.5 rounded-md border border-white/[0.08] bg-black/20 px-2 py-1.5"
        >
          {activity.slice(0, 2).map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-2 text-[11px] text-white/80"
            >
              <span className="min-w-0 truncate">{item.title}</span>
              <span className="shrink-0 text-[10px] uppercase text-white/45">{item.status}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div
        data-testid="hww-preview-canvas"
        className={cn(
          "flex min-h-[280px] flex-1 flex-col overflow-hidden rounded-lg border border-white/[0.1] bg-black/25",
          previewPhase === "ready" && previewViewport === "mobile" ? "items-center" : "",
        )}
      >
        {canRenderPreviewIframe && previewUrl ? (
          <div
            className={cn(
              "flex min-h-0 w-full flex-1 flex-col overflow-hidden p-2",
              previewViewport === "mobile" ? "items-center" : "",
            )}
          >
            <div
              className="relative min-h-0 w-full flex-1 overflow-hidden"
              data-testid="hww-preview-frame-wrap"
            >
              <iframe
                key={`${previewUrl || "preview"}|${preview?.runtime_session_id || ""}|${preview?.preview_endpoint_id || ""}|${preview?.source_snapshot_id || ""}|${iframeReloadNonce}`}
                title="App preview"
                src={previewUrl}
                className={cn(
                  "block h-full min-h-0 w-full rounded-md border border-white/[0.12] bg-black/20",
                  previewViewport === "mobile" ? "max-w-[390px]" : "",
                )}
                data-testid="hww-preview-iframe"
                sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                onLoad={(event) => {
                  const frame = event.currentTarget;
                  try {
                    const doc = frame.contentDocument;
                    const frameText = String(doc?.body?.innerText || "").trim();
                    const contentType = String(doc?.contentType || "").toLowerCase();
                    if (
                      /PREVIEW_PROXY_[A-Z_]+/.test(frameText) ||
                      (contentType.includes("application/json") &&
                        (frameText.includes("PREVIEW_PROXY_") ||
                          frameText.includes("upstream is unavailable")))
                    ) {
                      setIframeProxyError(
                        frameText.slice(0, 240) || "PREVIEW_PROXY_UPSTREAM_UNAVAILABLE",
                      );
                      void refreshPreviewRuntimeStatus({ includeLifecycle: false });
                      return;
                    }
                    setIframeProxyError(null);
                  } catch {
                    // Cross-origin restrictions should not apply for same-origin preview proxy,
                    // but keep this tolerant in case browser sandbox policies vary.
                  }
                }}
              />
              {visualEditModeActive ? (
                <button
                  type="button"
                  className="absolute inset-0 z-20 cursor-crosshair rounded-lg border border-emerald-400/70 bg-emerald-500/5"
                  data-testid="hww-visual-edit-overlay"
                  onClick={(event) => {
                    const rect = event.currentTarget.getBoundingClientRect();
                    const x = Math.max(0, Math.min(event.clientX - rect.left, rect.width));
                    const y = Math.max(0, Math.min(event.clientY - rect.top, rect.height));
                    const target = {
                      x: Number(x.toFixed(2)),
                      y: Number(y.toFixed(2)),
                      width: 1,
                      height: 1,
                      viewport_width: Number(rect.width.toFixed(2)),
                      viewport_height: Number(rect.height.toFixed(2)),
                      device_mode: rect.width <= 640 ? ("mobile" as const) : ("desktop" as const),
                    };
                    setVisualEditTarget(target);
                    setVisualEditNotice(null);
                    setVisualEditError(null);
                    setVisualEditModeActive(false);
                  }}
                  aria-label="Select a preview region"
                  title="Click where you want HAM to change the UI."
                />
              ) : null}
            </div>
          </div>
        ) : (
          <div
            className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-10 text-center"
            data-testid={
              previewPhase === "no_project"
                ? "hww-preview-state-no-project"
                : "hww-preview-placeholder"
            }
          >
            <p
              className="text-[13px] text-white/85"
              data-testid={
                previewPhase === "no_project" || previewPhase === "no_source"
                  ? "hww-preview-tell-ham"
                  : "hww-preview-primary-title"
              }
            >
              {primaryState.title}
            </p>
            {primaryState.subtitle ? (
              <p
                className="max-w-md text-[12px] text-white/55"
                data-testid="hww-preview-primary-subtitle"
              >
                {primaryState.subtitle}
              </p>
            ) : null}
            {previewPhase === "ready" && preview?.mode === "cloud" && previewProxySessionMinting ? (
              <p
                className="max-w-md text-[12px] text-white/60"
                data-testid="hww-preview-auth-pending"
              >
                Preview authentication in progress…
              </p>
            ) : null}
            {previewPhase === "ready" && preview?.mode === "cloud" && previewProxySessionError ? (
              <p
                className="max-w-md text-[12px] text-amber-200/90"
                data-testid="hww-preview-auth-error"
              >
                Preview authentication failed. Refresh status and try again.
              </p>
            ) : null}
            {previewPhase === "error" ? (
              <p
                className="max-w-md text-[12px] text-amber-200/90"
                data-testid="hww-preview-state-error"
              >
                {isProjectNotFoundError(error || "")
                  ? "Project record not found. Refresh workspace or create a new project."
                  : sanitizePreviewFetchError(error || preview?.message || "") ||
                    (error
                      ? sanitizeWorkbenchProjectAccessMessage(String(error))
                      : preview?.message || "Something went wrong. Open Advanced for details.")}
              </p>
            ) : null}
            {previewPhase === "error" ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="text-[11px]"
                data-testid="hww-preview-retry"
                onClick={() => void refresh()}
                disabled={loading}
              >
                Try again
              </Button>
            ) : null}
          </div>
        )}
      </div>
      <details
        className="shrink-0 rounded-md border border-white/[0.08] bg-black/15 p-2"
        data-testid="hww-preview-advanced"
      >
        <summary className="cursor-pointer select-none text-[11px] text-white/60">
          Advanced / Diagnostics
        </summary>
        <div className="mt-3 space-y-3">
          {preview ? (
            <p className="text-[10px] text-white/45" data-testid="hww-preview-api-message">
              API status: {preview.message || "—"}
              {preview.source_snapshot_id && preview.status !== "ready" ? (
                <span> · snapshot linked</span>
              ) : null}
            </p>
          ) : null}
          {previewUrl ? (
            <p className="text-[10px] text-white/45">
              Preview URL:{" "}
              <span data-testid="hww-preview-url-value" className="text-white/60">
                {previewUrl}
              </span>
            </p>
          ) : null}
          {showConnectForm ? (
            <form
              className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (!ws || !pid) return;
                setSubmitBusy(true);
                setError(null);
                void postBuilderLocalPreview(ws, pid, {
                  preview_url: previewUrlInput,
                  source_snapshot_id: preview?.source_snapshot_id || null,
                })
                  .then((res) => {
                    setPreview(res.preview_status);
                    void refreshActivity();
                  })
                  .catch((err) => {
                    setError(err instanceof Error ? err.message : String(err));
                  })
                  .finally(() => {
                    setSubmitBusy(false);
                  });
              }}
              data-testid="hww-preview-connect-form"
            >
              <p className="text-[11px] text-white/60">
                Start your app locally, then paste the local preview URL.
              </p>
              <input
                type="url"
                value={previewUrlInput}
                onChange={(e) => setPreviewUrlInput(e.target.value)}
                placeholder="http://localhost:3000 (local dev only)"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-preview-url-input"
              />
              <Button
                type="submit"
                size="sm"
                variant="secondary"
                className="text-[11px]"
                data-testid="hww-preview-connect-submit"
                disabled={submitBusy}
              >
                {submitBusy ? "Connecting…" : "Connect local preview"}
              </Button>
            </form>
          ) : null}
          <div
            className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
            data-testid="hww-local-run-profile-section"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
              Local run profile
            </p>
            <p className="text-[11px] text-white/60">
              This saves local run instructions only. HAM will not execute commands in this step.
            </p>
            <p className="text-[11px] text-white/55">
              Start the app yourself for now, then connect its local preview URL.
            </p>
            <p className="text-[11px] text-white/65" data-testid="hww-local-run-profile-status">
              Status:{" "}
              {runProfile?.status === "configured"
                ? "Configured"
                : runProfile?.status === "disabled"
                  ? "Disabled"
                  : "Not configured"}
            </p>
            {runProfile?.profile ? (
              <p className="text-[11px] text-white/55" data-testid="hww-local-run-profile-summary">
                {runProfile.profile.display_name}: {runProfile.profile.working_directory} ·{" "}
                {(runProfile.profile.dev_command_argv || []).join(" ")}
              </p>
            ) : null}
            {runProfileError ? (
              <p className="text-amber-200/90" data-testid="hww-local-run-profile-error">
                Could not load local run profile: {runProfileError}
              </p>
            ) : null}
            <form
              className="grid gap-2 md:grid-cols-2"
              data-testid="hww-local-run-profile-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (!ws || !pid) return;
                setRunProfileBusy(true);
                setRunProfileError(null);
                const payload: LocalRunProfilePayload = {
                  display_name: runProfileForm.display_name || "Local run profile",
                  working_directory: runProfileForm.working_directory || ".",
                  dev_command: runProfileForm.dev_command || "",
                  install_command: runProfileForm.install_command || "",
                  build_command: runProfileForm.build_command || "",
                  test_command: runProfileForm.test_command || "",
                  expected_preview_url: runProfileForm.expected_preview_url || "",
                  source_snapshot_id: runProfileForm.source_snapshot_id || null,
                  status: "configured",
                  metadata: runProfileForm.metadata || {},
                };
                void saveBuilderLocalRunProfile(ws, pid, payload)
                  .then((saved) => {
                    setRunProfile(saved);
                    void refreshActivity();
                  })
                  .catch((err) => {
                    setRunProfileError(err instanceof Error ? err.message : String(err));
                  })
                  .finally(() => {
                    setRunProfileBusy(false);
                  });
              }}
            >
              <input
                type="text"
                value={runProfileForm.display_name}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, display_name: e.target.value }))
                }
                placeholder="Local run profile"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-display-name"
              />
              <input
                type="text"
                value={runProfileForm.working_directory}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, working_directory: e.target.value }))
                }
                placeholder="."
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-working-directory"
              />
              <input
                type="text"
                value={runProfileForm.dev_command}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, dev_command: e.target.value }))
                }
                placeholder="npm run dev"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-dev-command"
              />
              <input
                type="text"
                value={runProfileForm.install_command || ""}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, install_command: e.target.value }))
                }
                placeholder="npm install (optional)"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-install-command"
              />
              <input
                type="text"
                value={runProfileForm.build_command || ""}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, build_command: e.target.value }))
                }
                placeholder="npm run build (optional)"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-build-command"
              />
              <input
                type="text"
                value={runProfileForm.test_command || ""}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, test_command: e.target.value }))
                }
                placeholder="npm test (optional)"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                data-testid="hww-local-run-profile-test-command"
              />
              <input
                type="url"
                value={runProfileForm.expected_preview_url || ""}
                onChange={(e) =>
                  setRunProfileForm((prev) => ({ ...prev, expected_preview_url: e.target.value }))
                }
                placeholder="http://localhost:5173 (optional)"
                className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90 md:col-span-2"
                data-testid="hww-local-run-profile-expected-preview-url"
              />
              <div className="flex flex-wrap items-center gap-2 md:col-span-2">
                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  className="text-[11px]"
                  data-testid="hww-local-run-profile-save"
                  disabled={runProfileBusy || !ws || !pid}
                >
                  {runProfileBusy ? "Saving…" : "Save local run profile"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="text-[11px]"
                  data-testid="hww-local-run-profile-clear"
                  disabled={runProfileBusy || !ws || !pid || !runProfile?.profile}
                  onClick={() => {
                    if (!ws || !pid) return;
                    setRunProfileBusy(true);
                    setRunProfileError(null);
                    void deleteBuilderLocalRunProfile(ws, pid)
                      .then((payload) => {
                        setRunProfile(payload);
                        void refreshActivity();
                      })
                      .catch((err) => {
                        setRunProfileError(err instanceof Error ? err.message : String(err));
                      })
                      .finally(() => {
                        setRunProfileBusy(false);
                      });
                  }}
                >
                  Clear profile
                </Button>
                {runProfile?.profile?.expected_preview_url ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="text-[11px]"
                    data-testid="hww-local-run-profile-use-preview-url"
                    onClick={() => {
                      setPreviewUrlInput(
                        runProfile.profile?.expected_preview_url || "http://localhost:3000",
                      );
                    }}
                  >
                    Use as preview URL
                  </Button>
                ) : null}
              </div>
            </form>
          </div>
          <div
            className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
            data-testid="hww-cloud-runtime-section"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
              Cloud preview runtime
            </p>
            <p className="text-[11px] text-white/60">{cloudRuntimePrimaryCopy}</p>
            <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-refresh-copy">
              {cloudRuntimeSecondaryCopy}
            </p>
            <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-status">
              Status: {cloudRuntimeState}
            </p>
            <p
              className="text-[11px] text-white/55"
              data-testid="hww-cloud-runtime-provider-status"
            >
              Provider: {cloudRuntimeProviderStatus.replace("_", " ")}
            </p>
            <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-provider-copy">
              {cloudRuntimeProviderCopy}
            </p>
            {(cloudRuntimeState === "experiment_not_enabled" ||
              cloudRuntimeState === "disabled") && (
              <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-setup-copy">
                Enable HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED or configure cloud_run_poc
                provider.
              </p>
            )}
            {cloudRuntime?.message ? (
              <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-message">
                {cloudRuntime.message}
              </p>
            ) : null}
            {cloudRuntimeLatestJob ? (
              <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-latest-job">
                Latest job: {cloudRuntimeLatestJob.status} / {cloudRuntimeLatestJob.phase}
              </p>
            ) : null}
            {cloudRuntimeLifecycle ? (
              <p className="text-[11px] text-white/55" data-testid="hww-cloud-runtime-lifecycle">
                Lifecycle: {cloudRuntimeLifecycle.phase}
                {cloudRuntimeLifecycle.provider_status
                  ? ` · ${cloudRuntimeLifecycle.provider_status}`
                  : ""}
                {cloudRuntimeLifecycle.logs_summary
                  ? ` · ${cloudRuntimeLifecycle.logs_summary}`
                  : ""}
              </p>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="text-[11px]"
              data-testid="hww-cloud-runtime-refresh-status"
              disabled={!ws || !pid || !cloudRuntimeLatestJob?.id || loading}
              onClick={() => {
                if (!ws || !pid || !cloudRuntimeLatestJob?.id) return;
                setCloudRuntimeError(null);
                void getBuilderCloudRuntimeJobStatus(ws, pid, cloudRuntimeLatestJob.id)
                  .then((payload) => {
                    setCloudRuntimeLifecycle(payload.lifecycle);
                    setPreview(payload.preview_status);
                  })
                  .catch((err) => {
                    setCloudRuntimeError(err instanceof Error ? err.message : String(err));
                  });
              }}
            >
              Refresh cloud runtime status
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="text-[11px]"
              data-testid="hww-cloud-runtime-request-poc"
              disabled={
                !ws || !pid || !cloudRetryEnabled || cloudRuntimeJobBusy || !activeSourceSnapshotId
              }
              onClick={() => {
                if (!ws || !pid || !cloudRetryEnabled || !activeSourceSnapshotId) return;
                setCloudRuntimeJobBusy(true);
                setCloudRuntimeJobError(null);
                setCloudRuntimeJobNotice(null);
                setCloudRuntimeLifecycle({
                  phase: "queued",
                  message: "Retry requested. Provisioning a fresh cloud preview run.",
                  updated_at: new Date().toISOString(),
                  provider_status: null,
                  logs_summary: null,
                });
                void requestBuilderCloudRuntime(ws, pid, {
                  source_snapshot_id: activeSourceSnapshotId,
                  force_new: true,
                  metadata: { request_source: "workbench_preview_retry" },
                })
                  .then((payload) => {
                    setCloudRuntime(payload.cloud_runtime);
                    setPreview((prev) =>
                      prev
                        ? {
                            ...prev,
                            mode: "cloud",
                            status: "building",
                            health: "unknown",
                            message: "Retry requested. Provisioning cloud preview.",
                            source_snapshot_id: activeSourceSnapshotId,
                          }
                        : prev,
                    );
                    setCloudRuntimeJobNotice(
                      "Retry started. HAM is provisioning a fresh cloud runtime preview.",
                    );
                    void refresh();
                    void refreshActivity();
                    void refreshWorkers();
                  })
                  .catch((err) => {
                    setCloudRuntimeJobError(err instanceof Error ? err.message : String(err));
                  })
                  .finally(() => {
                    setCloudRuntimeJobBusy(false);
                  });
              }}
            >
              {cloudRuntimeJobBusy ? "Retrying…" : "Retry preview"}
            </Button>
            {!activeSourceSnapshotId ? (
              <p
                className="text-[11px] text-white/55"
                data-testid="hww-cloud-runtime-source-required-copy"
              >
                Add a project source ZIP or folder before retrying cloud preview.
              </p>
            ) : null}
            {cloudPreviewHealthy ? (
              <p
                className="text-[11px] text-white/55"
                data-testid="hww-cloud-runtime-retry-healthy-copy"
              >
                Preview is already healthy. Use Refresh status for polling-only checks.
              </p>
            ) : null}
            {!cloudRuntimeRequestEnabled ? (
              <p
                className="text-[11px] text-white/55"
                data-testid="hww-cloud-runtime-disabled-copy"
              >
                {cloudRuntimeState === "experiment_not_enabled"
                  ? "Cloud runtime experiments are not enabled in this environment."
                  : cloudRuntimeState === "config_missing"
                    ? "Cloud runtime provider needs configuration before it can run."
                    : "Cloud runtime experiments are not enabled."}
              </p>
            ) : null}
            {cloudRuntimeJobError ? (
              <p className="text-amber-200/90" data-testid="hww-cloud-runtime-job-error">
                Could not retry cloud preview: {cloudRuntimeJobError}
              </p>
            ) : null}
            {cloudRuntimeJobNotice ? (
              <p className="text-emerald-200/90" data-testid="hww-cloud-runtime-job-notice">
                {cloudRuntimeJobNotice}
              </p>
            ) : null}
            {cloudRuntimeError ? (
              <p className="text-amber-200/90" data-testid="hww-cloud-runtime-error">
                {isProjectNotFoundError(cloudRuntimeError)
                  ? "Project record not found. Refresh workspace or create a new project."
                  : sanitizePreviewFetchError(cloudRuntimeError) || cloudRuntimeError}
              </p>
            ) : null}
          </div>
          <div
            className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
            data-testid="hww-worker-capability-section"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
              Optional coding workers
            </p>
            <p className="text-[11px] text-white/60">{optionalWorkerIntroCopy}</p>
            {workersError ? (
              <p className="text-amber-200/90" data-testid="hww-worker-capability-error">
                Could not load worker capabilities: {workersError}
              </p>
            ) : null}
            {!workersError && workers.length === 0 ? (
              <p className="text-white/55" data-testid="hww-worker-capability-empty">
                No worker capability records available yet.
              </p>
            ) : null}
            {!workersError && workers.length > 0 ? (
              <ul className="space-y-1.5" data-testid="hww-worker-capability-list">
                {workers.map((worker) => {
                  const statusTone =
                    worker.status === "available"
                      ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/10"
                      : worker.status === "available_mock" || worker.status === "available_poc"
                        ? "text-sky-200 border-sky-400/30 bg-sky-500/10"
                        : worker.status === "needs_connection"
                          ? "text-amber-200 border-amber-400/30 bg-amber-500/10"
                          : worker.status === "disabled"
                            ? "text-white/60 border-white/[0.16] bg-white/[0.06]"
                            : "text-rose-200 border-rose-400/30 bg-rose-500/10";
                  const workerDetailCopy =
                    worker.worker_kind === "cursor_local_sdk" && worker.status === "disabled"
                      ? "Off — only needed for local Cursor execution."
                      : worker.worker_kind === "claude_agent" &&
                          worker.status === "needs_connection"
                        ? "Not connected — optional external worker."
                        : worker.environment_fit;
                  return (
                    <li
                      key={worker.worker_kind}
                      className="rounded-md border border-white/[0.08] bg-black/20 px-2 py-1.5"
                      data-testid="hww-worker-capability-item"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-[11px] text-white/85">{worker.display_name}</p>
                        <span
                          className={cn(
                            "rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
                            statusTone,
                          )}
                        >
                          {worker.status.replace("_", " ")}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-white/50">{workerDetailCopy}</p>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
          <div
            className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
            data-testid="hww-visual-edit-section"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
              Edit mode
            </p>
            <p className="text-[11px] text-white/60">
              Capture-only flow. This saves a visual edit request contract and does not execute
              edits.
            </p>
            {!visualEditReady ? (
              <p className="text-[11px] text-white/55" data-testid="hww-visual-edit-disabled-copy">
                Preview must be ready before entering Edit Mode.
              </p>
            ) : (
              <p className="text-[11px] text-white/55" data-testid="hww-visual-edit-ready-copy">
                Click `Edit`, then click a target in preview to open the request panel.
              </p>
            )}
            {visualEditModeActive ? (
              <p
                className="text-[11px] text-emerald-200/90"
                data-testid="hww-visual-edit-mode-active-copy"
              >
                Edit Mode active. Click the preview to capture a target.
              </p>
            ) : null}
            {visualEditTarget ? (
              <form
                className="space-y-2 rounded-md border border-white/[0.1] bg-black/30 p-2"
                data-testid="hww-visual-edit-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!visualEditReady || !ws || !pid || !visualEditTarget) {
                    return;
                  }
                  setVisualEditBusy(true);
                  setVisualEditError(null);
                  setVisualEditNotice(null);
                  const payload: CreateBuilderVisualEditRequestPayload = {
                    instruction: visualEditInstruction,
                    route: visualEditRoute || null,
                    preview_url_kind: previewUrlKind,
                    target: visualEditTarget,
                    selector_hints: visualEditSelectorHints
                      .split(",")
                      .map((value) => value.trim())
                      .filter((value) => value.length > 0),
                    bbox: {
                      x: visualEditTarget.x,
                      y: visualEditTarget.y,
                      width: visualEditTarget.width,
                      height: visualEditTarget.height,
                    },
                    runtime_session_id: preview?.runtime_session_id || null,
                    preview_endpoint_id: preview?.preview_endpoint_id || null,
                    source_snapshot_id: preview?.source_snapshot_id || null,
                    status: "queued",
                  };
                  void createBuilderVisualEditRequest(ws, pid, payload)
                    .then(() => {
                      setVisualEditInstruction("");
                      setVisualEditSelectorHints("");
                      setVisualEditTarget(null);
                      setVisualEditNotice(
                        "Edit request saved. Agent execution is not connected yet.",
                      );
                      void refreshVisualEditRequests();
                      void refreshActivity();
                    })
                    .catch((err) => {
                      setVisualEditError(err instanceof Error ? err.message : String(err));
                    })
                    .finally(() => {
                      setVisualEditBusy(false);
                    });
                }}
              >
                <p className="text-[11px] text-white/60">What should HAM change here?</p>
                <p
                  className="text-[11px] text-white/55"
                  data-testid="hww-visual-edit-target-summary"
                >
                  Target: x {visualEditTarget.x}, y {visualEditTarget.y}, viewport{" "}
                  {visualEditTarget.viewport_width} x {visualEditTarget.viewport_height},{" "}
                  {visualEditTarget.device_mode}
                </p>
                <textarea
                  value={visualEditInstruction}
                  onChange={(e) => setVisualEditInstruction(e.target.value)}
                  rows={3}
                  placeholder="Describe the visual change you want."
                  className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                  data-testid="hww-visual-edit-instruction"
                />
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    type="text"
                    value={visualEditRoute}
                    onChange={(e) => setVisualEditRoute(e.target.value)}
                    placeholder="/"
                    className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                    data-testid="hww-visual-edit-route"
                  />
                  <input
                    type="text"
                    value={visualEditSelectorHints}
                    onChange={(e) => setVisualEditSelectorHints(e.target.value)}
                    placeholder="Selector hints (optional, comma-separated)"
                    className="w-full rounded-md border border-white/[0.12] bg-black/40 px-2 py-1.5 text-[11px] text-white/90"
                    data-testid="hww-visual-edit-selector-hints"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="text-[11px]"
                    data-testid="hww-visual-edit-cancel"
                    onClick={() => {
                      setVisualEditTarget(null);
                      setVisualEditInstruction("");
                      setVisualEditModeActive(false);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    variant="secondary"
                    className="text-[11px]"
                    data-testid="hww-visual-edit-submit"
                    disabled={visualEditBusy || !visualEditInstruction.trim()}
                  >
                    {visualEditBusy ? "Saving request…" : "Save edit request"}
                  </Button>
                </div>
              </form>
            ) : (
              <p className="text-[11px] text-white/50" data-testid="hww-visual-edit-target-empty">
                No target selected yet.
              </p>
            )}
            {visualEditError ? (
              <p className="text-amber-200/90" data-testid="hww-visual-edit-error">
                Could not save visual edit request: {visualEditError}
              </p>
            ) : null}
            {visualEditNotice ? (
              <p className="text-emerald-200/90" data-testid="hww-visual-edit-success">
                {visualEditNotice}
              </p>
            ) : null}
            <p className="text-[11px] text-white/45" data-testid="hww-visual-edit-count">
              Saved requests: {visualEditRequests.length}
            </p>
          </div>
          <div
            className="space-y-2 rounded-lg border border-white/[0.08] bg-black/25 p-3"
            data-testid="hww-preview-activity-section"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/45">
              Builder activity
            </p>
            <p className="text-[11px] text-white/55" data-testid="hww-preview-activity-stream-copy">
              Activity updates live when connected. Build log streaming is not connected yet.
            </p>
            <p
              className="text-[11px] text-white/55"
              data-testid="hww-preview-activity-stream-state"
            >
              Live status:{" "}
              {activityStreamState === "live"
                ? "Live"
                : activityStreamState === "reconnecting"
                  ? "Reconnecting"
                  : "Offline / refresh manually"}
            </p>
            {activityError ? (
              <p className="text-amber-200/90" data-testid="hww-preview-activity-error">
                Could not load activity: {sanitizeWorkbenchProjectAccessMessage(activityError)}
              </p>
            ) : null}
            {!activityError && activity.length === 0 ? (
              <p className="text-white/55" data-testid="hww-preview-activity-empty">
                No builder activity yet. Source imports and preview changes will appear here.
              </p>
            ) : null}
            {!activityError && activity.length > 0 ? (
              <ul className="space-y-2" data-testid="hww-preview-activity-list">
                {activity.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-md border border-white/[0.07] bg-black/20 px-2 py-1.5"
                    data-testid="hww-preview-activity-item"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={cn(
                            "h-2 w-2 shrink-0 rounded-full",
                            item.status === "failed" || item.status === "error"
                              ? "bg-rose-400"
                              : item.status === "ready" || item.status === "succeeded"
                                ? "bg-emerald-400"
                                : "bg-amber-300",
                          )}
                        />
                        <span className="truncate text-[11px] text-white/85">{item.title}</span>
                      </div>
                      <span className="rounded border border-white/[0.12] px-1.5 py-0.5 text-[10px] uppercase text-white/65">
                        {item.status}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-white/55">{item.message}</p>
                    <p className="mt-1 text-[10px] text-white/40">
                      {item.timestamp}
                      {item.snapshot_id ? ` · snapshot ${item.snapshot_id}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      </details>
    </div>
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

type WorkbenchCodePanelProps = {
  workspaceId?: string | null;
  projectId?: string | null;
  sourceRefreshKey: number;
  onAddProjectSource: () => void;
  onSnapshotUpdated: () => void;
};

function WorkbenchCodePanel({
  workspaceId = null,
  projectId = null,
  sourceRefreshKey,
  onAddProjectSource,
  onSnapshotUpdated,
}: WorkbenchCodePanelProps) {
  const [snapshots, setSnapshots] = React.useState<BuilderSourceSnapshotRecord[]>([]);
  const [sources, setSources] = React.useState<BuilderProjectSourceRecord[]>([]);
  const [files, setFiles] = React.useState<
    Array<{
      path: string;
      size_bytes: number;
      type?: "file" | "directory";
      language?: string | null;
    }>
  >([]);
  const [activeSnapshotId, setActiveSnapshotId] = React.useState<string | null>(null);
  const [selectedPath, setSelectedPath] = React.useState<string | null>(null);
  const [content, setContent] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [fileChatMessage, setFileChatMessage] = React.useState("");
  const [fileChatMode, setFileChatMode] = React.useState<"edit" | "explain">("edit");
  const [fileChatBusy, setFileChatBusy] = React.useState(false);
  const [fileChatResult, setFileChatResult] = React.useState<string | null>(null);
  const [changedFiles, setChangedFiles] = React.useState<string[]>([]);

  const loadSnapshotFiles = React.useCallback(
    async (ws: string, pid: string, snapId: string) => {
      const manifest = await listBuilderSnapshotFiles(ws, pid, snapId);
      const rows = (manifest.files || []).map((f) => ({
        path: f.path,
        size_bytes: f.size_bytes,
        type: f.type ?? (f.is_dir ? "directory" : "file"),
        language: f.language ?? null,
      }));
      const fileRows = rows.filter((f) => f.type !== "directory");
      setFiles(rows);
      const nextPath =
        selectedPath && fileRows.some((f) => f.path === selectedPath)
          ? selectedPath
          : (fileRows[0]?.path ?? null);
      setSelectedPath(nextPath);
      setActiveSnapshotId(snapId);
      if (!nextPath) {
        setContent(null);
        return;
      }
      const body = await getBuilderSnapshotFileContent(ws, pid, snapId, nextPath);
      setContent(body.content);
    },
    [selectedPath],
  );

  React.useEffect(() => {
    const ws = workspaceId?.trim() || "";
    const pid = projectId?.trim() || "";
    if (!ws || !pid) {
      setSnapshots([]);
      setSources([]);
      setFiles([]);
      setActiveSnapshotId(null);
      setSelectedPath(null);
      setContent(null);
      setErr(null);
      setFileChatResult(null);
      setChangedFiles([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void (async () => {
      try {
        const [sn, src] = await Promise.all([
          listBuilderSourceSnapshots(ws, pid),
          listBuilderProjectSources(ws, pid),
        ]);
        if (cancelled) return;
        const snaps = sn.source_snapshots || [];
        setSnapshots(snaps);
        setSources(src.sources || []);
        const active = (src.sources || []).find((s) => s.active_snapshot_id)?.active_snapshot_id;
        const snapId = active || (snaps[0]?.id ?? null);
        if (!snapId) {
          setFiles([]);
          setActiveSnapshotId(null);
          setSelectedPath(null);
          setContent(null);
          return;
        }
        await loadSnapshotFiles(ws, pid, snapId);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : String(e));
          setFiles([]);
          setActiveSnapshotId(null);
          setContent(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, projectId, sourceRefreshKey, loadSnapshotFiles]);

  const ws = workspaceId?.trim() || "";
  const pid = projectId?.trim() || "";
  const activeSnapId =
    activeSnapshotId ||
    sources.find((s) => s.active_snapshot_id)?.active_snapshot_id ||
    snapshots[0]?.id ||
    null;

  React.useEffect(() => {
    if (!ws || !pid || !activeSnapId || !selectedPath) {
      setContent(null);
      return;
    }
    let cancelled = false;
    void getBuilderSnapshotFileContent(ws, pid, activeSnapId, selectedPath)
      .then((b) => {
        if (!cancelled) setContent(b.content);
      })
      .catch(() => {
        if (!cancelled) setContent(null);
      });
    return () => {
      cancelled = true;
    };
  }, [ws, pid, activeSnapId, selectedPath]);

  const hasSnapshot = Boolean(activeSnapId);
  const handleFileChat = React.useCallback(async () => {
    if (!ws || !pid || !activeSnapId || !selectedPath) return;
    const prompt = fileChatMessage.trim();
    if (!prompt) return;
    setFileChatBusy(true);
    setFileChatResult(null);
    setChangedFiles([]);
    try {
      const out = await postBuilderSnapshotFileChat(ws, pid, activeSnapId, {
        path: selectedPath,
        user_message: prompt,
        mode: fileChatMode,
      });
      setFileChatResult(out.assistant_message);
      setChangedFiles(out.changed_files || []);
      if (out.new_snapshot_id) {
        await loadSnapshotFiles(ws, pid, out.new_snapshot_id);
        onSnapshotUpdated();
      }
    } catch (e) {
      setFileChatResult(e instanceof Error ? e.message : String(e));
    } finally {
      setFileChatBusy(false);
    }
  }, [
    ws,
    pid,
    activeSnapId,
    selectedPath,
    fileChatMessage,
    fileChatMode,
    loadSnapshotFiles,
    onSnapshotUpdated,
  ]);

  return (
    <MutedPanel>
      <div className="flex flex-wrap items-center gap-2">
        <AddProjectSourceButton onClick={onAddProjectSource} />
      </div>
      {!ws || !pid ? (
        <p className="text-white/55">Select a workspace and project to browse generated source.</p>
      ) : null}
      {loading ? <p className="text-white/45">Loading source files…</p> : null}
      {err ? (
        <p className="text-amber-200/90" data-testid="hww-code-load-error">
          {err}
        </p>
      ) : null}
      {!hasSnapshot && ws && pid && !loading && !err ? (
        <p className="text-white/55" data-testid="hww-code-empty-state">
          No files yet. Ask HAM to build something.
        </p>
      ) : null}
      {hasSnapshot ? (
        <div className="grid min-h-[260px] gap-2 rounded-lg border border-white/[0.08] bg-black/25 md:grid-cols-[minmax(180px,1fr)_minmax(0,2fr)]">
          <div className="border-b border-white/[0.06] p-2 md:border-b-0 md:border-r md:border-white/[0.06]">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Files</p>
            <ul className="mt-2 max-h-[320px] space-y-1 overflow-y-auto text-[11px]">
              {files.map((f) => (
                <li key={f.path}>
                  {f.type === "directory" ? (
                    <p className="truncate rounded px-1 py-0.5 text-white/40">{f.path}</p>
                  ) : (
                    <button
                      type="button"
                      data-testid="hww-code-file-row"
                      className={cn(
                        "w-full truncate rounded px-1 py-0.5 text-left",
                        selectedPath === f.path ? "bg-emerald-500/15 text-white" : "text-white/70",
                      )}
                      onClick={() => setSelectedPath(f.path)}
                    >
                      {f.path}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
          <div className="p-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
              Viewer
            </p>
            {selectedPath ? (
              <>
                <p
                  className="mt-1 text-[10px] text-white/50"
                  data-testid="hww-code-active-file-path"
                >
                  {selectedPath}
                </p>
                <pre
                  className="mt-2 max-h-[250px] overflow-auto whitespace-pre-wrap rounded border border-white/[0.08] bg-black/40 p-2 text-[11px] text-white/85"
                  data-testid="hww-code-file-content"
                >
                  {content ?? "…"}
                </pre>
                <div className="mt-3 space-y-2 rounded border border-white/[0.08] bg-black/35 p-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
                    Chat with file
                  </p>
                  <p className="text-[11px] text-white/55">
                    Scoped to <span className="text-white/75">{selectedPath}</span>
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={fileChatMode === "edit" ? "default" : "secondary"}
                      className="h-7 text-[10px]"
                      onClick={() => setFileChatMode("edit")}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={fileChatMode === "explain" ? "default" : "secondary"}
                      className="h-7 text-[10px]"
                      onClick={() => setFileChatMode("explain")}
                    >
                      Explain
                    </Button>
                  </div>
                  <textarea
                    value={fileChatMessage}
                    onChange={(event) => setFileChatMessage(event.target.value)}
                    placeholder={
                      fileChatMode === "edit"
                        ? "Describe the file edit for this file..."
                        : "Ask what this file does..."
                    }
                    className="min-h-[76px] w-full rounded border border-white/[0.1] bg-black/40 px-2 py-1.5 text-[11px] text-white/90 outline-none focus:border-emerald-400/40"
                    data-testid="hww-code-file-chat-input"
                  />
                  <Button
                    type="button"
                    size="sm"
                    className="h-7 text-[10px]"
                    data-testid="hww-code-file-chat-submit"
                    disabled={fileChatBusy || !fileChatMessage.trim()}
                    onClick={() => void handleFileChat()}
                  >
                    {fileChatBusy ? "Working..." : "Chat with file"}
                  </Button>
                  {fileChatResult ? (
                    <p
                      className="rounded border border-white/[0.08] bg-black/40 px-2 py-1.5 text-[11px] text-white/75"
                      data-testid="hww-code-file-chat-result"
                    >
                      {fileChatResult}
                    </p>
                  ) : null}
                  {changedFiles.length > 0 ? (
                    <p
                      className="text-[10px] text-emerald-200/85"
                      data-testid="hww-code-file-chat-changed"
                    >
                      Changed: {changedFiles.join(", ")}
                    </p>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="mt-2 text-white/45">Select a file.</p>
            )}
          </div>
        </div>
      ) : null}
      {activeSnapId ? (
        <p className="text-[10px] text-white/40" data-testid="hww-code-active-snapshot">
          Project `{pid}` · Snapshot `{activeSnapId}`
        </p>
      ) : null}
      <p className="text-white/55">
        Use <span className="font-medium text-white/65">Add project source</span> for a full ZIP
        when you already have a project.{" "}
        <Link
          to="/workspace/files"
          className="font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
        >
          Files
        </Link>{" "}
        lists chat attachments separately.
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
      <p className="text-[11px] text-white/60" data-testid="hww-project-source-secondary-copy">
        Most users can simply ask HAM to build. Use this tab when you already have files or a ZIP.
      </p>
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
