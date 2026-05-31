/**
 * Workspace-scoped builder connection status (read-only configuration surface).
 * Task launches and routing happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Bot, Brain, ChevronRight, Cpu, ScanLine, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ProjectRecord } from "@/lib/ham/types";
import { listHamProjects } from "@/lib/ham/api";
import { cn } from "@/lib/utils";
import {
  fetchCodingReadinessSnapshot,
  fetchCodingAgentAccessSettings,
  fetchCursorReadiness,
  normalizeSelectedBuilder,
  patchCodingAgentAccessSettings,
  type CodingAgentReadiness,
  type SelectedBuilder,
} from "../../adapters/codingAgentsAdapter";
import { CODING_AGENT_LABELS } from "../coding-agents/codingAgentLabels";
import {
  BuilderConnectionDetailPanel,
  type BuilderConnectionLane,
  type BuilderConnectionPanelModel,
  type BuilderConnectionStatusTone,
} from "./BuilderConnectionDetailPanel";

type StatusTone = BuilderConnectionStatusTone;

type BuilderRowModel = {
  key: SelectedBuilder;
  lane: BuilderConnectionLane;
  icon: LucideIcon;
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: StatusTone;
  helper: string;
};

function ConnectionStatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold leading-snug",
        tone === "ready" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
        tone === "attention" && "border-amber-500/30 bg-amber-500/10 text-amber-200",
        tone === "blocked" && "border-slate-500/35 bg-slate-500/10 text-slate-200",
        tone === "neutral" && "border-white/15 bg-white/[0.04] text-white/55",
      )}
    >
      {label}
    </span>
  );
}

function splitGoodFor(raw: string) {
  return raw
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean);
}

function BuilderConnectionRow({
  builderKey,
  icon: Icon,
  title,
  subtitle,
  statusLabel,
  statusTone,
  helper,
  selected,
  disabled,
  saving,
  onSelect,
  onOpenDetails,
  isPanelOpen,
}: {
  builderKey: SelectedBuilder;
  icon: LucideIcon;
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: StatusTone;
  helper: string;
  selected: boolean;
  disabled: boolean;
  saving: boolean;
  onSelect: (builder: SelectedBuilder) => void;
  onOpenDetails: () => void;
  isPanelOpen: boolean;
}) {
  return (
    <li
      className={cn(
        "rounded-2xl border bg-[var(--theme-card)] p-4 shadow-[0_8px_28px_var(--theme-shadow)] transition-colors",
        selected ? "border-[var(--theme-accent)]" : "border-[var(--theme-border)]",
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <label className="flex min-w-0 flex-1 cursor-pointer gap-3">
          <input
            type="radio"
            aria-label={title}
            name="workspace-builder"
            value={builderKey}
            checked={selected}
            disabled={disabled}
            onChange={() => onSelect(builderKey)}
            className="mt-1 h-4 w-4 shrink-0 accent-[var(--theme-accent)]"
          />
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <Icon className="h-5 w-5 shrink-0 text-[var(--theme-accent)]" aria-hidden />
              <span className="text-sm font-semibold text-[var(--theme-text)]">{title}</span>
              {saving ? (
                <span className="text-[10px] font-medium text-[var(--theme-muted)]">Saving…</span>
              ) : null}
            </span>
            <span className="mt-0.5 block text-[11px] leading-snug text-[var(--theme-muted)]">
              {subtitle}
            </span>
            <span className="mt-2 block">
              <ConnectionStatusBadge label={statusLabel} tone={statusTone} />
            </span>
            <span className="mt-2 block text-[11px] leading-relaxed text-[var(--theme-muted)]">
              {helper}
            </span>
          </span>
        </label>
        <button
          type="button"
          aria-expanded={isPanelOpen}
          aria-haspopup="dialog"
          aria-label={`${CODING_AGENT_LABELS.builderPanelOpenDetailsPrefix} ${title}`}
          className="flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[var(--theme-muted)] transition-colors hover:bg-white/[0.04] hover:text-[var(--theme-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-accent)]"
          onClick={onOpenDetails}
        >
          <span>{CODING_AGENT_LABELS.builderPanelRowDetailHint}</span>
          <ChevronRight className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
        </button>
      </div>
    </li>
  );
}

function rowStatusFromReadiness(
  loading: boolean,
  readiness: CodingAgentReadiness,
  readyLabel: string,
  needsSetupLabel: string,
): { statusLabel: string; statusTone: StatusTone } {
  if (loading) {
    return {
      statusLabel: CODING_AGENT_LABELS.connectionStatusChecking,
      statusTone: "neutral",
    };
  }
  if (readiness === "ready") {
    return { statusLabel: readyLabel, statusTone: "ready" };
  }
  return { statusLabel: needsSetupLabel, statusTone: "attention" };
}

function selectedBuilderHelp(selected: SelectedBuilder | null) {
  if (!selected) return "No builder selected yet. HAM will ask you to choose before building.";
  if (selected === "cursor") return "Cursor runs through its own build flow for now.";
  if (selected === "claude") return "Claude runs through its own build flow for now.";
  if (selected === "hermes_agent") return "Hermes Agent new-build support is coming soon.";
  return "Selected for normal builds. Work still starts in chat.";
}

function saveErrorCopy(workspaceId: string) {
  if (!workspaceId.trim()) {
    return "Choose or create a workspace before saving a builder choice.";
  }
  return "Couldn't save your builder choice. Check your session and try again.";
}

function hermesRowModel(): BuilderRowModel {
  return {
    key: "hermes_agent",
    lane: "hermes",
    icon: Cpu,
    title: "Hermes Agent",
    subtitle: "HAM-native builder",
    statusLabel: "Coming soon",
    statusTone: "neutral",
    helper: "Hermes Agent new-build support is coming soon.",
  };
}

export function WorkspaceBuilderPreferences({ workspaceId }: { workspaceId: string }) {
  const [loading, setLoading] = React.useState(true);
  const [selectedBuilder, setSelectedBuilder] = React.useState<SelectedBuilder | null>(null);
  const [savingBuilder, setSavingBuilder] = React.useState<SelectedBuilder | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [cursorReadiness, setCursorReadiness] = React.useState<CodingAgentReadiness>("needs_setup");
  const [cursorError, setCursorError] = React.useState<string | null>(null);
  const [claudeReadiness, setClaudeReadiness] = React.useState<CodingAgentReadiness>("needs_setup");
  const [opencodeReadiness, setOpencodeReadiness] =
    React.useState<CodingAgentReadiness>("needs_setup");
  const [factoryReady, setFactoryReady] = React.useState(false);
  const [openLane, setOpenLane] = React.useState<BuilderConnectionLane | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setCursorError(null);
    setSaveError(null);
    const [settingsRes, cursorRes, codingSnap, projectsRes] = await Promise.all([
      fetchCodingAgentAccessSettings(workspaceId),
      fetchCursorReadiness(),
      fetchCodingReadinessSnapshot(),
      listHamProjects().catch(() => ({ projects: [] as ProjectRecord[] })),
    ]);
    if (settingsRes.ok) {
      setSelectedBuilder(normalizeSelectedBuilder(settingsRes.settings.selected_builder));
    }
    setCursorReadiness(cursorRes.readiness);
    if (cursorRes.error) setCursorError(cursorRes.error);
    setClaudeReadiness(codingSnap.claudeAgent);
    setOpencodeReadiness(codingSnap.opencode);
    setFactoryReady(projectsRes.projects.length > 0);
    setLoading(false);
  }, [workspaceId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSelectBuilder = React.useCallback(
    async (builder: SelectedBuilder) => {
      if (!workspaceId.trim() || savingBuilder || builder === selectedBuilder) return;
      const previous = selectedBuilder;
      setSaveError(null);
      setSavingBuilder(builder);
      setSelectedBuilder(builder);
      const res = await patchCodingAgentAccessSettings(workspaceId, {
        selected_builder: builder,
      });
      if (res.ok) {
        setSelectedBuilder(normalizeSelectedBuilder(res.settings.selected_builder));
      } else {
        setSelectedBuilder(previous);
        setSaveError(saveErrorCopy(workspaceId));
      }
      setSavingBuilder(null);
    },
    [selectedBuilder, savingBuilder, workspaceId],
  );

  const settingsTools = "/workspace/settings?section=tools";
  const settingsHermes = "/workspace/settings?section=hermes";
  const settingsHermesModels = `${settingsHermes}#openrouter-models`;
  const projectsPath = "/workspace/projects";

  let cursorStatusLabel: string;
  let cursorTone: StatusTone;
  if (loading) {
    cursorStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    cursorTone = "neutral";
  } else if (cursorError) {
    cursorStatusLabel = CODING_AGENT_LABELS.connectionStatusUnavailable;
    cursorTone = "blocked";
  } else if (cursorReadiness === "ready") {
    cursorStatusLabel = "Available";
    cursorTone = "ready";
  } else {
    cursorStatusLabel = CODING_AGENT_LABELS.connectionStatusNeedsConnection;
    cursorTone = "attention";
  }

  let claudeStatusLabel: string;
  let claudeTone: StatusTone;
  if (loading) {
    claudeStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    claudeTone = "neutral";
  } else if (claudeReadiness === "ready") {
    claudeStatusLabel = "Available";
    claudeTone = "ready";
  } else {
    claudeStatusLabel = CODING_AGENT_LABELS.connectionStatusNeedsCredentials;
    claudeTone = "attention";
  }

  let factoryStatusLabel: string;
  let factoryTone: StatusTone;
  if (loading) {
    factoryStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    factoryTone = "neutral";
  } else if (factoryReady) {
    factoryStatusLabel = "Available";
    factoryTone = "ready";
  } else {
    factoryStatusLabel = "Needs workspace setup";
    factoryTone = "attention";
  }

  let opencodeStatusLabel: string;
  let opencodeTone: StatusTone;
  if (loading) {
    opencodeStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    opencodeTone = "neutral";
  } else if (opencodeReadiness === "ready") {
    opencodeStatusLabel = "Available";
    opencodeTone = "ready";
  } else {
    opencodeStatusLabel = CODING_AGENT_LABELS.settingsStatusNeedsModelAccess;
    opencodeTone = "attention";
  }

  const panelModel: BuilderConnectionPanelModel | null = React.useMemo(() => {
    if (!openLane) return null;

    const toolsSecondaries = [
      { label: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools, to: settingsTools },
    ];

    if (openLane === "hermes") {
      const hermes = hermesRowModel();
      return {
        lane: "hermes",
        icon: hermes.icon,
        title: hermes.title,
        description: "Hermes Agent is the HAM-native builder option.",
        goodForItems: ["HAM-native builds", "Future local orchestration"],
        requires: "New-build support is coming soon.",
        statusLabel: hermes.statusLabel,
        statusTone: hermes.statusTone,
        primary: {
          label: "Open Hermes settings",
          to: settingsHermes,
        },
        secondaries: [
          {
            label: CODING_AGENT_LABELS.builderPanelSecondaryOpenModelSettings,
            to: settingsHermesModels,
          },
        ],
      };
    }

    if (openLane === "claude") {
      return {
        lane: "claude",
        icon: Brain,
        title: CODING_AGENT_LABELS.builderConnectionClaudeTitle,
        description: CODING_AGENT_LABELS.builderConnectionClaudeSubtitle,
        goodForItems: splitGoodFor(CODING_AGENT_LABELS.builderPanelClaudeGoodFor),
        requires: CODING_AGENT_LABELS.builderPanelClaudeRequires,
        statusLabel: claudeStatusLabel,
        statusTone: claudeTone,
        primary: {
          label:
            claudeReadiness === "ready"
              ? CODING_AGENT_LABELS.builderPanelPrimaryManageClaude
              : CODING_AGENT_LABELS.builderPanelPrimaryConnectClaude,
          to: settingsTools,
        },
        secondaries: toolsSecondaries,
      };
    }

    if (openLane === "cursor") {
      return {
        lane: "cursor",
        icon: Bot,
        title: CODING_AGENT_LABELS.builderConnectionCursorTitle,
        description: CODING_AGENT_LABELS.builderConnectionCursorSubtitle,
        goodForItems: splitGoodFor(CODING_AGENT_LABELS.builderPanelCursorGoodFor),
        requires: CODING_AGENT_LABELS.builderPanelCursorRequires,
        statusLabel: cursorStatusLabel,
        statusTone: cursorTone,
        primary: {
          label:
            cursorReadiness === "ready" && !cursorError
              ? CODING_AGENT_LABELS.builderPanelPrimaryManageCursor
              : CODING_AGENT_LABELS.builderPanelPrimaryConnectCursor,
          to: settingsTools,
        },
        secondaries: toolsSecondaries,
      };
    }

    if (openLane === "factory") {
      return {
        lane: "factory",
        icon: ScanLine,
        title: CODING_AGENT_LABELS.builderConnectionFactoryTitle,
        description: CODING_AGENT_LABELS.builderConnectionFactorySubtitle,
        goodForItems: splitGoodFor(CODING_AGENT_LABELS.builderPanelFactoryGoodFor),
        requires: CODING_AGENT_LABELS.builderPanelFactoryRequires,
        statusLabel: factoryStatusLabel,
        statusTone: factoryTone,
        primary: {
          label: factoryReady
            ? CODING_AGENT_LABELS.builderPanelPrimaryManageFactory
            : CODING_AGENT_LABELS.builderPanelPrimarySetupRunner,
          to: factoryReady ? settingsTools : projectsPath,
        },
        secondaries: [
          { label: CODING_AGENT_LABELS.builderPanelSecondaryOpenProjects, to: projectsPath },
          { label: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools, to: settingsTools },
        ],
      };
    }

    return {
      lane: "opencode",
      icon: Sparkles,
      title: CODING_AGENT_LABELS.opencodeProviderName,
      description: CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle,
      goodForItems: splitGoodFor(CODING_AGENT_LABELS.builderPanelOpencodeGoodFor),
      requires: CODING_AGENT_LABELS.builderPanelOpencodeRequires,
      statusLabel: opencodeStatusLabel,
      statusTone: opencodeTone,
      primary: {
        label: CODING_AGENT_LABELS.actionConfigureModelAccess,
        to: settingsHermes,
      },
      secondaries: [
        {
          label: CODING_AGENT_LABELS.builderPanelSecondaryOpenModelSettings,
          to: settingsHermesModels,
        },
      ],
    };
  }, [
    openLane,
    claudeReadiness,
    claudeStatusLabel,
    claudeTone,
    cursorReadiness,
    cursorError,
    cursorStatusLabel,
    cursorTone,
    factoryReady,
    factoryStatusLabel,
    factoryTone,
    opencodeStatusLabel,
    opencodeTone,
    projectsPath,
    settingsHermes,
    settingsHermesModels,
    settingsTools,
  ]);

  const rows: BuilderRowModel[] = [
    {
      key: "opencode",
      lane: "opencode",
      icon: Sparkles,
      title: CODING_AGENT_LABELS.opencodeProviderName,
      subtitle: CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle,
      statusLabel: opencodeStatusLabel,
      statusTone: opencodeTone,
      helper:
        opencodeReadiness === "ready"
          ? "Available to select. A managed build still needs a workspace-ready project."
          : "Needs model access before HAM can use it for normal builds.",
    },
    {
      key: "factory_droid",
      lane: "factory",
      icon: ScanLine,
      title: CODING_AGENT_LABELS.builderConnectionFactoryTitle,
      subtitle: CODING_AGENT_LABELS.builderConnectionFactorySubtitle,
      statusLabel: factoryStatusLabel,
      statusTone: factoryTone,
      helper: factoryReady
        ? "Available to select for managed workspace builds."
        : "Needs a workspace project before HAM can use it for normal builds.",
    },
    {
      key: "cursor",
      lane: "cursor",
      icon: Bot,
      title: CODING_AGENT_LABELS.builderConnectionCursorTitle,
      subtitle: CODING_AGENT_LABELS.builderConnectionCursorSubtitle,
      statusLabel: cursorStatusLabel,
      statusTone: cursorTone,
      helper: "Cursor runs through its own build flow for now.",
    },
    {
      key: "claude",
      lane: "claude",
      icon: Brain,
      title: CODING_AGENT_LABELS.builderConnectionClaudeTitle,
      subtitle: CODING_AGENT_LABELS.builderConnectionClaudeSubtitle,
      statusLabel: claudeStatusLabel,
      statusTone: claudeTone,
      helper: "Claude runs through its own build flow for now.",
    },
    hermesRowModel(),
  ];

  return (
    <>
      <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)]/90 p-4 shadow-[0_12px_40px_var(--theme-shadow)]">
        <div>
          <h2 className="text-sm font-semibold text-[var(--theme-text)]">Builder</h2>
          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--theme-muted)]">
            Choose which builder HAM uses for normal builds. Work still starts in chat.
          </p>
        </div>
        <p
          data-testid="hww-selected-builder-helper"
          className="text-[11px] leading-relaxed text-[var(--theme-muted)]"
        >
          {selectedBuilderHelp(selectedBuilder)}
        </p>
        <ul className="list-none space-y-2 p-0">
          {rows.map((row) => (
            <BuilderConnectionRow
              key={row.key}
              builderKey={row.key}
              icon={row.icon}
              title={row.title}
              subtitle={row.subtitle}
              statusLabel={row.statusLabel}
              statusTone={row.statusTone}
              helper={row.helper}
              selected={selectedBuilder === row.key}
              disabled={loading || savingBuilder !== null || !workspaceId.trim()}
              saving={savingBuilder === row.key}
              onSelect={onSelectBuilder}
              onOpenDetails={() => setOpenLane(row.lane)}
              isPanelOpen={openLane === row.lane}
            />
          ))}
        </ul>
        {saveError ? (
          <p role="alert" className="text-[11px] font-medium text-amber-300">
            {saveError}
          </p>
        ) : null}
      </section>
      {panelModel ? (
        <BuilderConnectionDetailPanel model={panelModel} onClose={() => setOpenLane(null)} />
      ) : null}
    </>
  );
}
