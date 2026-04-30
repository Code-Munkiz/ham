import * as React from "react";
import {
  ArrowRight,
  BookOpen,
  ChevronDown,
  Hammer,
  Loader2,
  RefreshCw,
  Rocket,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HwwText, hwwCentsToEstTokens, hwwCentsToUsd } from "../../hwwText";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import {
  workspaceConductorAdapter,
  type ConductorSettings,
  type MissionPhase,
  type QuickAction,
  type WorkspaceMission,
} from "../../adapters/conductorAdapter";
import { WorkspaceManagedMissionsLivePanel } from "../../components/WorkspaceManagedMissionsLivePanel";
import { WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";

/**
 * Upstream shape: `src/screens/gateway/conductor.tsx` — quick presets + optional goal title.
 * Mirrored for copy/placement; runtime goes through HAM /api/workspace/conductor only.
 */
const QUICK_ACTIONS: { id: QuickAction; label: string; icon: React.ElementType; prompt: string }[] = [
  {
    id: "research",
    label: "Research",
    icon: BookOpen,
    prompt: "Research the problem space, gather constraints, compare approaches, and propose the most viable plan.",
  },
  {
    id: "build",
    label: "Build",
    icon: Hammer,
    prompt: "Build the requested feature end-to-end, including implementation, validation, and a concise delivery summary.",
  },
  {
    id: "review",
    label: "Review",
    icon: ShieldCheck,
    prompt: "Review the current implementation for correctness, regressions, missing tests, and release risks.",
  },
  {
    id: "deploy",
    label: "Deploy",
    icon: Rocket,
    prompt: "Prepare the work for deployment, verify readiness, and summarize any operational follow-ups.",
  },
];

const AGENT_NAMES = ["Nova", "Pixel", "Blaze", "Echo", "Sage", "Drift", "Flux", "Volt"];
const AGENT_EMOJIS = ["🤖", "⚡", "🔥", "🌊", "🌿", "💫", "🔮", "⭐"];
const BLENDED_COST_PER_MILLION_TOKENS = 5;

const PLANNING_STEPS = ["Planning the mission…", "Analyzing requirements…", "Preparing agents…", "Writing the spec…"];
const WORKING_STEPS = [
  "📋 Reviewing the brief…",
  "🔍 Scanning existing patterns…",
  "✏️ Drafting the implementation…",
  "🧠 Thinking through edge cases…",
  "🚀 Almost there…",
];

const OFFICE_PLACEHOLDERS = ["Nova", "Pixel", "Blaze"];

const ACTIVITY_PAGE_SIZE = 3;

type HistoryFilter = "all" | "completed" | "failed";

function getAgentPersona(index: number) {
  return { name: AGENT_NAMES[index % AGENT_NAMES.length]!, emoji: AGENT_EMOJIS[index % AGENT_EMOJIS.length]! };
}

function estimateTokenCost(totalTokens: number): number {
  return (Math.max(0, totalTokens) / 1_000_000) * BLENDED_COST_PER_MILLION_TOKENS;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(value >= 0.1 ? 2 : 3)}`;
}

function getShortModelName(model: string | null | undefined): string {
  if (!model) return "Unknown";
  const parts = model.split("/");
  return parts[parts.length - 1] || model;
}

function formatElapsedMs(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function formatRelativeTime(iso: string | null | undefined, now: number) {
  if (!iso) return "just now";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "just now";
  const d = Math.max(0, Math.floor((now - t) / 1000));
  if (d < 10) return "just now";
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
}

type MissionCostWorker = {
  id: string;
  label: string;
  totalTokens: number;
  personaEmoji: string;
  personaName: string;
};

function MissionCostSection({
  totalTokens,
  workers,
  expanded,
  onToggle,
}: {
  totalTokens: number;
  workers: MissionCostWorker[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const estimatedCost = estimateTokenCost(totalTokens);
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-5 py-4">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex w-full items-start justify-between gap-4 text-left">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Mission Cost</p>
          <p className="mt-1 text-sm text-[var(--theme-muted-2)]">Approximate at $5 / 1M tokens blended from input/output pricing.</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] px-3 py-2 text-xs font-medium text-[var(--theme-text)]">
          {expanded ? "Hide" : "Show"}
          <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", expanded && "rotate-180")} />
        </span>
      </button>
      {expanded ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--theme-muted)]">Total Tokens</p>
              <p className="mt-2 text-2xl font-semibold text-[var(--theme-text)]">{totalTokens.toLocaleString()}</p>
            </div>
            <div className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--theme-muted)]">Estimated Cost</p>
              <p className="mt-2 text-2xl font-semibold text-[var(--theme-text)]">{formatUsd(estimatedCost)}</p>
            </div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]">
            <div className="flex items-center justify-between border-b border-[var(--theme-border)] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--theme-muted)]">
              <span>Workers</span>
              <span>Cost</span>
            </div>
            {workers.length > 0 ? (
              <div className="divide-y divide-[var(--theme-border)]">
                {workers.map((w) => (
                  <div key={w.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                    <span className="font-medium text-[var(--theme-text)]">
                      {w.personaEmoji} {w.personaName}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[var(--theme-muted)]">{w.label}</span>
                    <span className="text-xs text-[var(--theme-muted)]">{w.totalTokens.toLocaleString()} tok</span>
                    <span className="min-w-[4.5rem] text-right font-medium text-[var(--theme-text)]">
                      {formatUsd(estimateTokenCost(w.totalTokens))}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-4 py-3 text-sm text-[var(--theme-muted)]">Per-worker token details were not captured for this mission.</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CyclingStatus({ steps, intervalMs = 3000 }: { steps: string[]; intervalMs?: number }) {
  const [step, setStep] = React.useState(0);
  React.useEffect(() => {
    const t = window.setInterval(() => setStep((c) => (c + 1) % steps.length), intervalMs);
    return () => window.clearInterval(t);
  }, [intervalMs, steps.length]);
  return (
    <div className="flex items-center gap-3 py-3">
      <div className="size-3.5 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
      <p className="text-sm text-[var(--theme-muted)] transition-opacity duration-500">{steps[step]}</p>
    </div>
  );
}

function PlanningBlock() {
  return <CyclingStatus steps={PLANNING_STEPS} intervalMs={2500} />;
}

type WorkerStatus = "running" | "complete" | "stale" | "idle";

function getWorkerBorderClass(st: WorkerStatus) {
  if (st === "complete") return "border-l-emerald-400";
  if (st === "running") return "border-l-sky-400";
  if (st === "idle") return "border-l-amber-400";
  return "border-l-red-400";
}

function getWorkerDot(st: WorkerStatus) {
  if (st === "complete") return { dot: "bg-emerald-400", label: "Complete" as const };
  if (st === "running") return { dot: "bg-sky-400 animate-pulse", label: "Running" as const };
  if (st === "idle") return { dot: "bg-amber-400", label: "Idle" as const };
  return { dot: "bg-red-400", label: "Stale" as const };
}

const WORKER_LABELS = ["Worker α", "Worker β", "Worker γ", "Worker δ"];

function splitOutputLines(
  lines: { at: number; line: string }[],
): { at: number; line: string }[][] {
  const sorted = [...lines].sort((a, b) => a.at - b.at);
  const buckets: { at: number; line: string }[][] = [[], [], [], []];
  sorted.forEach((ln, i) => {
    buckets[i % 4]!.push(ln);
  });
  return buckets;
}

function ConductorWorkerCard({
  index,
  label,
  model,
  status,
  output,
  now,
  missionCreatedAtMs,
  lastUpdateMs,
}: {
  index: number;
  label: string;
  model: string;
  status: WorkerStatus;
  output: string;
  now: number;
  missionCreatedAtMs: number;
  lastUpdateMs: number;
}) {
  const persona = getAgentPersona(index);
  const dot = getWorkerDot(status);
  const border = getWorkerBorderClass(status);
  const lastSeg = output.trim();
  return (
    <div className={cn("overflow-hidden rounded-2xl border border-[var(--theme-border)] border-l-4 bg-[var(--theme-card)] px-4 py-3", border)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("size-2.5 rounded-full", dot.dot)} />
            <p className="truncate text-sm font-medium text-[var(--theme-text)]">
              {persona.emoji} {persona.name} <span className="text-[var(--theme-muted)]">·</span> {label}
            </p>
          </div>
          <p className="mt-1 text-xs text-[var(--theme-muted-2)]">Task worker lane</p>
        </div>
        <span className="rounded-full border border-[var(--theme-border)] bg-[var(--theme-card2)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--theme-muted)]">
          {dot.label}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] px-3 py-2">
          <p className="text-[var(--theme-muted)]">Model</p>
          <p className="mt-1 truncate text-[var(--theme-text)]">{getShortModelName(model)}</p>
        </div>
        <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] px-3 py-2">
          <p className="text-[var(--theme-muted)]">Tokens</p>
          <p className="mt-1 text-[var(--theme-text)]">—</p>
        </div>
        <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] px-3 py-2">
          <p className="text-[var(--theme-muted)]">Elapsed</p>
          <p className="mt-1 text-[var(--theme-text)]">{formatElapsedMs(Math.max(0, now - missionCreatedAtMs))}</p>
        </div>
        <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] px-3 py-2">
          <p className="text-[var(--theme-muted)]">Last update</p>
          <p className="mt-1 text-[var(--theme-text)]">{formatRelativeTime(new Date(lastUpdateMs).toISOString(), now)}</p>
        </div>
      </div>
      <div className="mt-3 overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-4">
        {lastSeg ? (
          <div className="max-h-[400px] max-w-none overflow-auto text-sm text-[var(--theme-text)]">
            <HwwText text={lastSeg} />
          </div>
        ) : (
          <CyclingStatus steps={WORKING_STEPS} intervalMs={3500} />
        )}
      </div>
    </div>
  );
}

type OfficeRow = {
  id: string;
  name: string;
  modelId: string;
  lastLine: string;
  status: "active" | "idle" | "error" | "spawning" | "paused";
};

function ConductorOfficeStrip({ rows, height, missionRunning }: { rows: OfficeRow[]; height: number; missionRunning: boolean }) {
  return (
    <section
      className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] shadow-[0_24px_80px_var(--theme-shadow)]"
      style={{ minHeight: height, height }}
    >
      <div className="hww-scroll h-full overflow-y-auto p-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {rows.map((r) => {
            const meta =
              r.status === "active"
                ? { label: "Active", ring: "bg-emerald-500", pulse: missionRunning }
                : r.status === "spawning"
                  ? { label: "Starting", ring: "bg-sky-500", pulse: true }
                  : r.status === "error"
                    ? { label: "Error", ring: "bg-red-500", pulse: false }
                    : r.status === "paused"
                      ? { label: "Paused", ring: "bg-amber-500", pulse: false }
                      : { label: "Idle", ring: "bg-zinc-400", pulse: false };
            return (
              <div key={r.id} className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className={cn("size-2.5 rounded-full", meta.ring, meta.pulse && "animate-pulse")} />
                    <span className="truncate text-sm font-medium text-[var(--theme-text)]">{r.name}</span>
                  </div>
                  <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-[var(--theme-muted)]">{meta.label}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--theme-muted-2)]">{r.modelId}</p>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--theme-muted)]">{r.lastLine || "—"}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function missionToFilter(m: WorkspaceMission, f: HistoryFilter) {
  if (f === "all") return true;
  if (f === "completed") return m.phase === "completed";
  return m.phase === "failed";
}

function phaseToUi(phase: MissionPhase): "home" | "preview" | "active" | "complete" {
  if (phase === "draft") return "preview";
  if (phase === "running") return "active";
  return "complete";
}

export function WorkspaceConductorScreen() {
  const [missions, setMissions] = React.useState<WorkspaceMission[]>([]);
  const [settings, setSettings] = React.useState<ConductorSettings | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [missionModalOpen, setMissionModalOpen] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [goalDraft, setGoalDraft] = React.useState("");
  const [selectedAction, setSelectedAction] = React.useState<QuickAction>("build");
  const [activityFilter, setActivityFilter] = React.useState<HistoryFilter>("all");
  const [activityPage, setActivityPage] = React.useState(0);
  const [completeCostExpanded, setCompleteCostExpanded] = React.useState(true);
  const [sDraft, setSDraft] = React.useState({ budgetCents: 10_000, defaultModel: "ham-local", notes: "" });
  const [now, setNow] = React.useState(() => Date.now());
  const [managedLiveRefresh, setManagedLiveRefresh] = React.useState(0);

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

  React.useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const bumpManagedAndLoad = React.useCallback(() => {
    setManagedLiveRefresh((n) => n + 1);
    void load();
  }, [load]);

  const selected = missions.find((m) => m.id === selectedId) ?? null;
  const uiKind: "home" | "missing" | "preview" | "active" | "complete" = !selectedId
    ? "home"
    : !selected
      ? "missing"
      : phaseToUi(selected.phase);

  const totalTokEst = (m: WorkspaceMission) => hwwCentsToEstTokens(m.costCents);

  const costWorkers = React.useMemo((): MissionCostWorker[] => {
    if (!selected) return [];
    const tt = totalTokEst(selected);
    const base = Math.max(0, Math.floor(tt / 4));
    const rem = Math.max(0, tt - base * 4);
    return [0, 1, 2, 3].map((i) => {
      const p = getAgentPersona(i);
      return {
        id: `w-${i}`,
        label: WORKER_LABELS[i] ?? `Worker ${i + 1}`,
        totalTokens: base + (i < rem ? 1 : 0),
        personaEmoji: p.emoji,
        personaName: p.name,
      };
    });
  }, [selected]);

  const homeOfficeRows: OfficeRow[] = React.useMemo(() => {
    const running = missions.find((m) => m.phase === "running" || m.phase === "draft");
    if (running) {
      const last = running.outputs
        .slice()
        .sort((a, b) => b.at - a.at)[0];
      return OFFICE_PLACEHOLDERS.map((name, i) => ({
        id: `p-${i}`,
        name,
        modelId: running.quickAction ? `${running.quickAction}` : settings?.defaultModel ?? "auto",
        lastLine: i === 0 && last ? last.line : "Waiting for work…",
        status: i === 0 && running.phase === "running" ? "active" : "idle",
      }));
    }
    return OFFICE_PLACEHOLDERS.map((name, i) => ({
      id: `p-${i}`,
      name,
      modelId: settings?.defaultModel ?? "auto",
      lastLine: "Waiting for work…",
      status: "idle" as const,
    }));
  }, [missions, settings?.defaultModel]);

  const activeOfficeRows: OfficeRow[] = React.useMemo(() => {
    if (!selected || selected.phase !== "running") return homeOfficeRows;
    const last = selected.outputs
      .slice()
      .sort((a, b) => b.at - a.at)[0];
    return OFFICE_PLACEHOLDERS.map((name, i) => ({
      id: `a-${i}`,
      name,
      modelId: selected.quickAction ? String(selected.quickAction) : settings?.defaultModel ?? "auto",
      lastLine: i === 0 && last ? last.line : "Coordinating…",
      status: "active" as const,
    }));
  }, [selected, settings?.defaultModel, homeOfficeRows]);

  const activityBase = React.useMemo(() => {
    return [...missions].filter((m) => missionToFilter(m, activityFilter)).sort((a, b) => b.updatedAt - a.updatedAt);
  }, [missions, activityFilter]);
  const activityTotalPages = Math.max(1, Math.ceil(activityBase.length / ACTIVITY_PAGE_SIZE));
  const safeActivityPage = Math.min(activityPage, activityTotalPages - 1);
  const visibleMissions = activityBase.slice(
    safeActivityPage * ACTIVITY_PAGE_SIZE,
    (safeActivityPage + 1) * ACTIVITY_PAGE_SIZE,
  );

  const saveSettings = async () => {
    setBusy("s");
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

  const handleNewMission = () => {
    setSelectedId(null);
    setGoalDraft("");
  };

  const handleQuick = (a: (typeof QUICK_ACTIONS)[number]) => {
    setSelectedAction(a.id);
    setGoalDraft((c) => {
      const t = c.trim();
      if (!t) return `${a.label}: `;
      if (t.toLowerCase().startsWith(`${a.label.toLowerCase()}:`)) return c;
      return `${a.label}: ${t}`;
    });
  };

  const handleCreateFromModal = async () => {
    const t = goalDraft.trim();
    if (!t) return;
    setBusy("new");
    const { mission, error: err } = await workspaceConductorAdapter.create(t, t, selectedAction);
    setBusy(null);
    if (err) setError(err);
    else {
      setMissionModalOpen(false);
      setGoalDraft("");
      if (mission) {
        setSelectedId(mission.id);
        void load();
      }
    }
  };

  const runSelected = async () => {
    if (!selected) return;
    setBusy("run");
    const { error: err } = await workspaceConductorAdapter.run(selected.id);
    setBusy(null);
    if (err) setError(err);
    else void load();
  };

  const failSelected = async () => {
    if (!selected) return;
    if (!window.confirm("Stop mission and mark failed?")) return;
    setBusy("fail");
    const { error: err } = await workspaceConductorAdapter.fail(selected.id);
    setBusy(null);
    if (err) setError(err);
    else void load();
  };

  const onDelete = async (id: string) => {
    if (!window.confirm("Remove this mission?")) return;
    setBusy("d");
    const { error: err } = await workspaceConductorAdapter.delete(id);
    setBusy(null);
    if (err) setError(err);
    else {
      if (selectedId === id) setSelectedId(null);
      void load();
    }
  };

  const outputJoined = (m: WorkspaceMission) =>
    m.outputs
      .slice()
      .sort((a, b) => a.at - b.at)
      .map((o) => o.line)
      .join("\n\n");
  const completeSummary = (m: WorkspaceMission) => {
    const fail = m.phase === "failed";
    const lines = [
      fail ? "Mission stopped" : "Mission completed",
      "",
      `**Goal:** ${m.title}`,
      `**Duration:** ${formatElapsedMs((m.updatedAt - m.createdAt) * 1000)}`,
      `**Est. spend:** ${hwwCentsToUsd(m.costCents)} · ~${hwwCentsToEstTokens(m.costCents).toLocaleString()} tok`,
    ];
    return lines.join("\n");
  };

  const root = (inner: React.ReactNode) => (
    <div className="flex min-h-full min-w-0 flex-col overflow-y-auto bg-[var(--theme-bg)] text-[var(--theme-text)]" style={HWS_PARITY_THEME}>
      {inner}
    </div>
  );

  if (loading && missions.length === 0) {
    return root(
      <main className="mx-auto flex w-full max-w-[760px] flex-1 flex-col items-center justify-center px-4 py-16 text-sm text-[var(--theme-muted)]">
        <Loader2 className="mb-2 h-5 w-5 animate-spin" />
        Loading Conductor…
      </main>,
    );
  }

  if (uiKind === "home") {
    return root(
      <>
        <main className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col items-stretch justify-center px-4 py-4 md:px-6 md:py-6">
          {error && (
            <div className="mb-4">
              <WorkspaceSurfaceStateCard
                title="Conductor is temporarily unavailable"
                description="Mission supervision is unavailable right now. Retry to reconnect."
                tone="amber"
                technicalDetail={error}
                primaryAction={
                  <Button
                    type="button"
                    size="sm"
                    className="bg-[var(--theme-accent)] text-white hover:bg-[var(--theme-accent-strong)]"
                    onClick={() => bumpManagedAndLoad()}
                    disabled={!!busy}
                  >
                    Retry
                  </Button>
                }
              />
            </div>
          )}
          <WorkspaceManagedMissionsLivePanel refreshSignal={managedLiveRefresh} variant="conductor" />
          <div className="w-full space-y-6">
            <div className="space-y-2 text-center">
              <div className="relative flex items-center justify-center">
                <div className="inline-flex items-center gap-2.5 rounded-full border border-[var(--theme-border)] bg-[var(--theme-card)] px-5 py-2.5 text-sm font-semibold uppercase tracking-[0.24em] text-[var(--theme-muted)]">
                  Conductor
                  <span className="size-2.5 rounded-full bg-emerald-400" />
                </div>
                <div className="absolute right-0 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => bumpManagedAndLoad()}
                    className="inline-flex size-9 items-center justify-center rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-0 text-[var(--theme-muted)] hover:border-[var(--theme-accent)]"
                    aria-label="Sync"
                    disabled={!!busy}
                  >
                    <RefreshCw className={cn("h-4 w-4", busy && "animate-spin")} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setMissionModalOpen(true)}
                    className="inline-flex size-9 items-center justify-center rounded-xl bg-[var(--theme-accent)] p-0 text-white shadow-sm hover:bg-[var(--theme-accent-strong)]"
                    aria-label="New Mission"
                  >
                    <Rocket className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setSettingsOpen(true)}
                    className="inline-flex size-9 items-center justify-center rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-0 text-[var(--theme-muted)] hover:border-[var(--theme-accent)]"
                    aria-label="Conductor settings"
                  >
                    <Settings className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <p className="text-sm text-[var(--theme-muted-2)]">
                Supervise active Cloud Agent missions, then coordinate local agents for follow-up work.
              </p>
            </div>

            <section className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Mission surfaces</p>
              <div className="mt-2 grid gap-2 text-sm text-[var(--theme-muted-2)] sm:grid-cols-2">
                <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2">
                  <p className="font-medium text-[var(--theme-text)]">Cloud Agent missions</p>
                  <p className="mt-1 text-xs">Live mission status, checkpoints, outputs, and controls.</p>
                </div>
                <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2">
                  <p className="font-medium text-[var(--theme-text)]">Local agents</p>
                  <p className="mt-1 text-xs">Conductor worker activity and local execution progress.</p>
                </div>
              </div>
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--theme-muted)]">Local agent activity</h2>
                <span className="text-[10px] text-[var(--theme-muted-2)]">Local Conductor workers</span>
              </div>
              <ConductorOfficeStrip
                rows={homeOfficeRows}
                height={520}
                missionRunning={homeOfficeRows.some((r) => r.status === "active")}
              />
            </section>

            <section className="mt-6 w-full space-y-3">
                <div className="flex items-center gap-3">
                  <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--theme-muted)]">Local mission history</h2>
                  {activityTotalPages > 1 && (
                    <div className="ml-auto flex items-center gap-1.5">
                      <span className="text-[10px] text-[var(--theme-muted-2)]">
                        {safeActivityPage + 1}/{activityTotalPages}
                      </span>
                      <button
                        type="button"
                        disabled={safeActivityPage === 0}
                        onClick={() => setActivityPage((p) => Math.max(0, p - 1))}
                        className="inline-flex size-6 items-center justify-center rounded-lg border border-[var(--theme-border)] text-xs text-[var(--theme-muted)] hover:border-[var(--theme-accent)] disabled:opacity-30"
                      >
                        ‹
                      </button>
                      <button
                        type="button"
                        disabled={safeActivityPage >= activityTotalPages - 1}
                        onClick={() => setActivityPage((p) => Math.min(activityTotalPages - 1, p + 1))}
                        className="inline-flex size-6 items-center justify-center rounded-lg border border-[var(--theme-border)] text-xs text-[var(--theme-muted)] hover:border-[var(--theme-accent)] disabled:opacity-30"
                      >
                        ›
                      </button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {(["all", "completed", "failed"] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => {
                        setActivityFilter(f);
                        setActivityPage(0);
                      }}
                      className={cn(
                        "rounded-full border px-3 py-1 text-[11px] font-medium capitalize transition-colors",
                        activityFilter === f
                          ? "border-[var(--theme-accent)] bg-[var(--theme-accent-soft)] text-[var(--theme-accent-strong)]"
                          : "border-[var(--theme-border)] text-[var(--theme-muted-2)] hover:border-[var(--theme-accent)] hover:text-[var(--theme-text)]",
                      )}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                {visibleMissions.length > 0 ? (
                  <div className="min-h-[140px] space-y-1.5">
                    {visibleMissions.map((entry) => (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={() => setSelectedId(entry.id)}
                        className="flex w-full items-center gap-3 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-3 py-2 text-left text-sm transition-colors hover:border-[var(--theme-accent)]"
                      >
                        <span className="min-w-0 flex-1 truncate font-medium text-[var(--theme-text)]">{entry.title}</span>
                        <span
                          className={cn(
                            "w-[76px] shrink-0 rounded-full border px-2 py-0.5 text-center text-[10px] font-medium uppercase tracking-[0.12em]",
                            entry.phase === "completed"
                              ? "border-emerald-400/35 bg-emerald-500/10 text-emerald-300"
                              : entry.phase === "failed"
                                ? "border-red-400/35 bg-red-500/10 text-red-300"
                                : "border-sky-400/35 bg-sky-500/10 text-sky-300",
                          )}
                        >
                          {entry.phase === "completed" ? "Complete" : entry.phase === "failed" ? "Failed" : entry.phase}
                        </span>
                        <span className="w-[52px] shrink-0 text-right text-xs text-[var(--theme-muted-2)]">
                          {formatRelativeTime(new Date(entry.updatedAt * 1000).toISOString(), now)}
                        </span>
                        <span className="w-[72px] shrink-0 text-right text-xs text-[var(--theme-muted)]">
                          {hwwCentsToEstTokens(entry.costCents).toLocaleString()} tok
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-8 text-center text-sm">
                    <p className="font-medium text-[var(--theme-text)]">No active mission</p>
                    <p className="mt-2 text-[var(--theme-muted)]">
                      {activityFilter === "all"
                        ? "No active Cloud Agent missions. Launch a mission from Chat or start one here."
                        : `No ${activityFilter} missions. Try another filter or create a mission.`}
                    </p>
                  </div>
                )}
              </section>
          </div>
        </main>

        {missionModalOpen ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--theme-bg)_48%,transparent)] px-4 py-6 backdrop-blur-md"
            onClick={() => setMissionModalOpen(false)}
            style={HWS_PARITY_THEME}
          >
            <div
              className="w-full max-w-2xl rounded-3xl border border-[var(--theme-border2)] bg-[var(--theme-card)] p-5 shadow-[0_24px_80px_var(--theme-shadow)] sm:p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold tracking-tight text-[var(--theme-text)]">New Mission</h2>
                  <p className="mt-1 text-sm text-[var(--theme-muted-2)]">Describe the mission, constraints, and desired outcome.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setMissionModalOpen(false)}
                  className="inline-flex size-9 items-center justify-center rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] text-lg text-[var(--theme-muted)] hover:border-[var(--theme-accent)]"
                  aria-label="Close"
                >
                  ×
                </button>
              </div>
              <form
                className="mt-5 space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleCreateFromModal();
                }}
              >
                <div className="flex flex-wrap gap-2">
                  {QUICK_ACTIONS.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => handleQuick(a)}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                        selectedAction === a.id
                          ? "border-[var(--theme-accent)] bg-[var(--theme-accent-soft)] text-[var(--theme-accent-strong)]"
                          : "border-[var(--theme-border)] text-[var(--theme-muted)] hover:border-[var(--theme-accent)]",
                      )}
                    >
                      <a.icon className="h-3.5 w-3.5" />
                      {a.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={goalDraft}
                  onChange={(e) => setGoalDraft(e.target.value)}
                  placeholder={`${QUICK_ACTIONS.find((q) => q.id === selectedAction)?.label ?? "Build"}: describe the mission, constraints, and desired outcome.`}
                  disabled={!!busy}
                  rows={8}
                  className="min-h-[220px] w-full rounded-3xl border border-[var(--theme-border2)] bg-[var(--theme-bg)] px-4 py-4 text-sm text-[var(--theme-text)] outline-none placeholder:text-[var(--theme-muted-2)] focus:border-[var(--theme-accent)] disabled:opacity-50"
                />
                <div className="flex justify-end">
                  <Button
                    type="submit"
                    disabled={!goalDraft.trim() || !!busy}
                    className="rounded-full bg-[var(--theme-accent)] px-5 text-white hover:bg-[var(--theme-accent-strong)]"
                  >
                    {busy ? "Launching…" : "Launch Mission"}
                    <ArrowRight className="ml-1 h-4 w-4" />
                  </Button>
                </div>
              </form>
            </div>
          </div>
        ) : null}

        {settingsOpen ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[color-mix(in_srgb,var(--theme-bg)_55%,transparent)] px-4 py-6 backdrop-blur-md"
            onClick={() => setSettingsOpen(false)}
            style={HWS_PARITY_THEME}
          >
            <div
              className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-[var(--theme-border2)] bg-[var(--theme-card)] p-5 sm:p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Mission Defaults</p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--theme-text)]">Conductor settings</h2>
                  <p className="mt-2 text-sm text-[var(--theme-muted-2)]">Defaults for new missions and spend tracking.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSettingsOpen(false)}
                  className="inline-flex size-10 items-center justify-center rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card2)] text-lg text-[var(--theme-muted)]"
                  aria-label="Close settings"
                >
                  ×
                </button>
              </div>
              <div className="mt-6 space-y-4 text-sm">
                <label className="block space-y-1">
                  <span className="text-[var(--theme-text)]">Default model label</span>
                  <input
                    value={sDraft.defaultModel}
                    onChange={(e) => setSDraft((s) => ({ ...s, defaultModel: e.target.value }))}
                    className="w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3 text-[var(--theme-text)] outline-none focus:border-[var(--theme-accent)]"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-[var(--theme-text)]">Budget (cents)</span>
                  <input
                    type="number"
                    value={sDraft.budgetCents}
                    onChange={(e) => setSDraft((s) => ({ ...s, budgetCents: Number(e.target.value) }))}
                    className="w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3 text-[var(--theme-text)]"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-[var(--theme-text)]">Notes</span>
                  <textarea
                    value={sDraft.notes}
                    onChange={(e) => setSDraft((s) => ({ ...s, notes: e.target.value }))}
                    className="min-h-[64px] w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3 text-[var(--theme-text)]"
                  />
                </label>
              </div>
              <div className="mt-6 flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setSettingsOpen(false)}>
                  Cancel
                </Button>
                <Button type="button" onClick={() => void saveSettings()} disabled={!!busy}>
                  Save
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </>,
    );
  }

  if (uiKind === "missing") {
    return root(
      <main className="mx-auto w-full max-w-[720px] flex-1 px-4 py-10 text-center text-sm text-[var(--theme-muted)]">
        <p>Mission not found (it may have been removed).</p>
        <Button type="button" className="mt-3" onClick={() => setSelectedId(null)}>
          Back to Conductor
        </Button>
      </main>,
    );
  }

  if (uiKind === "preview" && selected) {
    return root(
      <main className="mx-auto flex min-h-0 w-full max-w-[720px] flex-1 flex-col items-stretch justify-center px-4 py-4 md:px-6 md:py-8">
        {error && (
          <WorkspaceSurfaceStateCard
            className="mb-4"
            title="Action could not complete"
            tone="amber"
            technicalDetail={error}
            primaryAction={
              <Button type="button" size="sm" variant="secondary" onClick={() => bumpManagedAndLoad()} disabled={!!busy}>
                Retry
              </Button>
            }
          />
        )}
        <div className="space-y-4">
          <button
            type="button"
            onClick={handleNewMission}
            className="inline-flex items-center gap-2 self-start rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-3 py-2 text-sm text-[var(--theme-muted)] hover:border-[var(--theme-border2)] hover:text-[var(--theme-text)]"
          >
            <span aria-hidden>←</span> Back
          </button>
          <div className="space-y-2 text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--theme-accent)]">Mission Decomposition</p>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--theme-text)]">{selected.title}</h1>
            <p className="text-sm text-[var(--theme-muted-2)]">Review the mission brief, then run when ready.</p>
          </div>
          <section className="rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-6 shadow-[0_24px_80px_var(--theme-shadow)]">
            <div className="flex items-center justify-between gap-3 border-b border-[var(--theme-border)] pb-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Mission Planning</p>
                <p className="mt-1 text-xs text-[var(--theme-muted-2)]">Review the brief before running</p>
              </div>
              <span className="animate-pulse rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300">
                Ready
              </span>
            </div>
            <div className="mt-4 min-h-[200px] overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-5 py-4">
              {selected.body ? (
                <div className="space-y-4">
                  <div className="max-h-[500px] overflow-auto text-sm text-[var(--theme-text)]">
                    <HwwText text={selected.body} />
                  </div>
                  <PlanningBlock />
                </div>
              ) : (
                <PlanningBlock />
              )}
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <Button type="button" variant="secondary" onClick={handleNewMission} className="rounded-xl" disabled={!!busy}>
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => void runSelected()}
                disabled={!!busy}
                className="rounded-xl bg-[var(--theme-accent)] text-white hover:bg-[var(--theme-accent-strong)]"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Run mission
              </Button>
            </div>
          </section>
        </div>
      </main>,
    );
  }

  if (uiKind === "active" && selected) {
    const buckets = splitOutputLines(selected.outputs);
    const completedN = buckets.filter((b) => b.length > 0).length;
    const totalW = 4;
    const missionProgress = Math.min(100, Math.round((completedN / totalW) * 100) || (selected.outputs.length > 0 ? 40 : 5));
    const missionElapsed = now - selected.createdAt * 1000;

    return root(
      <main className="mx-auto flex min-h-0 w-full max-w-[720px] flex-1 flex-col justify-center px-4 py-4 md:px-6 md:py-8">
        {error && (
          <WorkspaceSurfaceStateCard
            className="mb-4"
            title="Action could not complete"
            tone="amber"
            technicalDetail={error}
            primaryAction={
              <Button type="button" size="sm" variant="secondary" onClick={() => bumpManagedAndLoad()} disabled={!!busy}>
                Retry
              </Button>
            }
          />
        )}
        <div className="flex w-full flex-col gap-6">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--theme-border)] bg-[var(--theme-card)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--theme-muted)]">
              Conductor
              <span className="size-2.5 animate-pulse rounded-full bg-emerald-400" />
            </div>
          </div>
          <section className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-5 py-5 shadow-[0_24px_80px_var(--theme-shadow)]">
            <div className="text-center">
              <h1 className="line-clamp-2 text-xl font-semibold tracking-tight text-[var(--theme-text)] sm:text-2xl">{selected.title}</h1>
              <div className="mt-2 flex items-center justify-center gap-2 text-xs text-[var(--theme-muted)]">
                <span>{formatElapsedMs(missionElapsed)}</span>
                <span className="text-[var(--theme-border)]">·</span>
                <span>{completedN}/{totalW} with output</span>
                <span className="text-[var(--theme-border)]">·</span>
                <span>1 active</span>
              </div>
            </div>
            <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-[var(--theme-border)]">
              <div className="h-full rounded-full bg-[var(--theme-accent)] transition-[width] duration-500" style={{ width: `${missionProgress}%` }} />
            </div>
            <div className="mt-3 flex items-center justify-center gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => void failSelected()}
                disabled={!!busy}
                className="rounded-xl border border-[var(--theme-danger-border)] bg-[var(--theme-danger-soft)] px-3 text-xs text-[var(--theme-danger)]"
              >
                Stop mission
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={handleNewMission} className="text-xs text-[var(--theme-muted)]">
                Back
              </Button>
            </div>
          </section>
          <ConductorOfficeStrip rows={activeOfficeRows} height={360} missionRunning />
          <div className="space-y-4">
            {buckets.map((b, i) => {
              const text = b.map((l) => l.line).join("\n\n");
              const st: WorkerStatus = text ? "running" : "idle";
              const lastUpdateMs = b.length ? Math.max(...b.map((l) => l.at)) * 1000 : selected.updatedAt * 1000;
              return (
                <ConductorWorkerCard
                  key={i}
                  index={i}
                  label={WORKER_LABELS[i] ?? `Worker ${i + 1}`}
                  model={settings?.defaultModel ?? "auto"}
                  status={st}
                  output={text}
                  now={now}
                  missionCreatedAtMs={selected.createdAt * 1000}
                  lastUpdateMs={lastUpdateMs}
                />
              );
            })}
          </div>
        </div>
      </main>,
    );
  }

  if (uiKind === "complete" && selected) {
    const totalT = hwwCentsToEstTokens(selected.costCents);
    return root(
      <main className="mx-auto flex min-h-0 w-full max-w-[720px] flex-1 flex-col px-4 py-4 md:px-6 md:py-8">
        {error && (
          <WorkspaceSurfaceStateCard
            className="mb-4"
            title="Action could not complete"
            tone="amber"
            technicalDetail={error}
            primaryAction={
              <Button type="button" size="sm" variant="secondary" onClick={() => bumpManagedAndLoad()} disabled={!!busy}>
                Retry
              </Button>
            }
          />
        )}
        <div className="space-y-6">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--theme-border)] bg-[var(--theme-card)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--theme-muted)]">
              Conductor
              <span className="size-2.5 rounded-full bg-emerald-400" />
            </div>
          </div>
          {selected.phase === "failed" && (
            <div className="rounded-2xl border border-[var(--theme-danger-border)] bg-[var(--theme-danger-soft)] px-5 py-4">
              <p className="text-sm font-semibold text-[var(--theme-danger)]">Mission failed</p>
              <p className="mt-1 text-sm text-[var(--theme-text)]">Outputs may be partial.</p>
            </div>
          )}
          <div className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-6 shadow-[0_24px_80px_var(--theme-shadow)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p
                  className={cn(
                    "text-xs font-semibold uppercase tracking-[0.24em]",
                    selected.phase === "failed" ? "text-red-400" : "text-[var(--theme-accent)]",
                  )}
                >
                  {selected.phase === "failed" ? "Mission Stopped" : "Mission Complete"}
                </p>
                <h1 className="mt-2 text-xl font-semibold tracking-tight text-[var(--theme-text)] sm:text-2xl">{selected.title}</h1>
                <p className="mt-2 text-xs text-[var(--theme-muted-2)]">
                  4/4 workers · {formatElapsedMs((selected.updatedAt - selected.createdAt) * 1000)} elapsed
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  onClick={handleNewMission}
                  className="rounded-xl bg-[var(--theme-accent)] px-5 text-white hover:bg-[var(--theme-accent-strong)]"
                >
                  New mission
                </Button>
                <Button type="button" variant="secondary" onClick={() => setSelectedId(null)} className="rounded-xl">
                  Mission list
                </Button>
              </div>
            </div>
          </div>
          <section className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-6 shadow-[0_24px_80px_var(--theme-shadow)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Output</p>
                <p className="mt-1 text-xs text-[var(--theme-muted-2)]">Full run log (Markdown-styled)</p>
              </div>
            </div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-5 py-4">
              {outputJoined(selected) ? (
                <div className="max-h-[600px] overflow-auto text-sm text-[var(--theme-text)]">
                  <HwwText text={outputJoined(selected)} />
                </div>
              ) : (
                <p className="text-sm text-[var(--theme-muted)]">No run output on file.</p>
              )}
            </div>
          </section>
          <section className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-6 shadow-[0_24px_80px_var(--theme-shadow)]">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-muted)]">Agent summary</p>
              <span
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium",
                  selected.phase === "failed"
                    ? "border border-red-400/35 bg-red-500/10 text-red-300"
                    : "border border-emerald-400/35 bg-emerald-500/10 text-emerald-300",
                )}
              >
                {selected.phase === "failed" ? "Stopped" : "Complete"}
              </span>
            </div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-5 py-4">
              <div className="max-h-[400px] overflow-auto text-sm text-[var(--theme-text)]">
                <HwwText text={completeSummary(selected)} />
              </div>
            </div>
            {[0, 1, 2, 3].map((i) => {
              const w = getAgentPersona(i);
              return (
                <div key={i} className="mt-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm">
                  <span className="size-2 rounded-full bg-emerald-400" />
                  <span className="font-medium text-[var(--theme-text)]">
                    {w.emoji} {w.name}
                  </span>
                  <span className="text-[var(--theme-muted)]">{WORKER_LABELS[i]}</span>
                  <span className="ml-auto text-xs text-[var(--theme-muted)]">
                    {getShortModelName(settings?.defaultModel)} · {Math.floor(totalT / 4).toLocaleString()} tok
                  </span>
                </div>
              );
            })}
            {(totalT > 0 || costWorkers.length > 0) && (
              <div className="mt-4">
                <MissionCostSection
                  totalTokens={totalT}
                  workers={costWorkers}
                  expanded={completeCostExpanded}
                  onToggle={() => setCompleteCostExpanded((c) => !c)}
                />
              </div>
            )}
            {outputJoined(selected) && (
              <details className="mt-4 overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-5 py-4">
                <summary className="cursor-pointer text-xs font-medium text-[var(--theme-muted)]">Raw agent output</summary>
                <div className="mt-4 border-t border-[var(--theme-border)] pt-4">
                  <div className="max-h-[400px] overflow-auto text-sm text-[var(--theme-text)]">
                    <HwwText text={outputJoined(selected)} />
                  </div>
                </div>
              </details>
            )}
          </section>
          <div className="flex justify-end">
            <Button type="button" variant="ghost" className="text-red-300" onClick={() => void onDelete(selected.id)} disabled={!!busy}>
              Remove mission
            </Button>
          </div>
        </div>
      </main>,
    );
  }

  return null;
}
