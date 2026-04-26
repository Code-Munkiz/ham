import * as React from "react";
import { Clock, LayoutGrid, Pause, Play, Plus, RefreshCw, Settings2, Terminal, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  workspaceOperationsAdapter,
  type OperationsSettings,
  type ScheduledJob,
  type WorkspaceAgent,
} from "../../adapters/operationsAdapter";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function statusBadge(s: WorkspaceAgent["status"]) {
  switch (s) {
    case "active":
      return "bg-emerald-500/25 text-emerald-100";
    case "idle":
      return "bg-white/10 text-white/80";
    case "paused":
      return "bg-amber-500/20 text-amber-100";
    case "error":
      return "bg-red-500/25 text-red-100";
    default:
      return "bg-white/10 text-white/80";
  }
}

export function WorkspaceOperationsScreen() {
  const [view, setView] = React.useState<"overview" | "outputs">("overview");
  const [agents, setAgents] = React.useState<WorkspaceAgent[]>([]);
  const [jobs, setJobs] = React.useState<ScheduledJob[]>([]);
  const [settings, setSettings] = React.useState<OperationsSettings | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [newOpen, setNewOpen] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [newModel, setNewModel] = React.useState("ham-local");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [sDraft, setSDraft] = React.useState({ defaultModel: "ham-local", outputsRetention: 50, notes: "" });
  const [detail, setDetail] = React.useState<WorkspaceAgent | null>(null);
  const [formName, setFormName] = React.useState("");
  const [formModel, setFormModel] = React.useState("");
  const [formCron, setFormCron] = React.useState("");
  const [formCronOn, setFormCronOn] = React.useState(false);
  const [addJobOpen, setAddJobOpen] = React.useState(false);
  const [jobName, setJobName] = React.useState("");
  const [jobCron, setJobCron] = React.useState("0 * * * *");

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [a, j, gs] = await Promise.all([
      workspaceOperationsAdapter.listAgents(),
      workspaceOperationsAdapter.listScheduled(),
      workspaceOperationsAdapter.getSettings(),
    ]);
    if (a.bridge.status === "pending") {
      setError(a.bridge.detail);
      setAgents([]);
    } else {
      setAgents(a.agents);
    }
    if (j.bridge.status === "ready") {
      setJobs(j.jobs);
    } else {
      setJobs([]);
    }
    if (gs.bridge.status === "ready" && gs.settings) {
      setSettings(gs.settings);
      setSDraft({
        defaultModel: gs.settings.defaultModel,
        outputsRetention: gs.settings.outputsRetention,
        notes: gs.settings.notes,
      });
    } else {
      setSettings(null);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const openDetail = (ag: WorkspaceAgent) => {
    setDetail(ag);
    setFormName(ag.name);
    setFormModel(ag.model);
    setFormCron(ag.cronExpr);
    setFormCronOn(ag.cronEnabled);
  };

  const saveDetail = async () => {
    if (!detail) return;
    setBusy(detail.id);
    const { error: err } = await workspaceOperationsAdapter.patchAgent(detail.id, {
      name: formName.trim() || detail.name,
      model: formModel,
      cronEnabled: formCronOn,
      cronExpr: formCron,
    });
    setBusy(null);
    if (err) setError(err);
    else {
      setDetail(null);
      void load();
    }
  };

  const deleteAgent = async (id: string) => {
    if (!window.confirm("Delete this agent?")) return;
    setBusy(id);
    const { error: err } = await workspaceOperationsAdapter.deleteAgent(id);
    setBusy(null);
    if (err) setError(err);
    else {
      if (detail?.id === id) setDetail(null);
      void load();
    }
  };

  const onCreate = async () => {
    if (!newName.trim()) return;
    setBusy("new");
    const { agent, error: err } = await workspaceOperationsAdapter.createAgent(newName.trim(), newModel);
    setBusy(null);
    if (err) setError(err);
    else {
      setNewOpen(false);
      setNewName("");
      setNewModel("ham-local");
      if (agent) setDetail(agent);
      void load();
    }
  };

  const onAddScheduled = async () => {
    if (!jobName.trim()) return;
    setBusy("job");
    const { error: err } = await workspaceOperationsAdapter.createScheduled(jobName.trim(), jobCron);
    setBusy(null);
    if (err) setError(err);
    else {
      setAddJobOpen(false);
      setJobName("");
      setJobCron("0 * * * *");
      void load();
    }
  };

  const saveOpsSettings = async () => {
    setBusy("os");
    const { settings: s, error: err } = await workspaceOperationsAdapter.patchSettings({
      defaultModel: sDraft.defaultModel,
      outputsRetention: sDraft.outputsRetention,
      notes: sDraft.notes,
    });
    setBusy(null);
    if (err) setError(err);
    else {
      if (s) setSettings(s);
      setSettingsOpen(false);
    }
  };

  const allOutputLines = React.useMemo(() => {
    const lines: { agent: string; at: number; line: string }[] = [];
    for (const ag of agents) {
      for (const o of ag.outputs) {
        lines.push({ agent: ag.name, at: o.at, line: o.line });
      }
    }
    return lines.sort((a, b) => b.at - a.at);
  }, [agents]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col p-3 md:p-4">
      <div className="shrink-0">
        <p className="hww-pill mb-1">Workspace</p>
        <h1 className="text-base font-semibold text-white/95">Operations</h1>
        <p className="mt-0.5 max-w-2xl text-[11px] text-white/45">
          OPS-001…007 — Agent cards, play/pause, cron + scheduled jobs, settings. Storage{" "}
          <code className="text-white/50">.ham/workspace_state/operations.json</code> (local HAM; no direct upstream
          calls).
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </Button>
        <Button type="button" size="sm" className="h-7 gap-1" onClick={() => setNewOpen((v) => !v)}>
          <Plus className="h-3.5 w-3.5" />
          New agent
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1"
          onClick={() => setAddJobOpen((v) => !v)}
        >
          <Clock className="h-3.5 w-3.5" />
          Add job
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 border-white/10 bg-black/30 text-amber-200/90 hover:bg-white/5"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings2 className="h-3.5 w-3.5" />
          Settings
        </Button>
        <div className="ml-auto flex rounded border border-white/10 bg-black/30 p-0.5">
          <Button
            type="button"
            size="sm"
            variant={view === "overview" ? "secondary" : "ghost"}
            className="h-7 gap-1"
            onClick={() => setView("overview")}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Overview
          </Button>
          <Button
            type="button"
            size="sm"
            variant={view === "outputs" ? "secondary" : "ghost"}
            className="h-7 gap-1"
            onClick={() => setView("outputs")}
          >
            <Terminal className="h-3.5 w-3.5" />
            Outputs
          </Button>
        </div>
      </div>

      {addJobOpen && (
        <div className="mt-2 flex flex-wrap items-end gap-2 rounded border border-white/10 bg-black/30 p-2">
          <input
            className="hww-input h-7 max-w-xs rounded px-2 text-xs"
            placeholder="Job name"
            value={jobName}
            onChange={(e) => setJobName(e.target.value)}
          />
          <input
            className="hww-input h-7 max-w-xs rounded px-2 text-xs"
            placeholder="Cron e.g. 0 * * * *"
            value={jobCron}
            onChange={(e) => setJobCron(e.target.value)}
          />
          <Button type="button" size="sm" className="h-7" onClick={() => void onAddScheduled()} disabled={!!busy}>
            Save job
          </Button>
        </div>
      )}

      {error && (
        <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100/90">
          {error}
        </div>
      )}

      {settings && view === "overview" && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          {[
            ["Agents", String(agents.length)],
            ["Scheduled", String(jobs.length)],
            ["Default model", settings.defaultModel],
          ].map(([k, v]) => (
            <div key={k} className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-center">
              <div className="text-[9px] font-semibold uppercase tracking-wide text-white/40">{k}</div>
              <div className="text-xs font-semibold text-white/90">{v}</div>
            </div>
          ))}
        </div>
      )}

      {newOpen && (
        <div className="mt-2 rounded border border-white/10 bg-black/30 p-2">
          <div className="flex flex-wrap gap-2">
            <input
              className="hww-input h-7 max-w-xs rounded px-2 text-xs"
              placeholder="Name *"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              className="hww-input h-7 max-w-xs rounded px-2 text-xs"
              placeholder="Model"
              value={newModel}
              onChange={(e) => setNewModel(e.target.value)}
            />
            <Button type="button" size="sm" className="h-7" onClick={onCreate} disabled={!newName.trim() || !!busy}>
              Create
            </Button>
          </div>
        </div>
      )}

      {loading && agents.length === 0 && <p className="mt-2 text-[11px] text-white/40">Loading…</p>}

      {view === "overview" && (
        <div className="mt-3 min-h-0 flex-1">
          <p className="text-[10px] font-semibold uppercase text-white/40">Agent cards</p>
          <ul className="mt-1 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {agents.length === 0 && !loading && (
              <li className="text-[11px] text-white/40">No agents yet. Create one or use New agent.</li>
            )}
            {agents.map((ag) => (
              <li
                key={ag.id}
                className="flex flex-col rounded border border-white/10 bg-black/20 p-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    className="text-left text-sm font-medium text-amber-100/90 hover:underline"
                    onClick={() => openDetail(ag)}
                  >
                    {ag.name}
                  </button>
                  <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase", statusBadge(ag.status))}>
                    {ag.status}
                  </span>
                </div>
                <p className="mt-0.5 text-[10px] text-white/50">Model: {ag.model}</p>
                <p className="text-[10px] text-white/40">
                  Cron: {ag.cronEnabled ? ag.cronExpr || "(empty)" : "off"}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-7"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy(ag.id);
                      const { error: err } = await workspaceOperationsAdapter.play(ag.id);
                      setBusy(null);
                      if (err) setError(err);
                      else void load();
                    }}
                  >
                    <Play className="h-3.5 w-3.5" />
                    Play
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-7"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy(ag.id);
                      const { error: err } = await workspaceOperationsAdapter.pause(ag.id);
                      setBusy(null);
                      if (err) setError(err);
                      else void load();
                    }}
                  >
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </Button>
                </div>
              </li>
            ))}
          </ul>

          {jobs.length > 0 && (
            <div className="mt-3">
              <p className="text-[10px] font-semibold uppercase text-white/40">Cron / scheduled jobs</p>
              <ul className="mt-1 space-y-1">
                {jobs.map((j) => (
                  <li
                    key={j.id}
                    className="flex items-center justify-between rounded border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-white/80"
                  >
                    <span>{j.name}</span>
                    <span className="text-white/50">{j.cronExpr}</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 text-red-300"
                      onClick={async () => {
                        if (!window.confirm("Remove scheduled job?")) return;
                        setBusy(j.id);
                        const { error: err } = await workspaceOperationsAdapter.deleteScheduled(j.id);
                        setBusy(null);
                        if (err) setError(err);
                        else void load();
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {view === "outputs" && (
        <div className="mt-3 min-h-0 flex-1 overflow-auto rounded border border-white/10 bg-black/20 p-2">
          <p className="text-[10px] font-semibold uppercase text-white/40">Aggregated output lines (newest first)</p>
          <pre className="mt-1 max-h-[min(50vh,360px)] overflow-auto font-mono text-[10px] text-emerald-100/80">
            {allOutputLines.length === 0
              ? "—"
              : allOutputLines.map((l) => `[${fmt(l.at)}] ${l.agent}: ${l.line}`).join("\n")}
          </pre>
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="w-full max-w-md rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="text-sm font-semibold text-white/95">Agent detail</h2>
            <div className="mt-2 grid gap-2 text-xs">
              <label className="text-white/60">
                Name
                <input className="hww-input mt-0.5 w-full" value={formName} onChange={(e) => setFormName(e.target.value)} />
              </label>
              <label className="text-white/60">
                Model
                <input className="hww-input mt-0.5 w-full" value={formModel} onChange={(e) => setFormModel(e.target.value)} />
              </label>
              <label className="flex items-center gap-2 text-white/60">
                <input type="checkbox" checked={formCronOn} onChange={(e) => setFormCronOn(e.target.checked)} />
                Cron enabled
              </label>
              <label className="text-white/60">
                Cron expression
                <input className="hww-input mt-0.5 w-full" value={formCron} onChange={(e) => setFormCron(e.target.value)} />
              </label>
            </div>
            <div className="mt-2 text-[10px] text-white/40">Outputs ({detail.outputs.length} lines)</div>
            <pre className="mt-1 max-h-32 overflow-auto rounded border border-white/10 bg-black/40 p-2 font-mono text-[9px] text-white/70">
              {detail.outputs
                .slice()
                .sort((a, b) => a.at - b.at)
                .map((o) => `${fmt(o.at)}  ${o.line}`)
                .join("\n") || "—"}
            </pre>
            <div className="mt-3 flex flex-wrap justify-between gap-2">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="text-red-300"
                onClick={() => void deleteAgent(detail.id)}
                disabled={!!busy}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => setDetail(null)}>
                  Close
                </Button>
                <Button type="button" size="sm" onClick={() => void saveDetail()} disabled={!!busy}>
                  Save
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="w-full max-w-md rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="text-sm font-semibold text-white/95">Operations settings</h2>
            <div className="mt-2 grid gap-2 text-xs">
              <label className="text-white/60">
                Default model
                <input
                  className="hww-input mt-0.5 w-full"
                  value={sDraft.defaultModel}
                  onChange={(e) => setSDraft((s) => ({ ...s, defaultModel: e.target.value }))}
                />
              </label>
              <label className="text-white/60">
                Output retention (lines)
                <input
                  type="number"
                  className="hww-input mt-0.5 w-full"
                  value={sDraft.outputsRetention}
                  onChange={(e) => setSDraft((s) => ({ ...s, outputsRetention: Number(e.target.value) }))}
                />
              </label>
              <label className="text-white/60">
                Notes
                <textarea
                  className="hww-input mt-0.5 min-h-[64px] w-full"
                  value={sDraft.notes}
                  onChange={(e) => setSDraft((s) => ({ ...s, notes: e.target.value }))}
                />
              </label>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setSettingsOpen(false)}>
                Cancel
              </Button>
              <Button type="button" size="sm" onClick={() => void saveOpsSettings()} disabled={!!busy}>
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
