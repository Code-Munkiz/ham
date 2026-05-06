/**
 * Upstream: src/routes/memory.tsx (Memory | Knowledge tabs) +
 * src/screens/memory/memory-browser-screen.tsx (list + read + search + line editor).
 * HAM maps filesystem calls to /api/workspace/memory (JSON v0) — layout/IA preserved.
 */
import * as React from "react";
import { BookOpen, Brain, ChevronDown, ChevronUp, Pencil, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { workspaceMemoryAdapter, type WorkspaceMemoryItem } from "../../adapters/memoryAdapter";
import { WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";

type FileMeta = { path: string; name: string; size: number; modified: string };
type SearchHit = { path: string; line: number; text: string };

function itemPath(m: WorkspaceMemoryItem): string {
  const base = m.kind === "preference" ? "memory/preferences" : "memories";
  return `${base}/${m.id}.md`;
}

function toIso(ts: number): string {
  return new Date(ts * 1000).toISOString();
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatMod(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(t);
}

function highlightMatch(text: string, query: string): { text: string; hit: boolean }[] {
  const needle = query.trim();
  if (!needle) return [{ text, hit: false }];
  const lower = text.toLowerCase();
  const m = lower.indexOf(needle.toLowerCase());
  if (m < 0) return [{ text, hit: false }];
  return [
    { text: text.slice(0, m), hit: false },
    { text: text.slice(m, m + needle.length), hit: true },
    { text: text.slice(m + needle.length), hit: false },
  ];
}

function searchItems(items: WorkspaceMemoryItem[], q: string): SearchHit[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return [];
  const out: SearchHit[] = [];
  for (const it of items) {
    const p = itemPath(it);
    if (it.title.toLowerCase().includes(needle)) {
      out.push({ path: p, line: 1, text: it.title });
    }
    const lines = it.body.split(/\r?\n/);
    lines.forEach((line, i) => {
      if (line.toLowerCase().includes(needle)) {
        out.push({ path: p, line: i + 1, text: line });
      }
    });
    for (const t of it.tags) {
      if (t.toLowerCase().includes(needle)) {
        out.push({ path: p, line: 1, text: `tag: ${t}` });
      }
    }
  }
  return out.slice(0, 200);
}

function StateBox({ label, error }: { label: string; error?: boolean }) {
  return (
    <div
      className={cn(
        "flex min-h-32 items-center justify-center rounded-xl border px-4 py-3 text-sm",
        error
          ? "border-amber-500/35 bg-amber-500/10 text-amber-100/90"
          : "border-white/10 bg-black/20 text-[var(--theme-muted,theme(colors.neutral.400))]",
      )}
    >
      {error ? (
        <span className="max-w-full whitespace-pre-wrap break-words text-left leading-relaxed">
          {label}
        </span>
      ) : (
        label
      )}
    </div>
  );
}

function FileRow({
  file,
  selected,
  onSelect,
}: {
  file: FileMeta;
  selected: boolean;
  onSelect: (p: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(file.path)}
      className={cn(
        "w-full rounded-lg border px-2.5 py-2 text-left transition-colors",
        selected
          ? "border-emerald-500/60 bg-emerald-500/10"
          : "border-white/10 bg-black/20 hover:border-white/20 hover:bg-white/[0.04]",
      )}
    >
      <div className="truncate font-mono text-xs text-[var(--theme-text)]">{file.path}</div>
      <div className="mt-0.5 text-[11px] text-[var(--theme-muted)]">
        {formatBytes(file.size)} · {formatMod(file.modified)}
      </div>
    </button>
  );
}

function MemoryEditorPanel({
  item,
  content,
  lines,
  err,
  selectedPath,
  listLoading,
  isEditing,
  draft,
  setDraft,
  onSave,
  onCancel,
  onEdit,
  saving,
  hasUnsaved,
  focusLine,
  lineRefs,
}: {
  item: WorkspaceMemoryItem | null;
  content: string;
  lines: string[];
  err: string | null;
  selectedPath: string | null;
  listLoading: boolean;
  isEditing: boolean;
  draft: string;
  setDraft: (s: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onEdit: () => void;
  saving: boolean;
  hasUnsaved: boolean;
  focusLine: number | null;
  lineRefs: React.MutableRefObject<Record<number, HTMLDivElement | null>>;
}) {
  return (
    <section className="min-h-0 rounded-2xl border border-white/10 bg-black/25 md:col-span-2">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-[var(--theme-text)]">
            {selectedPath || "Select a file"}
          </div>
          {item && (
            <div className="text-xs text-[var(--theme-muted)]">
              {item.kind} · {item.tags.length ? item.tags.join(", ") : "no tags"}
            </div>
          )}
        </div>
        {selectedPath && item ? (
          <div className="ml-3 flex items-center gap-2">
            {isEditing ? (
              <>
                <button
                  type="button"
                  disabled={saving}
                  onClick={onSave}
                  className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:brightness-110 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={onCancel}
                  className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-semibold text-[var(--theme-text)] hover:bg-white/5"
                >
                  Cancel
                </button>
                {hasUnsaved ? (
                  <span className="inline-block size-2 rounded-full bg-amber-400" title="Unsaved" />
                ) : null}
              </>
            ) : (
              <button
                type="button"
                onClick={onEdit}
                className="relative inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-semibold text-[var(--theme-text)] hover:bg-white/5"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </button>
            )}
          </div>
        ) : null}
      </div>
      <div className={cn("h-full p-2 md:p-3", isEditing ? "overflow-hidden" : "overflow-auto")}>
        {listLoading && <StateBox label="Loading memory…" />}
        {err && <StateBox label={err} error />}
        {!listLoading && !err && !selectedPath && (
          <StateBox label="No memory entries yet. Memory storage is connected, but no file is selected." />
        )}
        {!listLoading && !err && selectedPath && !item && <StateBox label="Item not found" error />}
        {item && !listLoading && !err && isEditing && (
          <div
            className="h-full min-h-[200px] rounded-xl p-2"
            style={{
              border: "1px solid var(--theme-border)",
              backgroundColor: "var(--theme-card)",
            }}
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-[min(60vh,480px)] w-full resize-none rounded-lg px-3 py-2 font-mono text-[13px] outline-none ring-0"
              style={{
                border: "1px solid var(--theme-border)",
                backgroundColor: "var(--theme-bg)",
                color: "var(--theme-text)",
              }}
              spellCheck={false}
            />
          </div>
        )}
        {item && !listLoading && !err && !isEditing && (
          <div
            className="rounded-xl"
            style={{
              border: "1px solid var(--theme-border)",
              backgroundColor: "var(--theme-card)",
            }}
          >
            <div className="font-mono text-xs">
              {lines.map((line, index) => {
                const n = index + 1;
                const hi = focusLine === n;
                return (
                  <div
                    key={n}
                    ref={(el) => {
                      lineRefs.current[n] = el;
                    }}
                    className={cn(
                      "grid grid-cols-[56px_1fr] gap-0 border-b border-white/[0.06] last:border-b-0",
                      hi && "bg-yellow-500/10",
                    )}
                  >
                    <div
                      className={cn(
                        "select-none border-r border-white/10 px-2 py-0.5 text-right text-[var(--theme-muted)]",
                        hi && "text-yellow-200",
                      )}
                    >
                      {n}
                    </div>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words px-3 py-0.5 text-neutral-200">
                      {line || " "}
                    </pre>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export function WorkspaceMemoryScreen() {
  const [routeTab, setRouteTab] = React.useState<"memory" | "knowledge">("memory");
  const [items, setItems] = React.useState<WorkspaceMemoryItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [bridgeError, setBridgeError] = React.useState<string | null>(null);
  const [searchInput, setSearchInput] = React.useState("");
  const [mobileFilesOpen, setMobileFilesOpen] = React.useState(true);
  const [selectedPath, setSelectedPath] = React.useState<string | null>(null);
  const [focusLine, setFocusLine] = React.useState<number | null>(null);
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const lineRefs = React.useRef<Record<number, HTMLDivElement | null>>({});
  const searchTerm = searchInput.trim();

  const byPath = React.useMemo(() => {
    const m = new Map<string, WorkspaceMemoryItem>();
    for (const it of items) m.set(itemPath(it), it);
    return m;
  }, [items]);

  const fileItems: FileMeta[] = React.useMemo(() => {
    return items.map((it) => {
      const p = itemPath(it);
      return {
        path: p,
        name: p,
        size: it.body.length,
        modified: toIso(it.updatedAt),
      };
    });
  }, [items]);

  const selectedItem = selectedPath ? (byPath.get(selectedPath) ?? null) : null;
  const content = selectedItem?.body ?? "";
  const lines = React.useMemo(() => content.split(/\r?\n/), [content]);
  const hasUnsaved = isEditing && draft !== content;

  React.useEffect(() => {
    if (!selectedPath && fileItems[0]) {
      setSelectedPath(fileItems[0].path);
    } else if (selectedPath && !items.some((it) => itemPath(it) === selectedPath)) {
      setSelectedPath(fileItems[0]?.path ?? null);
    }
  }, [items, fileItems, selectedPath]);

  const load = React.useCallback(async () => {
    setLoading(true);
    setBridgeError(null);
    const { items: list, bridge } = await workspaceMemoryAdapter.list(undefined, false);
    if (bridge.status === "pending") {
      setBridgeError(bridge.detail);
      setItems([]);
    } else {
      setItems(list);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    if (!isEditing) {
      setDraft(content);
    }
  }, [content, isEditing, selectedPath]);

  React.useEffect(() => {
    if (!focusLine) return;
    const t = lineRefs.current[focusLine];
    t?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusLine, lines, selectedPath]);

  const searchHits = React.useMemo(
    () => (searchTerm ? searchItems(items, searchTerm) : []),
    [items, searchTerm],
  );
  const searchEnabled = searchTerm.length > 0;

  function trySelect(p: string, line?: number): boolean {
    if (isEditing && hasUnsaved) {
      if (!window.confirm("Discard unsaved changes and switch?")) return false;
    }
    if (isEditing) {
      setIsEditing(false);
      setDraft("");
    }
    setSelectedPath(p);
    setFocusLine(line ?? null);
    return true;
  }

  async function saveEdit() {
    if (!selectedItem || saving) return;
    setSaving(true);
    const { error } = await workspaceMemoryAdapter.patch(selectedItem.id, { body: draft });
    setSaving(false);
    if (error) {
      setBridgeError(error);
      return;
    }
    setIsEditing(false);
    void load();
  }

  if (bridgeError && !loading && items.length === 0) {
    return (
      <div
        className="hws-root flex h-full min-h-0 flex-col p-4"
        style={{ backgroundColor: "var(--theme-bg)" }}
      >
        <WorkspaceSurfaceStateCard
          title="Memory API is not available in this HAM deployment."
          description="Other workspace features may still work. Memory is served from the HAM API at /api/workspace/memory — not the local Files/Terminal connection."
          tone="amber"
          technicalDetail={bridgeError}
          primaryAction={
            <Button type="button" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div
      className="hws-root flex h-full min-h-0 flex-col"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      <Tabs
        value={routeTab}
        onValueChange={(v) => setRouteTab(v as "memory" | "knowledge")}
        className="flex h-full min-h-0 flex-col"
      >
        <div
          className="shrink-0 border-b px-3 pt-3 md:px-4 md:pt-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <TabsList className="h-auto w-full justify-start gap-1 border-0 bg-transparent p-0">
            <TabsTrigger
              value="memory"
              className="rounded-none border-0 border-b-2 border-transparent bg-transparent px-3 pb-2 text-sm data-[state=active]:border-b-emerald-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none"
            >
              Memory
            </TabsTrigger>
            <TabsTrigger
              value="knowledge"
              className="rounded-none border-0 border-b-2 border-transparent bg-transparent px-3 pb-2 text-sm data-[state=active]:border-b-emerald-500 data-[state=active]:bg-transparent data-[state=active]:shadow-none"
            >
              Knowledge
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent
          value="knowledge"
          className="m-0 min-h-0 flex-1 overflow-auto focus-visible:outline-none"
        >
          <div className="p-4 md:p-6">
            <div className="mx-auto max-w-2xl rounded-2xl border border-dashed border-white/15 bg-black/20 p-6 text-center">
              <div className="mb-2 flex justify-center gap-2 text-[var(--theme-muted)]">
                <BookOpen className="h-8 w-8" />
              </div>
              <h2 className="text-lg font-semibold text-[var(--theme-text)]">Knowledge</h2>
              <p className="mt-2 text-sm text-[var(--theme-muted)]">
                Upstream maps this tab to a local/remote wiki (see{" "}
                <code className="text-xs">knowledge-browser-screen</code>). HAM does not expose{" "}
                <code className="text-xs">/api/knowledge</code> in this build — no wiki tree or
                graph here.
              </p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="memory" className="m-0 min-h-0 flex-1 focus-visible:outline-none">
          <div
            className="flex h-full min-h-0 flex-col"
            style={{ backgroundColor: "var(--theme-bg)" }}
          >
            <div
              className="shrink-0 px-3 py-2 md:px-4"
              style={{ borderBottom: "1px solid var(--theme-border)" }}
            >
              <h2 className="text-sm font-semibold text-[var(--theme-text)]">Memory browser</h2>
              <p className="mt-0.5 text-xs text-[var(--theme-muted)]">
                Search and edit entries stored by the HAM Memory API. This is not Memory Heist sync
                — JSON v0 on the API host only.
              </p>
            </div>
            <div
              className="shrink-0 px-3 py-3 md:px-4"
              style={{ borderBottom: "1px solid var(--theme-border)" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="inline-flex size-9 items-center justify-center rounded-xl"
                  style={{
                    border: "1px solid var(--theme-border)",
                    backgroundColor: "var(--theme-card)",
                  }}
                >
                  <Brain className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="relative">
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                      style={{ color: "var(--theme-muted)" }}
                    />
                    <input
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder="Search memory files"
                      className="w-full rounded-xl py-2 pl-9 pr-3 text-sm outline-none"
                      style={{
                        border: "1px solid var(--theme-border)",
                        backgroundColor: "var(--theme-card)",
                        color: "var(--theme-text)",
                      }}
                    />
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  className="shrink-0"
                  onClick={async () => {
                    const title = window.prompt("New memory title", "note");
                    if (!title?.trim()) return;
                    const { item, error } = await workspaceMemoryAdapter.create({
                      title: title.trim(),
                      body: "",
                      tags: [],
                      kind: "note",
                    });
                    if (error) {
                      setBridgeError(error);
                      return;
                    }
                    if (item) {
                      void (async () => {
                        await load();
                        setSelectedPath(itemPath(item));
                        setIsEditing(true);
                        setDraft(item.body);
                      })();
                    }
                  }}
                >
                  New
                </Button>
              </div>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 md:grid-cols-3 md:p-4">
              <aside className="flex min-h-0 flex-col rounded-2xl border border-white/10 bg-black/20 md:col-span-1">
                <button
                  type="button"
                  className="flex items-center justify-between px-3 py-2 text-left md:cursor-default"
                  onClick={() => setMobileFilesOpen((v) => !v)}
                >
                  <span className="text-xs font-semibold uppercase tracking-wide text-[var(--theme-muted)]">
                    Memory files ({fileItems.length})
                  </span>
                  <span className="md:hidden text-[var(--theme-muted)]">
                    {mobileFilesOpen ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </span>
                </button>

                {searchEnabled ? (
                  <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
                    <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--theme-muted)]">
                      Search results
                    </div>
                    <div className="space-y-1">
                      {searchHits.length === 0 ? (
                        <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-[var(--theme-muted)]">
                          No matches
                        </div>
                      ) : (
                        searchHits.map((result, index) => (
                          <button
                            key={`${result.path}:${result.line}:${index}`}
                            type="button"
                            onClick={() => {
                              if (trySelect(result.path, result.line)) setMobileFilesOpen(false);
                            }}
                            className="w-full rounded-lg border border-white/10 bg-black/20 px-2.5 py-2 text-left hover:border-white/20"
                          >
                            <div className="truncate text-[11px] text-[var(--theme-muted)]">
                              {result.path}:{result.line}
                            </div>
                            <div className="mt-0.5 line-clamp-2 text-xs text-neutral-200">
                              {highlightMatch(result.text, searchTerm).map((part, i) => (
                                <span
                                  key={i}
                                  className={
                                    part.hit
                                      ? "rounded bg-yellow-500/20 px-0.5 text-yellow-100"
                                      : undefined
                                  }
                                >
                                  {part.text || " "}
                                </span>
                              ))}
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                ) : (
                  <div
                    className={cn(
                      "min-h-0 flex-1 px-2 pb-2",
                      !mobileFilesOpen && "hidden md:block",
                    )}
                  >
                    <div className="max-h-72 space-y-1 overflow-y-auto pr-1 md:h-full md:max-h-none">
                      {loading && (
                        <div className="rounded-lg border border-white/10 px-3 py-2 text-xs text-[var(--theme-muted)]">
                          Loading…
                        </div>
                      )}
                      {!loading && fileItems.length === 0 && (
                        <div className="space-y-1.5 rounded-lg border border-dashed border-white/15 px-3 py-3 text-xs text-[var(--theme-muted)]">
                          <p className="font-medium text-[var(--theme-text)]">
                            No memory entries yet
                          </p>
                          <p>
                            Memory storage is connected, but no entries are available. Use New to
                            create a note.
                          </p>
                        </div>
                      )}
                      {!loading &&
                        fileItems.map((f) => (
                          <FileRow
                            key={f.path}
                            file={f}
                            selected={selectedPath === f.path}
                            onSelect={(p) => {
                              void trySelect(p);
                            }}
                          />
                        ))}
                    </div>
                  </div>
                )}
              </aside>

              <MemoryEditorPanel
                item={selectedItem}
                content={content}
                lines={lines}
                err={null}
                selectedPath={selectedPath}
                listLoading={loading}
                isEditing={isEditing}
                draft={draft}
                setDraft={setDraft}
                onSave={() => void saveEdit()}
                onCancel={() => {
                  setDraft(content);
                  setIsEditing(false);
                }}
                onEdit={() => {
                  setDraft(content);
                  setIsEditing(true);
                }}
                saving={saving}
                hasUnsaved={hasUnsaved}
                focusLine={focusLine}
                lineRefs={lineRefs}
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
