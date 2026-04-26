import * as React from "react";
import { motion } from "motion/react";
import {
  BookOpen,
  Briefcase,
  CheckCircle2,
  CircleDot,
  Clock,
  Crown,
  Hammer,
  Home,
  Layers3,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HwwText, hwwCentsToEstTokens, hwwCentsToUsd } from "../../hwwText";
import {
  workspaceConductorAdapter,
  type ConductorSettings,
  type MissionPhase,
  type QuickAction,
  type WorkspaceMission,
} from "../../adapters/conductorAdapter";

const QUICK: { id: QuickAction; label: string; icon: React.ElementType; hint: string }[] = [
  { id: "research", label: "Research", icon: BookOpen, hint: "Scout + summarize context" },
  { id: "build", label: "Build", icon: Hammer, hint: "Plan implementation surface" },
  { id: "review", label: "Review", icon: ShieldCheck, hint: "Diff & risk scan" },
  { id: "deploy", label: "Deploy", icon: Rocket, hint: "Release checklist shell" },
];

const WORKER_PERSONAS = [
  { id: "alpha", name: "Scout", role: "Recon" },
  { id: "beta", name: "Builder", role: "Ship" },
  { id: "gamma", name: "Critic", role: "Review" },
  { id: "delta", name: "Ops", role: "Stabilize" },
] as const;

type UiPhase = "home" | "preview" | "active" | "complete";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function deriveUiPhase(m: WorkspaceMission | null): UiPhase {
  if (!m) return "home";
  if (m.phase === "draft") return "preview";
  if (m.phase === "running") return "active";
  if (m.phase === "completed" || m.phase === "failed") return "complete";
  return "home";
}

function splitOutputs(
  lines: { at: number; line: string }[],
): { name: string; role: string; id: string; lines: { at: number; line: string }[] }[] {
  const sorted = [...lines].sort((a, b) => a.at - b.at);
  const buckets: { at: number; line: string }[][] = WORKER_PERSONAS.map(() => []);
  sorted.forEach((ln, i) => {
    buckets[i % WORKER_PERSONAS.length]!.push(ln);
  });
  return WORKER_PERSONAS.map((w, i) => ({ ...w, lines: buckets[i]! }));
}

const PHASE_STEPS: { id: UiPhase; label: string; icon: React.ElementType }[] = [
  { id: "home", label: "Home", icon: Home },
  { id: "preview", label: "Preview", icon: CircleDot },
  { id: "active", label: "Active", icon: Send },
  { id: "complete", label: "Complete", icon: CheckCircle2 },
];

function missionPhaseToUiStepId(p: MissionPhase | null, hasSelection: boolean): UiPhase {
  if (!hasSelection) return "home";
  if (p === "draft") return "preview";
  if (p === "running") return "active";
  return "complete";
}

function phasePill(phase: MissionPhase) {
  const map: Record<MissionPhase, string> = {
    draft: "bg-sky-500/20 text-sky-100",
    running: "bg-amber-500/25 text-amber-100",
    completed: "bg-emerald-500/20 text-emerald-100",
    failed: "bg-red-500/20 text-red-100",
  };
  return map[phase] ?? "bg-white/10 text-white/80";
}

