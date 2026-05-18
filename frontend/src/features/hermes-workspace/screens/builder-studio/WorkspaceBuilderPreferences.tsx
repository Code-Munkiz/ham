/**
 * Workspace-scoped builder connection status (read-only configuration surface).
 * Task launches and routing happen from workspace chat, not from this surface.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import { Bot, Brain, ScanLine, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ProjectRecord } from "@/lib/ham/types";
import { listHamProjects } from "@/lib/ham/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  fetchCodingReadinessSnapshot,
  fetchCursorReadiness,
  type CodingAgentReadiness,
} from "../../adapters/codingAgentsAdapter";
import { CODING_AGENT_LABELS } from "../coding-agents/codingAgentLabels";

type StatusTone = "ready" | "attention" | "blocked" | "neutral";

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

function BuilderConnectionRow({
  icon: Icon,
  title,
  subtitle,
  statusLabel,
  statusTone,
  actionLabel,
  actionTo,
}: {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: StatusTone;
  actionLabel: string;
  actionTo: string;
}) {
  return (
    <li className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_8px_28px_var(--theme-shadow)]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 gap-3">
          <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--theme-accent)]" aria-hidden />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[var(--theme-text)]">{title}</h3>
            <p className="mt-0.5 text-[11px] leading-snug text-[var(--theme-muted)]">{subtitle}</p>
            <div className="mt-2">
              <ConnectionStatusBadge label={statusLabel} tone={statusTone} />
            </div>
          </div>
        </div>
        <Button asChild variant="secondary" size="sm" className="h-9 shrink-0 sm:self-center">
          <Link to={actionTo}>{actionLabel}</Link>
        </Button>
      </div>
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

  const cursorAction =
    cursorReadiness === "ready" && !cursorError
      ? { label: CODING_AGENT_LABELS.actionManage, to: settingsTools }
      : { label: CODING_AGENT_LABELS.actionConnectCursor, to: settingsTools };

  const claudeAction =
    claudeReadiness === "ready"
      ? { label: CODING_AGENT_LABELS.actionManage, to: settingsTools }
      : { label: CODING_AGENT_LABELS.actionConnectClaude, to: settingsTools };

  const factoryAction = factoryReady
    ? { label: CODING_AGENT_LABELS.actionManage, to: settingsTools }
    : { label: CODING_AGENT_LABELS.actionConnectFactory, to: projectsPath };

  const opencodeAction =
    opencodeReadiness === "ready"
      ? { label: CODING_AGENT_LABELS.actionManage, to: settingsTools }
      : { label: CODING_AGENT_LABELS.actionConfigureModelAccess, to: settingsHermes };

  return (
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
          actionLabel={claudeAction.label}
          actionTo={claudeAction.to}
        />
        <BuilderConnectionRow
          icon={Bot}
          title={CODING_AGENT_LABELS.builderConnectionCursorTitle}
          subtitle={CODING_AGENT_LABELS.builderConnectionCursorSubtitle}
          statusLabel={cursorStatusLabel}
          statusTone={cursorTone}
          actionLabel={cursorAction.label}
          actionTo={cursorAction.to}
        />
        <BuilderConnectionRow
          icon={ScanLine}
          title={CODING_AGENT_LABELS.builderConnectionFactoryTitle}
          subtitle={CODING_AGENT_LABELS.builderConnectionFactorySubtitle}
          statusLabel={factoryStatusLabel}
          statusTone={factoryTone}
          actionLabel={factoryAction.label}
          actionTo={factoryAction.to}
        />
        <BuilderConnectionRow
          icon={Sparkles}
          title={CODING_AGENT_LABELS.opencodeProviderName}
          subtitle={CODING_AGENT_LABELS.builderConnectionOpencodeSubtitle}
          statusLabel={opencodeStatusLabel}
          statusTone={opencodeTone}
          actionLabel={opencodeAction.label}
          actionTo={opencodeAction.to}
        />
      </ul>
    </section>
  );
}
