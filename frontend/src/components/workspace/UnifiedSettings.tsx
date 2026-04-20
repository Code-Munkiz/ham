import * as React from "react";
import {
  Key,
  Globe,
  ToyBrick,
  Database,
  History,
  Activity,
  BarChart3,
  FileSearch,
  HardDrive,
  Cpu,
  Zap,
  Layout,
  Brain,
  Layers,
  Users,
  Box,
  Plus,
  RefreshCw,
  Lock,
  Calendar,
  Package,
  Search,
  Eye,
  CheckCircle2,
  Download,
  Settings2,
  UserPlus,
  Power,
  Terminal,
  Monitor,
  BookOpen,
  ListFilter,
  ArrowUpRight,
} from "lucide-react";

import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  clearSavedCursorApiKey,
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchCursorCredentialsStatus,
  fetchCursorModels,
  fetchSettingsWriteStatus,
  postSettingsApply,
  postSettingsPreview,
  saveCursorApiKey,
  type HamSettingsChanges,
  type HamSettingsMemoryHeistPatch,
  type HamSettingsPreviewResponse,
} from "@/lib/ham/api";
import type { ContextEnginePayload, CursorCredentialsStatus } from "@/lib/ham/types";

function ApiKeysPanel() {
  const [status, setStatus] = React.useState<CursorCredentialsStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [draftKey, setDraftKey] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [modelsProbe, setModelsProbe] = React.useState<string | null>(null);
  const [modelsBusy, setModelsBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await fetchCursorCredentialsStatus();
      setStatus(s);
    } catch (e) {
      setStatus(null);
      setError(e instanceof Error ? e.message : "Failed to load Cursor key status");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const onSave = async () => {
    if (!draftKey.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await saveCursorApiKey(draftKey.trim());
      setDraftKey("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const onClearSaved = async () => {
    setBusy(true);
    setError(null);
    try {
      await clearSavedCursorApiKey();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setBusy(false);
    }
  };

  const onTestModels = async () => {
    setModelsBusy(true);
    setModelsProbe(null);
    setError(null);
    try {
      const data = await fetchCursorModels();
      const s =
        typeof data === "object" && data !== null
          ? JSON.stringify(data).slice(0, 1200)
          : String(data);
      setModelsProbe(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Models probe failed");
    } finally {
      setModelsBusy(false);
    }
  };

  const sourceLabel =
    status?.source === "ui"
      ? "Saved in HAM (shared)"
      : status?.source === "env"
        ? "Server environment (CURSOR_API_KEY)"
        : "Not configured";

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-[#FF6B00]/20 bg-black/50 p-6 space-y-4 shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Key className="h-4 w-4 text-[#FF6B00]" />
              <h3 className="text-[13px] font-black text-white uppercase tracking-[0.2em] italic">
                Cursor Cloud API key
              </h3>
            </div>
            <p className="text-[10px] font-bold text-white/35 uppercase tracking-widest max-w-2xl leading-relaxed">
              Ham proxies Cursor Cloud Agents (<span className="font-mono text-white/50">GET/POST /v0/*</span>) with
              this key. Stored only on the API host filesystem (see path below). Set{" "}
              <span className="font-mono text-white/45">HAM_CURSOR_CREDENTIALS_FILE</span> on Cloud Run/Docker with a
              mounted volume so the key survives restarts. Anyone with access to this Settings page can rotate the team
              key.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || busy}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[9px] font-black uppercase tracking-widest text-white/50 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/5 text-[11px] font-bold text-red-400/90">
            {error}
          </div>
        )}

        {loading && !status && (
          <p className="text-[10px] font-bold text-white/25 uppercase tracking-widest">Loading key status…</p>
        )}

        {status && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg border border-white/5 bg-black/40 space-y-2">
              <div className="text-[9px] font-black text-white/25 uppercase tracking-widest">Active key source</div>
              <div className="text-[12px] font-black text-[#FF6B00] uppercase tracking-tight">{sourceLabel}</div>
              {status.configured && status.masked_preview && (
                <div className="text-[10px] font-mono text-white/45">Preview: {status.masked_preview}</div>
              )}
            </div>
            <div className="p-4 rounded-lg border border-white/5 bg-black/40 space-y-2">
              <div className="text-[9px] font-black text-white/25 uppercase tracking-widest">Who is paying / labeled</div>
              {status.error && !status.user_email ? (
                <div className="text-[11px] font-bold text-amber-500/80">{status.error}</div>
              ) : (
                <>
                  <div className="text-[12px] font-black text-white">
                    {status.api_key_name ?? "—"}{" "}
                    <span className="text-white/30 font-bold text-[10px] uppercase tracking-widest">(key name)</span>
                  </div>
                  <div className="text-[11px] font-mono text-white/55 break-all">
                    {status.user_email ?? "—"}{" "}
                    <span className="text-white/25 text-[9px] font-bold uppercase tracking-widest">(account)</span>
                  </div>
                  {status.key_created_at && (
                    <div className="text-[9px] font-bold text-white/25 uppercase tracking-wider">
                      Key issued: {status.key_created_at}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {status?.storage_path && (
          <div className="p-4 rounded-lg border border-white/5 bg-black/30 space-y-1">
            <div className="text-[9px] font-black text-white/25 uppercase tracking-widest">Key file on API host</div>
            <div className="text-[10px] font-mono text-white/55 break-all">{status.storage_path}</div>
            {status.storage_override_env ? (
              <div className="text-[9px] font-bold text-emerald-500/70 uppercase tracking-wider">
                Override: HAM_CURSOR_CREDENTIALS_FILE is set
              </div>
            ) : null}
          </div>
        )}

        {status?.wired_for && (
          <div className="p-4 rounded-lg border border-[#FF6B00]/15 bg-black/40 space-y-3">
            <div className="text-[9px] font-black text-white/25 uppercase tracking-widest">
              What uses this key (backend, this deployment)
            </div>
            <ul className="space-y-2 text-[10px] font-bold text-white/45 uppercase tracking-wider">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500/90 shrink-0 mt-0.5" />
                <span>
                  <span className="text-white/70">Models list</span> — Ham{" "}
                  <span className="font-mono text-white/50">GET /api/cursor/models</span> → Cursor{" "}
                  <span className="font-mono text-white/50">GET /v0/models</span>
                </span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500/90 shrink-0 mt-0.5" />
                <span>
                  <span className="text-white/70">Run cloud agent / missions</span> — Ham{" "}
                  <span className="font-mono text-white/50">POST /api/cursor/agents/launch</span> → Cursor{" "}
                  <span className="font-mono text-white/50">POST /v0/agents</span>
                </span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500/90 shrink-0 mt-0.5" />
                <span>
                  <span className="text-white/70">CI hooks and automation</span> — same launch URL with a bearer-less
                  server-to-server call to your Ham API (Basic auth key is server-side only).
                </span>
              </li>
              <li className="text-[9px] font-bold text-white/30 normal-case tracking-normal pl-6 border-l border-white/10 ml-1">
                {status.wired_for.ci_hooks_note}
              </li>
              <li className="flex items-start gap-2 pt-1 border-t border-white/5">
                {status.wired_for.dashboard_chat_uses_cursor ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500/90 shrink-0 mt-0.5" />
                ) : (
                  <span className="text-amber-500/90 font-black shrink-0 w-3.5 text-center">—</span>
                )}
                <span>
                  <span className="text-white/70">Dashboard chat</span> —{" "}
                  {status.wired_for.dashboard_chat_uses_cursor ? (
                    "uses Cursor"
                  ) : (
                    <span className="text-amber-500/85">not routed through Cursor REST</span>
                  )}
                  . {status.wired_for.dashboard_chat_note}
                </span>
              </li>
            </ul>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                type="button"
                disabled={modelsBusy || !status.configured}
                onClick={() => void onTestModels()}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[#FF6B00]/35 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-[#FF6B00]/10 transition-colors disabled:opacity-30"
              >
                <Zap className={cn("h-3.5 w-3.5", modelsBusy && "animate-pulse")} />
                Test Cursor API (models)
              </button>
              {!status.configured && (
                <span className="text-[9px] font-bold text-white/25 uppercase tracking-widest">
                  Configure a key first
                </span>
              )}
            </div>
            {modelsProbe && (
              <pre className="text-[9px] font-mono text-white/45 whitespace-pre-wrap break-all max-h-32 overflow-y-auto p-2 rounded bg-black/50 border border-white/5">
                {modelsProbe}
              </pre>
            )}
          </div>
        )}

        <div className="space-y-2 pt-2 border-t border-white/5">
          <label className="text-[9px] font-black text-white/30 uppercase tracking-widest block">
            Paste new Cursor API key (replaces saved key)
          </label>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="password"
              autoComplete="off"
              value={draftKey}
              onChange={(e) => setDraftKey(e.target.value)}
              placeholder="crsr_…"
              className="flex-1 h-11 px-4 rounded-lg bg-black/60 border border-white/10 font-mono text-[11px] text-white/80 placeholder:text-white/15 focus:outline-none focus:border-[#FF6B00]/40"
            />
            <button
              type="button"
              disabled={busy || !draftKey.trim()}
              onClick={() => void onSave()}
              className="h-11 px-6 rounded-lg bg-[#FF6B00] text-[10px] font-black text-black uppercase tracking-widest hover:bg-[#ff8534] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Save & verify
            </button>
          </div>
          {status?.source === "ui" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onClearSaved()}
              className="text-[9px] font-black text-white/35 uppercase tracking-widest hover:text-red-400/90 transition-colors"
            >
              Remove saved key (fall back to CURSOR_API_KEY env if set)
            </button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-white/5 bg-white/[0.02] p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-white/25" />
          <h4 className="text-[11px] font-black text-white/60 uppercase tracking-widest">OpenRouter (chat gateway)</h4>
        </div>
        <p className="text-[10px] font-bold text-white/30 uppercase tracking-widest leading-relaxed">
          Dashboard chat still uses <span className="font-mono text-white/45">HERMES_GATEWAY_MODE=openrouter</span> and{" "}
          <span className="font-mono text-white/45">OPENROUTER_API_KEY</span> unless you change the gateway on the API
          host. Cursor and OpenRouter can both be configured; wiring chat to Composer is a separate gateway mode.
        </p>
      </div>

      <div className="rounded-lg border border-white/5 border-dashed bg-black/20 p-5 space-y-2">
        <div className="text-[10px] font-black text-white/25 uppercase tracking-widest">Roadmap</div>
        <p className="text-[10px] font-bold text-white/35 uppercase tracking-wider">
          <span className="text-white/50">Local Composer</span> — Node SDK / sidecar for repo-on-disk workflows (separate
          from Cloud Agents REST above).
        </p>
      </div>
    </div>
  );
}

function buildHamSettingsChanges(fields: {
  sessionMax: string;
  sessionPreserve: string;
  toolPrune: string;
  arch: string;
  cmd: string;
  critic: string;
}): HamSettingsChanges {
  const p = (s: string): number | undefined => {
    const n = Number(String(s).trim());
    if (!Number.isFinite(n) || n <= 0) return undefined;
    return Math.floor(n);
  };
  const mh: HamSettingsMemoryHeistPatch = {};
  const sm = p(fields.sessionMax);
  if (sm !== undefined) mh.session_compaction_max_tokens = sm;
  const sp = p(fields.sessionPreserve);
  if (sp !== undefined) mh.session_compaction_preserve = sp;
  const tp = p(fields.toolPrune);
  if (tp !== undefined) mh.session_tool_prune_chars = tp;
  const out: HamSettingsChanges = {};
  if (Object.keys(mh).length > 0) {
    out.memory_heist = mh;
  }
  const ar = p(fields.arch);
  if (ar !== undefined) out.architect_instruction_chars = ar;
  const cm = p(fields.cmd);
  if (cm !== undefined) out.commander_instruction_chars = cm;
  const cr = p(fields.critic);
  if (cr !== undefined) out.critic_instruction_chars = cr;
  return out;
}

/** Preview / apply allowlisted keys to `.ham/settings.json` (server-validated). */
function AllowlistedWorkspaceSettings({
  data,
  onApplied,
}: {
  data: ContextEnginePayload;
  onApplied: () => void;
}) {
  const cwd = data.cwd;
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [projectErr, setProjectErr] = React.useState<string | null>(null);
  const [writesEnabled, setWritesEnabled] = React.useState<boolean | null>(null);
  const [sessionMax, setSessionMax] = React.useState("");
  const [sessionPreserve, setSessionPreserve] = React.useState("");
  const [toolPrune, setToolPrune] = React.useState("");
  const [archChars, setArchChars] = React.useState("");
  const [cmdChars, setCmdChars] = React.useState("");
  const [criticChars, setCriticChars] = React.useState("");
  const [preview, setPreview] = React.useState<HamSettingsPreviewResponse | null>(null);
  const [writeToken, setWriteToken] = React.useState("");
  const [busy, setBusy] = React.useState<"preview" | "apply" | null>(null);

  React.useEffect(() => {
    setSessionMax(String(data.session_memory.compact_max_tokens));
    setSessionPreserve(String(data.session_memory.compact_preserve));
    setToolPrune(String(data.session_memory.tool_prune_chars));
    setArchChars(String(data.roles.architect.instruction_budget_chars));
    setCmdChars(String(data.roles.commander.instruction_budget_chars));
    setCriticChars(String(data.roles.critic.instruction_budget_chars));
    setPreview(null);
  }, [data]);

  React.useEffect(() => {
    let cancelled = false;
    setProjectErr(null);
    setProjectId(null);
    void (async () => {
      try {
        const id = await ensureProjectIdForWorkspaceRoot(cwd);
        if (!cancelled) setProjectId(id);
      } catch (e) {
        if (!cancelled) {
          setProjectErr(e instanceof Error ? e.message : "Could not resolve project for this workspace.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cwd]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const s = await fetchSettingsWriteStatus();
        if (!cancelled) setWritesEnabled(s.writes_enabled);
      } catch {
        if (!cancelled) setWritesEnabled(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const changes = React.useMemo(
    () =>
      buildHamSettingsChanges({
        sessionMax,
        sessionPreserve,
        toolPrune,
        arch: archChars,
        cmd: cmdChars,
        critic: criticChars,
      }),
    [sessionMax, sessionPreserve, toolPrune, archChars, cmdChars, criticChars],
  );

  const hasPatch =
    (changes.memory_heist && Object.keys(changes.memory_heist).length > 0) ||
    changes.architect_instruction_chars !== undefined ||
    changes.commander_instruction_chars !== undefined ||
    changes.critic_instruction_chars !== undefined;

  const runPreview = async () => {
    if (!projectId) return;
    if (!hasPatch) {
      toast.error("Enter at least one valid positive number.");
      return;
    }
    setBusy("preview");
    setPreview(null);
    try {
      const pr = await postSettingsPreview(projectId, changes);
      setPreview(pr);
      if (pr.diff.length === 0) {
        toast.message("No effective change — values already match merged config.");
      } else {
        toast.success("Preview ready — review diff and warnings, then apply.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setBusy(null);
    }
  };

  const runApply = async () => {
    if (!projectId || !preview) return;
    const tok = writeToken.trim();
    if (!tok) {
      toast.error("Paste HAM_SETTINGS_WRITE_TOKEN to apply.");
      return;
    }
    setBusy("apply");
    try {
      const result = await postSettingsApply(projectId, changes, preview.base_revision, tok);
      toast.success(`Applied. Backup: ${result.backup_id}`);
      setPreview(null);
      setWriteToken("");
      onApplied();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(null);
    }
  };

  const inputCls =
    "w-full mt-1 px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-[11px] font-mono text-white/80 placeholder:text-white/25 focus:outline-none focus:ring-1 focus:ring-[#FF6B00]/50";

  return (
    <div className="p-6 bg-black/40 border border-[#FF6B00]/20 rounded-xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h4 className="text-[11px] font-black text-[#FF6B00] uppercase tracking-widest italic">
            Allowlisted config writes
          </h4>
          <p className="text-[9px] font-bold text-white/30 uppercase tracking-widest mt-2 max-w-2xl leading-relaxed">
            Writes only <span className="font-mono">.ham/settings.json</span> on the server (merge with validation,
            backup, audit). Matches <span className="font-mono">POST .../settings/preview|apply</span>. Preview is
            unauthenticated; apply uses your token for this browser session only (not stored in the app bundle).
          </p>
        </div>
        {writesEnabled === false && (
          <span className="text-[9px] font-bold text-amber-500/90 uppercase tracking-widest px-2 py-1 rounded border border-amber-500/30 bg-amber-500/5">
            Apply disabled — set HAM_SETTINGS_WRITE_TOKEN on the API
          </span>
        )}
      </div>

      {projectErr && (
        <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/5 text-[10px] text-red-400/90">
          {projectErr}
        </div>
      )}
      {!projectId && !projectErr && (
        <div className="text-[10px] font-bold text-white/35 uppercase tracking-widest">Resolving project…</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">session_compaction_max_tokens</label>
          <input className={inputCls} value={sessionMax} onChange={(e) => setSessionMax(e.target.value)} inputMode="numeric" />
        </div>
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">session_compaction_preserve</label>
          <input className={inputCls} value={sessionPreserve} onChange={(e) => setSessionPreserve(e.target.value)} inputMode="numeric" />
        </div>
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">session_tool_prune_chars</label>
          <input className={inputCls} value={toolPrune} onChange={(e) => setToolPrune(e.target.value)} inputMode="numeric" />
        </div>
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">architect_instruction_chars</label>
          <input className={inputCls} value={archChars} onChange={(e) => setArchChars(e.target.value)} inputMode="numeric" />
        </div>
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">commander_instruction_chars</label>
          <input className={inputCls} value={cmdChars} onChange={(e) => setCmdChars(e.target.value)} inputMode="numeric" />
        </div>
        <div>
          <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">critic_instruction_chars</label>
          <input className={inputCls} value={criticChars} onChange={(e) => setCriticChars(e.target.value)} inputMode="numeric" />
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!projectId || busy !== null}
          onClick={() => void runPreview()}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#FF6B00]/20 border border-[#FF6B00]/40 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-[#FF6B00]/30 disabled:opacity-40"
        >
          {busy === "preview" ? "Preview…" : "Preview"}
        </button>
        <button
          type="button"
          disabled={
            !projectId ||
            !preview ||
            preview.diff.length === 0 ||
            !writesEnabled ||
            !writeToken.trim() ||
            busy !== null
          }
          onClick={() => void runApply()}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/15 text-[9px] font-black uppercase tracking-widest text-white/70 hover:border-[#FF6B00]/40 hover:text-[#FF6B00] disabled:opacity-40"
        >
          {busy === "apply" ? "Apply…" : "Apply"}
        </button>
      </div>

      <div>
        <label className="text-[9px] font-black text-white/35 uppercase tracking-widest">
          HAM_SETTINGS_WRITE_TOKEN (session only)
        </label>
        <input
          className={inputCls}
          type="password"
          autoComplete="off"
          value={writeToken}
          onChange={(e) => setWriteToken(e.target.value)}
          placeholder="Required to apply — paste from your API env"
        />
      </div>

      {preview && (
        <div className="space-y-3 border border-white/10 rounded-lg p-4 bg-black/30">
          <div className="text-[9px] font-mono text-white/40 break-all">
            base_revision: {preview.base_revision.slice(0, 16)}… → {preview.write_target}
          </div>
          {preview.warnings.length > 0 && (
            <ul className="list-disc pl-4 space-y-1 text-[10px] text-amber-400/90">
              {preview.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          {preview.diff.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[9px] font-mono text-left">
                <thead>
                  <tr className="text-white/35 uppercase tracking-tighter">
                    <th className="py-1 pr-2">path</th>
                    <th className="py-1 pr-2">old</th>
                    <th className="py-1">new</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.diff.map((d) => (
                    <tr key={d.path} className="border-t border-white/5 text-white/55">
                      <td className="py-1 pr-2 align-top">{d.path}</td>
                      <td className="py-1 pr-2 align-top text-red-400/70">{String(d.old)}</td>
                      <td className="py-1 align-top text-green-400/70">{String(d.new)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ContextAndMemoryPanel() {
  const [data, setData] = React.useState<ContextEnginePayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchContextEngine();
      setData(payload);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load context engine snapshot");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const roleOrder = [
    { key: "architect" as const, label: "Architect" },
    { key: "commander" as const, label: "Routing (Hermes)" },
    { key: "critic" as const, label: "Review (Hermes)" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[10px] font-bold text-white/30 uppercase tracking-widest max-w-xl leading-relaxed">
          Live snapshot from <span className="font-mono text-[#FF6B00]/80">GET /api/context-engine</span>
          {" "}(Vite dev proxies <span className="font-mono">/api</span> to FastAPI; production set{" "}
          <span className="font-mono">VITE_HAM_API_BASE</span>). Snapshot uses the API process working directory unless you use a project-scoped route.
        </p>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[9px] font-black uppercase tracking-widest text-white/50 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 transition-colors disabled:opacity-40"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl border border-red-500/30 bg-red-500/5 text-[11px] font-bold text-red-400/90">
          {error}
        </div>
      )}

      {loading && !data && !error && (
        <div className="p-12 rounded-xl border border-white/5 bg-black/30 text-center text-[10px] font-bold text-white/25 uppercase tracking-widest">
          Loading context engine…
        </div>
      )}

      {data && (
        <>
          <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-3">
            <div className="text-[9px] font-black text-white/25 uppercase tracking-widest">Working directory</div>
            <div className="text-[11px] font-mono text-white/70 break-all leading-relaxed">{data.cwd}</div>
            <div className="flex flex-wrap gap-4 text-[9px] font-bold text-white/35 uppercase tracking-wider">
              <span>{data.current_date}</span>
              <span>{data.platform_info}</span>
              <span>{data.file_count} indexed files</span>
              <span>{data.instruction_file_count} instruction files</span>
              <span className={data.git.has_repo ? "text-green-500/70" : "text-amber-500/70"}>
                Git {data.git.has_repo ? "detected" : "unavailable"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {roleOrder.map(({ key, label }) => {
              const r = data.roles[key];
              const pct = Math.min(
                100,
                (r.rendered_chars / Math.max(1, r.instruction_budget_chars + r.max_diff_chars)) * 100,
              );
              return (
                <div
                  key={key}
                  className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-4 shadow-xl"
                >
                  <div className="text-[10px] font-black text-[#FF6B00] uppercase tracking-widest italic">
                    {label}
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-[10px] font-bold text-white/35 uppercase tracking-wider">
                      <span>Assembled context</span>
                      <span className="font-mono text-white/60">{r.rendered_chars.toLocaleString()} chars</span>
                    </div>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden border border-white/10">
                      <div
                        className="h-full bg-[#FF6B00]/80 shadow-[0_0_12px_rgba(255,107,0,0.35)]"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-[9px] font-bold text-white/25 uppercase tracking-wide leading-relaxed">
                      Instruction budget {r.instruction_budget_chars.toLocaleString()} chars · Diff cap{" "}
                      {r.max_diff_chars.toLocaleString()} chars (matches <span className="font-mono">swarm_agency</span>{" "}
                      per-role render)
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-4">
              <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">
                Session memory (compaction)
              </h4>
              <dl className="space-y-2 text-[10px] font-mono text-white/55">
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">compact_max_tokens</dt>
                  <dd>{data.session_memory.compact_max_tokens}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">compact_preserve</dt>
                  <dd>{data.session_memory.compact_preserve}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">tool_prune_chars</dt>
                  <dd>{data.session_memory.tool_prune_chars}</dd>
                </div>
              </dl>
              <p className="text-[9px] font-bold text-white/25 uppercase tracking-widest leading-relaxed">
                From merged config via <span className="font-mono">memory_heist</span> section (see JSON below).
              </p>
            </div>
            <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-4">
              <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">
                Module defaults (ContextBuilder)
              </h4>
              <dl className="space-y-2 text-[10px] font-mono text-white/55">
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">max_instruction_file_chars</dt>
                  <dd>{data.module_defaults.max_instruction_file_chars}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">max_total_instruction_chars</dt>
                  <dd>{data.module_defaults.max_total_instruction_chars}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-white/30 uppercase tracking-tighter">max_diff_chars</dt>
                  <dd>{data.module_defaults.max_diff_chars}</dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-3">
            <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">Git snapshot sizes</h4>
            <p className="text-[9px] font-bold text-white/25 uppercase tracking-widest">
              Character counts only — raw diff/log not exposed over the API.
            </p>
            <dl className="grid grid-cols-3 gap-4 text-[10px] font-mono text-white/55">
              <div>
                <dt className="text-white/30 uppercase text-[9px]">status</dt>
                <dd>{data.git.status_chars}</dd>
              </div>
              <div>
                <dt className="text-white/30 uppercase text-[9px]">diff</dt>
                <dd>{data.git.diff_chars}</dd>
              </div>
              <div>
                <dt className="text-white/30 uppercase text-[9px]">log</dt>
                <dd>{data.git.log_chars}</dd>
              </div>
            </dl>
          </div>

          {data.config_sources.length > 0 && (
            <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-3">
              <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">Loaded config files</h4>
              <ul className="space-y-2 text-[10px] font-mono text-white/50 break-all">
                {data.config_sources.map((s) => (
                  <li key={s.path}>
                    <span className="text-[#FF6B00]/60">[{s.source}]</span> {s.path}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.instruction_files.length > 0 && (
            <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-3">
              <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">Instruction files</h4>
              <ul className="space-y-1.5 text-[10px] font-mono text-white/50">
                {data.instruction_files.map((f) => (
                  <li key={`${f.scope}:${f.relative_path}`}>
                    {f.relative_path}{" "}
                    <span className="text-white/25">({f.scope})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="p-6 bg-black/40 border border-white/5 rounded-xl space-y-2">
            <h4 className="text-[11px] font-black text-white uppercase tracking-widest italic">
              Merged <span className="font-mono">memory_heist</span> keys
            </h4>
            {Object.keys(data.memory_heist_section).length === 0 ? (
              <p className="text-[10px] font-bold text-white/25 uppercase tracking-widest">
                No keys under <span className="font-mono">memory_heist</span> in merged JSON (defaults apply).
              </p>
            ) : (
              <pre className="text-[9px] font-mono text-white/45 overflow-x-auto max-h-40 overflow-y-auto p-3 bg-black/50 rounded-lg border border-white/5">
                {JSON.stringify(data.memory_heist_section, null, 2)}
              </pre>
            )}
          </div>

          <AllowlistedWorkspaceSettings data={data} onApplied={() => void load()} />
        </>
      )}
    </div>
  );
}

export type SettingsSubSectionId =
  | "api-keys"
  | "environment"
  | "tools-extensions"
  | "context-memory"
  | "execution-history"
  | "system-logs"
  | "diagnostics"
  | "kernel-health"
  | "context-audit"
  | "bridge-dump"
  | "workforce-profiles"
  | "resource-storage"
  | "jobs";

interface UnifiedSettingsProps {
  activeSubSegment: SettingsSubSectionId;
  onSubSegmentChange: (id: SettingsSubSectionId) => void;
  variant?: "overlay" | "page";
}

const settingsStructure = [
  {
    group: "Secrets & environment",
    items: [
      { id: "api-keys", label: "API Keys", icon: Key },
      { id: "environment", label: "Environment", icon: Terminal },
      { id: "tools-extensions", label: "Tools and Extensions", icon: ToyBrick },
    ],
  },
  {
    group: "Workspace Preferences",
    items: [{ id: "context-memory", label: "Context & Memory", icon: Brain }],
  },
  {
    group: "Advanced",
    items: [
      { id: "execution-history", label: "Execution History", icon: History },
      { id: "system-logs", label: "System Logs", icon: Activity },
      { id: "diagnostics", label: "Diagnostics", icon: BarChart3 },
      { id: "kernel-health", label: "Kernel Health", icon: Zap },
      { id: "context-audit", label: "Context Audit", icon: FileSearch },
      { id: "bridge-dump", label: "Bridge Dump", icon: HardDrive },
      { id: "workforce-profiles", label: "Workforce Profiles", icon: Users },
      { id: "resource-storage", label: "Resource Storage", icon: Box },
      { id: "jobs", label: "Jobs", icon: Calendar },
    ],
  },
];

/** Valid `tab` query values for `/settings?tab=…`. */
export function normalizeSettingsTabParam(
  tab: string | null | undefined,
): SettingsSubSectionId {
  let t = tab;
  if (t === "mission-history") {
    t = "execution-history";
  }
  const ok = settingsStructure
    .flatMap((g) => g.items)
    .some((i) => i.id === t);
  return ok ? (t as SettingsSubSectionId) : "api-keys";
}

export function UnifiedSettings({
  activeSubSegment,
  onSubSegmentChange,
  variant = "overlay",
}: UnifiedSettingsProps) {
  const activeLabel = settingsStructure
    .flatMap((g) => g.items)
    .find((i) => i.id === activeSubSegment)?.label;

  return (
    <div className="flex h-full bg-[#050505] font-sans">
      {/* Internal Settings Sub-Nav */}
      <div className={cn(
        "w-64 border-r border-white/5 p-8 flex flex-col gap-10 overflow-y-auto shrink-0",
        variant === "page" ? "bg-transparent" : "bg-[#0c0c0c]"
      )}>
        {settingsStructure.map((group) => (
          <div key={group.group} className="space-y-4">
            <h4 className="px-3 text-[9px] font-black text-white/20 uppercase tracking-[0.4em] italic leading-none">
              {group.group}
            </h4>
            <div className="space-y-1">
              {group.items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => onSubSegmentChange(item.id as SettingsSubSectionId)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left group",
                    activeSubSegment === item.id
                      ? "bg-[#FF6B00]/10 text-[#FF6B00]"
                      : "text-white/30 hover:text-white hover:bg-white/[0.03]"
                  )}
                >
                  <item.icon
                    className={cn(
                      "h-3.5 w-3.5",
                      activeSubSegment === item.id
                        ? "text-[#FF6B00]"
                        : "text-white/20"
                    )}
                  />
                  <span className="text-[10px] font-black uppercase tracking-widest whitespace-nowrap">
                    {item.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Sub-Settings Content Area */}
      <div className="flex-1 overflow-y-auto p-12 pb-32 scrollbar-hide">
        <div className="space-y-12 animate-in fade-in slide-in-from-right-4 duration-500 max-w-4xl">
          {/* Section Header */}
          <div className="space-y-3 pb-8 border-b border-white/5">
            <h2 className="text-3xl font-black text-white uppercase italic tracking-tighter leading-none">
              {activeLabel}
            </h2>
            <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-2xl">
              {activeSubSegment === "environment" ? (
                <>
                  Read-only reference for local <span className="font-mono text-white/35">.env</span> variables. Edit the file on disk; values are never shown here (alpha).
                </>
              ) : (
                <>Industrial grade {activeSubSegment.replace("-", " ")} configuration for secure HAM operations.</>
              )}
            </p>
          </div>

          <div className="space-y-10">
            {/* --- CONFIGURATION PAGES --- */}
            {["api-keys", "environment", "tools-extensions", "context-memory"].includes(activeSubSegment) && (
              <div className="space-y-6">
                {activeSubSegment === "api-keys" && <ApiKeysPanel />}

                {activeSubSegment === "environment" && (
                  <div className="space-y-6">
                    <div className="rounded-lg border border-white/10 bg-black/40 p-5 space-y-3">
                      <p className="text-[11px] font-bold text-white/50 leading-relaxed">
                        <span className="text-[#FF6B00] uppercase tracking-widest text-[10px] font-black">Secrets</span> — use{" "}
                        <span className="font-mono text-white/60">API Keys</span> above for provider tokens. This page lists{" "}
                        <span className="italic text-white/40">names</span> only so you know what Ham reads from the process environment (mostly model routing).
                      </p>
                      <p className="text-[10px] font-bold text-white/25 uppercase tracking-widest">
                        Copy <span className="font-mono">.env.example</span> → <span className="font-mono">.env</span> at the repo root; restart CLI / API after edits.
                      </p>
                    </div>
                    <div className="overflow-hidden rounded-lg border border-white/5 bg-white/[0.02]">
                      <table className="w-full text-left text-[11px]">
                        <thead className="border-b border-white/10 bg-black/50 text-[9px] font-black uppercase tracking-widest text-white/35">
                          <tr>
                            <th className="px-4 py-3">Variable</th>
                            <th className="px-4 py-3">Kind</th>
                            <th className="px-4 py-3">Role</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-white/55">
                          {[
                            {
                              name: "OPENROUTER_API_KEY",
                              kind: "Secret",
                              role: "LLM calls via LiteLLM / OpenRouter (same key as API Keys conceptually).",
                            },
                            {
                              name: "OPENROUTER_API_URL",
                              kind: "Config",
                              role: "Optional override; default https://openrouter.ai/api/v1",
                            },
                            {
                              name: "DEFAULT_MODEL",
                              kind: "Config",
                              role: "Default model id when not set elsewhere (e.g. openai/gpt-4o-mini).",
                            },
                            {
                              name: "OPENROUTER_HTTP_REFERER",
                              kind: "Optional",
                              role: "OpenRouter attribution / site URL.",
                            },
                            {
                              name: "OPENROUTER_APP_TITLE",
                              kind: "Optional",
                              role: "OpenRouter app name string.",
                            },
                            {
                              name: "CURSOR_API_KEY",
                              kind: "Secret",
                              role: "Cursor API key when not set via Settings (falls back after UI-saved key is cleared).",
                            },
                            {
                              name: "HAM_AUTHOR",
                              kind: "Optional",
                              role: "Attributed author on persisted run records; falls back to USER / USERNAME.",
                            },
                          ].map((row) => (
                            <tr key={row.name} className="hover:bg-white/[0.02]">
                              <td className="px-4 py-3 font-mono text-[10px] text-[#FF6B00]/90">{row.name}</td>
                              <td className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-white/35">{row.kind}</td>
                              <td className="px-4 py-3 text-[10px] leading-snug text-white/40">{row.role}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest">
                      Alpha: no live env inspection — add server-backed <span className="font-mono">GET /api/env/names</span> later if needed.
                    </p>
                  </div>
                )}

                {activeSubSegment === "tools-extensions" && (
                   <div className="space-y-16 animate-in fade-in slide-in-from-bottom-2 duration-500">
                      {/* Section 1: Built-in Tools */}
                      <div className="space-y-6">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <ToyBrick className="h-4 w-4 text-[#FF6B00]" />
                              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">Built-in Tools</h3>
                            </div>
                            <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">Core HAM operational capabilities</p>
                          </div>
                          <div className="h-px flex-1 mx-8 bg-white/5" />
                          <div className="flex items-center gap-3">
                             <span className="text-[8px] font-black text-white/10 uppercase tracking-widest">Active Pool: 6/7</span>
                             <div className="h-1 w-12 bg-white/5 rounded-full overflow-hidden">
                                <div className="h-full bg-[#FF6B00] w-[85%]" />
                             </div>
                          </div>
                        </div>
                        <div className="space-y-2">
                          {[
                            { name: "Code Interpreter", desc: "Execute sandboxed code in Python and JS environments.", status: "active", scope: "all droids", icon: Terminal, load: "High" },
                            { name: "Web Intelligence", desc: "Live web traversal and semantic extraction.", status: "active", scope: "selected droids", icon: Globe, load: "Nominal" },
                            { name: "Image Extraction", desc: "Multi-modal vision analysis for visual datasets.", status: "setup required", scope: "team only", icon: Zap, load: "Standby" },
                            { name: "Browser", desc: "Autonomous browser orchestration for task completion.", status: "active", scope: "all droids", icon: Monitor, load: "Idle" },
                            { name: "Preview", desc: "Real-time rendering of generated artifacts and code.", status: "active", scope: "all droids", icon: Eye, load: "Idle" },
                            { name: "Search", desc: "Industrial-grade index searching across global networks.", status: "inactive", scope: "team only", icon: Search, load: "Locked" },
                            { name: "Workspace Context", desc: "High-density local knowledge indexing.", status: "active", scope: "all droids", icon: Brain, load: "Syncing" },
                          ].map((tool, i) => (
                            <div key={i} className="group flex items-center gap-6 p-4 bg-black/40 border border-white/5 rounded-xl hover:border-[#FF6B00]/20 transition-all shadow-lg relative overflow-hidden">
                              <div className="absolute top-0 left-0 w-1 h-full bg-[#FF6B00] opacity-0 group-hover:opacity-100 transition-opacity" />
                              <div className="h-10 w-10 shrink-0 bg-white/[0.03] rounded border border-white/5 flex items-center justify-center group-hover:bg-[#FF6B00]/10 transition-colors">
                                <tool.icon className="h-4 w-4 text-[#FF6B00]" />
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] font-black text-white uppercase tracking-widest truncate">{tool.name}</span>
                                  <div className={cn(
                                    "px-1.5 py-0.5 rounded-[2px] text-[7px] font-black uppercase tracking-tighter",
                                    tool.status === 'active' ? "bg-green-500/10 text-green-500 border border-green-500/20" : 
                                    tool.status === 'setup required' ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" : 
                                    "bg-white/5 text-white/20 border border-white/10"
                                  )}>
                                    {tool.status}
                                  </div>
                                </div>
                                <p className="text-[9px] font-bold text-white/40 uppercase tracking-widest truncate italic leading-none">{tool.desc}</p>
                              </div>
                              <div className="hidden md:flex flex-col items-center gap-1 px-4 border-l border-white/5 min-w-[100px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Load State</span>
                                <span className="text-[9px] font-mono font-bold text-[#FF6B00]/60 uppercase tracking-tighter italic">{tool.load}</span>
                              </div>
                              <div className="hidden md:flex flex-col items-end gap-1 px-4 border-l border-white/5 min-w-[120px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Assignment</span>
                                <span className="text-[9px] font-black text-white/40 uppercase tracking-tighter italic whitespace-nowrap">{tool.scope}</span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Assign</button>
                                <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Configure</button>
                                <button className="h-8 px-3 rounded bg-[#FF6B00]/10 border border-[#FF6B00]/20 text-[9px] font-black text-[#FF6B00] uppercase tracking-widest hover:bg-[#FF6B00]/20 transition-all">
                                  {tool.status === 'active' ? "Disable" : "Enable"}
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Section 2: Extensions & Plugins */}
                      <div className="space-y-6">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <Package className="h-4 w-4 text-[#FF6B00]" />
                              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">Extensions & Plugins</h3>
                            </div>
                            <p className="text-[10px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">3rd party integrations and modular enhancements</p>
                          </div>
                          <div className="flex items-center gap-3 ml-8">
                             <div className="h-px w-24 bg-white/5" />
                             <button className="flex items-center gap-2 px-3 py-1.5 rounded border border-[#FF6B00]/20 bg-[#FF6B00]/5 text-[#FF6B00] hover:bg-[#FF6B00]/10 transition-all group">
                                <Plus className="h-3 w-3" />
                                <span className="text-[9px] font-black uppercase tracking-widest italic leading-none">Add Extension</span>
                             </button>
                             <div className="h-px flex-1 bg-white/5" />
                          </div>
                        </div>
                        <div className="space-y-2">
                          {[
                            { name: "Mercury UI Tab", type: "UI Interface", installed: true, enabled: true, desc: "Custom operational surface for high-frequency trading data.", icon: Layout, version: "v1.2.4" },
                            { name: "Azure Bridge", type: "Provider Integration", installed: true, enabled: false, desc: "Connects HAM units to Azure Cloud Service endpoints.", icon: Database, version: "v0.9.8" },
                            { name: "Slack Bridge", type: "Social Hub", installed: false, enabled: false, desc: "Bidirectional workspace communication pipeline.", icon: RefreshCw, version: "v2.1.0" },
                            { name: "Auth Bundle", type: "Security Extension", installed: true, enabled: true, desc: "Advanced OAuth and JWT validation logic.", icon: Lock, version: "v4.0.1" },
                          ].map((ext, i) => (
                            <div key={i} className="group flex items-center gap-6 p-4 bg-black/40 border border-white/5 rounded-xl hover:bg-white/[0.02] transition-all relative overflow-hidden">
                              <div className="h-10 w-10 shrink-0 border border-white/5 rounded bg-white/[0.02] flex items-center justify-center opacity-40 group-hover:opacity-100 transition-opacity">
                                <ext.icon className="h-4 w-4 text-white" />
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] font-black text-white uppercase tracking-widest">{ext.name}</span>
                                  <span className="text-[8px] font-bold text-[#FF6B00]/60 uppercase tracking-widest italic px-1.5 py-0.5 rounded-[2px] bg-[#FF6B00]/5 border border-[#FF6B00]/10">{ext.type}</span>
                                </div>
                                <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest truncate italic leading-none">{ext.desc}</p>
                              </div>
                              <div className="hidden md:flex flex-col items-center gap-1 px-4 border-l border-white/5 min-w-[80px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Version</span>
                                <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-tighter italic">{ext.version}</span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                {!ext.installed ? (
                                  <button className="h-8 px-4 rounded bg-[#FF6B00] text-[9px] font-black text-black uppercase tracking-widest hover:bg-[#FF8533] transition-all flex items-center gap-2">
                                    <Download className="h-3 w-3" />
                                    <span>Install</span>
                                  </button>
                                ) : (
                                  <>
                                    <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all flex items-center gap-2">
                                       <ArrowUpRight className="h-3 w-3" />
                                       <span>Open</span>
                                    </button>
                                    <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Configure</button>
                                    <button className={cn(
                                      "h-8 px-4 rounded text-[9px] font-black uppercase tracking-widest transition-all",
                                      ext.enabled ? "bg-[#FF6B00]/10 border border-[#FF6B00]/20 text-[#FF6B00]" : "bg-white/5 border border-white/10 text-white/20"
                                    )}>
                                      {ext.enabled ? "Disable" : "Enable"}
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                   </div>
                )}

                {activeSubSegment === "context-memory" && <ContextAndMemoryPanel />}
              </div>
            )}

            {/* --- HEALTH / STATUS PAGES --- */}
            {["kernel-health", "diagnostics"].includes(activeSubSegment) && (
              <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                   {[
                      { label: "Kernel Version", value: "2.5.0-HAM", status: "Operational", trend: "Stable" },
                      { label: "Active Workers", value: "154 Units", status: "Optimal", trend: "Nominal" },
                      { label: "Bridge Latency", value: "12ms", status: "Accelerated", trend: "High Speed" },
                      { label: "Memory Pressure", value: "14%", status: "Safe", trend: "Liquid Content" },
                      { label: "Provider Sync", value: "3/3 Active", status: "Aligned", trend: "Synchronized" },
                      { label: "Resource Load", value: "48%", status: "Balanced", trend: "Managed" },
                   ].map((metric, i) => (
                      <div key={i} className="p-6 bg-[#0c0c0c] border border-white/5 rounded-xl space-y-4 hover:border-white/20 transition-all">
                         <div className="flex justify-between items-start">
                            <span className="text-[10px] font-black text-white/20 uppercase tracking-widest leading-none">{metric.label}</span>
                            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]" />
                         </div>
                         <div className="space-y-1">
                            <div className="text-xl font-black text-white italic tracking-tighter leading-none">{metric.value}</div>
                            <div className="flex items-center gap-2">
                               <span className="text-[9px] font-black text-[#FF6B00] uppercase italic tracking-widest">{metric.status}</span>
                               <span className="text-[8px] font-bold text-white/10 uppercase tracking-widest">{metric.trend}</span>
                            </div>
                         </div>
                      </div>
                   ))}
                </div>

                <div className="p-10 bg-black/40 border border-white/10 rounded-2xl relative overflow-hidden group">
                   <div className="absolute inset-0 bg-gradient-to-r from-[#FF6B00]/5 to-transparent skew-x-12 -translate-x-full group-hover:translate-x-full transition-transform duration-[2000ms] ease-in-out" />
                   <div className="space-y-6 relative z-10 text-center">
                      <div className="h-1 w-1 bg-[#FF6B00] mx-auto rounded-full" />
                      <div className="space-y-2">
                         <h4 className="text-[12px] font-black text-white uppercase italic tracking-[0.4em]">Run Deep Sector Scan</h4>
                         <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-sm mx-auto leading-relaxed">Initiate a full-system audit of all workforce bridge connections and memory registers.</p>
                      </div>
                      <button className="px-10 py-3 bg-[#FF6B00]/10 border border-[#FF6B00]/40 text-[10px] font-black text-[#FF6B00] uppercase tracking-[0.3em] italic hover:bg-[#FF6B00] hover:text-black transition-all rounded shadow-xl">Start System Diagnostics</button>
                   </div>
                </div>
              </div>
            )}

            {/* --- HISTORY / AUDIT PAGES --- */}
            {["execution-history", "system-logs", "context-audit", "bridge-dump"].includes(activeSubSegment) && (
              <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-700">
                <div className="flex items-center justify-between px-6 py-4 bg-white/[0.02] border border-white/10 rounded-xl">
                   <div className="flex items-center gap-4">
                      <History className="h-4 w-4 text-[#FF6B00]" />
                      <span className="text-[11px] font-black text-white uppercase tracking-widest italic">Live Audit Stream</span>
                   </div>
                   <div className="flex items-center gap-4">
                      <div className="flex items-center gap-2 px-3 py-1 bg-black/40 border border-white/5 rounded text-[9px] font-black text-white/20 uppercase tracking-widest">
                         <FileSearch className="h-3 w-3" /> Filter Log Level
                      </div>
                      <div className="text-[9px] font-black text-[#FF6B00] uppercase tracking-widest underline underline-offset-4 cursor-pointer">Export Payload</div>
                   </div>
                </div>

                <div className="bg-[#0c0c0c] border border-white/5 rounded-xl divide-y divide-white/5 overflow-hidden shadow-2xl">
                   {[
                      { time: "05:12:04", action: "BRIDGE_RE_SYNC", actor: "Kernel", result: "COMPLETE", detail: "Rotated 154 worker heartbeat keys." },
                      { time: "05:10:55", action: "MEMORY_FLUSH", actor: "System", result: "NOMINAL", detail: "Purged 3.4GB of stale cache registers." },
                      { time: "05:08:21", action: "ID_VERIFY", actor: "Security", result: "SECURE", detail: "Verified user ham-admin82 through biometric bridge." },
                      { time: "05:04:12", action: "UNIT_REALLOCATE", actor: "Kernel", result: "ALIGNED", detail: "Moved 4 units from extraction to logic core." },
                      { time: "04:59:33", action: "TOOL_CALIBRATE", actor: "Chipset", result: "ACCELERATED", detail: "Optimized Code Interpreter for v3 architecture." },
                   ].map((log, i) => (
                      <div key={i} className="flex grid grid-cols-12 gap-8 items-center px-8 py-6 hover:bg-white/[0.02] transition-colors group">
                         <div className="col-span-1 text-[10px] font-mono text-white/20 whitespace-nowrap">{log.time}</div>
                         <div className="col-span-3 text-[11px] font-black text-[#FF6B00]/80 uppercase italic tracking-widest leading-none group-hover:text-[#FF6B00] transition-colors">{log.action}</div>
                         <div className="col-span-2 text-[9px] font-black text-white/20 uppercase tracking-[0.2em]">{log.actor}</div>
                         <div className="col-span-4 text-[11px] font-bold text-white/40 italic leading-relaxed">{log.detail}</div>
                         <div className="col-span-2 text-right">
                            <span className="text-[10px] font-black px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-500/60 uppercase">{log.result}</span>
                         </div>
                      </div>
                   ))}
                </div>
              </div>
            )}

            {/* --- JOBS / OTHERS --- */}
            {activeSubSegment === "jobs" && (
               <div className="space-y-8">
                  <div className="p-12 bg-black/40 border border-[#FF6B00]/20 border-dashed rounded-3xl flex flex-col items-center justify-center text-center space-y-8 animate-in zoom-in-95 duration-700">
                     <div className="h-20 w-20 bg-black/60 border border-white/5 rounded-full flex items-center justify-center relative group overflow-hidden">
                        <div className="absolute inset-0 bg-[#FF6B00]/2 animate-pulse" />
                        <Calendar className="h-8 w-8 text-white/10 relative z-10" />
                     </div>
                     <div className="space-y-3 relative z-10">
                        <h3 className="text-xl font-black text-white uppercase italic tracking-[0.3em]">SCHEDULER_OFFLINE</h3>
                        <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] max-w-sm mx-auto leading-relaxed italic">The automated task scheduler is currently set to manual override. Scheduled jobs will be surfaced here in HAM v3.2.</p>
                     </div>
                     <button className="px-10 py-3 bg-white/5 border border-white/10 text-[10px] font-black text-white/20 uppercase tracking-widest rounded transition-all hover:bg-white/10 hover:text-white group">
                        Define Cron Directive <Plus className="ml-2 h-3.5 w-3.5 inline group-hover:text-[#FF6B00] transition-colors" />
                     </button>
                  </div>
               </div>
            )}

            {/* General Placeholder for everything else */}
            {!["api-keys", "environment", "tools-extensions", "context-memory", "kernel-health", "diagnostics", "execution-history", "system-logs", "context-audit", "bridge-dump", "jobs"].includes(activeSubSegment) && (
              <div className="space-y-10">
                <div className="p-16 bg-black/20 border border-white/5 border-dashed rounded-2xl flex flex-col items-center justify-center text-center space-y-8 group transition-all hover:bg-black/40">
                  <div className="h-16 w-16 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center transition-transform group-hover:scale-110">
                    <Zap className="h-6 w-6 text-white/10 group-hover:text-[#FF6B00]" />
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-lg font-black text-white/40 uppercase italic tracking-[0.3em] group-hover:text-white transition-colors leading-none">calibration_active</h3>
                    <p className="text-[11px] font-bold text-white/10 group-hover:text-white/20 uppercase tracking-[0.4em] max-w-sm mx-auto transition-colors leading-relaxed">
                      The {activeLabel} subsystem is currently being optimized for high-throughput bridge operations.
                    </p>
                  </div>
                  <div className="flex items-center gap-3 opacity-40">
                    <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] animate-pulse" />
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-[0.5em]">awaiting telemetry</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
