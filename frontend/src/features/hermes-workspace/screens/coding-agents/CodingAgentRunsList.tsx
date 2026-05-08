import * as React from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  deriveDroidRunStatus,
  droidRunStatusLabel,
  fetchDroidAuditRunsForProject,
  type DroidAuditRunStatus,
} from "../../adapters/codingAgentsAdapter";
import type { ControlPlaneRunPublic } from "@/lib/ham/types";
import { CODING_AGENT_LABELS } from "./codingAgentLabels";

export function CodingAgentRunsList({
  projectId,
  refreshKey,
}: {
  projectId: string | null;
  refreshKey: number;
}) {
  const [runs, setRuns] = React.useState<ControlPlaneRunPublic[]>([]);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const out = await fetchDroidAuditRunsForProject(projectId);
    if (out.ok === true) {
      setRuns(out.runs);
      setErrorMessage(null);
    } else {
      setErrorMessage(out.errorMessage);
      setRuns([]);
    }
    setLoading(false);
  }, [projectId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  return (
    <section className="space-y-2 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_12px_40px_var(--theme-shadow)]">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.auditTitle}
        </h2>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void refresh()}
          disabled={loading}
          className="h-7 gap-1"
        >
          <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
          Refresh
        </Button>
      </header>
      {errorMessage && <p className="text-xs text-amber-300/90">{errorMessage}</p>}
      {!loading && runs.length === 0 && !errorMessage && (
        <div className="rounded-xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
          <p className="text-sm font-medium text-[var(--theme-text)]">
            {CODING_AGENT_LABELS.auditNoRunsTitle}
          </p>
          <p className="mt-1 text-xs text-[var(--theme-muted)]">
            {CODING_AGENT_LABELS.auditNoRunsBody}
          </p>
        </div>
      )}
      {runs.length > 0 && (
        <ul className="divide-y divide-[var(--theme-border)] rounded-xl border border-[var(--theme-border)]">
          {runs.map((r) => (
            <RunRow key={r.ham_run_id} run={r} />
          ))}
        </ul>
      )}
    </section>
  );
}

function RunRow({ run }: { run: ControlPlaneRunPublic }) {
  const status: DroidAuditRunStatus = deriveDroidRunStatus(run.status);
  const summary = (run.summary ?? "").trim() || (run.error_summary ?? "").trim() || "";
  const when = formatTimestamp(run.updated_at || run.created_at);
  return (
    <li className="flex flex-col gap-1 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-[var(--theme-text)]">{when}</span>
        <span className={statusPillClass(status)}>{droidRunStatusLabel(status)}</span>
      </div>
      {summary && <p className="line-clamp-2 text-xs text-[var(--theme-muted)]">{summary}</p>}
    </li>
  );
}

function statusPillClass(status: DroidAuditRunStatus): string {
  const base =
    "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider";
  switch (status) {
    case "running":
      return cn(base, "border-sky-500/40 bg-sky-500/10 text-sky-200");
    case "complete":
      return cn(base, "border-emerald-500/40 bg-emerald-500/10 text-emerald-200");
    case "failed":
      return cn(base, "border-rose-500/40 bg-rose-500/10 text-rose-200");
    default:
      return cn(base, "border-amber-500/40 bg-amber-500/10 text-amber-200");
  }
}

function formatTimestamp(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
