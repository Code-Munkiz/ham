import * as React from "react";
import { motion } from "motion/react";
import {
  Activity,
  Bot,
  Clock,
  LayoutGrid,
  Loader2,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  Terminal,
  Trash2,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HwwText } from "../../hwwText";
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
      return "bg-emerald-500/25 text-emerald-100 ring-1 ring-emerald-500/30";
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

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-gradient-to-b from-[#0a1014] to-[#080c10] p-2 md:p-3">
      <header className="shrink-0 border-b border-white/5 pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="mb-0.5 flex items-center gap-1.5">
              <p className="hww-pill">Agent team</p>
              <span className="text-[9px] text-white/35">Operations · HAM v0</span>
            </div>
            <h1 className="flex items-center gap-1.5 text-base font-semibold text-white/95">
              <Users className="h-4 w-4 text-cyan-400/80" />
              Agent Operations
            </h1>
            <p className="mt-0.5 max-w-2xl text-[11px] text-white/45">
              Gateway-style shell for persistent agents, cron, and outputs. Backed by{" "}
              <code className="text-white/50">/api/workspace/operations</code> — no browser secrets, no upstream fetches.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
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
            <Button type="button" size="sm" className="h-7 gap-1" onClick={() => setNewOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              New agent
            </Button>
            <Button type="button" size="sm" variant="secondary" className="h-7 gap-1" onClick={() => setAddJobOpen((v) => !v)}>
              <Clock className="h-3.5 w-3.5" />
              Schedule
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 border-white/10 bg-black/30 text-amber-200/90 hover:bg-white/5"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 className="h-3.5 w-3.5" />
              Team settings
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
        </div>
      </header>

      {error && (
        <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100/90">
          {error}
        </div>
      )}

      {view === "overview" && (
        <motion.div initial={{ opacity: 0.96 }} animate={{ opacity: 1 }} className="mt-2 shrink-0">
          <div className="grid gap-2 lg:grid-cols-[1fr,320px]">
            <div className="overflow-hidden rounded-xl border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 via-black/30 to-violet-500/5 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-[9px] font-semibold uppercase tracking-wider text-cyan-200/50">Orchestrator</p>
                  <p className="mt-0.5 text-sm font-semibold text-white/95">Persistent agent team</p>
                  <p className="text-[10px] text-white/50">
                    Default model: <span className="text-white/80">{settings?.defaultModel ?? "—"}</span>
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-1.5 text-center text-[10px]">
                  <div className="min-w-[4.5rem] rounded-lg border border-white/10 bg-black/30 py-1.5">
                    <div className="text-white/40">Agents</div>
                    <div className="text-lg font-semibold text-white/95">{agents.length}</div>
                  </div>
                  <div className="min-w-[4.5rem] rounded-lg border border-white/10 bg-black/30 py-1.5">
                    <div className="text-white/40">Active</div>
                    <div className="text-lg font-semibold text-emerald-200/90">{activeCount}</div>
                  </div>
                  <div className="min-w-[4.5rem] rounded-lg border border-white/10 bg-black/30 py-1.5">
                    <div className="text-white/40">Cron</div>
                    <div className="text-lg font-semibold text-amber-200/90">{jobs.length}</div>
                  </div>
                </div>
              </div>
              <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-black/50">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500/60 to-violet-500/50"
                  style={{ width: `${Math.min(100, (activeCount / Math.max(1, agents.length)) * 100)}%` }}
                />
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/25 p-2">
              <p className="text-[9px] font-semibold uppercase text-white/45">Recent activity</p>
              <ul className="hww-scroll mt-1 max-h-28 space-y-0.5 overflow-auto text-[10px] text-white/65">
                {recentActivity.length === 0 && <li className="text-white/35">No lines yet — play an agent or send chat.</li>}
                {recentActivity.map((l) => (
                  <li key={`${l.id}-${l.at}-${l.line.slice(0, 8)}`} className="line-clamp-1 font-mono">
                    <span className="text-white/40">{fmt(l.at)}</span>{" "}
                    <span className="text-amber-200/80">{l.agent}</span> · {l.line}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </motion.div>
      )}

      {addJobOpen && (
        <div className="mt-2 rounded-xl border border-white/10 bg-black/30 p-2">
          <p className="text-[9px] font-semibold uppercase text-white/45">New scheduled job</p>
          <div className="mt-1 flex flex-wrap items-end gap-2">
            <input
              className="hww-input h-7 max-w-xs rounded px-2 text-xs"
              placeholder="Job name"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
            />
            <input
              className="hww-input h-7 max-w-xs rounded px-2 font-mono text-xs"
              placeholder="0 * * * *"
              value={jobCron}
              onChange={(e) => setJobCron(e.target.value)}
            />
            <div className="flex flex-wrap gap-1">
              {CRON_PRESETS.map((p) => (
                <Button key={p.expr} type="button" size="sm" variant="secondary" className="h-6 text-[9px]" onClick={() => setJobCron(p.expr)}>
                  {p.label}
                </Button>
              ))}
            </div>
            <Button type="button" size="sm" className="h-7" onClick={() => void onAddScheduled()} disabled={!!busy}>
              Save
            </Button>
          </div>
        </div>
      )}

      {newOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="w-full max-w-md rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-white/95">
              <Bot className="h-4 w-4 text-cyan-300/80" />
              New agent
            </h2>
            <div className="mt-2 grid gap-2 text-xs">
              <div className="grid grid-cols-[4rem,1fr] items-end gap-2">
                <label className="text-white/60">
                  Emoji
                  <input
                    className="hww-input mt-0.5 w-full text-center"
                    value={newEmoji}
                    onChange={(e) => setNewEmoji(e.target.value)}
                    maxLength={8}
                  />
                </label>
                <label className="text-white/60">
                  Name
                  <input
                    className="hww-input mt-0.5 w-full"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </label>
              </div>
              <label className="text-white/60">
                Model
                <select
                  className="hww-input mt-0.5 w-full"
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
              <label className="text-white/60">
                System prompt
                <textarea
                  className="hww-input mt-0.5 min-h-[72px] w-full"
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

      {loading && agents.length === 0 && <p className="mt-2 text-[11px] text-white/40">Loading team…</p>}

      {view === "overview" && (
        <div className="mt-2 grid min-h-0 flex-1 gap-2 lg:grid-cols-[1fr,320px]">
          <ul className="hww-scroll grid min-h-0 content-start grid-cols-1 gap-2 overflow-auto sm:grid-cols-2 xl:grid-cols-3">
            {agents.length === 0 && !loading && (
              <li className="col-span-full rounded border border-dashed border-white/15 p-4 text-center text-[11px] text-white/40">
                <Sparkles className="mx-auto mb-1 h-5 w-5 text-amber-400/50" />
                No agents. Create a card or wire gateway runtime later.
              </li>
            )}
            {agents.map((ag) => {
              const em = ag.emoji || "🤖";
              return (
                <li
                  key={ag.id}
                  className={cn(
                    "flex min-h-[9rem] flex-col rounded-xl border p-2 transition-colors",
                    focusId === ag.id
                      ? "border-cyan-500/50 bg-cyan-500/5"
                      : "border-white/10 bg-black/30 hover:border-white/20",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" className="min-w-0 text-left" onClick={() => openDetail(ag)}>
                      <span className="text-lg leading-none" aria-hidden>
                        {em}
                      </span>{" "}
                      <span className="text-sm font-semibold text-amber-100/90 hover:underline">{ag.name}</span>
                    </button>
                    <span className={cn("shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-semibold uppercase", statusBadge(ag.status))}>
                      {ag.status}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-1 font-mono text-[10px] text-cyan-200/80">{ag.model}</p>
                  <p className="line-clamp-2 text-[10px] text-white/40">{ag.systemPrompt || "No system prompt (HAM local)."}</p>
                  <div className="mt-auto flex flex-wrap gap-1 pt-1.5">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="h-7 flex-1"
                      disabled={!!busy}
                      onClick={async (e) => {
                        e.stopPropagation();
                        setFocusId(ag.id);
                        setBusy(ag.id);
                        const { error: err } = await workspaceOperationsAdapter.play(ag.id);
                        setBusy(null);
                        if (err) setError(err);
                        else void load();
                      }}
                    >
                      {busy === ag.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                      Run
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 flex-1"
                      disabled={!!busy}
                      onClick={async (e) => {
                        e.stopPropagation();
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
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2"
                      onClick={(e) => {
                        e.stopPropagation();
                        setFocusId(ag.id);
                      }}
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/10 bg-[#0b1018]">
            <div className="border-b border-white/10 px-2 py-1.5">
              <p className="text-[9px] font-semibold uppercase text-white/45">Inline team chat</p>
              <p className="text-[9px] text-white/40">Posts through HAM <code className="text-white/50">/message</code> (synthetic echo).</p>
            </div>
            <div className="hww-scroll min-h-0 flex-1 space-y-1 overflow-auto p-2">
              {focusAgent ? (
                focusAgent.outputs
                  .slice()
                  .sort((a, b) => a.at - b.at)
                  .map((o) => (
                    <div
                      key={`${o.at}-${o.line.slice(0, 24)}`}
                      className="rounded border border-white/5 bg-black/30 p-1.5 text-[10px] text-white/80"
                    >
                      <HwwText text={o.line} />
                    </div>
                  ))
              ) : (
                <p className="text-[11px] text-white/40">Select an agent or tap the chat icon to focus.</p>
              )}
            </div>
            <div className="border-t border-white/10 p-2">
              <div className="flex gap-1">
                <input
                  className="hww-input h-8 min-w-0 flex-1 text-[11px]"
                  placeholder={focusId ? "Message the focused agent…" : "Focus an agent first"}
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
                <Button type="button" size="sm" className="h-8 shrink-0" disabled={!focusId || !chatDraft.trim() || !!busy} onClick={() => void sendChat()}>
                  <Activity className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {view === "outputs" && (
        <div className="hww-scroll mt-2 min-h-0 flex-1 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3">
          <p className="text-[9px] font-semibold uppercase text-white/45">Full outputs (newest first)</p>
          <div className="mt-2 space-y-1.5">
            {allOutputLines.length === 0 ? (
              <p className="text-[11px] text-white/40">—</p>
            ) : (
              allOutputLines.map((l) => (
                <div key={`${l.id}-${l.at}-${l.line.slice(0, 20)}`} className="rounded border border-white/5 bg-black/40 p-2">
                  <p className="text-[9px] text-amber-200/80">
                    {l.agent} · {fmt(l.at)}
                  </p>
                  <HwwText text={l.line} className="mt-0.5" />
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="hww-scroll max-h-[min(90vh,640px)] w-full max-w-lg overflow-auto rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-white/95">
              <span className="text-xl" aria-hidden>
                {formEmoji || "🤖"}
              </span>
              Agent
            </h2>
            <div className="mt-2 grid gap-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <label className="text-white/60">
                  Emoji
                  <input
                    className="hww-input mt-0.5 w-full text-center"
                    value={formEmoji}
                    onChange={(e) => setFormEmoji(e.target.value)}
                    maxLength={8}
                  />
                </label>
                <label className="text-white/60">
                  Name
                  <input className="hww-input mt-0.5 w-full" value={formName} onChange={(e) => setFormName(e.target.value)} />
                </label>
              </div>
              <label className="text-white/60">
                Model
                <select
                  className="hww-input mt-0.5 w-full"
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
              <label className="text-white/60">
                System prompt
                <textarea
                  className="hww-input mt-0.5 min-h-[96px] w-full"
                  value={formPrompt}
                  onChange={(e) => setFormPrompt(e.target.value)}
                />
              </label>
              <label className="flex items-center gap-2 text-white/60">
                <input type="checkbox" checked={formCronOn} onChange={(e) => setFormCronOn(e.target.checked)} />
                Cron
              </label>
              <label className="text-white/60">
                Cron expression
                <input
                  className="hww-input mt-0.5 w-full font-mono"
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
            <p className="mt-2 text-[10px] text-white/40">Output buffer ({detail.outputs.length} lines)</p>
            <div className="mt-1 max-h-32 overflow-auto rounded border border-white/10 bg-black/40 p-2">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" role="dialog">
          <div className="w-full max-w-md rounded border border-white/10 bg-[#0a1218] p-3 shadow-xl">
            <h2 className="text-sm font-semibold text-white/95">Team settings</h2>
            <div className="mt-2 grid gap-2 text-xs">
              <label className="text-white/60">
                Default model
                <select
                  className="hww-input mt-0.5 w-full"
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

      {view === "overview" && jobs.length > 0 && (
        <div className="mt-2 shrink-0">
          <p className="text-[9px] font-semibold uppercase text-white/45">Schedules &amp; cron registry</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {jobs.map((j) => (
              <li
                key={j.id}
                className="flex min-w-0 max-w-sm items-center gap-2 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-[10px] text-white/80"
              >
                <Clock className="h-3 w-3 shrink-0 text-amber-300/80" />
                <span className="min-w-0 truncate font-medium">{j.name}</span>
                <code className="shrink-0 text-[9px] text-cyan-200/80">{j.cronExpr}</code>
                <label className="ml-auto flex items-center gap-0.5 text-[8px] text-white/50">
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
                  className="h-6 w-6 shrink-0 p-0 text-red-300"
                  onClick={async () => {
                    if (!window.confirm("Delete scheduled job?")) return;
                    setBusy(j.id);
                    const { error: err } = await workspaceOperationsAdapter.deleteScheduled(j.id);
                    setBusy(null);
                    if (err) setError(err);
                    else void load();
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
