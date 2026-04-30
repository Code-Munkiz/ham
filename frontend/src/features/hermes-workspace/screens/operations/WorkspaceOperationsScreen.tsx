import * as React from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  Bot,
  Brain,
  Clock,
  LayoutGrid,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  Terminal,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HwwText } from "../../hwwText";
import { HWS_PARITY_THEME } from "../../workspaceParityTheme";
import {
  workspaceOperationsAdapter,
  type OperationsSettings,
  type ScheduledJob,
  type WorkspaceAgent,
} from "../../adapters/operationsAdapter";
import { WorkspaceManagedMissionsLivePanel } from "../../components/WorkspaceManagedMissionsLivePanel";
import { WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function fmtRelative(ts: number) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return fmt(ts);
}

function statusDotClass(s: WorkspaceAgent["status"]) {
  const base = "h-2 w-2 shrink-0 rounded-full";
  if (s === "error") return cn(base, "bg-red-500");
  if (s === "active") return cn(base, "animate-pulse bg-emerald-500");
  if (s === "paused") return cn(base, "bg-amber-400");
  return cn(base, "bg-slate-400");
}

/** Static catalog — labels only; routing stays on HAM `/api/workspace/operations`. */
const MODEL_CATALOG = [
  { id: "ham-local", label: "HAM Local (v0)" },
  { id: "gpt-4.1", label: "gpt-4.1 (label)" },
  { id: "claude-3-5-sonnet", label: "claude-3.5 (label)" },
  { id: "o4-mini", label: "o4-mini (label)" },
] as const;

const CRON_PRESETS: { label: string; expr: string }[] = [
  { label: "Hourly", expr: "0 * * * *" },
  { label: "Daily 09:00", expr: "0 9 * * *" },
  { label: "Weekdays", expr: "0 9 * * 1-5" },
];

