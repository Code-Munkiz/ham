import * as React from "react";
import {
  ChevronRight,
  File,
  FilePlus,
  Folder,
  FolderPlus,
  Pencil,
  RefreshCw,
  Save,
  Search,
  Upload,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LocalMachineConnectCta } from "../../components/LocalMachineConnectCta";
import {
  fetchLocalWorkspaceHealth,
  isLocalRuntimeConfigured,
  type LocalRuntimeHealthPayload,
} from "../../adapters/localRuntime";
import { workspaceFileAdapter, type FileBridgeState, type WorkspaceFileEntry } from "../../adapters/filesAdapter";

const ROOT_LABEL = "Workspace";

function normalizePath(p: string) {
  return p.replace(/\\/g, "/");
}

function getParentPath(pathValue: string) {
  const normalized = normalizePath(pathValue);
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  return parts.slice(0, -1).join("/");
}

function filterTree(entries: WorkspaceFileEntry[], term: string): WorkspaceFileEntry[] {
  if (!term.trim()) return entries;
  const lower = term.toLowerCase();
  const walk = (e: WorkspaceFileEntry): WorkspaceFileEntry | null => {
    if (e.type === "file") {
      return e.name.toLowerCase().includes(lower) ? e : null;
    }
    const ch = e.children;
    if (ch == null) {
      return e.name.toLowerCase().includes(lower) ? e : null;
    }
    const children = ch.map(walk).filter((c): c is WorkspaceFileEntry => c !== null);
    if (e.name.toLowerCase().includes(lower) || children.length > 0) {
      return { ...e, children };
    }
    return null;
  };
  return entries.map(walk).filter((e): e is WorkspaceFileEntry => e !== null);
}

function mergeAtPath(
  list: WorkspaceFileEntry[],
  targetPath: string,
  newChildren: WorkspaceFileEntry[],
): WorkspaceFileEntry[] {
  return list.map((e) => {
    if (e.path === targetPath && e.type === "folder") {
      return { ...e, children: newChildren };
    }
    if (Array.isArray(e.children)) {
      return { ...e, children: mergeAtPath(e.children, targetPath, newChildren) };
    }
    return e;
  });
}

type PromptState =
  | { mode: "rename" | "new-file" | "new-folder"; targetPath: string; defaultValue?: string }
  | null;

type Ctx = { x: number; y: number; entry: WorkspaceFileEntry } | null;

type SaveUiState = "idle" | "saving" | "saved" | "error";

