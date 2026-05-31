/**
 * Workspace-scoped builder connection status (read-only configuration surface).
 * Task launches and routing happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Bot, Brain, ChevronRight, Cpu, ScanLine, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ProjectRecord } from "@/lib/ham/types";
import { ensureBuilderDefaultProject, listHamProjects } from "@/lib/ham/api";
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
  setupActionLabel?: string;
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
  setupActionLabel,
  selected,
  disabled,
  saving,
  setupBusy,
  onToggle,
  onSetup,
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
  setupActionLabel?: string;
  selected: boolean;
  disabled: boolean;
  saving: boolean;
  setupBusy: boolean;
  onToggle: (builder: SelectedBuilder) => void;
  onSetup: (builder: SelectedBuilder) => void;
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
            {setupActionLabel ? (
              <button
                type="button"
                disabled={setupBusy}
                onClick={() => onSetup(builderKey)}
                className="mt-2 inline-flex w-fit items-center rounded-lg border border-[var(--theme-accent)]/35 px-2.5 py-1 text-[11px] font-medium text-[var(--theme-accent)] transition-colors hover:bg-[var(--theme-accent)]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-accent)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {setupBusy ? "Finishing setup..." : setupActionLabel}
              </button>
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
}): { statusLabel: string; statusTone: StatusTone } {
  if (opts.loading) {
    return { statusLabel: CODING_AGENT_LABELS.connectionStatusChecking, statusTone: "neutral" };
  }
  if (opts.platformReady && opts.managedProjectReady) {
    return { statusLabel: "Ready", statusTone: "ready" };
  }
  return { statusLabel: "Finish setup", statusTone: "attention" };
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

function managedBuilderDetail(opts: {
  lane: BuilderConnectionLane;
  icon: LucideIcon;
  title: string;
  description: string;
  ready: boolean;
  selected: boolean;
  status: { statusLabel: string; statusTone: StatusTone };
}): BuilderConnectionPanelModel {
  if (opts.ready) {
    return {
      lane: opts.lane,
      icon: opts.icon,
      title: opts.title,
      description: opts.description,
      statusLabel: "Ready",
      statusTone: "ready",
      statusDetail: `HAM will use ${opts.title} when you ask it to build.`,
    };
  }

  return {
    lane: opts.lane,
    icon: opts.icon,
    title: opts.title,
    description: opts.description,
    statusLabel: opts.status.statusLabel,
    statusTone: opts.status.statusTone,
    statusDetail: opts.selected
      ? `Finish setup before HAM can use ${opts.title} for builds.`
      : `Turn this on, then finish setup so HAM can use ${opts.title} for builds.`,
    primary: opts.selected ? { label: "Finish setup", action: "finish_setup" } : undefined,
  };
}

export function WorkspaceBuilderPreferences({ workspaceId }: { workspaceId: string }) {
  const [loading, setLoading] = React.useState(true);
  const [selectedBuilder, setSelectedBuilder] = React.useState<SelectedBuilder | null>(null);
  const [savingBuilder, setSavingBuilder] = React.useState<SelectedBuilder | null>(null);
  const [setupBuilder, setSetupBuilder] = React.useState<SelectedBuilder | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [setupMessage, setSetupMessage] = React.useState<string | null>(null);
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
    setSetupMessage(null);
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

  const onFinishSetup = React.useCallback(
    async (builder: SelectedBuilder) => {
      if (!workspaceId.trim() || setupBuilder) return;
      if (builder !== "opencode" && builder !== "factory_droid") return;
      setSetupMessage(null);
      setSetupBuilder(builder);
      try {
        await ensureBuilderDefaultProject(workspaceId);
        await refresh();
      } catch {
        setSetupMessage(
          "Couldn't finish setup here. Open Projects and create or attach a workspace project.",
        );
      } finally {
        setSetupBuilder(null);
      }
    },
    [refresh, setupBuilder, workspaceId],
  );

  const settingsTools = "/workspace/settings?section=tools";

  let cursorStatusLabel: string;
  let cursorTone: StatusTone;
  if (loading) {
    cursorStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    cursorTone = "neutral";
  } else if (cursorError) {
    cursorStatusLabel = CODING_AGENT_LABELS.connectionStatusUnavailable;
    cursorTone = "blocked";
  } else if (cursorReadiness === "ready") {
    cursorStatusLabel = "Ready";
    cursorTone = "ready";
  } else {
    cursorStatusLabel = "Finish setup";
    cursorTone = "attention";
  }

  let claudeStatusLabel: string;
  let claudeTone: StatusTone;
  if (loading) {
    claudeStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    claudeTone = "neutral";
  } else if (claudeReadiness === "ready") {
    claudeStatusLabel = "Ready";
    claudeTone = "ready";
  } else {
    claudeStatusLabel = "Finish setup";
    claudeTone = "attention";
  }

  const opencodePlatformReady = opencodeReadiness === "ready";
  const opencodeBuildReady = opencodePlatformReady && managedProjectReady;
  const opencodeRowStatus = inChatBuilderRowStatus({
    loading,
    platformReady: opencodePlatformReady,
    managedProjectReady,
  });
  const factoryBuildReady = factoryReady && managedProjectReady;
  const factoryRowStatus = inChatBuilderRowStatus({
    loading,
    platformReady: factoryReady,
    managedProjectReady,
  });

  const panelModel: BuilderConnectionPanelModel | null = React.useMemo(() => {
    if (!openLane) return null;

    if (openLane === "hermes") {
      const hermes = hermesRowModel();
      return {
        lane: "hermes",
        icon: hermes.icon,
        title: hermes.title,
        description: "Hermes Agent is the HAM-native builder option.",
        statusLabel: hermes.statusLabel,
        statusTone: hermes.statusTone,
        statusDetail: "Hermes Agent new-build support is coming soon.",
      };
    }

    if (openLane === "claude") {
      return {
        lane: "claude",
        icon: Brain,
        title: CODING_AGENT_LABELS.builderConnectionClaudeTitle,
        description: CODING_AGENT_LABELS.builderConnectionClaudeSubtitle,
        statusLabel: claudeStatusLabel,
        statusTone: claudeTone,
        statusDetail:
          claudeReadiness === "ready"
            ? "Claude is ready. It runs through its own build flow for now."
            : "Finish setup before HAM can use Claude for builds.",
        primary:
          claudeReadiness === "ready"
            ? undefined
            : { label: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools, to: settingsTools },
      };
    }

    if (openLane === "cursor") {
      return {
        lane: "cursor",
        icon: Bot,
        title: CODING_AGENT_LABELS.builderConnectionCursorTitle,
        description: CODING_AGENT_LABELS.builderConnectionCursorSubtitle,
        statusLabel: cursorStatusLabel,
        statusTone: cursorTone,
        statusDetail:
          cursorReadiness === "ready" && !cursorError
            ? "Cursor is ready. It runs through its own build flow for now."
            : "Finish setup before HAM can use Cursor for builds.",
        primary:
          cursorReadiness === "ready" && !cursorError
            ? undefined
            : { label: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools, to: settingsTools },
      };
    }

    if (openLane === "factory") {
      return managedBuilderDetail({
        lane: "factory",
        icon: ScanLine,
        title: CODING_AGENT_LABELS.builderConnectionFactoryTitle,
        description: CODING_AGENT_LABELS.builderConnectionFactorySubtitle,
        ready: factoryBuildReady,
        selected: selectedBuilder === "factory_droid",
        status: factoryRowStatus,
      });
    }

    return managedBuilderDetail({
      lane: "opencode",
      icon: Sparkles,
      title: CODING_AGENT_LABELS.opencodeProviderName,
      description: CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle,
      ready: opencodeBuildReady,
      selected: selectedBuilder === "opencode",
      status: opencodeRowStatus,
    });
  }, [
    openLane,
    claudeReadiness,
    claudeStatusLabel,
    claudeTone,
    cursorReadiness,
    cursorError,
    cursorStatusLabel,
    cursorTone,
    factoryBuildReady,
    factoryRowStatus.statusLabel,
    factoryRowStatus.statusTone,
    opencodeBuildReady,
    opencodeRowStatus.statusLabel,
    opencodeRowStatus.statusTone,
    selectedBuilder,
    settingsTools,
  ]);

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
        ? "Ready for normal builds. Work starts in chat."
        : selectedBuilder === "opencode"
          ? "Finish setup before HAM can use OpenCode. HAM will prepare a workspace project for builds."
          : "Turn this on, then finish setup so HAM can use OpenCode for builds.",
      setupActionLabel:
        selectedBuilder === "opencode" && !opencodeBuildReady ? "Finish setup" : undefined,
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
        ? "Ready for normal builds. Work starts in chat."
        : selectedBuilder === "factory_droid"
          ? "Finish setup before HAM can use Factory Droid. HAM will prepare a workspace project for builds."
          : "Turn this on, then finish setup so HAM can use Factory Droid for builds.",
      setupActionLabel:
        selectedBuilder === "factory_droid" && !factoryBuildReady ? "Finish setup" : undefined,
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
              setupActionLabel={row.setupActionLabel}
              selected={selectedBuilder === row.key}
              disabled={
                loading ||
                savingBuilder !== null ||
                setupBuilder !== null ||
                !workspaceId.trim() ||
                row.key === "hermes_agent"
              }
              saving={savingBuilder === row.key}
              setupBusy={setupBuilder === row.key}
              onToggle={onToggleBuilder}
              onSetup={onFinishSetup}
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
        {setupMessage ? (
          <p role="alert" className="text-[11px] font-medium text-amber-300">
            {setupMessage}
          </p>
        ) : null}
      </section>
      {panelModel ? (
        <BuilderConnectionDetailPanel
          model={panelModel}
          onClose={() => setOpenLane(null)}
          onFinishSetup={(lane) => {
            if (lane === "opencode") void onFinishSetup("opencode");
            if (lane === "factory") void onFinishSetup("factory_droid");
          }}
        />
      ) : null}
    </>
  );
}
