/**
 * Workspace-scoped builder preferences + provider readiness (configuration only).
 * Task launches happen from workspace chat, not from this surface.
 */
import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bot, Brain, ChevronDown, ChevronUp, ScanLine, Settings2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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

function preferenceModeOptionDisabled(
  mode: PreferenceMode,
  s: CodingAgentAccessSettings | null,
): boolean {
  if (!s) return false;
  if (mode === "prefer_premium_reasoning") return !s.allow_claude_agent;
  if (mode === "prefer_open_custom") return !s.allow_opencode;
  if (mode === "prefer_connected_repo") return !s.allow_cursor;
  return false;
}

function preferenceModeUnavailableHint(mode: PreferenceMode): string | null {
  if (mode === "prefer_premium_reasoning") {
    return CODING_AGENT_LABELS.settingsPreferenceModePremiumUnavailableHint;
  }
  if (mode === "prefer_open_custom") {
    return CODING_AGENT_LABELS.settingsPreferenceModeOpenCustomUnavailableHint;
  }
  if (mode === "prefer_connected_repo") {
    return CODING_AGENT_LABELS.settingsPreferenceModeConnectedRepoUnavailableHint;
  }
  return null;
}

function PreferenceModeDropdown({
  modeOptions,
  value,
  settings,
  onChange,
  labelId,
}: {
  modeOptions: { value: PreferenceMode; label: string }[];
  value: PreferenceMode;
  settings: CodingAgentAccessSettings | null;
  onChange: (next: PreferenceMode) => void;
  labelId: string;
}) {
  const currentLabel =
    modeOptions.find((o) => o.value === value)?.label ??
    CODING_AGENT_LABELS.settingsPreferenceModeRecommended;

  const controlBaseId = labelId.replace(/-label$/, "");
  const triggerId = `${controlBaseId}-trigger`;
  const valueRegionId = `${controlBaseId}-value`;

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button
          type="button"
          variant="outline"
          id={triggerId}
          aria-labelledby={`${labelId} ${valueRegionId}`}
          className="mt-1 h-auto min-h-10 w-full justify-between gap-2 border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-left text-sm font-normal text-[var(--theme-text)] hover:bg-[var(--theme-bg)]"
        >
          <span id={valueRegionId} className="min-w-0 flex-1 truncate">
            {currentLabel}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className={cn(
            "z-[200] max-h-[min(320px,60vh)] min-w-[var(--radix-dropdown-menu-trigger-width)] overflow-y-auto rounded-xl border border-white/12",
            "bg-[#0c141c] p-1 shadow-[0_12px_40px_rgba(0,0,0,0.55)]",
          )}
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          {modeOptions.map((opt) => {
            const dis = preferenceModeOptionDisabled(opt.value, settings);
            const hint = dis ? preferenceModeUnavailableHint(opt.value) : null;
            const selected = value === opt.value;
            return (
              <DropdownMenu.Item
                key={opt.value}
                disabled={dis}
                textValue={opt.label}
                className={cn(
                  "mx-0 flex cursor-pointer flex-col gap-0.5 rounded-md px-2.5 py-2 text-left text-sm outline-none",
                  "data-[highlighted]:bg-white/[0.08]",
                  dis
                    ? "cursor-not-allowed bg-white/[0.02] text-white/70 data-[disabled]:pointer-events-none data-[disabled]:opacity-100"
                    : "text-white/95",
                )}
                onSelect={() => {
                  onChange(opt.value);
                }}
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 font-medium leading-snug">{opt.label}</span>
                  {selected ? (
                    <span
                      className="shrink-0 text-[11px] font-semibold text-emerald-300/90"
                      aria-hidden
                    >
                      ✓
                    </span>
                  ) : null}
                </span>
                {dis && hint ? (
                  <span className="text-[11px] leading-snug text-white/55">{hint}</span>
                ) : null}
                {dis ? <span className="sr-only">Unavailable</span> : null}
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

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
        <label
          id="builder-studio-preference-mode-label"
          htmlFor="builder-studio-preference-mode-trigger"
          className="block text-xs font-medium text-[var(--theme-muted)]"
        >
          {CODING_AGENT_LABELS.settingsPreferenceModeLabel}
        </label>
        <PreferenceModeDropdown
          labelId="builder-studio-preference-mode-label"
          modeOptions={modeOptions}
          value={s?.preference_mode ?? "recommended"}
          settings={s}
          onChange={(next) => void patch({ preference_mode: next })}
        />
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