export function WorkspaceFilesScreen() {
  const [collapsed, setCollapsed] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);
  const [entries, setEntries] = React.useState<WorkspaceFileEntry[]>([]);
  const [bridge, setBridge] = React.useState<FileBridgeState>({ status: "pending", detail: "Runtime bridge pending" });
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set());
  const [contextMenu, setContextMenu] = React.useState<Ctx>(null);
  const [promptState, setPromptState] = React.useState<PromptState>(null);
  const [promptValue, setPromptValue] = React.useState("");
  const [previewPath, setPreviewPath] = React.useState<string | null>(null);
  const [editorValue, setEditorValue] = React.useState(
    `// Files workspace
// Use the file tree to browse. Runtime bridge may be pending for server-backed storage.

function ready() {
  return true;
}
`,
  );
  const [readPath, setReadPath] = React.useState<string | null>(null);
  const [readBridge, setReadBridge] = React.useState<FileBridgeState | null>(null);
  const [saveState, setSaveState] = React.useState<SaveUiState>("idle");
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [fsHealth, setFsHealth] = React.useState<LocalRuntimeHealthPayload | null>(null);
  const [loadingFolder, setLoadingFolder] = React.useState<string | null>(null);
  const uploadInputRef = React.useRef<HTMLInputElement | null>(null);
  const uploadTargetRef = React.useRef("");
  const saveFlashTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const { entries: next, bridge: b } = await workspaceFileAdapter.list();
    setEntries(next);
    setBridge(b);
    if (b.status === "ready" && isLocalRuntimeConfigured()) {
      setFsHealth(await fetchLocalWorkspaceHealth());
    } else {
      setFsHealth(null);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    const onChanged = () => void refresh();
    window.addEventListener("hww-local-runtime-changed", onChanged);
    return () => window.removeEventListener("hww-local-runtime-changed", onChanged);
  }, [refresh]);

  React.useEffect(
    () => () => {
      if (saveFlashTimer.current) clearTimeout(saveFlashTimer.current);
    },
    [],
  );

  React.useEffect(() => {
    const m = window.matchMedia("(max-width: 767px)");
    const u = () => setIsMobile(m.matches);
    u();
    m.addEventListener("change", u);
    return () => m.removeEventListener("change", u);
  }, []);

  React.useEffect(() => {
    if (isMobile) setCollapsed(true);
  }, [isMobile]);

  React.useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close);
    };
  }, [contextMenu]);

  const filtered = React.useMemo(() => filterTree(entries, search), [entries, search]);
  const searchActive = search.trim().length > 0;
  const disconnected =
    bridge.status === "pending" && bridge.localCode === "unconfigured" && !loading;
  const localError =
    bridge.status === "pending" &&
    (bridge.localCode === "unreachable" || bridge.localCode === "wrong_api") &&
    !loading;
  const noEnvRoot =
    !loading && bridge.status === "ready" && Boolean(fsHealth) && fsHealth?.workspaceRootConfigured === false;

  const openPrompt = (state: NonNullable<PromptState>) => {
    setPromptState(state);
    setPromptValue(state.defaultValue || "");
  };

  const handlePromptSubmit = async () => {
    if (!promptState) return;
    const value = promptValue.trim();
    if (!value) return;
    if (promptState.mode === "rename") {
      const parent = getParentPath(promptState.targetPath);
      const nextPath = parent ? `${parent}/${value}` : value;
      const r = await workspaceFileAdapter.postJson({
        action: "rename",
        from: promptState.targetPath,
        to: nextPath,
      });
      if (!r.ok) {
        setBridge(r.bridge);
      }
    } else if (promptState.mode === "new-folder") {
      const nextPath = promptState.targetPath ? `${promptState.targetPath}/${value}` : value;
      const r = await workspaceFileAdapter.postJson({ action: "mkdir", path: nextPath });
      if (!r.ok) {
        setBridge(r.bridge);
      }
    } else {
      const nextPath = promptState.targetPath ? `${promptState.targetPath}/${value}` : value;
      const r = await workspaceFileAdapter.postJson({ action: "write", path: nextPath, content: "" });
      if (!r.ok) {
        setBridge(r.bridge);
      }
    }
    setPromptState(null);
    setPromptValue("");
    await refresh();
  };

  const handleDelete = async (entry: WorkspaceFileEntry) => {
    if (!window.confirm(`Move ${entry.name} to trash?`)) return;
    const r = await workspaceFileAdapter.postJson({ action: "delete", path: entry.path });
    if (!r.ok) {
      setBridge(r.bridge);
    }
    if (readPath === entry.path) {
      setReadPath(null);
      setPreviewPath(null);
    }
    await refresh();
  };

  const handleDownload = (entry: WorkspaceFileEntry) => {
    const url = workspaceFileAdapter.buildDownloadUrl(entry.path);
    if (!url) {
      window.alert("Local runtime is not connected. Set the URL in Workspace → Settings → Connection.");
      return;
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = entry.name;
    a.click();
  };

  const handleUploadClick = (targetPath: string) => {
    uploadTargetRef.current = targetPath;
    uploadInputRef.current?.click();
  };

  const handleUploadChange: React.ChangeEventHandler<HTMLInputElement> = async (event) => {
    const fileList = event.target.files;
    if (!fileList?.length) return;
    for (const file of Array.from(fileList)) {
      const form = new FormData();
      form.append("path", uploadTargetRef.current || "");
      form.append("file", file);
      const r = await workspaceFileAdapter.postFormData(form);
      if (!r.ok) {
        setBridge(r.bridge);
      }
    }
    event.target.value = "";
    await refresh();
  };

  const handleFolderClick = async (entry: WorkspaceFileEntry) => {
    if (entry.type !== "folder") return;
    if (searchActive) return;
    if (expanded.has(entry.path)) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.delete(entry.path);
        return next;
      });
      return;
    }
    if (entry.children == null) {
      setLoadingFolder(entry.path);
      const { entries: sub, bridge: b } = await workspaceFileAdapter.listPath(entry.path);
      setLoadingFolder(null);
      setBridge(b);
      if (b.status === "ready") {
        setEntries((prev) => mergeAtPath(prev, entry.path, sub));
        setFsHealth(await fetchLocalWorkspaceHealth());
        setExpanded((prev) => new Set(prev).add(entry.path));
      }
      return;
    }
    setExpanded((prev) => new Set(prev).add(entry.path));
  };

  const loadFile = async (path: string) => {
    setReadPath(path);
    setReadBridge(null);
    setSaveState("idle");
    setSaveError(null);
    const { text, bridge: b } = await workspaceFileAdapter.readText(path);
    setReadBridge(b);
    if (text != null) {
      setEditorValue(text);
    }
  };

  const handleSave = async () => {
    if (!readPath) return;
    if (saveFlashTimer.current) {
      clearTimeout(saveFlashTimer.current);
      saveFlashTimer.current = null;
    }
    setSaveState("saving");
    setSaveError(null);
    const r = await workspaceFileAdapter.postJson({
      action: "write",
      path: readPath,
      content: editorValue,
    });
    if (!r.ok) {
      setSaveState("error");
      setSaveError(r.error || "Save failed");
      if (r.bridge) setBridge(r.bridge);
      return;
    }
    setSaveState("saved");
    saveFlashTimer.current = setTimeout(() => {
      setSaveState("idle");
      saveFlashTimer.current = null;
    }, 2200);
    await refresh();
  };

  const handleFileClick = async (entry: WorkspaceFileEntry) => {
    if (entry.type === "folder") {
      await handleFolderClick(entry);
      return;
    }
    const ref = `See file: workspace/${normalizePath(entry.path)}`;
    setEditorValue((p) => `${p}\n${ref}\n`);
    setPreviewPath(entry.path);
    await loadFile(entry.path);
  };

  const renderEntry = (entry: WorkspaceFileEntry, depth: number): React.ReactNode => {
    const isEx = searchActive || expanded.has(entry.path);
    const padding = 10 + depth * 12;
    return (
      <div key={entry.path}>
        <button
          type="button"
          onClick={() => {
            void handleFileClick(entry);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            setContextMenu({ x: e.clientX, y: e.clientY, entry });
          }}
          className="group flex w-full items-center gap-1.5 rounded-md py-1 text-left text-[13px] text-[#c8d4e0] transition hover:bg-white/[0.06]"
          style={{ paddingLeft: padding }}
        >
          {entry.type === "folder" ? (
            <ChevronRight
              className={cn("h-3.5 w-3.5 shrink-0 text-white/50 transition-transform", isEx && "rotate-90")}
            />
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          {entry.type === "folder" ? <Folder className="h-4 w-4 shrink-0 text-[#7eb8ff]/90" /> : null}
          {entry.type === "file" ? <File className="h-4 w-4 shrink-0 text-white/55" /> : null}
          <span className="truncate">{entry.name}</span>
        </button>
        {entry.type === "folder" && isEx && loadingFolder === entry.path ? (
          <p className="pl-[1.5rem] text-[11px] text-white/40" style={{ paddingLeft: 10 + (depth + 1) * 12 }}>
            Loading…
          </p>
        ) : null}
        {entry.type === "folder" && isEx && Array.isArray(entry.children)
          ? entry.children.map((c) => renderEntry(c, depth + 1))
          : null}
      </div>
    );
  };

  const breadcrumb = readPath
    ? normalizePath(readPath).split("/").filter(Boolean)
    : previewPath
      ? normalizePath(previewPath).split("/").filter(Boolean)
      : [];

  return (
    <div className="hww-files flex h-full min-h-0 flex-col overflow-hidden text-[#e2eaf3]">
      <div className="flex h-full min-h-0 flex-1 overflow-hidden">
        <aside
          className={cn(
            "hww-files-explorer border-r border-[color:var(--ham-workspace-line)] bg-[#050d12]/90 transition-[width,opacity] duration-200",
            collapsed ? "w-0 overflow-hidden border-0 p-0 opacity-0" : "w-[min(100%,280px)] shrink-0 opacity-100",
          )}
        >
          <div className="flex h-11 items-center justify-between border-b border-[color:var(--ham-workspace-line)] px-2.5">
            <span className="text-[13px] font-semibold text-white/90">{ROOT_LABEL}</span>
            <div className="flex items-center gap-0.5">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/60"
                onClick={() => {
                  void refresh();
                }}
                title="Refresh"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/60"
                onClick={() => handleUploadClick("")}
                title="Upload"
              >
                <Upload className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-white/60"
                onClick={() => openPrompt({ mode: "new-file", targetPath: "" })}
                title="New file"
              >
                <FilePlus className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="p-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/35"
                aria-hidden
              />
              <input
                id="hww-files-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search files"
                className="hww-input w-full rounded-md text-[12px]"
              />
            </div>
          </div>
          <div className="hww-scroll min-h-0 flex-1 overflow-y-auto px-1 pb-3">
            {loading ? (
              <p className="px-2 py-1 text-[11px] text-white/45">Loading…</p>
            ) : disconnected ? (
              <div className="px-1.5 py-2">
                <p className="px-1 text-[12px] font-medium text-white/80">Connect to browse local files</p>
                <p className="mt-1 px-1 text-[11px] leading-relaxed text-white/45">
                  Files and Terminal use the HAM process on this computer, not Cloud Run.
                </p>
                <div className="mt-2">
                  <LocalMachineConnectCta
                    variant="compact"
                    onSuccess={() => void refresh()}
                    className="!p-3"
                    showOpenSettings
                    showOpenFiles={false}
                  />
                </div>
              </div>
            ) : localError ? (
              <div className="px-1.5 py-2">
                <p className="px-1 text-[12px] text-amber-200/85">Could not use the saved local URL. Try again below.</p>
                <p className="mt-1 px-1 break-words text-[10px] text-amber-200/60" title={bridge.detail}>
                  {bridge.detail}
                </p>
                <div className="mt-2">
                  <LocalMachineConnectCta
                    variant="compact"
                    onSuccess={() => void refresh()}
                    className="!p-3"
                    showOpenSettings
                    showOpenFiles={false}
                  />
                </div>
              </div>
            ) : !entries.length && bridge.status === "pending" ? (
              <p className="px-2 py-2 text-[11px] leading-relaxed text-white/45">No file tree yet. Check the local API.</p>
            ) : !entries.length && bridge.status === "ready" ? (
              <div className="px-2 py-4 text-center text-[12px] text-white/50">
                <p className="mb-2">Workspace is empty</p>
                <div className="flex justify-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openPrompt({ mode: "new-file", targetPath: "" })}
                  >
                    <FilePlus className="mr-1 h-3.5 w-3.5" />
                    New file
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleUploadClick("")}>
                    <Upload className="mr-1 h-3.5 w-3.5" />
                    Upload
                  </Button>
                </div>
              </div>
            ) : (
              <div className="pb-2 pt-0.5">{filtered.map((e) => renderEntry(e, 0))}</div>
            )}
          </div>
          <input
            ref={uploadInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleUploadChange}
          />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <header className="flex shrink-0 items-center gap-2 border-b border-[color:var(--ham-workspace-line)] px-2 py-2 md:px-3">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0 text-white/55"
              onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? "Show files" : "Hide files"}
              title={collapsed ? "Show files" : "Hide files"}
            >
              <Folder className="h-4 w-4" />
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-medium text-white/90 md:text-base">Files</h1>
              <p className="hidden text-[12px] text-white/40 sm:line-clamp-1 sm:text-[13px]">
                Files are served by the local HAM API from the configured filesystem root on this machine.
              </p>
            </div>
            {fsHealth?.broadFilesystemAccess && fsHealth.workspaceRootPath ? (
              <span
                className="hidden max-w-[min(20rem,45vw)] truncate rounded border border-amber-500/35 bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-100/90 md:inline"
                title="Intentional operator / workstation mode"
              >
                Broad filesystem access: {fsHealth.workspaceRootPath}
              </span>
            ) : null}
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              {readPath ? (
                <>
                  {saveState === "error" && saveError ? (
                    <span className="max-w-[min(12rem,40vw)] truncate text-[10px] text-red-300/90" title={saveError}>
                      {saveError}
                    </span>
                  ) : null}
                  {saveState === "saved" ? (
                    <span className="text-[10px] text-emerald-300/90">Saved</span>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-8 gap-1 border border-white/10 bg-white/[0.06] text-[12px] text-white/90 hover:bg-white/10"
                    disabled={saveState === "saving" || disconnected}
                    onClick={() => void handleSave()}
                    title="Save file (Ctrl+S)"
                    aria-label="Save file"
                  >
                    {saveState === "saving" ? (
                      "Saving…"
                    ) : (
                      <>
                        <Save className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Save</span>
                      </>
                    )}
                  </Button>
                </>
              ) : null}
              {bridge.status === "pending" && bridge.localCode ? (
                <span className="max-w-[min(10rem,35vw)] truncate text-[10px] text-amber-200/80" title={bridge.detail}>
                  {bridge.localCode === "unconfigured" ? "Local runtime" : "Local error"}
                </span>
              ) : bridge.status === "pending" ? (
                <span className="text-[10px] text-amber-200/80">Local API…</span>
              ) : null}
            </div>
          </header>

          {breadcrumb.length > 0 ? (
            <div className="flex shrink-0 items-center gap-1 border-b border-[color:var(--ham-workspace-line)] px-2 py-1.5 text-[10px] font-mono text-white/50">
              {breadcrumb.map((seg, i) => (
                <React.Fragment key={`${i}-${seg}`}>
                  {i > 0 ? <span className="text-white/20">/</span> : null}
                  <span className="truncate text-white/65">{seg}</span>
                </React.Fragment>
              ))}
            </div>
          ) : null}

          <div className="hww-files-editor relative min-h-0 flex-1 p-1 md:p-2">
            {readBridge?.status === "pending" && readPath ? (
              <p className="mb-1 text-[10px] text-amber-200/75" title={readBridge.detail}>
                {readBridge.detail}
              </p>
            ) : null}
            {disconnected ? (
              <div className="mb-2 space-y-2 rounded-lg border border-amber-500/25 bg-amber-500/10 p-2 text-[12px] text-amber-100/90">
                <p className="px-1 font-medium">Connect this machine to open the editor and browse files.</p>
                <LocalMachineConnectCta
                  variant="compact"
                  onSuccess={() => void refresh()}
                  className="!border-0 !bg-transparent !p-2"
                  showOpenSettings
                  showOpenFiles={false}
                />
              </div>
            ) : null}
            {localError && !disconnected ? (
              <div className="mb-2 space-y-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2">
                <p className="px-1 text-[11px] text-amber-200/80">{bridge.detail}</p>
                <LocalMachineConnectCta
                  variant="compact"
                  onSuccess={() => void refresh()}
                  className="!border-0 !bg-transparent !p-2"
                  showOpenSettings
                  showOpenFiles={false}
                />
              </div>
            ) : null}
            {noEnvRoot && !disconnected ? (
              <div className="mb-2 rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2.5 text-[12px] text-sky-100/90">
                <p className="font-medium">Local runtime reachable — optional filesystem root</p>
                <p className="mt-1 text-[11px] text-sky-100/80">
                  Local runtime connected, but <span className="font-mono">HAM_WORKSPACE_ROOT</span> is not set on the API. Set it to
                  a project path or a broad path (e.g. <span className="font-mono">C:\</span> for operator mode). The API is using
                  the repo sandbox until then.
                </p>
              </div>
            ) : null}
            <textarea
              value={editorValue}
              onChange={(e) => {
                setEditorValue(e.target.value);
                if (saveState === "saved" || saveState === "error") {
                  setSaveState("idle");
                  setSaveError(null);
                }
              }}
              onKeyDown={(e) => {
                if (!readPath) return;
                if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                  e.preventDefault();
                  void handleSave();
                }
              }}
              spellCheck={false}
              className="h-full min-h-[200px] w-full resize-none rounded-lg border border-white/[0.08] bg-[#040a0f] px-2 py-2 font-mono text-[12px] leading-relaxed text-[#dbe7f0] outline-none ring-0"
            />
            {!readPath && !previewPath ? (
              <p className="pointer-events-none absolute bottom-3 left-3 text-[11px] text-white/30">No file selected</p>
            ) : null}
          </div>
        </main>
      </div>

      {contextMenu ? (
        <div
          className="fixed z-50 min-w-[160px] rounded-lg border border-white/10 bg-[#0b151c] p-1 text-[12px] text-white/90 shadow-xl"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-white/[0.08]"
            onClick={() => {
              openPrompt({
                mode: "rename",
                targetPath: contextMenu.entry.path,
                defaultValue: contextMenu.entry.name,
              });
              setContextMenu(null);
            }}
          >
            <Pencil className="h-3.5 w-3.5" /> Rename
          </button>
          {contextMenu.entry.type === "folder" ? (
            <>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-white/[0.08]"
                onClick={() => {
                  openPrompt({ mode: "new-file", targetPath: contextMenu.entry.path });
                  setContextMenu(null);
                }}
              >
                <FilePlus className="h-3.5 w-3.5" /> New file
              </button>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-white/[0.08]"
                onClick={() => {
                  openPrompt({ mode: "new-folder", targetPath: contextMenu.entry.path });
                  setContextMenu(null);
                }}
              >
                <FolderPlus className="h-3.5 w-3.5" /> New folder
              </button>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-white/[0.08]"
                onClick={() => {
                  handleUploadClick(contextMenu.entry.path);
                  setContextMenu(null);
                }}
              >
                <Upload className="h-3.5 w-3.5" /> Upload
              </button>
            </>
          ) : (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-white/[0.08]"
              onClick={() => {
                void handleDownload(contextMenu.entry);
                setContextMenu(null);
              }}
            >
              Download
            </button>
          )}
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-red-300 hover:bg-red-500/15"
            onClick={() => {
              void handleDelete(contextMenu.entry);
              setContextMenu(null);
            }}
          >
            Delete
          </button>
        </div>
      ) : null}

      {previewPath || readPath ? (
        <div className="border-t border-[color:var(--ham-workspace-line)] bg-[#050a0e]/90 px-2 py-1.5 text-[11px] text-white/55">
          Preview: <span className="font-mono text-white/80">{previewPath || readPath}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-2 h-6 text-[10px] text-white/50"
            onClick={() => {
              setPreviewPath(null);
              setReadPath(null);
              setSaveState("idle");
              setSaveError(null);
            }}
          >
            Close preview
          </Button>
        </div>
      ) : null}

      {promptState ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" role="dialog">
          <div className="w-full max-w-sm rounded-xl border border-white/10 bg-[#0a141b] p-4 shadow-2xl">
            <h2 className="text-sm font-semibold text-white/90">
              {promptState.mode === "rename" ? "Rename" : promptState.mode === "new-folder" ? "New folder" : "New file"}
            </h2>
            <input
              value={promptValue}
              onChange={(e) => setPromptValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  void handlePromptSubmit();
                }
                if (e.key === "Escape") {
                  setPromptState(null);
                }
              }}
              className="mt-2 w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white/90"
              autoFocus
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setPromptState(null)}>
                Cancel
              </Button>
              <Button type="button" size="sm" onClick={() => void handlePromptSubmit()}>
                OK
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
