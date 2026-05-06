import * as React from "react";
import { Plus, RefreshCw, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  workspaceTasksAdapter,
  type TaskStatus,
  type TaskSummary,
  type WorkspaceTask,
} from "../../adapters/tasksAdapter";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";

const COLUMNS: { id: TaskStatus; label: string }[] = [
  { id: "todo", label: "To do" },
  { id: "in_progress", label: "In progress" },
  { id: "done", label: "Done" },
];

export function WorkspaceTasksScreen() {
  const [tasks, setTasks] = React.useState<WorkspaceTask[]>([]);
  const [summary, setSummary] = React.useState<TaskSummary | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [searchApplied, setSearchApplied] = React.useState<string | undefined>(undefined);
  const [showDone, setShowDone] = React.useState(true);
  const [dialog, setDialog] = React.useState<WorkspaceTask | "new" | null>(null);
  const [formTitle, setFormTitle] = React.useState("");
  const [formBody, setFormBody] = React.useState("");
  const [formStatus, setFormStatus] = React.useState<TaskStatus>("todo");
  const [formDue, setFormDue] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [listRes, sumRes] = await Promise.all([
      workspaceTasksAdapter.list({
        q: searchApplied,
        includeDone: showDone,
      }),
      workspaceTasksAdapter.summary(),
    ]);
    if (listRes.bridge.status === "pending") {
      setError(listRes.bridge.detail);
      setTasks([]);
    } else {
      setTasks(listRes.tasks);
    }
    if (sumRes.bridge.status === "ready" && sumRes.summary) {
      setSummary(sumRes.summary);
    } else {
      setSummary(null);
    }
    setLoading(false);
  }, [searchApplied, showDone]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const applyFilter = () => {
    setSearchApplied(search.trim() || undefined);
  };

  const clearFilter = () => {
    setSearch("");
    setSearchApplied(undefined);
  };

  const openNew = (col: TaskStatus) => {
    setFormTitle("");
    setFormBody("");
    setFormStatus(col);
    setFormDue("");
    setDialog("new");
  };

  const openEdit = (t: WorkspaceTask) => {
    setFormTitle(t.title);
    setFormBody(t.body);
    setFormStatus(t.status);
    setFormDue(t.dueAt || "");
    setDialog(t);
  };

  const closeDialog = () => {
    setDialog(null);
  };

  const saveTask = async () => {
    if (!formTitle.trim()) return;
    setBusy(true);
    if (dialog === "new") {
      const { task, error: err } = await workspaceTasksAdapter.create(
        formTitle.trim(),
        formBody,
        formStatus,
        formDue || null,
      );
      setBusy(false);
      if (err) setError(err);
      else if (task) {
        closeDialog();
        void load();
      }
    } else if (dialog) {
      const { error: err } = await workspaceTasksAdapter.patch(dialog.id, {
        title: formTitle.trim(),
        body: formBody,
        status: formStatus,
        dueAt: formDue || null,
      });
      setBusy(false);
      if (err) setError(err);
      else {
        closeDialog();
        void load();
      }
    } else {
      setBusy(false);
    }
  };

  const deleteTask = async (t: WorkspaceTask) => {
    if (!window.confirm("Delete this task?")) return;
    setBusy(true);
    const { error: err } = await workspaceTasksAdapter.delete(t.id);
    setBusy(false);
    if (err) setError(err);
    else {
      closeDialog();
      void load();
    }
  };

  const byColumn = (s: TaskStatus) => tasks.filter((t) => t.status === s);
  const filterHint = searchApplied ? (
    <span className="text-[11px] text-white/50">
      Filtered: <span className="text-amber-200/80">&quot;{searchApplied}&quot;</span>{" "}
      <button type="button" className="ml-1 underline" onClick={clearFilter}>
        Clear
      </button>
    </span>
  ) : null;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3 p-3 md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        eyebrow="Workspace"
        title="Tasks"
        subtitle="Task board and summary from the HAM Tasks API (/api/workspace/tasks + /summary). Kanban columns map to server-backed status — not local Files."
        actions={
          <>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1 border-white/15 bg-white/5 text-white/90"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 border-white/10 bg-black/30 text-amber-200/90 shadow-sm hover:border-white/15 hover:bg-white/5 hover:text-amber-100"
              onClick={() => setShowDone((s) => !s)}
            >
              {showDone ? "Hide done" : "Show done"}
            </Button>
          </>
        }
      />

      {summary && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {[
            ["Total", String(summary.total)],
            ["In progress", String(summary.inProgress)],
            ["Overdue", String(summary.overdue)],
            ["Done", `${summary.donePercent}%`],
          ].map(([k, v]) => (
            <div
              key={k}
              className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-center"
            >
              <div className="text-[9px] font-semibold uppercase tracking-wide text-white/40">
                {k}
              </div>
              <div className="text-sm font-semibold text-white/90">{v}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 max-w-sm flex-1 items-center gap-1 rounded border border-white/10 bg-black/20 px-2">
          <Search className="h-3.5 w-3.5 text-white/30" />
          <input
            className="hww-input h-7 min-w-0 flex-1 border-0"
            placeholder="Filter tasks"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilter()}
          />
          <Button type="button" size="sm" variant="ghost" className="h-6" onClick={applyFilter}>
            Apply
          </Button>
        </div>
        {filterHint}
      </div>

      {error && (
        <WorkspaceSurfaceStateCard
          className="border-white/10 bg-amber-500/10 text-amber-100/90"
          title="Tasks API is not available"
          description="The task board needs /api/workspace/tasks on your HAM API."
          tone="amber"
          technicalDetail={error}
          primaryAction={
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="border-white/20 bg-white/10 text-white"
              onClick={() => void load()}
            >
              Retry
            </Button>
          }
        />
      )}

      {loading && tasks.length === 0 && <p className="text-[11px] text-white/40">Loading tasks…</p>}
      {!loading && tasks.length === 0 && !error && (
        <div className="rounded-xl border border-dashed border-white/15 bg-black/20 px-4 py-8 text-center text-sm text-white/50">
          {searchApplied ? (
            <>
              <p className="font-medium text-white/90">No tasks match</p>
              <p className="mt-2 text-xs leading-relaxed">
                Clear the filter or add a task in a column.
              </p>
            </>
          ) : (
            <>
              <p className="font-medium text-white/90">No tasks yet</p>
              <p className="mt-2 text-xs leading-relaxed">
                Create a task from a column, or launch a mission when your deployment writes tasks
                to the board.
              </p>
            </>
          )}
        </div>
      )}

      <div className="mt-3 grid min-h-0 flex-1 grid-cols-1 gap-2 md:grid-cols-3">
        {COLUMNS.map((col) => (
          <div
            key={col.id}
            className="flex min-h-0 min-w-0 flex-col rounded border border-white/10 bg-black/20"
          >
            <div className="flex items-center justify-between border-b border-white/10 px-2 py-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-white/50">
                {col.label}
              </span>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                title="Add in column"
                onClick={() => openNew(col.id)}
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-1.5">
              {byColumn(col.id).map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    className="w-full rounded border border-white/10 bg-[#0c1418] p-1.5 text-left hover:border-amber-500/20"
                    onClick={() => openEdit(t)}
                  >
                    <div className="text-xs font-medium text-white/90">{t.title}</div>
                    {t.dueAt ? (
                      <div className="text-[9px] text-amber-200/60">Due {t.dueAt}</div>
                    ) : null}
                    {t.body ? (
                      <p className="line-clamp-2 text-[10px] text-white/40">{t.body}</p>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {dialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3"
          role="dialog"
        >
          <div className="w-full max-w-md rounded border border-white/20 bg-[#0a1216] p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white/90">
                {dialog === "new" ? "New task" : "Edit task"}
              </h2>
              <button
                type="button"
                className="text-white/40 hover:text-white/70"
                onClick={closeDialog}
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-2">
              <input
                className="hww-input w-full rounded px-2 py-1.5"
                placeholder="Title"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
              />
              <textarea
                className="hww-input min-h-[4rem] w-full resize-y rounded px-2 py-1.5"
                placeholder="Body"
                value={formBody}
                onChange={(e) => setFormBody(e.target.value)}
              />
              <label className="block text-[10px] text-white/45">
                Status
                <select
                  className="mt-0.5 block w-full rounded border border-white/10 bg-black/40 px-2 py-1 text-xs"
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value as TaskStatus)}
                >
                  <option value="todo">To do</option>
                  <option value="in_progress">In progress</option>
                  <option value="done">Done</option>
                </select>
              </label>
              <input
                className="hww-input w-full rounded px-2 py-1.5"
                type="date"
                value={formDue.length >= 10 ? formDue.slice(0, 10) : formDue}
                onChange={(e) => setFormDue(e.target.value)}
              />
            </div>
            <div className="mt-3 flex flex-wrap justify-between gap-2">
              {dialog !== "new" && dialog && (
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  disabled={busy}
                  onClick={() => void deleteTask(dialog)}
                >
                  Delete
                </Button>
              )}
              <div className="ml-auto flex gap-2">
                <Button type="button" size="sm" variant="secondary" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void saveTask()}
                  disabled={!formTitle.trim() || busy}
                >
                  Save
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
