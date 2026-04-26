import * as React from "react";
import {
  BookOpen,
  Hammer,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  workspaceConductorAdapter,
  type ConductorSettings,
  type MissionPhase,
  type QuickAction,
  type WorkspaceMission,
} from "../../adapters/conductorAdapter";

const QUICK: { id: QuickAction; label: string; icon: React.ElementType }[] = [
  { id: "research", label: "Research", icon: BookOpen },
  { id: "build", label: "Build", icon: Hammer },
  { id: "review", label: "Review", icon: ShieldCheck },
  { id: "deploy", label: "Deploy", icon: Rocket },
];

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function phaseClass(p: MissionPhase) {
  switch (p) {
    case "draft":
      return "bg-white/10 text-white/80";
    case "running":
      return "bg-amber-500/25 text-amber-100";
    case "completed":
      return "bg-emerald-500/20 text-emerald-100";
    case "failed":
      return "bg-red-500/20 text-red-100";
    default:
      return "bg-white/10 text-white/80";
  }
}

export function WorkspaceConductorScreen() {
  const [missions, setMissions] = React.useState<WorkspaceMission[]>([]);
  const [settings, setSettings] = React.useState<ConductorSettings | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [phaseFilter, setPhaseFilter] = React.useState<"all" | MissionPhase | "active" | "history">("active");
  const [q, setQ] = React.useState("");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [newOpen, setNewOpen] = React.useState(false);
  const [nt, setNt] = React.useState("");
  const [nb, setNb] = React.useState("");
  const [composer, setComposer] = React.useState({ title: "", body: "" });
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [sDraft, setSDraft] = React.useState({ budgetCents: 10_000, defaultModel: "ham-local", notes: "" });

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [list, gs] = await Promise.all([workspaceConductorAdapter.list(), workspaceConductorAdapter.getSettings()]);
    if (list.bridge.status === "pending") {
      setError(list.bridge.detail);
      setMissions([]);
    } else {
      setMissions(list.missions);
    }
    if (gs.bridge.status === "ready" && gs.settings) {
      setSettings(gs.settings);
      setSDraft({
        budgetCents: gs.settings.budgetCents,
        defaultModel: gs.settings.defaultModel,
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

  const selected = missions.find((m) => m.id === selectedId) ?? null;

  const visible = React.useMemo(() => {
    let rows = missions;
    if (q.trim()) {
      const l = q.toLowerCase();
      rows = rows.filter((m) => `${m.title} ${m.body}`.toLowerCase().includes(l));
    }
    if (phaseFilter === "active")
      return rows.filter((m) => m.phase === "draft" || m.phase === "running");
    if (phaseFilter === "history")
      return rows.filter((m) => m.phase === "completed" || m.phase === "failed");
    if (phaseFilter !== "all") return rows.filter((m) => m.phase === phaseFilter);
    return rows;
  }, [missions, q, phaseFilter]);

  const onQuick = async (quick: QuickAction) => {
    setBusy(`q-${quick}`);
    const { mission, error: err } = await workspaceConductorAdapter.createQuick(quick);
    setBusy(null);
    if (err) setError(err);
    else if (mission) {
      setSelectedId(mission.id);
      void load();
    }
  };

  const onCreate = async () => {
    if (!nt.trim()) return;
    setBusy("new");
    const { mission, error: err } = await workspaceConductorAdapter.create(
      nt.trim(),
      nb,
      null,
    );
    setBusy(null);
    if (err) setError(err);
    else {
      setNewOpen(false);
      setNt("");
      setNb("");
      if (mission) setSelectedId(mission.id);
      void load();
    }
  };

  const onRun = async (id: string) => {
    setBusy(id);
    const { error: err } = await workspaceConductorAdapter.run(id);
    setBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onDelete = async (id: string) => {
    if (!window.confirm("Delete this mission?")) return;
    setBusy(id);
    const { error: err } = await workspaceConductorAdapter.delete(id);
    setBusy(null);
    if (err) setError(err);
    else {
      if (selectedId === id) setSelectedId(null);
      void load();
    }
  };

  const applyComposer = async () => {
    if (!composer.title.trim() && !composer.body.trim()) return;
    setBusy("composer");
    const t = composer.title.trim() || "Mission";
    const { mission, error: err } = await workspaceConductorAdapter.create(t, composer.body, null);
    setBusy(null);
    if (err) setError(err);
    else {
      setComposer({ title: "", body: "" });
      if (mission) setSelectedId(mission.id);
      void load();
    }
  };

  const saveSettings = async () => {
    setBusy("settings");
    const { settings: s, error: err } = await workspaceConductorAdapter.patchSettings({
      budgetCents: sDraft.budgetCents,
      defaultModel: sDraft.defaultModel,
      notes: sDraft.notes,
    });
    setBusy(null);
    if (err) setError(err);
    else {
      if (s) setSettings(s);
      setSettingsOpen(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col p-3 md:p-4">
      <div className="shrink-0">
        <p className="hww-pill mb-1">Workspace</p>
        <h1 className="text-base font-semibold text-white/95">Conductor</h1>
        <p className="mt-0.5 max-w-2xl text-[11px] text-white/45">
          COND-001…004 — Mission composer, quick actions, active/history, worker outputs, and settings. Storage{" "}
          <code className="text-white/50">.ham/workspace_state/conductor.json</code> (HAM-only; no upstream Hermes
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
          New Mission
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 border-white/10 bg-black/30 text-amber-200/90 hover:bg-white/5"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings2 className="h-3.5 w-3.5" />
          Conductor settings
        </Button>
        <div className="flex min-w-0 max-w-xs flex-1 items-center gap-1 rounded border border-white/10 bg-black/20 px-2">
          <Search className="h-3.5 w-3.5 text-white/30" />
          <input
            className="hww-input h-7 min-w-0 flex-1 border-0"
            placeholder="Filter activity"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-1 text-[10px] text-white/50">
          View
          <select
            className="hww-input h-7 rounded border border-white/10 bg-black/40 text-[11px] text-white/90"
            value={phaseFilter}
            onChange={(e) => setPhaseFilter(e.target.value as typeof phaseFilter)}
          >
            <option value="active">Active (draft + running)</option>
            <option value="history">Completed + failed</option>
            <option value="all">All phases</option>
            <option value="draft">Draft</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </label>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {QUICK.map(({ id, label, icon: Icon }) => (
          <Button
            key={id}
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 gap-1"
            disabled={!!busy}
            onClick={() => void onQuick(id)}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </Button>
        ))}
      </div>

      {error && (
        <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100/90">
          {error}
        </div>
      )}

      {settings && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {[
            ["Budget (¢)", String(settings.budgetCents)],
            ["Default model", settings.defaultModel],
            ["Missions", String(missions.length)],
            [
              "Est. cost (sum ¢)",
              String(missions.reduce((a, m) => a + (m.costCents || 0), 0)),
            ],
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
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="hww-input rounded px-2 py-1.5 text-xs"
              placeholder="Title *"
              value={nt}
              onChange={(e) => setNt(e.target.value)}
            />
            <input
              className="hww-input rounded px-2 py-1.5 text-xs"
              placeholder="Description / mission body"
              value={nb}
              onChange={(e) => setNb(e.target.value)}
            />
          </div>
          <div className="mt-2 flex gap-2">
            <Button type="button" size="sm" onClick={onCreate} disabled={!nt.trim() || !!busy}>
              Create
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setNewOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="mt-2 rounded border border-white/10 bg-black/20 p-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Mission composer</p>
        <div className="mt-1 grid gap-1.5 md:grid-cols-2">
          <input
            className="hww-input rounded px-2 py-1.5 text-xs"
            placeholder="Title"
            value={composer.title}
            onChange={(e) => setComposer((c) => ({ ...c, title: e.target.value }))}
          />
          <Button type="button" size="sm" className="h-7 w-fit" onClick={applyComposer} disabled={!!busy}>
            Create from composer
          </Button>
        </div>
        <textarea
          className="hww-input mt-1 min-h-[72px] w-full rounded px-2 py-1.5 text-xs"
          placeholder="Mission body — quick actions also seed templates via API."
          value={composer.body}
          onChange={(e) => setComposer((c) => ({ ...c, body: e.target.value }))}
        />
      </div>

      {loading && missions.length === 0 && <p className="mt-2 text-[11px] text-white/40">Loading…</p>}

      <div className="mt-3 grid min-h-0 flex-1 grid-cols-1 gap-2 lg:grid-cols-2">
        <div className="flex min-h-0 min-w-0 flex-col rounded border border-white/10 bg-black/20">
          <div className="border-b border-white/10 px-2 py-1.5 text-[10px] font-semibold uppercase text-white/50">
            Missions &amp; activity
          </div>
          <ul className="hww-scroll min-h-0 flex-1 overflow-auto p-1.5">
            {visible.length === 0 && <li className="px-1 py-2 text-[11px] text-white/40">No missions in this view.</li>}
            {visible.map((m) => (
              <li key={m.id} className="mb-1">
                <button
                  type="button"
                  onClick={() => setSelectedId(m.id)}
                  className={cn(
                    "w-full rounded border px-2 py-1.5 text-left text-xs transition-colors",
                    selectedId === m.id
                      ? "border-amber-500/50 bg-amber-500/10"
                      : "border-white/10 bg-black/20 hover:border-white/20",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-white/90">{m.title}</span>
                    <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase", phaseClass(m.phase))}>
                      {m.phase}
                    </span>
                  </div>
                  {m.body ? (
                    <p className="mt-0.5 line-clamp-2 text-[10px] text-white/45">{m.body}</p>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col rounded border border-white/10 bg-black/20">
          <div className="border-b border-white/10 px-2 py-1.5 text-[10px] font-semibold uppercase text-white/50">
            Active mission / worker output
          </div>
          {!selected && (
            <p className="p-2 text-[11px] text-white/40">Select a mission to view outputs, run, or remove.</p>
          )}
          {selected && (
            <div className="hww-scroll flex min-h-0 flex-1 flex-col overflow-auto p-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={cn("rounded px-1.5 py-0.5 text-[9px] uppercase", phaseClass(selected.phase))}>
                  {selected.phase}
                </span>
                <span className="text-[10px] text-white/45">Cost {selected.costCents} ¢</span>
                <span className="text-[10px] text-white/45">Updated {fmt(selected.updatedAt)}</span>
              </div>
              <p className="mt-1 text-sm font-medium text-white/95">{selected.title}</p>
              <p className="mt-0.5 whitespace-pre-wrap text-[11px] text-white/60">{selected.body}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                <Button
                  type="button"
                  size="sm"
                  className="h-7"
                  disabled={!!busy || selected.phase === "completed" || selected.phase === "failed" || selected.phase === "running"}
                  onClick={() => void onRun(selected.id)}
                >
                  Run mission
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="h-7"
                  disabled={!!busy}
                  onClick={async () => {
                    setBusy("fail");
                    const { error: err } = await workspaceConductorAdapter.fail(selected.id);
                    setBusy(null);
                    if (err) setError(err);
                    else void load();
                  }}
                >
                  Mark failed
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 text-red-300"
                  disabled={!!busy}
                  onClick={() => void onDelete(selected.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </Button>
              </div>
              <p className="mt-2 text-[10px] font-semibold uppercase text-white/40">Worker / mission output</p>
              <pre className="mt-1 max-h-48 overflow-auto rounded border border-white/10 bg-black/40 p-2 font-mono text-[10px] text-emerald-100/90">
                {selected.outputs.length === 0
                  ? "—"
                  : selected.outputs
                      .slice()
                      .sort((a, b) => a.at - b.at)
                      .map((o) => `${fmt(o.at)}  ${o.line}`)
                      .join("\n")}
              </pre>
            </div>
          )}
        </div>
      </div>

      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="w-full max-w-md rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="text-sm font-semibold text-white/95">Conductor settings</h2>
            <div className="mt-2 grid gap-2 text-xs">
              <label className="text-white/60">
                Budget (cents)
                <input
                  type="number"
                  className="hww-input mt-0.5 w-full"
                  value={sDraft.budgetCents}
                  onChange={(e) => setSDraft((s) => ({ ...s, budgetCents: Number(e.target.value) }))}
                />
              </label>
              <label className="text-white/60">
                Default model label
                <input
                  className="hww-input mt-0.5 w-full"
                  value={sDraft.defaultModel}
                  onChange={(e) => setSDraft((s) => ({ ...s, defaultModel: e.target.value }))}
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
              <Button type="button" size="sm" onClick={() => void saveSettings()} disabled={!!busy}>
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
