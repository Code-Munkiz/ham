/**
 * Workspace-scoped builder connection status (read-only configuration surface).
 * Task launches and routing happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Link } from "react-router-dom";
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

type BuilderSetupAction = { label: string; to: string };

type BuilderRowModel = {
  key: SelectedBuilder;
  lane: BuilderConnectionLane;
  icon: LucideIcon;
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: StatusTone;
  helper: string;
  setupAction?: BuilderSetupAction;
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

function BuilderSwitch({
  checked,
  disabled,
  onToggle,
  label,
}: {
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors",
        checked
          ? "border-[var(--theme-accent)] bg-[var(--theme-accent)]/80"
          : "border-white/20 bg-white/[0.08]",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-1",
        )}
      />
    </button>
  );
}

function BuilderConnectionRow({
  builderKey,
  icon: Icon,
  title,
  subtitle,
  statusLabel,
  statusTone,
  helper,
  setupAction,
  selected,
  disabled,
  saving,
  onToggle,
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
  setupAction?: BuilderSetupAction;
  selected: boolean;
  disabled: boolean;
  saving: boolean;
  onToggle: (builder: SelectedBuilder) => void;
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
        <div className="flex min-w-0 flex-1 gap-3">
          <BuilderSwitch
            checked={selected}
            disabled={disabled}
            onToggle={() => onToggle(builderKey)}
            label={title}
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
            {setupAction ? (
              <Link
                to={setupAction.to}
                className="mt-2 inline-flex w-fit items-center text-[11px] font-medium text-[var(--theme-accent)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-accent)]"
              >
                {setupAction.label}
              </Link>
            ) : null}
          </span>
        </div>
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

// In-chat managed builders (OpenCode / Factory Droid) can only run a build when
// their provider is platform-ready AND the workspace has a managed-workspace
// project to build into. This mirrors the chat-side readiness gate
// (`_selected_builder_ready`) so Builders never claims "Ready" when chat would
// still block the build. Platform-only availability is not enough.
function inChatBuilderRowStatus(opts: {
  loading: boolean;
  platformReady: boolean;
  managedProjectReady: boolean;
  isSelected: boolean;
}): { statusLabel: string; statusTone: StatusTone } {
  if (opts.loading) {
    return { statusLabel: CODING_AGENT_LABELS.connectionStatusChecking, statusTone: "neutral" };
  }
  if (opts.platformReady && opts.managedProjectReady) {
    return { statusLabel: "Ready", statusTone: "ready" };
  }
  if (opts.isSelected) {
    return { statusLabel: "Selected, needs setup", statusTone: "attention" };
  }
  if (!opts.platformReady) {
    return { statusLabel: "Needs setup", statusTone: "attention" };
  }
  return { statusLabel: "Needs workspace setup", statusTone: "attention" };
}

function inChatBuilderSetupAction(opts: {
  builder: "opencode" | "factory_droid";
  platformReady: boolean;
  managedProjectReady: boolean;
  settingsHermes: string;
  settingsTools: string;
  projectsPath: string;
}): BuilderSetupAction {
  if (!opts.platformReady) {
    return opts.builder === "opencode"
      ? { label: "Open setup", to: opts.settingsHermes }
      : { label: "Go to Connected Tools", to: opts.settingsTools };
  }
  return { label: "Create or attach a workspace project", to: opts.projectsPath };
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

function saveFailureCopy(workspaceId: string, raw?: string | null) {
  const msg = (raw || "").toLowerCase();
  if (msg.includes("refresh or sign in again")) {
    return "Couldn't save your builder choice. Refresh or sign in again.";
  }
  if (msg.includes("choose or create a workspace")) {
    return "Couldn't save your builder choice. Choose or create a workspace first.";
  }
  if (msg.includes("not valid")) {
    return "Couldn't save your builder choice. The selected builder is not valid.";
  }
  if (msg.includes("unavailable")) {
    return "Couldn't save your builder choice. Builder settings are unavailable.";
  }
  if (msg.includes("connection")) {
    return "Couldn't save your builder choice. Check your connection and try again.";
  }
  if (!workspaceId.trim()) return saveErrorCopy(workspaceId);
  return "Couldn't save your builder choice. Try again.";
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
  const [managedProjectReady, setManagedProjectReady] = React.useState(false);
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
    // A managed in-chat build needs a project attached to a workspace, mirroring
    // the chat-side managed-workspace gate. "Any project exists" is not enough.
    setManagedProjectReady(
      projectsRes.projects.some((p) => Boolean((p.workspace_id ?? "").trim())),
    );
    setLoading(false);
  }, [workspaceId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const onToggleBuilder = React.useCallback(
    async (builder: SelectedBuilder) => {
      if (!workspaceId.trim() || savingBuilder) return;
      const previous = selectedBuilder;
      const next = builder === selectedBuilder ? null : builder;
      setSaveError(null);
      setSavingBuilder(builder);
      setSelectedBuilder(next);
      const res = await patchCodingAgentAccessSettings(workspaceId, {
        selected_builder: next,
      });
      if (res.ok === true) {
        setSelectedBuilder(normalizeSelectedBuilder(res.settings.selected_builder));
      } else {
        setSelectedBuilder(previous);
        setSaveError(saveFailureCopy(workspaceId, res.errorMessage));
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

  const opencodePlatformReady = opencodeReadiness === "ready";
  const opencodeBuildReady = opencodePlatformReady && managedProjectReady;
  const opencodeRowStatus = inChatBuilderRowStatus({
    loading,
    platformReady: opencodePlatformReady,
    managedProjectReady,
    isSelected: selectedBuilder === "opencode",
  });
  const factoryBuildReady = factoryReady && managedProjectReady;
  const factoryRowStatus = inChatBuilderRowStatus({
    loading,
    platformReady: factoryReady,
    managedProjectReady,
    isSelected: selectedBuilder === "factory_droid",
  });

  const rows: BuilderRowModel[] = [
    {
      key: "opencode",
      lane: "opencode",
      icon: Sparkles,
      title: CODING_AGENT_LABELS.opencodeProviderName,
      subtitle: CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle,
      statusLabel: opencodeRowStatus.statusLabel,
      statusTone: opencodeRowStatus.statusTone,
      helper: opencodeBuildReady
        ? "Runs as a managed build you review before it runs."
        : "Runs as a managed build you review first. Needs model access and a workspace-ready project.",
      setupAction:
        selectedBuilder === "opencode" && !opencodeBuildReady
          ? inChatBuilderSetupAction({
              builder: "opencode",
              platformReady: opencodePlatformReady,
              managedProjectReady,
              settingsHermes,
              settingsTools,
              projectsPath,
            })
          : undefined,
    },
    {
      key: "factory_droid",
      lane: "factory",
      icon: ScanLine,
      title: CODING_AGENT_LABELS.builderConnectionFactoryTitle,
      subtitle: CODING_AGENT_LABELS.builderConnectionFactorySubtitle,
      statusLabel: factoryRowStatus.statusLabel,
      statusTone: factoryRowStatus.statusTone,
      helper: factoryBuildReady
        ? "Runs as a managed build you review before it runs."
        : "Runs as a managed build you review first. Needs a workspace-ready project.",
      setupAction:
        selectedBuilder === "factory_droid" && !factoryBuildReady
          ? inChatBuilderSetupAction({
              builder: "factory_droid",
              platformReady: factoryReady,
              managedProjectReady,
              settingsHermes,
              settingsTools,
              projectsPath,
            })
          : undefined,
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
              setupAction={row.setupAction}
              selected={selectedBuilder === row.key}
              disabled={
                loading ||
                savingBuilder !== null ||
                !workspaceId.trim() ||
                row.key === "hermes_agent"
              }
              saving={savingBuilder === row.key}
              onToggle={onToggleBuilder}
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
