import * as React from "react";
import { Cloud, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  fetchManagedMissions,
  type ManagedMissionLifecycle,
  type ManagedMissionSnapshot,
} from "../adapters/managedMissionsAdapter";
import { WorkspaceSurfaceStateCard } from "./workspaceSurfaceChrome";

function formatRelativeIso(iso: string | null | undefined, nowMs: number) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const d = Math.max(0, Math.floor((nowMs - t) / 1000));
  if (d < 10) return "just now";
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

function lifecyclePill(lc: ManagedMissionLifecycle) {
  const map: Record<ManagedMissionLifecycle, { cls: string; label: string }> = {
    open: {
      cls: "border-sky-400/35 bg-sky-500/10 text-sky-300",
      label: "Open",
    },
    succeeded: {
      cls: "border-emerald-400/35 bg-emerald-500/10 text-emerald-300",
      label: "Succeeded",
    },
    failed: {
      cls: "border-red-400/35 bg-red-500/10 text-red-300",
      label: "Failed",
    },
    archived: {
      cls: "border-[var(--theme-border)] bg-[var(--theme-card2)] text-[var(--theme-muted)]",
      label: "Archived",
    },
  };
  const m = map[lc] ?? map.open;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]",
        m.cls,
      )}
    >
      {m.label}
    </span>
  );
}

type Props = {
  /** Increment (e.g. from parent Sync) to refetch this panel. */
  refreshSignal: number;
  variant: "operations" | "conductor";
};

export function WorkspaceManagedMissionsLivePanel({ refreshSignal, variant }: Props) {
  const [missions, setMissions] = React.useState<ManagedMissionSnapshot[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [httpStatus, setHttpStatus] = React.useState<number | null>(null);
  const [now, setNow] = React.useState(() => Date.now());

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const r = await fetchManagedMissions(80);
    setMissions(r.missions);
    setHttpStatus(r.httpStatus);
    setError(r.error);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load, refreshSignal]);

  React.useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(t);
  }, []);

  const title =
    variant === "operations"
      ? "Cloud Agent missions (live)"
      : "Managed Cloud Agent missions (live)";

  const subtitle =
    variant === "operations"
      ? "Server-observed ManagedMission history from GET /api/cursor/managed/missions. This is not the local Operations v0 JSON roster."
      : "Same durable store as Operations — use alongside Conductor practice missions (JSON) without conflating them.";

  return (
    <section className="rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-5 shadow-[0_20px_60px_var(--theme-shadow)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-accent)]">
            <Cloud className="h-5 w-5" strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--theme-text)]">{title}</h2>
            <p className="mt-1 text-sm text-[var(--theme-muted-2)]">{subtitle}</p>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="border border-[var(--theme-border)] bg-[var(--theme-bg)]"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error ? (
        <div className="mt-4">
          <WorkspaceSurfaceStateCard
            title="Could not load managed missions"
            description="The HAM API returned an error for GET /api/cursor/managed/missions. Cursor Cloud Agent history is unavailable until this succeeds."
            tone="amber"
            technicalDetail={httpStatus != null ? `[${httpStatus}] ${error}` : error}
            primaryAction={
              <Button type="button" size="sm" variant="secondary" onClick={() => void load()} disabled={loading}>
                Retry
              </Button>
            }
          />
        </div>
      ) : null}

      {!error && loading && missions.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--theme-muted)]">Loading managed missions…</p>
      ) : null}

      {!error && !loading && missions.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-6 text-center text-sm text-[var(--theme-muted)]">
          <p className="font-medium text-[var(--theme-text)]">No managed missions on file</p>
          <p className="mt-2">
            When you launch a managed Cloud Agent via HAM (for example POST /api/cursor/agents/launch with managed
            handling), persisted missions appear here. Empty is normal if none have been recorded for this API host.
          </p>
        </div>
      ) : null}

      {!error && missions.length > 0 ? (
        <div className="mt-4 hww-scroll max-h-[min(420px,50vh)] overflow-auto rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]">
          <table className="w-full min-w-[640px] border-collapse text-left text-sm">
            <thead className="sticky top-0 z-[1] border-b border-[var(--theme-border)] bg-[var(--theme-card)]">
              <tr className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                <th className="px-3 py-2">Lifecycle</th>
                <th className="px-3 py-2">Cursor agent</th>
                <th className="px-3 py-2">Cursor status</th>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Repo / ref</th>
                <th className="px-3 py-2 text-right">Updated</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => {
                const repo = [m.repository_observed, m.ref_observed].filter(Boolean).join(" @ ") || "—";
                return (
                  <tr key={m.mission_registry_id} className="border-b border-[var(--theme-border)]/80 last:border-b-0">
                    <td className="px-3 py-2 align-top">{lifecyclePill(m.mission_lifecycle)}</td>
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-[var(--theme-text)]">
                      {m.cursor_agent_id}
                    </td>
                    <td className="max-w-[140px] px-3 py-2 align-top font-mono text-[11px] text-[var(--theme-muted)]">
                      {m.cursor_status_last_observed ?? "—"}
                    </td>
                    <td className="max-w-[200px] px-3 py-2 align-top text-xs text-[var(--theme-muted-2)]">
                      {m.status_reason_last_observed ?? m.last_review_headline ?? "—"}
                    </td>
                    <td className="max-w-[220px] px-3 py-2 align-top text-xs text-[var(--theme-muted)]">
                      <span className="line-clamp-2">{repo}</span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 align-top text-right text-xs text-[var(--theme-muted-2)]">
                      {formatRelativeIso(m.last_server_observed_at || m.updated_at, now)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
