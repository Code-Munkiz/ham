import * as React from "react";
import { ChevronRight, File, FilePlus, Folder, FolderPlus, Pencil, RefreshCw, Search, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
    const children = (e.children || []).map(walk).filter((c): c is WorkspaceFileEntry => c !== null);
    if (e.name.toLowerCase().includes(lower) || children.length > 0) {
      return { ...e, children };
    }
    return null;
  };
  return entries.map(walk).filter((e): e is WorkspaceFileEntry => e !== null);
}

type PromptState =
  | { mode: "rename" | "new-file" | "new-folder"; targetPath: string; defaultValue?: string }
  | null;

type Ctx = { x: number; y: number; entry: WorkspaceFileEntry } | null;

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
  const uploadInputRef = React.useRef<HTMLInputElement | null>(null);
  const uploadTargetRef = React.useRef("");

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const { entries: next, bridge: b } = await workspaceFileAdapter.list();
    setEntries(next);
    setBridge(b);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

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
      form.append("action", "upload");
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

  const toggleFolder = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const loadFile = async (path: string) => {
    setReadPath(path);
    setReadBridge(null);
    const { text, bridge: b } = await workspaceFileAdapter.readText(path);
    setReadBridge(b);
    if (text != null) {
      setEditorValue(text);
    }
  };

  const handleFileClick = async (entry: WorkspaceFileEntry) => {
    if (entry.type === "folder") {
      if (!searchActive) {
        toggleFolder(entry.path);
      }
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
        {entry.type === "folder" && isEx && entry.children?.length
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
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/35" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search files"
                className="hww-input w-full rounded-md py-1.5 pl-8 pr-2 text-[12px]"
              />
            </div>
          </div>
          <div className="hww-scroll min-h-0 flex-1 overflow-y-auto px-1 pb-3">
            {loading ? (
              <p className="px-2 py-1 text-[11px] text-white/45">Loading…</p>
            ) : !entries.length && bridge.status === "pending" ? (
              <p className="px-2 py-2 text-[11px] leading-relaxed text-white/45">No file tree yet. Runtime bridge pending.</p>
            ) : !entries.length ? (
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
                Explore your workspace and edit in the buffer.
              </p>
            </div>
            {bridge.status === "pending" ? (
              <span className="ml-auto shrink-0 text-[10px] text-amber-200/80">Runtime bridge pending</span>
            ) : null}
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
              <p className="mb-1 text-[10px] text-amber-200/75">File read: runtime bridge pending (buffer below may be from insert-as-reference or default).</p>
            ) : null}
            <textarea
              value={editorValue}
              onChange={(e) => setEditorValue(e.target.value)}
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