function stripEmojiPrefix(name: string) {
  const t = name.replace(/^\p{Extended_Pictographic}[\uFE0F\u200D\p{Extended_Pictographic}]*/u, "").trim();
  return t || name;
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
  const [newEmoji, setNewEmoji] = React.useState("🤖");
  const [newPrompt, setNewPrompt] = React.useState("");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [sDraft, setSDraft] = React.useState({ defaultModel: "ham-local", outputsRetention: 50, notes: "" });
  const [detail, setDetail] = React.useState<WorkspaceAgent | null>(null);
  const [formName, setFormName] = React.useState("");
  const [formModel, setFormModel] = React.useState("");
  const [formEmoji, setFormEmoji] = React.useState("");
  const [formPrompt, setFormPrompt] = React.useState("");
  const [formCron, setFormCron] = React.useState("");
  const [formCronOn, setFormCronOn] = React.useState(false);
  const [addJobOpen, setAddJobOpen] = React.useState(false);
  const [jobName, setJobName] = React.useState("");
  const [jobCron, setJobCron] = React.useState("0 * * * *");
  const [focusId, setFocusId] = React.useState<string | null>(null);
  const [chatDraft, setChatDraft] = React.useState("");
  const [cronPanelFor, setCronPanelFor] = React.useState<string | null>(null);
  const [managedLiveRefresh, setManagedLiveRefresh] = React.useState(0);

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
    setFocusId(ag.id);
    setDetail(ag);
    setFormName(ag.name);
    setFormModel(ag.model);
    setFormEmoji(ag.emoji || "🤖");
    setFormPrompt(ag.systemPrompt || "");
    setFormCron(ag.cronExpr);
    setFormCronOn(ag.cronEnabled);
  };

  const saveDetail = async () => {
    if (!detail) return;
    setBusy(detail.id);
    const { error: err } = await workspaceOperationsAdapter.patchAgent(detail.id, {
      name: formName.trim() || detail.name,
      model: formModel,
      emoji: formEmoji.trim() || "🤖",
      systemPrompt: formPrompt,
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
      if (focusId === id) setFocusId(null);
      void load();
    }
  };

  const onCreate = async () => {
    if (!newName.trim()) return;
    setBusy("new");
    const { agent, error: err } = await workspaceOperationsAdapter.createAgent(newName.trim(), newModel, {
      emoji: newEmoji.trim() || "🤖",
      systemPrompt: newPrompt,
    });
    setBusy(null);
    if (err) setError(err);
    else {
      setNewOpen(false);
      setNewName("");
      setNewModel("ham-local");
      setNewEmoji("🤖");
      setNewPrompt("");
      if (agent) {
        setDetail(agent);
        setFocusId(agent.id);
      }
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
    const lines: { agent: string; at: number; line: string; id: string }[] = [];
    for (const ag of agents) {
      for (const o of ag.outputs) {
        lines.push({ agent: ag.name, at: o.at, line: o.line, id: ag.id });
      }
    }
    return lines.sort((a, b) => b.at - a.at);
  }, [agents]);

  const recentActivity = React.useMemo(() => allOutputLines.slice(0, 12), [allOutputLines]);

  const focusAgent = React.useMemo(() => agents.find((a) => a.id === focusId) ?? null, [agents, focusId]);

  const sendChat = async () => {
    if (!focusId || !chatDraft.trim()) return;
    setBusy(`chat-${focusId}`);
    const { error: err } = await workspaceOperationsAdapter.appendMessage(focusId, chatDraft.trim());
    setBusy(null);
    setChatDraft("");
    if (err) setError(err);
    else void load();
  };

  const activeCount = agents.filter((a) => a.status === "active").length;
  const activePct = Math.min(100, (activeCount / Math.max(1, agents.length)) * 100);

  return (
    <main
      className="flex h-full min-h-0 min-w-0 flex-col overflow-auto bg-[var(--theme-bg)] px-3 pb-20 pt-5 text-[var(--theme-text)] md:px-5 md:pt-7"
      style={HWS_PARITY_THEME}
    >
      <section className="mx-auto w-full max-w-[1320px] space-y-4">
        <header className="flex flex-col gap-4 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-5 py-4 shadow-[0_20px_60px_var(--theme-shadow)] md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-accent)] shadow-sm">
              <Brain className="h-5 w-5" strokeWidth={1.8} />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--theme-text)]">Operations</h1>
              <p className="mt-1 text-sm text-[var(--theme-muted)]">
                Mission control for launched work: monitor active agents, review outputs, and coordinate next actions.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] hover:bg-[var(--theme-card2)]"
              onClick={() => {
                setManagedLiveRefresh((n) => n + 1);
                void load();
              }}
              disabled={loading}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Sync
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] hover:bg-[var(--theme-card2)]"
              onClick={() => setAddJobOpen((v) => !v)}
            >
              <Clock className="h-3.5 w-3.5" />
              Schedule
            </Button>
            <div className="inline-flex rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setView("overview")}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  view === "overview"
                    ? "bg-[var(--theme-accent)] text-[color-mix(in_srgb,var(--theme-text)_5%,#041208)]"
                    : "text-[var(--theme-muted)] hover:bg-[var(--theme-card2)]",
                )}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                Overview
              </button>
              <button
                type="button"
                onClick={() => setView("outputs")}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  view === "outputs"
                    ? "bg-[var(--theme-accent)] text-[color-mix(in_srgb,var(--theme-text)_5%,#041208)]"
                    : "text-[var(--theme-muted)] hover:bg-[var(--theme-card2)]",
                )}
              >
                <Terminal className="h-3.5 w-3.5" />
                Outputs
              </button>
            </div>
            <Button
              className="bg-[var(--theme-accent)] text-[color-mix(in_srgb,var(--theme-text)_8%,#041208)] hover:bg-[var(--theme-accent-strong)]"
              type="button"
              size="sm"
              onClick={() => setNewOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              New Agent
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="border border-[var(--theme-border)] bg-[var(--theme-card)] text-[var(--theme-text)] hover:bg-[var(--theme-card2)]"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 className="h-3.5 w-3.5" />
              Settings
            </Button>
          </div>
        </header>

        <WorkspaceManagedMissionsLivePanel refreshSignal={managedLiveRefresh} variant="operations" />

        {loading && agents.length === 0 ? (
          <section className="rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-6 py-12 text-center text-sm text-[var(--theme-muted)] shadow-[0_24px_80px_var(--theme-shadow)]">
            Loading Operations roster…
          </section>
        ) : null}
        {error ? (
          <WorkspaceSurfaceStateCard
            className="shadow-[0_24px_80px_var(--theme-shadow)]"
            title="Operations API is not available"
            description="Chat may still work, but agent operations require the HAM operations routes on your API deployment."
            tone="amber"
            technicalDetail={error}
            primaryAction={
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="border border-[var(--theme-border)] bg-[var(--theme-bg)]"
                onClick={() => void load()}
              >
                Retry
              </Button>
            }
            secondaryAction={
              <Button type="button" size="sm" variant="ghost" className="text-[var(--theme-muted)]" asChild>
                <Link to="/workspace/chat">Open workspace chat</Link>
              </Button>
            }
          />
        ) : null}

        {addJobOpen && (
          <div className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_20px_50px_var(--theme-shadow)]">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--theme-muted)]">New scheduled job</p>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <input
                className="hww-input h-8 max-w-xs rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs text-[var(--theme-text)]"
                placeholder="Job name"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
              />
              <input
                className="hww-input h-8 max-w-xs rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 font-mono text-xs text-[var(--theme-text)]"
                placeholder="0 * * * *"
                value={jobCron}
                onChange={(e) => setJobCron(e.target.value)}
              />
              <div className="flex flex-wrap gap-1">
                {CRON_PRESETS.map((p) => (
                  <Button key={p.expr} type="button" size="sm" variant="secondary" className="h-7 text-[10px]" onClick={() => setJobCron(p.expr)}>
                    {p.label}
                  </Button>
                ))}
              </div>
              <Button type="button" size="sm" className="h-8" onClick={() => void onAddScheduled()} disabled={!!busy}>
                Save
              </Button>
            </div>
          </div>
        )}

        {view === "outputs" && !loading && (
          <div className="hww-scroll min-h-[40vh] overflow-auto rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-5 shadow-[0_20px_60px_var(--theme-shadow)]">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Full outputs (newest first)</p>
            <div className="mt-3 space-y-2">
              {allOutputLines.length === 0 ? (
                <p className="text-sm text-[var(--theme-muted)]">
                  No orchestrator output lines yet. Managed Cloud Agent missions show live activity above; open a mission in chat for
                  feed details.
                </p>
              ) : (
                allOutputLines.map((l) => (
                  <div key={`${l.id}-${l.at}-${l.line.slice(0, 20)}`} className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                    <p className="text-[10px] text-[var(--theme-accent)]">
                      {l.agent} · {fmt(l.at)}
                    </p>
                    <HwwText text={l.line} className="mt-1 text-sm" />
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {view === "overview" && !loading && (
          <>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
              <article className="flex min-h-[220px] flex-col rounded-[1.75rem] border border-[var(--theme-border)] border-l-4 border-l-[var(--theme-accent)] bg-[var(--theme-card)] p-5 shadow-[0_24px_80px_var(--theme-shadow)]">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold text-[var(--theme-text)]">Orchestrator</h2>
                    <p className="mt-1 text-sm text-[var(--theme-muted)]">
                      {agents.length} agents · {activeCount} active · {jobs.length} scheduled
                    </p>
                    <p className="mt-2 text-xs text-[var(--theme-muted-2)]">
                      Default model: <span className="font-medium text-[var(--theme-text)]">{settings?.defaultModel ?? "—"}</span>
                    </p>
                  </div>
                  <div className="flex w-full min-w-[200px] max-w-sm flex-col items-stretch gap-2 md:w-72">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--theme-bg)]">
                      <div className="h-full rounded-full bg-[var(--theme-accent)]" style={{ width: `${activePct}%` }} />
                    </div>
                    <p className="text-right text-[10px] text-[var(--theme-muted)]">Active share of roster</p>
                  </div>
                </div>
                <div className="mt-4 flex min-h-0 flex-1 flex-col justify-center rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-5 text-center">
                  <p className="text-sm text-[var(--theme-muted)]">Gateway chat session — open the workspace chat route for the full composer.</p>
                  <Button type="button" className="mt-3 self-center bg-[var(--theme-accent)] text-[color-mix(in_srgb,var(--theme-text)_8%,#041208)]" size="sm" asChild>
                    <Link to="/workspace/chat" className="inline-flex items-center gap-1.5">
                      Open workspace chat
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </Button>
                  <p className="mt-3 text-xs text-[var(--theme-muted-2)]">
                    Use Chat to steer missions, ask for status updates, or request follow-up tasks.
                  </p>
                </div>
              </article>
            </motion.div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {agents.length === 0 && !loading && (
                <div className="col-span-full rounded-2xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-8 text-center sm:col-span-2 xl:col-span-3">
                  <Sparkles className="mx-auto mb-2 h-6 w-6 text-[var(--theme-warning)]" />
                  <p className="text-sm font-medium text-[var(--theme-text)]">No agents yet</p>
                  <p className="mt-2 text-sm text-[var(--theme-muted)]">
                    Create an agent with <strong>New Agent</strong>, or launch a mission from Conductor to populate the roster when your workflow creates agents.
                  </p>
                </div>
              )}
              {agents.map((ag, index) => {
                const em = ag.emoji || "🤖";
                const displayName = stripEmojiPrefix(ag.name);
                const isActive = ag.status === "active";
                const lastLines = ag.outputs
                  .slice()
                  .sort((a, b) => b.at - a.at)
                  .slice(0, 2);
                const cronN = ag.cronEnabled ? 1 : 0;
                return (
                  <motion.div
                    key={ag.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.04, duration: 0.2 }}
                  >
                    <article
                      className={cn(
                        "flex min-h-[19rem] flex-col rounded-[1.5rem] border border-[var(--theme-border)] bg-[var(--theme-card)] p-3 shadow-[0_20px_60px_color-mix(in_srgb,var(--theme-shadow)_14%,transparent)]",
                        focusId === ag.id && "ring-1 ring-[var(--theme-accent)]",
                      )}
                      onClick={() => setFocusId(ag.id)}
                    >
                      <div className="relative flex min-h-8 items-center">
                        <div className="absolute left-0 flex items-center">
                          <button
                            type="button"
                            aria-label={cronN > 0 ? `Cron: ${ag.cronExpr || "on"}` : "No agent cron"}
                            onClick={(e) => {
                              e.stopPropagation();
                              setCronPanelFor((c) => (c === ag.id ? null : ag.id));
                            }}
                            className={cn(
                              "inline-flex h-8 shrink-0 items-center gap-1 rounded-lg px-1.5 text-[var(--theme-muted)] transition-colors hover:bg-[var(--theme-bg)] hover:text-[var(--theme-text)]",
                              cronPanelFor === ag.id && "bg-[var(--theme-bg)] text-[var(--theme-text)]",
                            )}
                          >
                            <Clock className="h-3.5 w-3.5" strokeWidth={2} />
                            {cronN > 0 ? (
                              <span className="inline-flex min-w-4 items-center justify-center rounded-full bg-[var(--theme-bg)] px-1.5 text-[10px] font-medium text-[var(--theme-text)]">
                                {cronN}
                              </span>
                            ) : null}
                          </button>
                        </div>
                        <div className="flex w-full justify-center px-16">
                          <h3 className="min-w-0 text-center text-sm font-semibold text-[var(--theme-text)]">
                            <span className="inline-flex max-w-full items-center justify-center gap-2">
                              <span className="truncate">{displayName}</span>
                              <span
                                className={statusDotClass(ag.status)}
                                aria-label={ag.status}
                                title={ag.status}
                              />
                            </span>
                          </h3>
                        </div>
                        <div className="absolute right-0 flex items-center gap-0.5">
                          <button
                            type="button"
                            aria-label={isActive ? `Pause ${displayName}` : `Run ${displayName}`}
                            onClick={async (e) => {
                              e.stopPropagation();
                              setBusy(ag.id);
                              const { error: err } = isActive
                                ? await workspaceOperationsAdapter.pause(ag.id)
                                : await workspaceOperationsAdapter.play(ag.id);
                              setBusy(null);
                              if (err) setError(err);
                              else void load();
                            }}
                            disabled={!!busy}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--theme-muted)] transition-colors hover:bg-[var(--theme-bg)] hover:text-[var(--theme-text)] disabled:opacity-50"
                          >
                            {busy === ag.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : isActive ? (
                              <Pause className="h-4 w-4" />
                            ) : (
                              <Play className="h-4 w-4" />
                            )}
                          </button>
                          <button
                            type="button"
                            aria-label={`Open settings for ${displayName}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              openDetail(ag);
                            }}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--theme-muted)] transition-colors hover:bg-[var(--theme-bg)] hover:text-[var(--theme-text)]"
                          >
                            <Settings2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>

                      <div className="flex flex-col items-center gap-1 px-2 py-2 text-center">
                        <div className="flex size-12 shrink-0 items-center justify-center text-3xl leading-none" aria-hidden>
                          {em}
                        </div>
                        <p className="w-full truncate text-[11px] text-[var(--theme-muted)]">
                          {ag.systemPrompt ? ag.systemPrompt : "No system prompt (HAM v0)."}
                        </p>
                        <p className="w-full truncate text-[10px] text-[var(--theme-muted)]/85">
                          {ag.cronEnabled ? `Cron · ${ag.cronExpr || "expr"}` : "Manual & messages only"}
                        </p>
                      </div>

                      <AnimatePresence initial={false}>
                        {cronPanelFor === ag.id ? (
                          <motion.section
                            key="cron-panel"
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.18, ease: "easeOut" }}
                            className="overflow-hidden"
                          >
                            <div
                              className="mb-2 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--theme-text)]">
                                <input
                                  type="checkbox"
                                  checked={ag.cronEnabled}
                                  onChange={async (e) => {
                                    setBusy(ag.id);
                                    const { error: err } = await workspaceOperationsAdapter.patchAgent(ag.id, {
                                      cronEnabled: e.target.checked,
                                      cronExpr: ag.cronExpr,
                                    });
                                    setBusy(null);
                                    if (err) setError(err);
                                    else void load();
                                  }}
                                />
                                Enable cron for this agent
                              </label>
                              <p className="mt-1 font-mono text-[10px] text-[var(--theme-muted)]">{ag.cronExpr || "—"}</p>
                              <Button
                                type="button"
                                variant="secondary"
                                size="sm"
                                className="mt-2 h-7 w-full text-[10px]"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openDetail(ag);
                                }}
                              >
                                Edit in agent settings
                              </Button>
                            </div>
                          </motion.section>
                        ) : null}
                      </AnimatePresence>

                      <div className="mt-auto min-h-0 flex-1 border-t border-[var(--theme-border)] pt-2">
                        <p className="mb-1 text-[9px] font-semibold uppercase text-[var(--theme-muted)]">Recent output</p>
                        <div className="hww-scroll max-h-[100px] space-y-1 overflow-y-auto text-left text-[10px] text-[var(--theme-text)]">
                          {lastLines.length === 0 ? (
                            <p className="text-[var(--theme-muted)]">—</p>
                          ) : (
                            lastLines.map((o) => (
                              <div key={`${o.at}`} className="line-clamp-2 rounded-lg border border-[var(--theme-border)]/60 bg-[var(--theme-bg)] p-1.5">
                                <HwwText text={o.line} />
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </article>
                  </motion.div>
                );
              })}

              <motion.button
                type="button"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: agents.length * 0.04, duration: 0.2 }}
                onClick={() => setNewOpen(true)}
                className="flex min-h-[19rem] flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-[var(--theme-border)] bg-[var(--theme-card)] p-4 text-center shadow-[0_20px_60px_color-mix(in_srgb,var(--theme-shadow)_10%,transparent)] transition-colors hover:border-[var(--theme-accent)] hover:bg-[var(--theme-accent-soft)]"
              >
                <Plus className="h-8 w-8 text-[var(--theme-muted)]" strokeWidth={1.5} />
                <span className="mt-3 text-sm text-[var(--theme-muted)]">Add Agent</span>
              </motion.button>
            </div>

            <section className="rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-5 shadow-[0_24px_80px_var(--theme-shadow)]">
              <h2 className="text-lg font-semibold text-[var(--theme-text)]">Recent Activity</h2>
              <p className="mt-1 text-sm text-[var(--theme-muted-2)]">Latest outputs across the team</p>
              <div className="mt-4 space-y-2">
                {recentActivity.length > 0 ? (
                  recentActivity.map((l) => {
                    const agMeta = agents.find((a) => a.id === l.id);
                    return (
                      <div
                        key={`${l.id}-${l.at}-${l.line.slice(0, 8)}`}
                        className="flex flex-col gap-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3 md:flex-row md:items-center md:justify-between"
                      >
                        <p className="text-sm text-[var(--theme-text)]">
                          <span className="mr-1">{agMeta?.emoji ?? "🤖"}</span>
                          <span className="font-medium">{agMeta ? stripEmojiPrefix(agMeta.name) : l.agent}:</span>{" "}
                          <span className="line-clamp-2 text-[var(--theme-muted-2)]">{l.line}</span>
                        </p>
                        <span className="shrink-0 text-sm text-[var(--theme-muted)]">{fmtRelative(l.at)}</span>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded-2xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-6 text-sm text-[var(--theme-muted)]">
                    No recent activity yet.
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_20px_60px_var(--theme-shadow)]">
              <div className="border-b border-[var(--theme-border)] pb-2">
                <h2 className="text-sm font-semibold text-[var(--theme-text)]">Team bridge</h2>
                <p className="text-xs text-[var(--theme-muted-2)]">
                  HAM v0: messages go through <code className="text-[var(--theme-muted)]">/message</code> (synthetic echo)
                </p>
              </div>
              <div className="mt-2 flex min-h-0 flex-col gap-2 md:grid md:grid-cols-[1fr,18rem] md:items-stretch">
                <div className="hww-scroll min-h-[140px] max-h-48 space-y-1.5 overflow-auto rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                    {focusAgent ? (
                    focusAgent.outputs
                      .slice()
                      .sort((a, b) => a.at - b.at)
                      .map((o) => (
                        <div key={`${o.at}-${o.line.slice(0, 16)}`} className="rounded-lg border border-[var(--theme-border)]/50 p-1.5 text-[10px] text-[var(--theme-text)]">
                          <HwwText text={o.line} />
                        </div>
                      ))
                  ) : (
                    <p className="p-2 text-sm text-[var(--theme-muted)]">Click an agent card to focus, or open settings for full edits.</p>
                  )}
                </div>
                <div className="flex flex-col justify-end gap-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-9 w-full rounded-lg border border-[var(--theme-border)] bg-[var(--theme-card)] px-2 text-xs text-[var(--theme-text)] placeholder:text-[var(--theme-muted)]"
                    placeholder={focusId ? "Message the focused agent…" : "Click a card above to focus an agent"}
                    value={chatDraft}
                    onChange={(e) => setChatDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void sendChat();
                      }
                    }}
                    disabled={!focusId}
                  />
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      size="sm"
                      className="bg-[var(--theme-accent)] text-[color-mix(in_srgb,var(--theme-text)_8%,#041208)]"
                      disabled={!focusId || !chatDraft.trim() || !!busy}
                      onClick={() => void sendChat()}
                    >
                      <Activity className="mr-1 h-3.5 w-3.5" />
                      Send
                    </Button>
                  </div>
                </div>
              </div>
            </section>

            {jobs.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Schedules &amp; cron registry</p>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {jobs.map((j) => (
                    <li
                      key={j.id}
                      className="flex min-w-0 max-w-sm items-center gap-2 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-3 py-1.5 text-[11px] text-[var(--theme-text)]"
                    >
                      <Clock className="h-3.5 w-3.5 shrink-0 text-[var(--theme-warning)]" />
                      <span className="min-w-0 truncate font-medium">{j.name}</span>
                      <code className="shrink-0 text-[10px] text-[var(--theme-accent)]">{j.cronExpr}</code>
                      <label className="ml-auto flex items-center gap-1 text-[10px] text-[var(--theme-muted)]">
                        <input
                          type="checkbox"
                          checked={j.enabled}
                          onChange={async (e) => {
                            setBusy(j.id);
                            const { error: err } = await workspaceOperationsAdapter.patchScheduled(j.id, { enabled: e.target.checked });
                            setBusy(null);
                            if (err) setError(err);
                            else void load();
                          }}
                        />
                        on
                      </label>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 shrink-0 p-0 text-red-300"
                        onClick={async () => {
                          if (!window.confirm("Delete scheduled job?")) return;
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
          </>
        )}
      </section>

      {newOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog" style={HWS_PARITY_THEME}>
          <div className="w-full max-w-md rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-xl">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-[var(--theme-text)]">
              <Bot className="h-4 w-4 text-[var(--theme-accent)]" />
              New agent
            </h2>
            <div className="mt-2 grid gap-2 text-xs">
              <div className="grid grid-cols-[4rem,1fr] items-end gap-2">
                <label className="text-[var(--theme-muted)]">
                  Emoji
                  <input
                    className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-1 text-center text-[var(--theme-text)]"
                    value={newEmoji}
                    onChange={(e) => setNewEmoji(e.target.value)}
                    maxLength={8}
                  />
                </label>
                <label className="text-[var(--theme-muted)]">
                  Name
                  <input
                    className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-[var(--theme-text)]"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </label>
              </div>
              <label className="text-[var(--theme-muted)]">
                Model
                <select
                  className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                >
                  {MODEL_CATALOG.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[var(--theme-muted)]">
                System prompt
                <textarea
                  className="mt-0.5 min-h-[72px] w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={newPrompt}
                  onChange={(e) => setNewPrompt(e.target.value)}
                  placeholder="You are a helpful agent operating in HAM v0 (local synthetic outputs)."
                />
              </label>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setNewOpen(false)}>
                Cancel
              </Button>
              <Button type="button" size="sm" onClick={() => void onCreate()} disabled={!newName.trim() || !!busy}>
                Create
              </Button>
            </div>
          </div>
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog" style={HWS_PARITY_THEME}>
          <div className="hww-scroll max-h-[min(90vh,640px)] w-full max-w-lg overflow-auto rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-xl">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-[var(--theme-text)]">
              <span className="text-xl" aria-hidden>
                {formEmoji || "🤖"}
              </span>
              Agent
            </h2>
            <div className="mt-2 grid gap-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[var(--theme-muted)]">
                  Emoji
                  <input
                    className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-center text-[var(--theme-text)]"
                    value={formEmoji}
                    onChange={(e) => setFormEmoji(e.target.value)}
                    maxLength={8}
                  />
                </label>
                <label className="text-[var(--theme-muted)]">
                  Name
                  <input
                    className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                  />
                </label>
              </div>
              <label className="text-[var(--theme-muted)]">
                Model
                <select
                  className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={formModel}
                  onChange={(e) => setFormModel(e.target.value)}
                >
                  {MODEL_CATALOG.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[var(--theme-muted)]">
                System prompt
                <textarea
                  className="mt-0.5 min-h-[96px] w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={formPrompt}
                  onChange={(e) => setFormPrompt(e.target.value)}
                />
              </label>
              <label className="flex items-center gap-2 text-[var(--theme-muted)]">
                <input type="checkbox" checked={formCronOn} onChange={(e) => setFormCronOn(e.target.checked)} />
                Cron
              </label>
              <label className="text-[var(--theme-muted)]">
                Cron expression
                <input
                  className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] font-mono text-[var(--theme-text)]"
                  value={formCron}
                  onChange={(e) => setFormCron(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-1">
                {CRON_PRESETS.map((p) => (
                  <Button key={p.expr} type="button" size="sm" variant="secondary" className="h-6 text-[9px]" onClick={() => setFormCron(p.expr)}>
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
            <p className="mt-2 text-[10px] text-[var(--theme-muted)]">Output buffer ({detail.outputs.length} lines)</p>
            <div className="mt-1 max-h-32 overflow-auto rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
              {detail.outputs.length === 0 ? (
                "—"
              ) : (
                <div className="space-y-1">
                  {detail.outputs
                    .slice()
                    .sort((a, b) => a.at - b.at)
                    .map((o, i) => (
                      <HwwText key={`${o.at}-${i}`} text={o.line} />
                    ))}
                </div>
              )}
            </div>
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog" style={HWS_PARITY_THEME}>
          <div className="w-full max-w-md rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-xl">
            <h2 className="text-sm font-semibold text-[var(--theme-text)]">Team settings</h2>
            <div className="mt-2 grid gap-2 text-xs">
              <label className="text-[var(--theme-muted)]">
                Default model
                <select
                  className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={sDraft.defaultModel}
                  onChange={(e) => setSDraft((s) => ({ ...s, defaultModel: e.target.value }))}
                >
                  {MODEL_CATALOG.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[var(--theme-muted)]">
                Output retention (lines)
                <input
                  type="number"
                  className="mt-0.5 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
                  value={sDraft.outputsRetention}
                  onChange={(e) => setSDraft((s) => ({ ...s, outputsRetention: Number(e.target.value) }))}
                />
              </label>
              <label className="text-[var(--theme-muted)]">
                Notes
                <textarea
                  className="mt-0.5 min-h-[64px] w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)]"
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

    </main>
  );
}
