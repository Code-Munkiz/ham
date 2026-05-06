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
  Orbit,
} from "lucide-react";

import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  clearSavedCursorApiKey,
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchProjectContextEngine,
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
import { DesktopBundlePanel } from "@/components/settings/DesktopBundlePanel";
import {
  fetchLocalWorkspaceContextSnapshot,
  fetchLocalWorkspaceHealth,
  isLocalRuntimeConfigured,
} from "@/features/hermes-workspace/adapters/localRuntime";
import {
  loadContextMemorySnapshot,
  shouldGateContextMemorySettingsMutations,
} from "@/features/hermes-workspace/lib/contextMemorySnapshotLoadPlan";
import { useOptionalWorkspaceHamProject } from "@/features/hermes-workspace/WorkspaceHamProjectContext";

export type SettingsPanelVisualVariant = "default" | "workspace";

export function ApiKeysPanel({ variant = "default" }: { variant?: SettingsPanelVisualVariant }) {
  const w = variant === "workspace";
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
    <div className={cn("space-y-6", w && "hww-settings-panels")}>
      <div
        className={cn(
          "space-y-4",
          w
            ? "hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-none md:p-6"
            : "rounded-xl border border-[#FF6B00]/20 bg-black/50 p-6 shadow-xl",
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Key className={cn("h-4 w-4", w ? "text-[#5eead4]/90" : "text-[#FF6B00]")} />
              <h3
                className={cn(
                  w
                    ? "text-sm font-semibold text-[#e8eef8]"
                    : "text-[13px] font-black uppercase italic tracking-[0.2em] text-white",
                )}
              >
                Cursor API key
              </h3>
            </div>
            <p
              className={cn(
                "max-w-2xl leading-relaxed",
                w
                  ? "text-[13px] text-white/45"
                  : "text-[10px] font-bold uppercase tracking-widest text-white/35",
              )}
            >
              {w ? (
                "Used for cloud agents and model calls through the Ham API. The key is stored on the server; team members with access can rotate it from here."
              ) : (
                <>
                  Ham proxies Cursor Cloud Agents (
                  <span className="font-mono text-white/50">GET/POST /v0/*</span>) with this key.
                  Stored only on the API host filesystem (see path below). Set{" "}
                  <span className="font-mono text-white/45">HAM_CURSOR_CREDENTIALS_FILE</span> on
                  Cloud Run/Docker with a mounted volume so the key survives restarts. Anyone with
                  access to this Settings page can rotate the team key.
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || busy}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors disabled:opacity-40",
              w
                ? "border-white/[0.1] text-[12px] font-medium text-white/60 hover:border-white/20 hover:bg-white/[0.04] hover:text-white/90"
                : "border-white/10 text-[9px] font-black uppercase tracking-widest text-white/50 hover:border-[#FF6B00]/30 hover:text-[#FF6B00]",
            )}
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
          <p
            className={cn(
              w
                ? "text-[13px] text-white/40"
                : "text-[10px] font-bold uppercase tracking-widest text-white/25",
            )}
          >
            Loading key status…
          </p>
        )}

        {status && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div
              className={cn(
                "space-y-2 rounded-xl border p-4",
                w ? "border-white/[0.06] bg-white/[0.02]" : "border-white/5 bg-black/40",
              )}
            >
              <div
                className={cn(
                  w
                    ? "text-xs font-medium text-white/50"
                    : "text-[9px] font-black uppercase tracking-widest text-white/25",
                )}
              >
                Key source
              </div>
              <div
                className={cn(
                  w
                    ? "text-sm font-medium text-[#99f6e4]/95"
                    : "text-[12px] font-black uppercase tracking-tight text-[#FF6B00]",
                )}
              >
                {sourceLabel}
              </div>
              {status.configured && status.masked_preview && (
                <div className={cn("text-white/45", w ? "text-xs" : "text-[10px] font-mono")}>
                  Preview: {status.masked_preview}
                </div>
              )}
            </div>
            <div
              className={cn(
                "space-y-2 rounded-xl border p-4",
                w ? "border-white/[0.06] bg-white/[0.02]" : "border-white/5 bg-black/40",
              )}
            >
              <div
                className={cn(
                  w
                    ? "text-xs font-medium text-white/50"
                    : "text-[9px] font-black uppercase tracking-widest text-white/25",
                )}
              >
                Account
              </div>
              {status.error && !status.user_email ? (
                <div className="text-[13px] font-medium text-amber-400/90">{status.error}</div>
              ) : (
                <>
                  <div
                    className={cn(
                      "text-white",
                      w ? "text-sm font-medium" : "text-[12px] font-black",
                    )}
                  >
                    {status.api_key_name ?? "—"}{" "}
                    <span
                      className={cn(
                        w
                          ? "text-white/40"
                          : "text-[10px] font-bold uppercase tracking-widest text-white/30",
                      )}
                    >
                      {w ? "" : "(key name)"}
                    </span>
                  </div>
                  <div
                    className={cn(
                      "break-all text-white/60",
                      w ? "text-sm" : "text-[11px] font-mono",
                    )}
                  >
                    {status.user_email ?? "—"}{" "}
                    {!w && (
                      <span className="text-[9px] font-bold uppercase tracking-widest text-white/25">
                        (account)
                      </span>
                    )}
                  </div>
                  {status.key_created_at && (
                    <div
                      className={cn(
                        "text-white/40",
                        w ? "text-xs" : "text-[9px] font-bold uppercase tracking-wider",
                      )}
                    >
                      Issued: {status.key_created_at}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {status?.storage_path && (
          <div
            className={cn(
              "space-y-1 rounded-xl border p-4",
              w ? "border-white/[0.06] bg-white/[0.02]" : "border-white/5 bg-black/30",
            )}
          >
            <div
              className={cn(
                w
                  ? "text-xs font-medium text-white/50"
                  : "text-[9px] font-black uppercase tracking-widest text-white/25",
              )}
            >
              File on server
            </div>
            <div
              className={cn(
                "break-all text-white/55",
                w ? "text-xs font-mono" : "text-[10px] font-mono",
              )}
            >
              {status.storage_path}
            </div>
            {status.storage_override_env ? (
              <div className="text-xs text-emerald-400/80">
                Override: HAM_CURSOR_CREDENTIALS_FILE is set
              </div>
            ) : null}
          </div>
        )}

        {status?.wired_for && (
          <div
            className={cn(
              "space-y-3 rounded-xl border p-4",
              w ? "border-white/[0.08] bg-white/[0.02]" : "border-[#FF6B00]/15 bg-black/40",
            )}
          >
            <div
              className={cn(
                w
                  ? "text-xs font-medium text-white/50"
                  : "text-[9px] font-black uppercase tracking-widest text-white/25",
              )}
            >
              {w ? "What this key is used for" : "What uses this key (backend, this deployment)"}
            </div>
            <ul
              className={cn(
                "space-y-2 text-white/55",
                w
                  ? "text-[13px] font-normal normal-case"
                  : "text-[10px] font-bold uppercase tracking-wider text-white/45",
              )}
            >
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
                  <span className="font-mono text-white/50">POST /api/cursor/agents/launch</span> →
                  Cursor <span className="font-mono text-white/50">POST /v0/agents</span>
                </span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500/90 shrink-0 mt-0.5" />
                <span>
                  <span className="text-white/70">CI hooks and automation</span> — same launch URL
                  with a bearer-less server-to-server call to your Ham API (Basic auth key is
                  server-side only).
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
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors disabled:opacity-30",
                  w
                    ? "border-white/[0.1] text-[12px] font-medium text-white/70 hover:border-[#5eead4]/30 hover:bg-white/[0.04] hover:text-white"
                    : "border-[#FF6B00]/35 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-[#FF6B00]/10",
                )}
              >
                <Zap className={cn("h-3.5 w-3.5", modelsBusy && "animate-pulse")} />
                Test models
              </button>
              {!status.configured && (
                <span
                  className={cn(
                    "text-white/40",
                    w ? "text-xs" : "text-[9px] font-bold uppercase tracking-widest",
                  )}
                >
                  Add a key first
                </span>
              )}
            </div>
            {modelsProbe && (
              <pre
                className={cn(
                  "whitespace-pre-wrap break-all font-mono text-white/50",
                  w
                    ? "max-h-32 overflow-y-auto rounded-lg border border-white/[0.06] bg-black/30 p-3 text-xs"
                    : "max-h-32 overflow-y-auto rounded border border-white/5 bg-black/50 p-2 text-[9px]",
                )}
              >
                {modelsProbe}
              </pre>
            )}
          </div>
        )}

        <div className={cn("space-y-2 border-t border-white/5 pt-2", w && "border-white/[0.06]")}>
          <label
            className={cn(
              "block",
              w
                ? "text-xs font-medium text-white/50"
                : "text-[9px] font-black uppercase tracking-widest text-white/30",
            )}
          >
            New key (replaces saved)
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              type="password"
              autoComplete="off"
              value={draftKey}
              onChange={(e) => setDraftKey(e.target.value)}
              placeholder="crsr_…"
              className={cn(
                "h-11 flex-1 rounded-lg border px-4 font-mono text-[13px] text-white/80 placeholder:text-white/20 focus:outline-none",
                w
                  ? "border-white/[0.1] bg-black/20 focus:border-[#5eead4]/30 focus:ring-1 focus:ring-[#5eead4]/20"
                  : "border-white/10 bg-black/60 text-[11px] focus:border-[#FF6B00]/40",
              )}
            />
            <button
              type="button"
              disabled={busy || !draftKey.trim()}
              onClick={() => void onSave()}
              className={cn(
                "h-11 rounded-lg px-6 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-30",
                w
                  ? "bg-[#0f766e] text-white hover:bg-[#0d9488] dark:bg-[#14b8a6]/90"
                  : "bg-[#FF6B00] text-[10px] font-black uppercase tracking-widest text-black hover:bg-[#ff8534]",
              )}
            >
              Save
            </button>
          </div>
          {status?.source === "ui" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onClearSaved()}
              className={cn(
                "text-white/40 transition-colors hover:text-red-300/90",
                w ? "text-xs" : "text-[9px] font-black uppercase tracking-widest",
              )}
            >
              Remove saved key
            </button>
          )}
        </div>
      </div>

      <div
        className={cn(
          "space-y-3 rounded-xl border p-5",
          w ? "border-white/[0.08] bg-white/[0.02]" : "border-white/5 bg-white/[0.02]",
        )}
      >
        <div className="flex items-center gap-2">
          <Globe className={cn("h-4 w-4", w ? "text-white/40" : "text-white/25")} />
          <h4
            className={cn(
              w
                ? "text-sm font-medium text-white/80"
                : "text-[11px] font-black uppercase tracking-widest text-white/60",
            )}
          >
            OpenRouter (chat)
          </h4>
        </div>
        <p
          className={cn(
            "leading-relaxed",
            w
              ? "text-[13px] text-white/45"
              : "text-[10px] font-bold uppercase tracking-widest text-white/30",
          )}
        >
          {w ? (
            <>
              When the API uses the OpenRouter gateway, set keys in the environment; see the
              Connection page for variable names. Cursor and OpenRouter can both be configured.
            </>
          ) : (
            <>
              Dashboard chat still uses{" "}
              <span className="font-mono text-white/45">HERMES_GATEWAY_MODE=openrouter</span> and{" "}
              <span className="font-mono text-white/45">OPENROUTER_API_KEY</span> unless you change
              the gateway on the API host. Cursor and OpenRouter can both be configured; wiring chat
              to Composer is a separate gateway mode.
            </>
          )}
        </p>
      </div>

      {!w && (
        <div className="space-y-2 rounded-lg border border-dashed border-white/5 bg-black/20 p-5">
          <div className="text-[10px] font-black uppercase tracking-widest text-white/25">
            Roadmap
          </div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-white/35">
            <span className="text-white/50">Local Composer</span> — Node SDK / sidecar for
            repo-on-disk workflows (separate from Cloud Agents REST above).
          </p>
        </div>
      )}
    </div>
  );
}

/** Read-only .env name table; used in full Settings and in Workspace "Connection" (repomix Connection tips reference env on disk). */
export function EnvironmentReadonlyPanel({
  variant = "default",
}: {
  variant?: SettingsPanelVisualVariant;
}) {
  const w = variant === "workspace";
  return (
    <div className="space-y-5">
      {!w && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-black/40 p-5">
          <h4 className="text-[11px] font-bold text-white/50">
            <span className="text-[#FF6B00] text-[10px] font-black uppercase tracking-widest">
              Secrets
            </span>{" "}
            — use <span className="font-mono text-white/60">API Keys</span> in Model &amp; provider
            for provider tokens. This page lists <span className="italic text-white/40">names</span>{" "}
            only so you know what Ham reads from the process environment (mostly model routing).
          </h4>
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/25">
            Copy <span className="font-mono">.env.example</span> →{" "}
            <span className="font-mono">.env</span> at the repo root; restart CLI / API after edits.
          </p>
        </div>
      )}
      <div
        className={cn(
          "overflow-hidden rounded-xl border",
          w ? "border-white/[0.08] bg-white/[0.02]" : "border-white/5 bg-white/[0.02]",
        )}
      >
        <table className="w-full text-left">
          <thead
            className={cn(
              "border-b text-left",
              w
                ? "border-white/[0.08] bg-white/[0.02] text-xs font-medium text-white/45"
                : "border-white/10 bg-black/50 text-[9px] font-black uppercase tracking-widest text-white/35",
            )}
          >
            <tr>
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Kind</th>
              <th className="px-4 py-2.5 font-medium">Role</th>
            </tr>
          </thead>
          <tbody
            className={cn(
              "divide-y text-white/60",
              w ? "divide-white/[0.06] text-[13px]" : "divide-white/5 text-[11px] text-white/55",
            )}
          >
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
                role: "Default model id when not set elsewhere (e.g. minimax/minimax-m2.5:free).",
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
                <td
                  className={cn(
                    "px-4 py-2.5 font-mono",
                    w ? "text-xs text-[#5eead4]/90" : "text-[10px] text-[#FF6B00]/90",
                  )}
                >
                  {row.name}
                </td>
                <td
                  className={cn(
                    "px-4 py-2.5",
                    w
                      ? "text-xs text-white/50"
                      : "text-[10px] font-bold uppercase tracking-widest text-white/35",
                  )}
                >
                  {row.kind}
                </td>
                <td
                  className={cn(
                    "px-4 py-2.5 leading-snug",
                    w ? "text-[13px] text-white/45" : "text-[10px] text-white/40",
                  )}
                >
                  {row.role}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p
        className={cn(
          w
            ? "text-xs text-white/30"
            : "text-[9px] font-bold uppercase tracking-widest text-white/20",
        )}
      >
        {w ? (
          "Server-backed env inspection (GET /api/env/names) is not wired yet; names are documented only."
        ) : (
          <>
            Alpha: no live env inspection — add server-backed{" "}
            <span className="font-mono">GET /api/env/names</span> later if needed.
          </>
        )}
      </p>
    </div>
  );
}

/** Tools & extensions surface; also used for Workspace MCP route (repomix `/settings/mcp`). */
export function ToolsAndExtensionsPanel() {
  return (
    <div className="space-y-16 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <ToyBrick className="h-4 w-4 text-[#FF6B00]" />
              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">
                Built-in Tools
              </h3>
            </div>
            <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">
              Core HAM operational capabilities
            </p>
          </div>
          <div className="h-px mx-8 flex-1 bg-white/5" />
          <div className="flex items-center gap-3">
            <span className="text-[8px] font-black uppercase tracking-widest text-white/10">
              Active Pool: 6/7
            </span>
            <div className="h-1 w-12 overflow-hidden rounded-full bg-white/5">
              <div className="h-full w-[85%] bg-[#FF6B00]" />
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {[
            {
              name: "Code Interpreter",
              desc: "Execute sandboxed code in Python and JS environments.",
              status: "active",
              scope: "workspace",
              icon: Terminal,
              load: "High",
            },
            {
              name: "Web Intelligence",
              desc: "Live web traversal and semantic extraction.",
              status: "active",
              scope: "workspace",
              icon: Globe,
              load: "Nominal",
            },
            {
              name: "Image Extraction",
              desc: "Multi-modal vision analysis for visual datasets.",
              status: "setup required",
              scope: "team only",
              icon: Zap,
              load: "Standby",
            },
            {
              name: "Browser",
              desc: "Autonomous browser orchestration for task completion.",
              status: "active",
              scope: "workspace",
              icon: Monitor,
              load: "Idle",
            },
            {
              name: "Preview",
              desc: "Real-time rendering of generated artifacts and code.",
              status: "active",
              scope: "workspace",
              icon: Eye,
              load: "Idle",
            },
            {
              name: "Search",
              desc: "Industrial-grade index searching across global networks.",
              status: "inactive",
              scope: "team only",
              icon: Search,
              load: "Locked",
            },
            {
              name: "Workspace Context",
              desc: "High-density local knowledge indexing.",
              status: "active",
              scope: "workspace",
              icon: Brain,
              load: "Syncing",
            },
          ].map((tool, i) => (
            <div
              key={i}
              className="group relative flex items-center gap-6 overflow-hidden rounded-xl border border-white/5 bg-black/40 p-4 shadow-lg transition-all hover:border-[#FF6B00]/20"
            >
              <div className="absolute left-0 top-0 h-full w-1 bg-[#FF6B00] opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-white/5 bg-white/[0.03] transition-colors group-hover:bg-[#FF6B00]/10">
                <tool.icon className="h-4 w-4 text-[#FF6B00]" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[11px] font-black uppercase tracking-widest text-white">
                    {tool.name}
                  </span>
                  <div
                    className={cn(
                      "rounded-[2px] px-1.5 py-0.5 text-[7px] font-black uppercase tracking-tighter",
                      tool.status === "active"
                        ? "border border-green-500/20 bg-green-500/10 text-green-500"
                        : tool.status === "setup required"
                          ? "border border-amber-500/20 bg-amber-500/10 text-amber-500"
                          : "border border-white/10 bg-white/5 text-white/20",
                    )}
                  >
                    {tool.status}
                  </div>
                </div>
                <p className="truncate text-[9px] font-bold uppercase tracking-widest italic leading-none text-white/40">
                  {tool.desc}
                </p>
              </div>
              <div className="hidden min-w-[100px] flex-col items-center gap-1 border-l border-white/5 px-4 md:flex">
                <span className="text-[7px] font-black uppercase tracking-widest text-white/10">
                  Load State
                </span>
                <span className="text-[9px] font-mono font-bold uppercase tracking-tighter italic text-[#FF6B00]/60">
                  {tool.load}
                </span>
              </div>
              <div className="hidden min-w-[120px] flex-col items-end gap-1 border-l border-white/5 px-4 md:flex">
                <span className="text-[7px] font-black uppercase tracking-widest text-white/10">
                  Assignment
                </span>
                <span className="whitespace-nowrap text-[9px] font-black uppercase tracking-tighter italic text-white/40">
                  {tool.scope}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  className="h-8 rounded border border-white/5 bg-white/[0.03] px-3 text-[9px] font-black uppercase tracking-widest text-white/40 transition-all hover:bg-white/10 hover:text-white"
                >
                  Assign
                </button>
                <button
                  type="button"
                  className="h-8 rounded border border-white/5 bg-white/[0.03] px-3 text-[9px] font-black uppercase tracking-widest text-white/40 transition-all hover:bg-white/10 hover:text-white"
                >
                  Configure
                </button>
                <button
                  type="button"
                  className="h-8 rounded border border-[#FF6B00]/20 bg-[#FF6B00]/10 px-3 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] transition-all hover:bg-[#FF6B00]/20"
                >
                  {tool.status === "active" ? "Disable" : "Enable"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <Package className="h-4 w-4 text-[#FF6B00]" />
              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">
                Extensions & Plugins
              </h3>
            </div>
            <p className="pl-7 text-[10px] font-bold uppercase tracking-widest leading-none text-white/20">
              3rd party integrations and modular enhancements
            </p>
          </div>
          <div className="ml-8 flex items-center gap-3">
            <div className="h-px w-24 bg-white/5" />
            <button
              type="button"
              className="group flex items-center gap-2 rounded border border-[#FF6B00]/20 bg-[#FF6B00]/5 px-3 py-1.5 text-[#FF6B00] hover:bg-[#FF6B00]/10"
            >
              <Plus className="h-3 w-3" />
              <span className="text-[9px] font-black uppercase tracking-widest italic leading-none">
                Add Extension
              </span>
            </button>
            <div className="h-px flex-1 bg-white/5" />
          </div>
        </div>
        <div className="space-y-2">
          {[
            {
              name: "Mercury UI Tab",
              type: "UI Interface",
              installed: true,
              enabled: true,
              desc: "Custom operational surface for high-frequency trading data.",
              icon: Layout,
              version: "v1.2.4",
            },
            {
              name: "Azure Bridge",
              type: "Provider Integration",
              installed: true,
              enabled: false,
              desc: "Connects HAM units to Azure Cloud Service endpoints.",
              icon: Database,
              version: "v0.9.8",
            },
            {
              name: "Slack Bridge",
              type: "Social Hub",
              installed: false,
              enabled: false,
              desc: "Bidirectional workspace communication pipeline.",
              icon: RefreshCw,
              version: "v2.1.0",
            },
            {
              name: "Auth Bundle",
              type: "Security Extension",
              installed: true,
              enabled: true,
              desc: "Advanced OAuth and JWT validation logic.",
              icon: Lock,
              version: "v4.0.1",
            },
          ].map((ext, i) => (
            <div
              key={i}
              className="group relative flex items-center gap-6 overflow-hidden rounded-xl border border-white/5 bg-black/40 p-4 transition-all hover:bg-white/[0.02]"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-white/5 bg-white/[0.02] opacity-40 transition-opacity group-hover:opacity-100">
                <ext.icon className="h-4 w-4 text-white" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-black uppercase tracking-widest text-white">
                    {ext.name}
                  </span>
                  <span className="rounded-[2px] border border-[#FF6B00]/10 bg-[#FF6B00]/5 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-widest italic text-[#FF6B00]/60">
                    {ext.type}
                  </span>
                </div>
                <p className="truncate text-[9px] font-bold uppercase tracking-widest italic leading-none text-white/20">
                  {ext.desc}
                </p>
              </div>
              <div className="hidden min-w-[80px] flex-col items-center gap-1 border-l border-white/5 px-4 md:flex">
                <span className="text-[7px] font-black uppercase tracking-widest text-white/10">
                  Version
                </span>
                <span className="text-[9px] font-mono font-bold uppercase tracking-tighter italic text-white/20">
                  {ext.version}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!ext.installed ? (
                  <button
                    type="button"
                    className="flex h-8 items-center gap-2 rounded bg-[#FF6B00] px-4 text-[9px] font-black uppercase tracking-widest text-black transition-all hover:bg-[#FF8533]"
                  >
                    <Download className="h-3 w-3" />
                    <span>Install</span>
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="flex h-8 items-center gap-2 rounded border border-white/5 bg-white/[0.03] px-3 text-[9px] font-black uppercase tracking-widest text-white/40 transition-all hover:bg-white/10 hover:text-white"
                    >
                      <ArrowUpRight className="h-3 w-3" />
                      <span>Open</span>
                    </button>
                    <button
                      type="button"
                      className="h-8 rounded border border-white/5 bg-white/[0.03] px-3 text-[9px] font-black uppercase tracking-widest text-white/40 transition-all hover:bg-white/10 hover:text-white"
                    >
                      Configure
                    </button>
                    <button
                      type="button"
                      className={cn(
                        "h-8 rounded px-4 text-[9px] font-black uppercase tracking-widest transition-all",
                        ext.enabled
                          ? "border border-[#FF6B00]/20 bg-[#FF6B00]/10 text-[#FF6B00]"
                          : "border border-white/10 bg-white/5 text-white/20",
                      )}
                    >
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
  visualVariant = "default",
  contextSnapshotLocal = false,
}: {
  data: ContextEnginePayload;
  onApplied: () => void;
  visualVariant?: SettingsPanelVisualVariant;
  /** True when the panel shows a snapshot from the connected machine (cloud preview/apply would be misleading). */
  contextSnapshotLocal?: boolean;
}) {
  const w = visualVariant === "workspace";
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
          setProjectErr(
            e instanceof Error ? e.message : "Could not resolve project for this workspace.",
          );
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

  const inputCls = cn(
    "mt-1 w-full rounded-lg border px-3 py-2 text-white/80 placeholder:text-white/25 focus:outline-none focus:ring-1",
    w
      ? "border-white/[0.1] bg-white/[0.04] text-sm focus:ring-[#5eead4]/40"
      : "border-white/10 bg-black/50 text-[11px] font-mono focus:ring-[#FF6B00]/50",
  );

  const fieldLbl = w
    ? "text-xs font-medium text-white/50"
    : "text-[9px] font-black text-white/35 uppercase tracking-widest";

  if (contextSnapshotLocal) {
    return (
      <div
        className={cn(
          "space-y-3 rounded-xl border p-6",
          w ? "border-white/[0.08] bg-white/[0.02]" : "border-[#FF6B00]/20 bg-black/40",
        )}
      >
        <h4
          className={cn(
            w
              ? "text-sm font-medium text-white/85"
              : "text-[11px] font-black uppercase italic tracking-widest text-[#FF6B00]",
          )}
        >
          Project settings writes
        </h4>
        <p
          className={cn(
            "max-w-2xl leading-relaxed",
            w ? "text-[13px] text-white/45" : "text-[10px] text-white/35",
          )}
        >
          Cloud settings changes are unavailable while viewing this computer&apos;s project
          snapshot. Preview and apply always use your linked cloud project, not the folder shown
          above.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "space-y-5 rounded-xl border p-6",
        w ? "border-white/[0.08] bg-white/[0.02]" : "border-[#FF6B00]/20 bg-black/40",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h4
            className={cn(
              w
                ? "text-sm font-medium text-white/85"
                : "text-[11px] font-black uppercase italic tracking-widest text-[#FF6B00]",
            )}
          >
            Project settings writes
          </h4>
          <p
            className={cn(
              "mt-2 max-w-2xl leading-relaxed",
              w
                ? "text-[13px] text-white/40"
                : "text-[9px] font-bold uppercase tracking-widest text-white/30",
            )}
          >
            {w ? (
              <>
                Writes <span className="font-mono text-sm text-white/50">.ham/settings.json</span>{" "}
                on the server with validation, backup, and audit. Preview is open; apply needs a
                one-time write token in this session (not stored in the bundle).
              </>
            ) : (
              <>
                Writes only <span className="font-mono">.ham/settings.json</span> on the server
                (merge with validation, backup, audit). Matches{" "}
                <span className="font-mono">POST .../settings/preview|apply</span>. Preview is
                unauthenticated; apply uses your token for this browser session only (not stored in
                the app bundle).
              </>
            )}
          </p>
        </div>
        {writesEnabled === false && (
          <span
            className={cn(
              "rounded-md px-2 py-1",
              w
                ? "border border-amber-500/20 bg-amber-500/5 text-xs text-amber-200/90"
                : "border border-amber-500/30 bg-amber-500/5 text-[9px] font-bold uppercase tracking-widest text-amber-500/90",
            )}
          >
            Apply disabled — set HAM_SETTINGS_WRITE_TOKEN on the API
          </span>
        )}
      </div>

      {projectErr && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-[13px] text-red-400/90">
          {projectErr}
        </div>
      )}
      {!projectId && !projectErr && (
        <div
          className={cn(
            w
              ? "text-sm text-white/40"
              : "text-[10px] font-bold uppercase tracking-widest text-white/35",
          )}
        >
          Resolving project…
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className={fieldLbl}>session_compaction_max_tokens</label>
          <input
            className={inputCls}
            value={sessionMax}
            onChange={(e) => setSessionMax(e.target.value)}
            inputMode="numeric"
          />
        </div>
        <div>
          <label className={fieldLbl}>session_compaction_preserve</label>
          <input
            className={inputCls}
            value={sessionPreserve}
            onChange={(e) => setSessionPreserve(e.target.value)}
            inputMode="numeric"
          />
        </div>
        <div>
          <label className={fieldLbl}>session_tool_prune_chars</label>
          <input
            className={inputCls}
            value={toolPrune}
            onChange={(e) => setToolPrune(e.target.value)}
            inputMode="numeric"
          />
        </div>
        <div>
          <label className={fieldLbl}>architect_instruction_chars</label>
          <input
            className={inputCls}
            value={archChars}
            onChange={(e) => setArchChars(e.target.value)}
            inputMode="numeric"
          />
        </div>
        <div>
          <label className={fieldLbl}>commander_instruction_chars</label>
          <input
            className={inputCls}
            value={cmdChars}
            onChange={(e) => setCmdChars(e.target.value)}
            inputMode="numeric"
          />
        </div>
        <div>
          <label className={fieldLbl}>critic_instruction_chars</label>
          <input
            className={inputCls}
            value={criticChars}
            onChange={(e) => setCriticChars(e.target.value)}
            inputMode="numeric"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!projectId || busy !== null}
          onClick={() => void runPreview()}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-4 py-2 disabled:opacity-40",
            w
              ? "border border-white/[0.1] text-[12px] font-medium text-white/80 hover:border-[#5eead4]/35 hover:bg-white/[0.04]"
              : "border border-[#FF6B00]/40 bg-[#FF6B00]/20 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-[#FF6B00]/30",
          )}
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
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border px-4 py-2 disabled:opacity-40",
            w
              ? "border-white/[0.08] text-[12px] font-medium text-white/60 hover:border-white/20 hover:text-white/90"
              : "border border-white/15 bg-white/5 text-[9px] font-black uppercase tracking-widest text-white/70 hover:border-[#FF6B00]/40 hover:text-[#FF6B00]",
          )}
        >
          {busy === "apply" ? "Apply…" : "Apply"}
        </button>
      </div>

      <div>
        <label className={fieldLbl}>HAM_SETTINGS_WRITE_TOKEN (session only)</label>
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
        <div
          className={cn(
            "space-y-3 rounded-lg border p-4",
            w ? "border-white/[0.08] bg-white/[0.02]" : "border border-white/10 bg-black/30",
          )}
        >
          <div className={cn("break-all font-mono text-white/40", w ? "text-xs" : "text-[9px]")}>
            base_revision: {preview.base_revision.slice(0, 16)}… → {preview.write_target}
          </div>
          {preview.warnings.length > 0 && (
            <ul
              className={cn(
                "list-disc space-y-1 pl-4 text-amber-400/90",
                w ? "text-sm" : "text-[10px]",
              )}
            >
              {preview.warnings.map((war) => (
                <li key={war}>{war}</li>
              ))}
            </ul>
          )}
          {preview.diff.length > 0 && (
            <div className="overflow-x-auto">
              <table className={cn("w-full text-left font-mono", w ? "text-xs" : "text-[9px]")}>
                <thead>
                  <tr
                    className={cn(w ? "text-white/40" : "text-white/35 uppercase tracking-tighter")}
                  >
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

export function ContextAndMemoryPanel({
  variant = "default",
}: {
  variant?: SettingsPanelVisualVariant;
}) {
  const w = variant === "workspace";
  const wsProject = useOptionalWorkspaceHamProject();
  const hamProjectId = wsProject?.hamProjectId ?? null;

  const [data, setData] = React.useState<ContextEnginePayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  /** "local" = connected machine snapshot; "project" / "global" = cloud API */
  const [snapshotSource, setSnapshotSource] = React.useState<"local" | "project" | "global" | null>(
    null,
  );
  const [fallbackNote, setFallbackNote] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    setFallbackNote(null);
    try {
      const outcome = await loadContextMemorySnapshot(hamProjectId, {
        isLocalRuntimeConfigured,
        fetchLocalWorkspaceHealth,
        fetchLocalWorkspaceContextSnapshot,
        fetchProjectContextEngine,
        fetchContextEngine,
      });
      setData(outcome.payload);
      setSnapshotSource(outcome.source);
      setFallbackNote(outcome.fallbackNote);
    } catch (e) {
      setData(null);
      setSnapshotSource(null);
      setError(e instanceof Error ? e.message : "Failed to load context engine snapshot");
    } finally {
      setLoading(false);
    }
  }, [hamProjectId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const roleOrder = [
    { key: "architect" as const, label: "Architect" },
    { key: "commander" as const, label: "Routing (Hermes)" },
    { key: "critic" as const, label: "Review (Hermes)" },
  ];

  const sourceBadge =
    snapshotSource === "local" ? (
      <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-200/95">
        This computer
      </span>
    ) : snapshotSource === "project" || snapshotSource === "global" ? (
      <span className="rounded-md border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-[11px] font-semibold text-sky-100/90">
        Cloud
      </span>
    ) : null;

  return (
    <div className={cn("space-y-6", w && "hww-settings-panels")}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex max-w-xl flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">{sourceBadge}</div>
          <p
            className={cn(
              "leading-relaxed",
              w
                ? "text-[13px] text-white/45"
                : "text-[10px] font-bold uppercase tracking-widest text-white/30",
            )}
          >
            {w ? (
              <>
                Project memory snapshot: when your connected folder is available on this computer,
                this panel prefers that folder. Otherwise it uses your linked cloud project, or the
                global cloud API view.
              </>
            ) : (
              <>
                Live snapshot from{" "}
                <span className="font-mono text-[#FF6B00]/80">GET /api/context-engine</span> or,
                when a Hermes workspace project id is available,{" "}
                <span className="font-mono text-[#FF6B00]/80">
                  GET /api/projects/{"{id}"}/context-engine
                </span>
                . Vite dev proxies <span className="font-mono">/api</span> to FastAPI; production
                uses <span className="font-mono">VITE_HAM_API_BASE</span>.
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors disabled:opacity-40",
            w
              ? "border-white/[0.1] text-[12px] font-medium text-white/60 hover:border-white/20 hover:bg-white/[0.04] hover:text-white/90"
              : "border-white/10 text-[9px] font-black uppercase tracking-widest text-white/50 hover:border-[#FF6B00]/30 hover:text-[#FF6B00]",
          )}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {snapshotSource === "local" && w && (
        <div className="space-y-2 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] p-4 text-[13px] leading-relaxed text-emerald-50/90">
          <p className="font-medium text-emerald-100/95">This computer</p>
          <p className="text-emerald-100/80">
            This panel is showing your connected project folder on this computer. Chat still uses
            the cloud app in this version.
          </p>
        </div>
      )}

      <div
        className={cn(
          "space-y-2 rounded-xl border p-4 leading-relaxed",
          w
            ? "border-amber-500/25 bg-amber-500/[0.06] text-[12px] text-amber-100/80"
            : "border-amber-500/20 bg-amber-500/[0.04] p-5 text-[9px] font-bold uppercase tracking-wide text-amber-100/70",
        )}
      >
        <p
          className={cn(
            w
              ? "font-medium text-amber-50/95"
              : "text-[10px] font-black tracking-widest text-amber-200/90",
          )}
        >
          {w
            ? "What the Cloud snapshot means"
            : "What this snapshot means (hosted &amp; containers)"}
        </p>
        <ul
          className={cn(
            "list-disc space-y-1.5 pl-4",
            w
              ? "text-[12px] text-amber-100/75"
              : "text-[9px] font-semibold normal-case tracking-normal text-amber-100/65",
          )}
        >
          {w ? (
            <>
              <li>
                The global cloud view reflects the cloud API process folder (hosted deployments
                often use something like <span className="font-mono text-amber-200/70">/app</span>),
                not a path on your laptop.
              </li>
              <li>
                Many cloud images omit a <span className="font-mono text-amber-200/70">.git</span>{" "}
                tree, so &quot;Git unavailable&quot; there is expected — it does{" "}
                <strong className="font-semibold">not</strong> mean project memory is broken.
              </li>
              <li>
                Link a workspace project to prefer that cloud project&apos;s folder when the cloud
                host can read it.
              </li>
            </>
          ) : (
            <>
              <li>
                The <span className="font-mono">global</span> route reflects the API process working
                directory (often something like <span className="font-mono">/app</span> on Cloud
                Run), not your laptop path.
              </li>
              <li>
                Many images omit <span className="font-mono">.git</span> (e.g. via{" "}
                <span className="font-mono">.dockerignore</span>
                ), so &quot;Git unavailable&quot; there is expected — it does{" "}
                <strong className="font-semibold">not</strong> mean{" "}
                <span className="font-mono">memory_heist</span> is broken.
              </li>
              <li>
                Open the Hermes workspace chat once to link a project id; the Context &amp; Memory
                panel then prefers the project-scoped route when the API can read that root.
              </li>
            </>
          )}
        </ul>
      </div>

      {fallbackNote && (
        <div
          className={cn(
            "rounded-xl border p-4",
            w
              ? "border-sky-500/25 bg-sky-500/[0.06] text-[13px] text-sky-100/85"
              : "border-sky-500/20 bg-sky-500/[0.04] text-[10px] font-bold uppercase tracking-wide text-sky-100/75",
          )}
        >
          {fallbackNote}
        </div>
      )}

      {snapshotSource && data && (
        <div
          className={cn(
            "rounded-lg border px-3 py-2",
            w
              ? "border-white/[0.08] text-[12px] text-white/55"
              : "border-white/10 font-mono text-[9px] text-white/35",
          )}
        >
          {w ? (
            <>
              <span className="font-medium text-white/65">Source: </span>
              {snapshotSource === "local" && (
                <span>
                  Connected folder on this computer (local Ham API with a configured project
                  folder).
                </span>
              )}
              {snapshotSource === "project" && <span>Linked cloud project folder.</span>}
              {snapshotSource === "global" && (
                <span>Global cloud API view{hamProjectId ? " (fallback)" : ""}.</span>
              )}
            </>
          ) : (
            <>
              Active route:{" "}
              {snapshotSource === "local" ? (
                <>
                  <span className="text-emerald-400/90">local</span>
                  {" · "}
                  <span className="text-white/55">GET /api/workspace/context-snapshot</span>
                </>
              ) : snapshotSource === "project" ? (
                <>
                  <span className="text-emerald-400/90">project</span>
                  {" · "}
                  <span className="text-white/55">
                    GET /api/projects/{hamProjectId}/context-engine
                  </span>
                </>
              ) : (
                <>
                  <span className="text-white/55">global</span>
                  {" · "}
                  <span className="text-white/55">GET /api/context-engine</span>
                  {hamProjectId ? " (fallback)" : ""}
                </>
              )}
            </>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-[13px] text-red-300/90">
          {error}
        </div>
      )}

      {loading && !data && !error && (
        <div
          className={cn(
            "rounded-xl border border-white/5 bg-black/30 p-12 text-center text-white/40",
            w ? "text-sm" : "text-[10px] font-bold uppercase tracking-widest",
          )}
        >
          Loading context…
        </div>
      )}

      {data && (
        <>
          <div
            className={cn(
              "space-y-3 rounded-xl border p-5",
              w ? "border-white/[0.08] bg-white/[0.02]" : "border border-white/5 bg-black/40 p-6",
            )}
          >
            <div
              className={cn(
                w
                  ? "text-xs font-medium text-white/50"
                  : "text-[9px] font-black uppercase tracking-widest text-white/25",
              )}
            >
              Working directory
            </div>
            <div
              className={cn(
                "break-all font-mono leading-relaxed text-white/75",
                w ? "text-sm" : "text-[11px]",
              )}
            >
              {data.cwd}
            </div>
            <div
              className={cn(
                "flex flex-wrap gap-3 text-white/50",
                w ? "text-xs" : "text-[9px] font-bold uppercase tracking-wider text-white/35",
              )}
            >
              <span>{data.current_date}</span>
              <span>{data.platform_info}</span>
              <span>{data.file_count} indexed files</span>
              <span>{data.instruction_file_count} instruction files</span>
              <span className={data.git.has_repo ? "text-green-500/70" : "text-amber-500/70"}>
                Git {data.git.has_repo ? "detected" : "unavailable"}
              </span>
            </div>
            {!data.git.has_repo && (
              <p
                className={cn(
                  "leading-relaxed",
                  w
                    ? "text-xs text-white/40"
                    : "text-[9px] font-bold uppercase tracking-wide text-white/30",
                )}
              >
                Without a <span className="font-mono">.git</span> directory in the scanned tree
                (common in slim deploy images), git-sized fields below may be zero. Configuration
                and instruction sampling still work.
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {roleOrder.map(({ key, label }) => {
              const r = data.roles[key];
              const instructionBudget = r.instruction_budget_chars;
              const diffCap = r.max_diff_chars;
              const combinedCeiling = Math.max(1, instructionBudget + diffCap);
              const assembled = r.rendered_chars;
              const ratio = assembled / combinedCeiling;
              const barWidthPct = Math.min(100, ratio * 100);
              const overCeiling = assembled > combinedCeiling;
              const barTitle = `Assembled ${assembled.toLocaleString()} chars · instruction budget ${instructionBudget.toLocaleString()} · diff cap ${diffCap.toLocaleString()} · combined ceiling ${combinedCeiling.toLocaleString()}`;
              return (
                <div
                  key={key}
                  className={cn(
                    "space-y-3 rounded-xl border p-5",
                    w
                      ? "border-white/[0.08] bg-white/[0.02]"
                      : "space-y-4 border border-white/5 bg-black/40 p-6 shadow-xl",
                  )}
                >
                  <div
                    className={cn(
                      w
                        ? "text-sm font-medium text-white/90"
                        : "text-[10px] font-black uppercase italic tracking-widest text-[#FF6B00]",
                    )}
                  >
                    {label}
                  </div>
                  <div className="space-y-2">
                    <div
                      className={cn(
                        "flex justify-between gap-2",
                        w
                          ? "text-xs text-white/50"
                          : "text-[10px] font-bold uppercase tracking-wider text-white/35",
                      )}
                    >
                      <span>Assembled (rendered)</span>
                      <span className="shrink-0 font-mono text-white/65">
                        {assembled.toLocaleString()} chars
                      </span>
                    </div>
                    <div
                      className={cn(
                        "h-2 overflow-hidden rounded-full border border-white/10 bg-white/5",
                      )}
                      title={barTitle}
                    >
                      <div
                        className={cn(
                          "h-full",
                          w
                            ? "bg-[#5eead4]/70"
                            : "bg-[#FF6B00]/80 shadow-[0_0_12px_rgba(255,107,0,0.35)]",
                          overCeiling && (w ? "bg-amber-400/85" : "bg-amber-500/90"),
                        )}
                        style={{ width: `${barWidthPct}%` }}
                      />
                    </div>
                    <p
                      className={cn(
                        "leading-relaxed",
                        w
                          ? "text-xs text-white/35"
                          : "text-[9px] font-bold uppercase tracking-wide text-white/25",
                      )}
                    >
                      Instruction budget {instructionBudget.toLocaleString()} chars · Diff cap{" "}
                      {diffCap.toLocaleString()} · Combined ceiling{" "}
                      {combinedCeiling.toLocaleString()}{" "}
                      {!w && (
                        <>
                          (<span className="font-mono">swarm_agency</span> per-role)
                        </>
                      )}
                    </p>
                    {overCeiling && (
                      <p
                        className={cn(
                          "font-medium text-amber-400/90",
                          w ? "text-xs" : "text-[9px] uppercase tracking-wide",
                        )}
                      >
                        Assembled size exceeds combined ceiling ({assembled.toLocaleString()} &gt;{" "}
                        {combinedCeiling.toLocaleString()}).
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div
              className={cn(
                "space-y-3 rounded-xl border p-5",
                w
                  ? "border-white/[0.08] bg-white/[0.02]"
                  : "space-y-4 border border-white/5 bg-black/40 p-6",
              )}
            >
              <h4
                className={cn(
                  w
                    ? "text-sm font-medium text-white/85"
                    : "text-[11px] font-black uppercase italic tracking-widest text-white",
                )}
              >
                Session memory
              </h4>
              <dl
                className={cn("space-y-2 font-mono text-white/60", w ? "text-sm" : "text-[10px]")}
              >
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    compact_max_tokens
                  </dt>
                  <dd>{data.session_memory.compact_max_tokens}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    compact_preserve
                  </dt>
                  <dd>{data.session_memory.compact_preserve}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    tool_prune_chars
                  </dt>
                  <dd>{data.session_memory.tool_prune_chars}</dd>
                </div>
              </dl>
              <p
                className={cn(
                  w
                    ? "text-xs text-white/35"
                    : "text-[9px] font-bold uppercase tracking-widest leading-relaxed text-white/25",
                )}
              >
                {w ? (
                  "From merged project config (memory_heist)."
                ) : (
                  <>
                    From merged config via <span className="font-mono">memory_heist</span> section
                    (see JSON below).
                  </>
                )}
              </p>
            </div>
            <div
              className={cn(
                "space-y-3 rounded-xl border p-5",
                w
                  ? "border-white/[0.08] bg-white/[0.02]"
                  : "space-y-4 border border-white/5 bg-black/40 p-6",
              )}
            >
              <h4
                className={cn(
                  w
                    ? "text-sm font-medium text-white/85"
                    : "text-[11px] font-black uppercase italic tracking-widest text-white",
                )}
              >
                Module defaults
              </h4>
              <dl
                className={cn("space-y-2 font-mono text-white/60", w ? "text-sm" : "text-[10px]")}
              >
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    max_instruction_file_chars
                  </dt>
                  <dd>{data.module_defaults.max_instruction_file_chars}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    max_total_instruction_chars
                  </dt>
                  <dd>{data.module_defaults.max_total_instruction_chars}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className={w ? "text-white/40" : "text-white/30 uppercase tracking-tighter"}>
                    max_diff_chars
                  </dt>
                  <dd>{data.module_defaults.max_diff_chars}</dd>
                </div>
              </dl>
            </div>
          </div>

          <div
            className={cn(
              "space-y-2 rounded-xl border p-5",
              w
                ? "border-white/[0.08] bg-white/[0.02]"
                : "space-y-3 border border-white/5 bg-black/40 p-6",
            )}
          >
            <h4
              className={cn(
                w
                  ? "text-sm font-medium text-white/85"
                  : "text-[11px] font-black uppercase italic tracking-widest text-white",
              )}
            >
              Git snapshot sizes
            </h4>
            <p
              className={cn(
                w
                  ? "text-xs text-white/40"
                  : "text-[9px] font-bold uppercase tracking-widest text-white/25",
              )}
            >
              Character counts only; raw diff and log are not returned by the API.
            </p>
            <dl
              className={cn(
                "grid grid-cols-3 gap-4 font-mono text-white/60",
                w ? "text-sm" : "text-[10px]",
              )}
            >
              <div>
                <dt className={w ? "text-white/40" : "text-[9px] uppercase text-white/30"}>
                  status
                </dt>
                <dd>{data.git.status_chars}</dd>
              </div>
              <div>
                <dt className={w ? "text-white/40" : "text-[9px] uppercase text-white/30"}>diff</dt>
                <dd>{data.git.diff_chars}</dd>
              </div>
              <div>
                <dt className={w ? "text-white/40" : "text-[9px] uppercase text-white/30"}>log</dt>
                <dd>{data.git.log_chars}</dd>
              </div>
            </dl>
          </div>

          {data.config_sources.length > 0 && (
            <div
              className={cn(
                "space-y-2 rounded-xl border p-5",
                w
                  ? "border-white/[0.08] bg-white/[0.02]"
                  : "space-y-3 border border-white/5 bg-black/40 p-6",
              )}
            >
              <h4
                className={cn(
                  w
                    ? "text-sm font-medium text-white/85"
                    : "text-[11px] font-black uppercase italic tracking-widest text-white",
                )}
              >
                Loaded config files
              </h4>
              <ul
                className={cn(
                  "space-y-2 break-all font-mono text-white/50",
                  w ? "text-xs" : "text-[10px]",
                )}
              >
                {data.config_sources.map((s) => (
                  <li key={s.path}>
                    <span className={w ? "text-[#5eead4]/80" : "text-[#FF6B00]/60"}>
                      [{s.source}]
                    </span>{" "}
                    {s.path}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.instruction_files.length > 0 && (
            <div
              className={cn(
                "space-y-2 rounded-xl border p-5",
                w
                  ? "border-white/[0.08] bg-white/[0.02]"
                  : "space-y-3 border border-white/5 bg-black/40 p-6",
              )}
            >
              <h4
                className={cn(
                  w
                    ? "text-sm font-medium text-white/85"
                    : "text-[11px] font-black uppercase italic tracking-widest text-white",
                )}
              >
                Instruction files
              </h4>
              <ul
                className={cn("space-y-1.5 font-mono text-white/50", w ? "text-xs" : "text-[10px]")}
              >
                {data.instruction_files.map((f) => (
                  <li key={`${f.scope}:${f.relative_path}`}>
                    {f.relative_path} <span className="text-white/25">({f.scope})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div
            className={cn(
              "space-y-2 rounded-xl border p-5",
              w
                ? "border-white/[0.08] bg-white/[0.02]"
                : "space-y-2 border border-white/5 bg-black/40 p-6",
            )}
          >
            <h4
              className={cn(
                w
                  ? "text-sm font-medium text-white/85"
                  : "text-[11px] font-black uppercase italic tracking-widest text-white",
              )}
            >
              Merged <span className="font-mono">memory_heist</span> keys
            </h4>
            {Object.keys(data.memory_heist_section).length === 0 ? (
              <p
                className={cn(
                  w
                    ? "text-sm text-white/40"
                    : "text-[10px] font-bold uppercase tracking-widest text-white/25",
                )}
              >
                {w ? (
                  "No custom keys; defaults apply."
                ) : (
                  <>
                    No keys under <span className="font-mono">memory_heist</span> in merged JSON
                    (defaults apply).
                  </>
                )}
              </p>
            ) : (
              <pre
                className={cn(
                  "max-h-40 overflow-y-auto overflow-x-auto rounded-lg border font-mono text-white/45",
                  w
                    ? "border-white/[0.08] bg-black/20 p-3 text-xs"
                    : "border border-white/5 bg-black/50 p-3 text-[9px]",
                )}
              >
                {JSON.stringify(data.memory_heist_section, null, 2)}
              </pre>
            )}
          </div>

          <AllowlistedWorkspaceSettings
            data={data}
            onApplied={() => void load()}
            visualVariant={w ? "workspace" : "default"}
            contextSnapshotLocal={shouldGateContextMemorySettingsMutations(snapshotSource)}
          />
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
  | "desktop-bundle"
  | "execution-history"
  | "system-logs"
  | "diagnostics"
  | "kernel-health"
  | "context-audit"
  | "bridge-dump"
  | "resource-storage"
  | "jobs";

interface UnifiedSettingsProps {
  activeSubSegment: SettingsSubSectionId;
  onSubSegmentChange: (id: SettingsSubSectionId) => void;
  variant?: "overlay" | "page";
  /** When true, only the right-hand content is rendered (parent supplies nav). */
  hideInternalNav?: boolean;
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
    group: "Desktop (HAM Desktop app)",
    items: [{ id: "desktop-bundle", label: "HAM + Hermes setup", icon: Orbit }],
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
      { id: "resource-storage", label: "Resource Storage", icon: Box },
      { id: "jobs", label: "Jobs", icon: Calendar },
    ],
  },
];

/** Valid `tab` query values for `/settings?tab=…`. */
export function normalizeSettingsTabParam(tab: string | null | undefined): SettingsSubSectionId {
  let t = tab;
  if (t === "mission-history") {
    t = "execution-history";
  }
  if (t === "workforce-profiles") {
    t = "api-keys";
  }
  const ok = settingsStructure.flatMap((g) => g.items).some((i) => i.id === t);
  return ok ? (t as SettingsSubSectionId) : "api-keys";
}

export function UnifiedSettings({
  activeSubSegment,
  onSubSegmentChange,
  variant = "overlay",
  hideInternalNav = false,
}: UnifiedSettingsProps) {
  const activeLabel = settingsStructure
    .flatMap((g) => g.items)
    .find((i) => i.id === activeSubSegment)?.label;

  return (
    <div className="flex h-full w-full min-w-0 bg-[#050505] font-sans">
      {/* Internal Settings Sub-Nav */}
      {!hideInternalNav ? (
        <div
          className={cn(
            "w-64 border-r border-white/5 p-8 flex flex-col gap-10 overflow-y-auto shrink-0",
            variant === "page" ? "bg-transparent" : "bg-[#0c0c0c]",
          )}
        >
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
                        : "text-white/30 hover:text-white hover:bg-white/[0.03]",
                    )}
                  >
                    <item.icon
                      className={cn(
                        "h-3.5 w-3.5",
                        activeSubSegment === item.id ? "text-[#FF6B00]" : "text-white/20",
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
      ) : null}

      {/* Sub-Settings Content Area */}
      <div
        className={cn(
          "min-w-0 flex-1 overflow-y-auto p-12 pb-32 scrollbar-hide",
          hideInternalNav && "p-6 md:p-10",
        )}
      >
        <div className="space-y-12 animate-in fade-in slide-in-from-right-4 duration-500 max-w-4xl">
          {/* Section Header */}
          <div className="space-y-3 pb-8 border-b border-white/5">
            <h2 className="text-3xl font-black text-white uppercase italic tracking-tighter leading-none">
              {activeLabel}
            </h2>
            <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-2xl">
              {activeSubSegment === "environment" ? (
                <>
                  Read-only reference for local{" "}
                  <span className="font-mono text-white/35">.env</span> variables. Edit the file on
                  disk; values are never shown here (alpha).
                </>
              ) : activeSubSegment === "desktop-bundle" ? (
                <>
                  Desktop-side: curated defaults, a local{" "}
                  <span className="font-mono text-white/35">hermes</span> check, allowlisted preset
                  runs, and (when the app reaches the API) a read-only API strip. This is not the
                  same host as the Ham API by default. No silent installs.
                </>
              ) : (
                <>
                  Industrial grade {activeSubSegment.replace("-", " ")} configuration for secure HAM
                  operations.
                </>
              )}
            </p>
          </div>

          <div className="space-y-10">
            {/* --- CONFIGURATION PAGES --- */}
            {[
              "api-keys",
              "environment",
              "tools-extensions",
              "context-memory",
              "desktop-bundle",
            ].includes(activeSubSegment) && (
              <div className="space-y-6">
                {activeSubSegment === "api-keys" && <ApiKeysPanel />}

                {activeSubSegment === "environment" && <EnvironmentReadonlyPanel />}

                {activeSubSegment === "tools-extensions" && <ToolsAndExtensionsPanel />}

                {activeSubSegment === "context-memory" && <ContextAndMemoryPanel />}

                {activeSubSegment === "desktop-bundle" && <DesktopBundlePanel />}
              </div>
            )}

            {/* --- HEALTH / STATUS PAGES --- */}
            {["kernel-health", "diagnostics"].includes(activeSubSegment) && (
              <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {[
                    {
                      label: "Kernel Version",
                      value: "2.5.0-HAM",
                      status: "Operational",
                      trend: "Stable",
                    },
                    {
                      label: "Active Workers",
                      value: "154 Units",
                      status: "Optimal",
                      trend: "Nominal",
                    },
                    {
                      label: "Bridge Latency",
                      value: "12ms",
                      status: "Accelerated",
                      trend: "High Speed",
                    },
                    {
                      label: "Memory Pressure",
                      value: "14%",
                      status: "Safe",
                      trend: "Liquid Content",
                    },
                    {
                      label: "Provider Sync",
                      value: "3/3 Active",
                      status: "Aligned",
                      trend: "Synchronized",
                    },
                    { label: "Resource Load", value: "48%", status: "Balanced", trend: "Managed" },
                  ].map((metric, i) => (
                    <div
                      key={i}
                      className="p-6 bg-[#0c0c0c] border border-white/5 rounded-xl space-y-4 hover:border-white/20 transition-all"
                    >
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] font-black text-white/20 uppercase tracking-widest leading-none">
                          {metric.label}
                        </span>
                        <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]" />
                      </div>
                      <div className="space-y-1">
                        <div className="text-xl font-black text-white italic tracking-tighter leading-none">
                          {metric.value}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] font-black text-[#FF6B00] uppercase italic tracking-widest">
                            {metric.status}
                          </span>
                          <span className="text-[8px] font-bold text-white/10 uppercase tracking-widest">
                            {metric.trend}
                          </span>
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
                      <h4 className="text-[12px] font-black text-white uppercase italic tracking-[0.4em]">
                        Run Deep Sector Scan
                      </h4>
                      <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-sm mx-auto leading-relaxed">
                        Initiate a full-system audit of bridge connections and memory registers.
                      </p>
                    </div>
                    <button className="px-10 py-3 bg-[#FF6B00]/10 border border-[#FF6B00]/40 text-[10px] font-black text-[#FF6B00] uppercase tracking-[0.3em] italic hover:bg-[#FF6B00] hover:text-black transition-all rounded shadow-xl">
                      Start System Diagnostics
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* --- HISTORY / AUDIT PAGES --- */}
            {["execution-history", "system-logs", "context-audit", "bridge-dump"].includes(
              activeSubSegment,
            ) && (
              <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-700">
                <div className="flex items-center justify-between px-6 py-4 bg-white/[0.02] border border-white/10 rounded-xl">
                  <div className="flex items-center gap-4">
                    <History className="h-4 w-4 text-[#FF6B00]" />
                    <span className="text-[11px] font-black text-white uppercase tracking-widest italic">
                      Live Audit Stream
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 px-3 py-1 bg-black/40 border border-white/5 rounded text-[9px] font-black text-white/20 uppercase tracking-widest">
                      <FileSearch className="h-3 w-3" /> Filter Log Level
                    </div>
                    <div className="text-[9px] font-black text-[#FF6B00] uppercase tracking-widest underline underline-offset-4 cursor-pointer">
                      Export Payload
                    </div>
                  </div>
                </div>

                <div className="bg-[#0c0c0c] border border-white/5 rounded-xl divide-y divide-white/5 overflow-hidden shadow-2xl">
                  {[
                    {
                      time: "05:12:04",
                      action: "BRIDGE_RE_SYNC",
                      actor: "Kernel",
                      result: "COMPLETE",
                      detail: "Rotated 154 worker heartbeat keys.",
                    },
                    {
                      time: "05:10:55",
                      action: "MEMORY_FLUSH",
                      actor: "System",
                      result: "NOMINAL",
                      detail: "Purged 3.4GB of stale cache registers.",
                    },
                    {
                      time: "05:08:21",
                      action: "ID_VERIFY",
                      actor: "Security",
                      result: "SECURE",
                      detail: "Verified user ham-admin82 through biometric bridge.",
                    },
                    {
                      time: "05:04:12",
                      action: "UNIT_REALLOCATE",
                      actor: "Kernel",
                      result: "ALIGNED",
                      detail: "Moved 4 units from extraction to logic core.",
                    },
                    {
                      time: "04:59:33",
                      action: "TOOL_CALIBRATE",
                      actor: "Chipset",
                      result: "ACCELERATED",
                      detail: "Optimized Code Interpreter for v3 architecture.",
                    },
                  ].map((log, i) => (
                    <div
                      key={i}
                      className="flex grid grid-cols-12 gap-8 items-center px-8 py-6 hover:bg-white/[0.02] transition-colors group"
                    >
                      <div className="col-span-1 text-[10px] font-mono text-white/20 whitespace-nowrap">
                        {log.time}
                      </div>
                      <div className="col-span-3 text-[11px] font-black text-[#FF6B00]/80 uppercase italic tracking-widest leading-none group-hover:text-[#FF6B00] transition-colors">
                        {log.action}
                      </div>
                      <div className="col-span-2 text-[9px] font-black text-white/20 uppercase tracking-[0.2em]">
                        {log.actor}
                      </div>
                      <div className="col-span-4 text-[11px] font-bold text-white/40 italic leading-relaxed">
                        {log.detail}
                      </div>
                      <div className="col-span-2 text-right">
                        <span className="text-[10px] font-black px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-500/60 uppercase">
                          {log.result}
                        </span>
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
                    <h3 className="text-xl font-black text-white uppercase italic tracking-[0.3em]">
                      SCHEDULER_OFFLINE
                    </h3>
                    <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] max-w-sm mx-auto leading-relaxed italic">
                      The automated task scheduler is currently set to manual override. Scheduled
                      jobs will be surfaced here in HAM v3.2.
                    </p>
                  </div>
                  <button className="px-10 py-3 bg-white/5 border border-white/10 text-[10px] font-black text-white/20 uppercase tracking-widest rounded transition-all hover:bg-white/10 hover:text-white group">
                    Define Cron Directive{" "}
                    <Plus className="ml-2 h-3.5 w-3.5 inline group-hover:text-[#FF6B00] transition-colors" />
                  </button>
                </div>
              </div>
            )}

            {/* General Placeholder for everything else */}
            {![
              "api-keys",
              "environment",
              "tools-extensions",
              "context-memory",
              "desktop-bundle",
              "kernel-health",
              "diagnostics",
              "execution-history",
              "system-logs",
              "context-audit",
              "bridge-dump",
              "jobs",
            ].includes(activeSubSegment) && (
              <div className="space-y-10">
                <div className="p-16 bg-black/20 border border-white/5 border-dashed rounded-2xl flex flex-col items-center justify-center text-center space-y-8 group transition-all hover:bg-black/40">
                  <div className="h-16 w-16 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center transition-transform group-hover:scale-110">
                    <Zap className="h-6 w-6 text-white/10 group-hover:text-[#FF6B00]" />
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-lg font-black text-white/40 uppercase italic tracking-[0.3em] group-hover:text-white transition-colors leading-none">
                      calibration_active
                    </h3>
                    <p className="text-[11px] font-bold text-white/10 group-hover:text-white/20 uppercase tracking-[0.4em] max-w-sm mx-auto transition-colors leading-relaxed">
                      The {activeLabel} subsystem is currently being optimized for high-throughput
                      bridge operations.
                    </p>
                  </div>
                  <div className="flex items-center gap-3 opacity-40">
                    <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] animate-pulse" />
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-[0.5em]">
                      awaiting telemetry
                    </span>
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
