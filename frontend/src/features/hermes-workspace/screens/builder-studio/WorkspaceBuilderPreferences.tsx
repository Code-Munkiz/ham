/**
 * Workspace-scoped builder connection status (read-only configuration surface).
 * Task launches and routing happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Bot, Brain, ChevronRight, ScanLine, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ProjectRecord } from "@/lib/ham/types";
import { listHamProjects } from "@/lib/ham/api";
import { cn } from "@/lib/utils";
import {
  fetchCodingReadinessSnapshot,
  fetchCursorReadiness,
  type CodingAgentReadiness,
} from "../../adapters/codingAgentsAdapter";
import { CODING_AGENT_LABELS } from "../coding-agents/codingAgentLabels";
import {
  BuilderConnectionDetailPanel,
  type BuilderConnectionLane,
  type BuilderConnectionPanelModel,
  type BuilderConnectionStatusTone,
} from "./BuilderConnectionDetailPanel";

type StatusTone = BuilderConnectionStatusTone;

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
  icon: Icon,
  title,
  subtitle,
  statusLabel,
  statusTone,
  onOpenDetails,
  isPanelOpen,
}: {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: StatusTone;
  onOpenDetails: () => void;
  isPanelOpen: boolean;
}) {
  return (
    <li>
      <button
        type="button"
        aria-expanded={isPanelOpen}
        aria-haspopup="dialog"
        aria-label={`${CODING_AGENT_LABELS.builderPanelOpenDetailsPrefix} ${title}`}
        className="w-full rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 text-left shadow-[0_8px_28px_var(--theme-shadow)] transition-colors hover:border-white/20 hover:bg-[var(--theme-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-bg)]"
        onClick={onOpenDetails}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-1 gap-3">
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--theme-accent)]" aria-hidden />
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-[var(--theme-text)]">{title}</h3>
              <p className="mt-0.5 text-[11px] leading-snug text-[var(--theme-muted)]">
                {subtitle}
              </p>
              <div className="mt-2">
                <ConnectionStatusBadge label={statusLabel} tone={statusTone} />
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1 text-xs font-medium text-[var(--theme-muted)] sm:self-center">
            <span>{CODING_AGENT_LABELS.builderPanelRowDetailHint}</span>
            <ChevronRight className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
          </div>
        </div>
      </button>
    </li>
  );
}

export function WorkspaceBuilderPreferences({ workspaceId }: { workspaceId: string }) {
  void workspaceId;
  const [loading, setLoading] = React.useState(true);
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
    const [cursorRes, codingSnap, projectsRes] = await Promise.all([
      fetchCursorReadiness(),
      fetchCodingReadinessSnapshot(),
      listHamProjects().catch(() => ({ projects: [] as ProjectRecord[] })),
    ]);
    setCursorReadiness(cursorRes.readiness);
    if (cursorRes.error) setCursorError(cursorRes.error);
    setClaudeReadiness(codingSnap.claudeAgent);
    setOpencodeReadiness(codingSnap.opencode);
    setFactoryReady(projectsRes.projects.length > 0);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

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
    cursorStatusLabel = CODING_AGENT_LABELS.settingsStatusReady;
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
    claudeStatusLabel = CODING_AGENT_LABELS.settingsStatusReady;
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
    factoryStatusLabel = CODING_AGENT_LABELS.settingsStatusReady;
    factoryTone = "ready";
  } else {
    factoryStatusLabel = CODING_AGENT_LABELS.connectionStatusNeedsRunner;
    factoryTone = "attention";
  }

  let opencodeStatusLabel: string;
  let opencodeTone: StatusTone;
  if (loading) {
    opencodeStatusLabel = CODING_AGENT_LABELS.connectionStatusChecking;
    opencodeTone = "neutral";
  } else if (opencodeReadiness === "ready") {
    opencodeStatusLabel = CODING_AGENT_LABELS.connectionStatusFree;
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

  return (
    <>
      <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)]/90 p-4 shadow-[0_12px_40px_var(--theme-shadow)]">
        <div>
          <h2 className="text-sm font-semibold text-[var(--theme-text)]">
            {CODING_AGENT_LABELS.builderConnectionsTitle}
          </h2>
          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--theme-muted)]">
            {CODING_AGENT_LABELS.builderConnectionsSubtitle}
          </p>
        </div>
        <ul className="list-none space-y-2 p-0">
          <BuilderConnectionRow
            icon={Brain}
            title={CODING_AGENT_LABELS.builderConnectionClaudeTitle}
            subtitle={CODING_AGENT_LABELS.builderConnectionClaudeSubtitle}
            statusLabel={claudeStatusLabel}
            statusTone={claudeTone}
            onOpenDetails={() => setOpenLane("claude")}
            isPanelOpen={openLane === "claude"}
          />
          <BuilderConnectionRow
            icon={Bot}
            title={CODING_AGENT_LABELS.builderConnectionCursorTitle}
            subtitle={CODING_AGENT_LABELS.builderConnectionCursorSubtitle}
            statusLabel={cursorStatusLabel}
            statusTone={cursorTone}
            onOpenDetails={() => setOpenLane("cursor")}
            isPanelOpen={openLane === "cursor"}
          />
          <BuilderConnectionRow
            icon={ScanLine}
            title={CODING_AGENT_LABELS.builderConnectionFactoryTitle}
            subtitle={CODING_AGENT_LABELS.builderConnectionFactorySubtitle}
            statusLabel={factoryStatusLabel}
            statusTone={factoryTone}
            onOpenDetails={() => setOpenLane("factory")}
            isPanelOpen={openLane === "factory"}
          />
          <BuilderConnectionRow
            icon={Sparkles}
            title={CODING_AGENT_LABELS.opencodeProviderName}
            subtitle={CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle}
            statusLabel={opencodeStatusLabel}
            statusTone={opencodeTone}
            onOpenDetails={() => setOpenLane("opencode")}
            isPanelOpen={openLane === "opencode"}
          />
        </ul>
      </section>
      {panelModel ? (
        <BuilderConnectionDetailPanel model={panelModel} onClose={() => setOpenLane(null)} />
      ) : null}
    </>
  );
}
