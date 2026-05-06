import * as React from "react";
import {
  ChevronDown,
  ChevronRight,
  Pause,
  Pencil,
  Play,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { workspaceJobsAdapter, type WorkspaceJob } from "../../adapters/jobsAdapter";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

export function WorkspaceJobsScreen() {
  const [jobs, setJobs] = React.useState<WorkspaceJob[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [searchApplied, setSearchApplied] = React.useState<string | undefined>(undefined);
  const [newOpen, setNewOpen] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [newDesc, setNewDesc] = React.useState("");
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set());
  const [actionBusy, setActionBusy] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const { jobs: list, bridge } = await workspaceJobsAdapter.list(searchApplied);
    if (bridge.status === "pending") {
      setError(bridge.detail);
      setJobs([]);
    } else {
      setJobs(list);
    }
    setLoading(false);
  }, [searchApplied]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const applySearch = () => {
    setSearchApplied(search.trim() || undefined);
  };

  const clearFilter = () => {
    setSearch("");
    setSearchApplied(undefined);
  };

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const onCreate = async () => {
    if (!newName.trim()) return;
    setActionBusy("new");
    const { job, error: err } = await workspaceJobsAdapter.create(newName.trim(), newDesc);
    setActionBusy(null);
    if (err) {
      setError(err);
      return;
    }
    if (job) {
      setNewOpen(false);
      setNewName("");
      setNewDesc("");
      void load();
    }
  };

  const onRun = async (id: string) => {
    setActionBusy(id);
    const { error: err } = await workspaceJobsAdapter.run(id);
    setActionBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onPause = async (id: string) => {
    setActionBusy(id);
    const { error: err } = await workspaceJobsAdapter.pause(id);
    setActionBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onResume = async (id: string) => {
    setActionBusy(id);
    const { error: err } = await workspaceJobsAdapter.resume(id);
    setActionBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onEdit = async (j: WorkspaceJob) => {
    const name = window.prompt("Job name", j.name);
    if (name === null) return;
    const desc = window.prompt("Description", j.description);
    if (desc === null) return;
    setActionBusy(j.id);
    const { error: err } = await workspaceJobsAdapter.patch(j.id, { name, description: desc });
    setActionBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onDelete = async (id: string) => {
    if (!window.confirm("Delete this job?")) return;
    setActionBusy(id);
    const { error: err } = await workspaceJobsAdapter.delete(id);
    setActionBusy(null);
    if (err) setError(err);
    else void load();
  };

  const filteredHint = searchApplied ? (
    <span className="text-[11px] text-white/50">
      Filtered by <span className="text-amber-200/80">&quot;{searchApplied}&quot;</span>
      <button type="button" className="ml-2 underline" onClick={clearFilter}>
        Clear
      </button>
    </span>
  ) : null;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3 p-3 md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        eyebrow="Workspace"
        title="Jobs"
        subtitle="Scheduled and on-demand jobs from the HAM Jobs API (/api/workspace/jobs). Run history is stored as JSON on the API host — not the local Files runtime."
        actions={
          <>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1.5 border-white/15 bg-white/5 text-white/90"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Refresh
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-7 gap-1"
              onClick={() => setNewOpen((v) => !v)}
            >
              <Plus className="h-3.5 w-3.5" />
              New job
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 max-w-sm flex-1 items-center gap-1 rounded border border-white/10 bg-black/20 px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-white/30" />
          <input
            className="hww-input h-7 min-w-0 flex-1 border-0 bg-transparent"
            placeholder="Search jobs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 text-[10px]"
            onClick={applySearch}
          >
            Search
          </Button>
        </div>
        {filteredHint}
      </div>

      {newOpen && (
        <div className="mt-2 rounded border border-white/10 bg-black/30 p-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="hww-input rounded px-2 py-1.5 text-xs"
              placeholder="Name *"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              className="hww-input rounded px-2 py-1.5 text-xs"
              placeholder="Description"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
          </div>
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setNewOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => void onCreate()}
              disabled={!newName.trim() || actionBusy === "new"}
            >
              Create
            </Button>
          </div>
        </div>
      )}

      {error && (
        <WorkspaceSurfaceStateCard
          className="border-white/10 bg-amber-500/10 text-amber-100/90"
          title="Jobs API is not available"
          description="Job definitions require the HAM jobs routes on your deployment."
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

      <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-0.5">
        {loading && jobs.length === 0 && <p className="text-[11px] text-white/40">Loading…</p>}
        {!loading && jobs.length === 0 && !error && (
          <div className="rounded-xl border border-dashed border-white/15 bg-black/20 px-4 py-8 text-center text-sm text-white/50">
            {searchApplied ? (
              <>
                <p className="font-medium text-white/85">No jobs match</p>
                <p className="mt-2 text-xs leading-relaxed">Clear search or create a new job.</p>
              </>
            ) : (
              <>
                <p className="font-medium text-white/85">No jobs scheduled yet</p>
                <p className="mt-2 text-xs leading-relaxed">
                  Create a job to automate a recurring workflow. Data is stored by the HAM API when
                  the route is available.
                </p>
                <Button type="button" size="sm" className="mt-4" onClick={() => setNewOpen(true)}>
                  New job
                </Button>
              </>
            )}
          </div>
        )}
        <ul className="space-y-2">
          {jobs.map((j) => {
            const open = expanded.has(j.id);
            return (
              <li key={j.id} className="rounded border border-white/[0.07] bg-black/25 p-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-white/30">
                        {j.id.slice(0, 8)}
                      </span>
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase",
                          j.status === "running" && "bg-emerald-500/20 text-emerald-200",
                          j.status === "paused" && "bg-amber-500/20 text-amber-200",
                          j.status === "idle" && "bg-white/10 text-white/50",
                        )}
                      >
                        {j.status}
                      </span>
                    </div>
                    <h2 className="text-sm font-medium text-white/90">{j.name}</h2>
                    {j.description ? (
                      <p className="text-[11px] text-white/45">{j.description}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title="Run now"
                      disabled={actionBusy === j.id}
                      onClick={() => void onRun(j.id)}
                    >
                      <Play className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title="Pause queue"
                      disabled={actionBusy === j.id}
                      onClick={() => void onPause(j.id)}
                    >
                      <Pause className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title="Resume"
                      disabled={actionBusy === j.id}
                      onClick={() => void onResume(j.id)}
                    >
                      <PlayCircle className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title="Edit"
                      onClick={() => void onEdit(j)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-red-300/60"
                      title="Delete"
                      onClick={() => void onDelete(j.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <button
                  type="button"
                  className="mt-1 flex items-center gap-0.5 text-[10px] text-white/40 hover:text-white/60"
                  onClick={() => toggleExpand(j.id)}
                >
                  {open ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                  Run history ({j.runs.length})
                </button>
                {open && (
                  <pre className="mt-1 max-h-40 overflow-auto rounded border border-white/10 bg-[#0a1014] p-2 text-[10px] text-emerald-100/80">
                    {j.runs.length
                      ? j.runs
                          .map(
                            (r) =>
                              `--- ${r.id.slice(0, 8)} @ ${fmt(r.startedAt)} [${r.status}] ---\n${r.output || "(no output)"}`,
                          )
                          .join("\n\n")
                      : "No runs yet."}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