export function WorkspaceConductorScreen() {
  const [missions, setMissions] = React.useState<WorkspaceMission[]>([]);
  const [settings, setSettings] = React.useState<ConductorSettings | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [q, setQ] = React.useState("");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [newOpen, setNewOpen] = React.useState(false);
  const [nt, setNt] = React.useState("");
  const [nb, setNb] = React.useState("");
  const [composer, setComposer] = React.useState({ title: "", body: "" });
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [sDraft, setSDraft] = React.useState({ budgetCents: 10_000, defaultModel: "ham-local", notes: "" });
  const [listTab, setListTab] = React.useState<"active" | "history">("active");

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
  const uiPhase = deriveUiPhase(selected);
  const stepHighlight = missionPhaseToUiStepId(selected?.phase ?? null, !!selected);

  const filteredMissions = React.useMemo(() => {
    let rows = missions;
    if (q.trim()) {
      const l = q.toLowerCase();
      rows = rows.filter((m) => `${m.title} ${m.body}`.toLowerCase().includes(l));
    }
    if (listTab === "active")
      return rows.filter((m) => m.phase === "draft" || m.phase === "running");
    return rows.filter((m) => m.phase === "completed" || m.phase === "failed");
  }, [missions, q, listTab]);

  const totalCostCents = React.useMemo(
    () => missions.reduce((a, m) => a + (m.costCents || 0), 0),
    [missions],
  );
  const budgetCents = settings?.budgetCents ?? 0;
  const spendRatio = budgetCents > 0 ? Math.min(1, totalCostCents / budgetCents) : 0;

  const onQuick = async (quick: QuickAction) => {
    setBusy(`q-${quick}`);
    const { mission, error: err } = await workspaceConductorAdapter.createQuick(quick);
    setBusy(null);
    if (err) setError(err);
    else if (mission) {
      setSelectedId(mission.id);
      setListTab("active");
      void load();
    }
  };

  const onCreate = async () => {
    if (!nt.trim()) return;
    setBusy("new");
    const { mission, error: err } = await workspaceConductorAdapter.create(nt.trim(), nb, null);
    setBusy(null);
    if (err) setError(err);
    else {
      setNewOpen(false);
      setNt("");
      setNb("");
      if (mission) {
        setSelectedId(mission.id);
        setListTab("active");
      }
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
    if (!window.confirm("Archive / delete this mission?")) return;
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
      if (mission) {
        setSelectedId(mission.id);
        setListTab("active");
      }
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

  const outputText = selected
    ? selected.outputs
        .slice()
        .sort((a, b) => a.at - b.at)
        .map((o) => o.line)
        .join("\n\n")
    : "";
  const workers = selected ? splitOutputs(selected.outputs) : [];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-gradient-to-b from-[#0a1018] via-[#0b0f16] to-[#0a0e14] p-2 md:p-3">
      <div className="shrink-0 border-b border-white/5 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="mb-0.5 flex items-center gap-1.5">
              <p className="hww-pill">Mission room</p>
              <span className="text-[9px] text-white/35">HAM bridge · v0</span>
            </div>
            <h1 className="flex items-center gap-1.5 text-base font-semibold tracking-tight text-white/95">
              <Crown className="h-4 w-4 text-amber-400/80" />
              Conductor
            </h1>
            <p className="mt-0.5 max-w-2xl text-[11px] text-white/45">
              Gateway-grade layout over HAM <code className="text-white/50">/api/workspace/conductor</code> — no upstream
              proxy; state in <code className="text-white/50">.ham/workspace_state/conductor.json</code>.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Sync
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 border-white/10 bg-black/20 text-amber-200/90 hover:bg-white/5"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 className="h-3.5 w-3.5" />
              Budget
            </Button>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1">
            {PHASE_STEPS.map((s) => {
              const active = s.id === stepHighlight;
              const Icon = s.icon;
              return (
                <div
                  key={s.id}
                  className={cn(
                    "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors",
                    active
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-100"
                      : "border-white/5 bg-black/20 text-white/40",
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {s.label}
                </div>
              );
            })}
          </div>
          {settings && (
            <div className="flex items-center gap-2 text-[10px] text-white/45">
              <Sparkles className="h-3 w-3 text-amber-400/60" />
              <span>Model: {settings.defaultModel}</span>
            </div>
          )}
        </div>
      </div>

      <div className="mt-2 flex min-h-0 flex-1 flex-col gap-2 lg:grid lg:grid-cols-[16rem,1fr,15.5rem] lg:items-stretch">
        <motion.aside
          initial={false}
          className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-white/10 bg-black/30 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-2 py-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/50">Board</p>
            <Button type="button" size="sm" variant="secondary" className="h-6 gap-0.5 px-1.5 text-[10px]" onClick={() => setNewOpen((v) => !v)}>
              <Plus className="h-3 w-3" />
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-0.5 border-b border-white/10 p-1">
            <button
              type="button"
              onClick={() => setListTab("active")}
              className={cn(
                "rounded-md px-2 py-1 text-[10px] font-medium",
                listTab === "active" ? "bg-amber-500/15 text-amber-100" : "text-white/45 hover:bg-white/5",
              )}
            >
              In flight
            </button>
            <button
              type="button"
              onClick={() => setListTab("history")}
              className={cn(
                "rounded-md px-2 py-1 text-[10px] font-medium",
                listTab === "history" ? "bg-emerald-500/15 text-emerald-100" : "text-white/45 hover:bg-white/5",
              )}
            >
              History
            </button>
          </div>
          <div className="border-b border-white/10 p-1.5">
            <div className="flex items-center gap-1 rounded border border-white/10 bg-black/20 px-1.5">
              <Search className="h-3 w-3 text-white/30" />
              <input
                className="hww-input h-7 min-w-0 flex-1 border-0 p-0 text-[11px]"
                placeholder="Filter missions"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
          </div>
          {newOpen && (
            <div className="border-b border-white/10 p-2">
              <p className="text-[9px] font-semibold text-white/40">Quick insert</p>
              <div className="mt-1 grid gap-1">
                <input
                  className="hww-input rounded px-2 py-1 text-[11px]"
                  placeholder="Title *"
                  value={nt}
                  onChange={(e) => setNt(e.target.value)}
                />
                <input
                  className="hww-input rounded px-2 py-1 text-[11px]"
                  placeholder="Body"
                  value={nb}
                  onChange={(e) => setNb(e.target.value)}
                />
                <div className="flex gap-1">
                  <Button type="button" size="sm" className="h-6 text-[10px]" onClick={() => void onCreate()} disabled={!nt.trim() || !!busy}>
                    Add
                  </Button>
                </div>
              </div>
            </div>
          )}
          <ul className="hww-scroll min-h-0 flex-1 space-y-1 overflow-auto p-1.5">
            {loading && missions.length === 0 && <li className="px-1 py-2 text-[11px] text-white/40">Loading…</li>}
            {filteredMissions.length === 0 && <li className="px-1 py-2 text-[11px] text-white/40">No missions in this column.</li>}
            {filteredMissions.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(m.id)}
                  className={cn(
                    "w-full rounded-lg border px-2 py-1.5 text-left text-[11px] transition-colors",
                    selectedId === m.id
                      ? "border-amber-500/40 bg-gradient-to-r from-amber-500/10 to-transparent"
                      : "border-white/5 bg-black/20 hover:border-white/15",
                  )}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="line-clamp-1 font-medium text-white/90">{m.title}</span>
                    <span className={cn("shrink-0 rounded px-1 py-0.5 text-[8px] uppercase", phasePill(m.phase))}>
                      {m.phase}
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </motion.aside>

        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-amber-500/15 bg-gradient-to-b from-amber-500/[0.04] to-black/40 p-2 shadow-lg">
          <div className="shrink-0 border-b border-white/10 pb-2">
            <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-amber-200/50">Office · mission room</p>
            <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-white/95">
                {selected ? selected.title : "Compose a mission to enter preview"}
              </p>
              {selected && (
                <div className="flex flex-wrap gap-1">
                  <span
                    className={cn(
                      "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase",
                      selected.phase === "failed" ? "bg-red-500/20 text-red-100" : phasePill(selected.phase),
                    )}
                  >
                    <Terminal className="h-3 w-3" />
                    {uiPhase}
                  </span>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100/90">
              {error}
            </div>
          )}

          {!selected && (
            <div className="flex min-h-0 flex-1 flex-col justify-center">
              <div className="mx-auto max-w-lg text-center">
                <div className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                  <Layers3 className="h-5 w-5 text-amber-300/80" />
                </div>
                <h2 className="text-sm font-semibold text-white/95">Home — mission command</h2>
                <p className="mt-1 text-[11px] text-white/45">Define a mission, preview with Markdown-style formatting, then run against the HAM v0 worker strip.</p>
                <div className="mt-3 grid gap-2 text-left">
                  <input
                    className="hww-input rounded-md px-2 py-1.5 text-xs"
                    placeholder="Mission title"
                    value={composer.title}
                    onChange={(e) => setComposer((c) => ({ ...c, title: e.target.value }))}
                  />
                  <textarea
                    className="hww-input min-h-[100px] rounded-md px-2 py-1.5 text-xs"
                    placeholder={"## Objective\n\n- Step one\n- Step two"}
                    value={composer.body}
                    onChange={(e) => setComposer((c) => ({ ...c, body: e.target.value }))}
                  />
                  <div className="flex flex-wrap gap-1.5">
                    <Button
                      type="button"
                      size="sm"
                      className="h-8 gap-1"
                      onClick={() => void applyComposer()}
                      disabled={!!busy}
                    >
                      <Briefcase className="h-3.5 w-3.5" />
                      Open preview
                    </Button>
                    {QUICK.map(({ id, label, icon: Icon }) => (
                      <Button
                        key={id}
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="h-8 gap-1 text-[10px]"
                        disabled={!!busy}
                        onClick={() => void onQuick(id)}
                      >
                        <Icon className="h-3.5 w-3.5" />
                        {label}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {selected && (
            <div className="hww-scroll min-h-0 flex-1 space-y-2 overflow-auto pt-1">
              {uiPhase === "preview" && (
                <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
                  <p className="text-[9px] font-semibold uppercase text-sky-200/50">Preview</p>
                  <HwwText text={selected.body} className="mt-1" />
                </div>
              )}
              {(uiPhase === "active" || uiPhase === "complete") && (
                <div
                  className={cn(
                    "rounded-lg border p-2",
                    selected.phase === "failed" ? "border-red-500/30 bg-red-500/5" : "border-emerald-500/20 bg-emerald-500/5",
                  )}
                >
                  <p className="text-[9px] font-semibold uppercase text-white/40">
                    {selected.phase === "failed" ? "Run ended · failed" : "Run log · Markdown view"}
                  </p>
                  <div className="mt-1 max-h-[40vh] overflow-auto rounded border border-white/5 bg-black/30 p-2">
                    {outputText ? <HwwText text={outputText} /> : <p className="text-[11px] text-white/40">—</p>}
                  </div>
                </div>
              )}

              {selected && uiPhase === "active" && selected.phase === "running" && (
                <p className="text-[10px] text-amber-200/70">
                  <Clock className="mr-0.5 inline h-3 w-3" />
                  Synthetic run in HAM; upstream gateway would stream here.
                </p>
              )}

              {selected && (
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    type="button"
                    size="sm"
                    className="h-8"
                    disabled={
                      !!busy || selected.phase === "completed" || selected.phase === "failed" || selected.phase === "running"
                    }
                    onClick={() => void onRun(selected.id)}
                  >
                    <Rocket className="mr-1 h-3.5 w-3.5" />
                    Launch
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-8"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy("fail");
                      const { error: err } = await workspaceConductorAdapter.fail(selected.id);
                      setBusy(null);
                      if (err) setError(err);
                      else {
                        setListTab("history");
                        void load();
                      }
                    }}
                  >
                    Mark failed
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 text-red-300"
                    disabled={!!busy}
                    onClick={() => void onDelete(selected.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Remove
                  </Button>
                </div>
              )}

              {selected && (
                <div>
                  <p className="text-[9px] font-semibold uppercase text-white/40">Worker wall</p>
                  <ul className="mt-1 grid grid-cols-1 gap-1 sm:grid-cols-2">
                    {workers.map((w) => (
                      <li key={w.id} className="rounded-lg border border-white/10 bg-black/40 p-2">
                        <p className="text-[10px] font-medium text-amber-100/90">
                          {w.name}
                          <span className="text-white/40"> · {w.role}</span>
                        </p>
                        <pre className="mt-1 max-h-24 overflow-auto font-mono text-[9px] text-emerald-100/80">
                          {w.lines.length === 0
                            ? "—"
                            : w.lines
                                .map((o) => `${fmt(o.at)}  ${o.line}`)
                                .join("\n")}
                        </pre>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </main>

        <aside className="flex min-h-0 min-w-0 flex-col gap-2 overflow-hidden">
          <div className="rounded-xl border border-white/10 bg-black/30 p-2">
            <p className="text-[9px] font-semibold uppercase text-white/45">Run economics</p>
            {settings && (
              <div className="mt-1 space-y-1.5 text-[11px] text-white/70">
                <div className="flex justify-between">
                  <span className="text-white/50">Budget</span>
                  <span className="font-mono text-amber-100/90">{hwwCentsToUsd(budgetCents)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-white/50">Recorded spend</span>
                  <span className="font-mono">{hwwCentsToUsd(totalCostCents)}</span>
                </div>
                <div className="flex justify-between text-[10px]">
                  <span className="text-white/45">Est. tokens (cosmetic)</span>
                  <span className="font-mono text-white/80">{hwwCentsToEstTokens(totalCostCents).toLocaleString()}</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-amber-500/60 to-amber-300/80"
                    style={{ width: `${spendRatio * 100}%` }}
                  />
                </div>
                {selected && (
                  <div className="border-t border-white/5 pt-1 text-[10px] text-white/50">
                    This mission: {hwwCentsToUsd(selected.costCents)} · {hwwCentsToEstTokens(selected.costCents)} tok (est.)
                  </div>
                )}
              </div>
            )}
            {!settings && <p className="mt-1 text-[10px] text-white/40">Load settings to show budget.</p>}
          </div>

          <div className="hww-scroll flex-1 space-y-1.5 overflow-auto rounded-xl border border-white/10 bg-black/25 p-2">
            <p className="text-[9px] font-semibold uppercase text-white/45">Quick actions</p>
            {QUICK.map(({ id, label, icon: Icon, hint }) => (
              <Button
                key={id}
                type="button"
                size="sm"
                variant="secondary"
                className="h-auto w-full flex-col items-stretch justify-start gap-0.5 py-1.5 text-left"
                disabled={!!busy}
                onClick={() => void onQuick(id)}
              >
                <span className="flex items-center gap-1.5 text-[11px]">
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {label}
                </span>
                <span className="pl-5 text-[9px] font-normal text-white/40">{hint}</span>
              </Button>
            ))}
          </div>
        </aside>
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
