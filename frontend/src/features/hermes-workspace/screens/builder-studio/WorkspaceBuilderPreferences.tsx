/**
 * Workspace-scoped builder preferences + provider readiness (configuration only).
 * Task launches happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Bot, Brain, ChevronDown, ChevronUp, ScanLine, Settings2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import type { ProjectRecord } from "@/lib/ham/types";
import { listHamProjects } from "@/lib/ham/api";
import {
  fetchCodingAgentAccessSettings,
  fetchCodingReadinessSnapshot,
  fetchCursorReadiness,
  patchCodingAgentAccessSettings,
  type CodingAgentAccessSettings,
  type CodingAgentReadiness,
  type PreferenceMode,
} from "../../adapters/codingAgentsAdapter";
import { CodingAgentReadinessPill } from "../coding-agents/CodingAgentReadinessPill";
import { CODING_AGENT_LABELS } from "../coding-agents/codingAgentLabels";

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3">
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--theme-accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <div>
        <p className="text-sm font-medium text-[var(--theme-text)]">{label}</p>
        <p className="mt-0.5 text-[11px] text-[var(--theme-muted)]">{description}</p>
      </div>
    </label>
  );
}

function AgentSettingsPanel({
  workspaceId,
  settings,
  onSettingsChange,
}: {
  workspaceId: string;
  settings: CodingAgentAccessSettings | null;
  onSettingsChange: (s: CodingAgentAccessSettings) => void;
}) {
  const s = settings;
  const saving = React.useRef(false);

  const patch = React.useCallback(
    async (update: Partial<CodingAgentAccessSettings>) => {
      if (saving.current) return;
      saving.current = true;
      const result = await patchCodingAgentAccessSettings(workspaceId, update);
      saving.current = false;
      if (result.ok) {
        onSettingsChange(result.settings);
      } else {
        toast.error(CODING_AGENT_LABELS.settingsSaveError, { duration: 6000 });
      }
    },
    [workspaceId, onSettingsChange],
  );

  const modeOptions: { value: PreferenceMode; label: string }[] = [
    { value: "recommended", label: CODING_AGENT_LABELS.settingsPreferenceModeRecommended },
    { value: "prefer_open_custom", label: CODING_AGENT_LABELS.settingsPreferenceModeOpenCustom },
    {
      value: "prefer_premium_reasoning",
      label: CODING_AGENT_LABELS.settingsPreferenceModePremiumReasoning,
    },
    {
      value: "prefer_connected_repo",
      label: CODING_AGENT_LABELS.settingsPreferenceModeConnectedRepo,
    },
  ];

  return (
    <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_12px_40px_var(--theme-shadow)]">
      <div>
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.settingsPanelTitle}
        </h2>
        <p className="mt-0.5 text-[11px] text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.settingsPanelSubtitle}
        </p>
      </div>

      <div className="space-y-2">
        <ToggleRow
          label={CODING_AGENT_LABELS.settingsFactoryDroidLabel}
          description={CODING_AGENT_LABELS.settingsFactoryDroidDescription}
          checked={s?.allow_factory_droid ?? true}
          onChange={(v) => void patch({ allow_factory_droid: v })}
        />
        <ToggleRow
          label={CODING_AGENT_LABELS.settingsClaudeAgentLabel}
          description={CODING_AGENT_LABELS.settingsClaudeAgentDescription}
          checked={s?.allow_claude_agent ?? true}
          onChange={(v) => void patch({ allow_claude_agent: v })}
        />
        <ToggleRow
          label={CODING_AGENT_LABELS.settingsOpencodeLabel}
          description={CODING_AGENT_LABELS.settingsOpencodeDescription}
          checked={s?.allow_opencode ?? false}
          onChange={(v) => void patch({ allow_opencode: v })}
        />
        <ToggleRow
          label={CODING_AGENT_LABELS.settingsCursorLabel}
          description={CODING_AGENT_LABELS.settingsCursorDescription}
          checked={s?.allow_cursor ?? true}
          onChange={(v) => void patch({ allow_cursor: v })}
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.settingsPreferenceModeLabel}
          <select
            className="mt-1 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-sm text-[var(--theme-text)]"
            value={s?.preference_mode ?? "recommended"}
            onChange={(e) => void patch({ preference_mode: e.target.value as PreferenceMode })}
          >
            {modeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}

function ProviderRow({
  readiness,
  readinessError,
  readinessLoading,
  droidReady,
  claudeAgentReadiness,
  opencodeReadiness,
  settingsOpen,
  onToggleSettings,
}: {
  readiness: CodingAgentReadiness;
  readinessError: string | null;
  readinessLoading: boolean;
  droidReady: boolean;
  claudeAgentReadiness: CodingAgentReadiness;
  opencodeReadiness: CodingAgentReadiness;
  settingsOpen: boolean;
  onToggleSettings: () => void;
}) {
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-4 py-3 shadow-[0_12px_40px_var(--theme-shadow)]">
      <div className="flex items-center gap-2">
        <Bot className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">Cursor</span>
        {readinessLoading ? (
          <span className="text-[10px] uppercase tracking-wider text-[var(--theme-muted)]">
            Checking…
          </span>
        ) : (
          <CodingAgentReadinessPill readiness={readiness} />
        )}
      </div>
      <span className="text-[var(--theme-muted)]">·</span>
      <div className="flex items-center gap-2">
        <ScanLine className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">Factory Droid</span>
        <CodingAgentReadinessPill readiness={droidReady ? "ready" : "needs_setup"} />
      </div>
      <span className="text-[var(--theme-muted)]">·</span>
      <div className="flex items-center gap-2">
        <Brain className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.settingsClaudeAgentLabel}
        </span>
        <CodingAgentReadinessPill readiness={claudeAgentReadiness} />
      </div>
      <span className="text-[var(--theme-muted)]">·</span>
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.opencodeProviderName}
        </span>
        <CodingAgentReadinessPill readiness={opencodeReadiness} />
      </div>
      {readinessError && <span className="text-[11px] text-amber-300/80">{readinessError}</span>}
      <button
        type="button"
        onClick={onToggleSettings}
        className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[var(--theme-muted)] transition-colors hover:text-[var(--theme-text)]"
        aria-expanded={settingsOpen}
        aria-label={CODING_AGENT_LABELS.settingsPanelTitle}
      >
        <Settings2 className="h-3.5 w-3.5" />
        {CODING_AGENT_LABELS.settingsPanelTitle}
        {settingsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
    </section>
  );
}

export function WorkspaceBuilderPreferences({ workspaceId }: { workspaceId: string }) {
  const [readiness, setReadiness] = React.useState<CodingAgentReadiness>("needs_setup");
  const [readinessError, setReadinessError] = React.useState<string | null>(null);
  const [readinessLoading, setReadinessLoading] = React.useState(true);
  const [opencodeReadiness, setOpencodeReadiness] =
    React.useState<CodingAgentReadiness>("needs_setup");
  const [claudeAgentReadiness, setClaudeAgentReadiness] =
    React.useState<CodingAgentReadiness>("needs_setup");
  const [agentSettings, setAgentSettings] = React.useState<CodingAgentAccessSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [droidReady, setDroidReady] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setReadinessLoading(true);
    setReadinessError(null);
    const [r, codingSnap, settingsResult, projectsRes] = await Promise.all([
      fetchCursorReadiness(),
      fetchCodingReadinessSnapshot(),
      fetchCodingAgentAccessSettings(workspaceId),
      listHamProjects().catch(() => ({ projects: [] as ProjectRecord[] })),
    ]);
    setDroidReady(projectsRes.projects.length > 0);
    if (settingsResult?.ok) {
      setAgentSettings(settingsResult.settings);
    }
    setReadiness(r.readiness);
    setOpencodeReadiness(codingSnap.opencode);
    setClaudeAgentReadiness(codingSnap.claudeAgent);
    if (r.error) setReadinessError(r.error);
    setReadinessLoading(false);
  }, [workspaceId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="flex flex-col gap-3">
      <ProviderRow
        readiness={readiness}
        readinessError={readinessError}
        readinessLoading={readinessLoading}
        droidReady={droidReady}
        claudeAgentReadiness={claudeAgentReadiness}
        opencodeReadiness={opencodeReadiness}
        settingsOpen={settingsOpen}
        onToggleSettings={() => setSettingsOpen((v) => !v)}
      />
      {settingsOpen ? (
        <AgentSettingsPanel
          workspaceId={workspaceId}
          settings={agentSettings}
          onSettingsChange={setAgentSettings}
        />
      ) : null}
    </div>
  );
}
