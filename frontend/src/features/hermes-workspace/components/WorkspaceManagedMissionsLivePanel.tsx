import * as React from "react";
import { Cloud, Loader2, RefreshCw, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  fetchManagedMissionDetail,
  fetchManagedMissions,
  syncManagedMissionByAgentId,
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

function fmtIsoLocal(iso: string | null | undefined) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return iso;
  return new Date(t).toLocaleString();
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

function DetailField({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="border-b border-[var(--theme-border)]/70 py-2 last:border-b-0">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">{label}</p>
      <p className={cn("mt-0.5 text-sm text-[var(--theme-text)] break-words", mono && "font-mono text-xs")}>
        {value ?? "—"}
      </p>
    </div>
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

  const [detailOpen, setDetailOpen] = React.useState(false);
  const [detailMission, setDetailMission] = React.useState<ManagedMissionSnapshot | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState<string | null>(null);

  const [syncAgentId, setSyncAgentId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);

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

  const openDetail = async (missionRegistryId: string) => {
    setActionError(null);
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setDetailMission(null);
    const r = await fetchManagedMissionDetail(missionRegistryId);
    setDetailLoading(false);
    if (r.mission) {
      setDetailMission(r.mission);
    } else {
      setDetailError(r.error ?? "Could not load mission");
    }
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setDetailMission(null);
    setDetailError(null);
    setDetailLoading(false);
  };

  const runSync = async (agentId: string) => {
    const aid = agentId.trim();
    if (!aid) return;
    setActionError(null);
    setSyncAgentId(aid);
    const r = await syncManagedMissionByAgentId(aid);
    setSyncAgentId(null);
    if (r.error) {
      setActionError(r.error);
      return;
    }
    await load();
    if (r.mission) {
      setDetailMission((cur) => {
        if (!cur) return cur;
        return cur.mission_registry_id === r.mission?.mission_registry_id ? r.mission! : cur;
      });
    }
  };

  const title =
    variant === "operations"
      ? "Cloud Agent missions (live)"
      : "Managed Cloud Agent missions (live)";

  const subtitle =
    variant === "operations"
      ? "Server-observed ManagedMission history from GET /api/cursor/managed/missions. This is not the local Operations v0 JSON roster."
      : "Same durable store as Operations — use alongside Conductor practice missions (JSON) without conflating them.";

  const d = detailMission;

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

      {actionError ? (
        <p className="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100/90">
          {actionError}
        </p>
      ) : null}

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
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead className="sticky top-0 z-[1] border-b border-[var(--theme-border)] bg-[var(--theme-card)]">
              <tr className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                <th className="px-3 py-2">Lifecycle</th>
                <th className="px-3 py-2">Cursor agent</th>
                <th className="px-3 py-2">Cursor status</th>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Repo / ref</th>
                <th className="px-3 py-2 text-right">Updated</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => {
                const repo = [m.repository_observed, m.ref_observed].filter(Boolean).join(" @ ") || "—";
                const agentOk = Boolean(m.cursor_agent_id?.trim());
                const rowBusy = syncAgentId === m.cursor_agent_id;
                return (
                  <tr key={m.mission_registry_id} className="border-b border-[var(--theme-border)]/80 last:border-b-0">
                    <td className="px-3 py-2 align-top">{lifecyclePill(m.mission_lifecycle)}</td>
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-[var(--theme-text)]">
                      {m.cursor_agent_id || "—"}
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
                    <td className="px-3 py-2 align-top text-right">
                      <div className="flex flex-col items-end gap-1 sm:flex-row sm:justify-end">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="h-7 border border-[var(--theme-border)] bg-[var(--theme-card)] px-2 text-[11px]"
                          onClick={() => void openDetail(m.mission_registry_id)}
                        >
                          Details
                        </Button>
                        {agentOk ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="secondary"
                            className="h-7 border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-[11px]"
                            disabled={!!syncAgentId}
                            onClick={() => void runSync(m.cursor_agent_id)}
                          >
                            {rowBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCw className="h-3 w-3" />}
                            Sync
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {detailOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/55 p-3"
          role="dialog"
          aria-modal="true"
          aria-labelledby="managed-mission-detail-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeDetail();
          }}
        >
          <div
            className="hww-scroll max-h-[min(90vh,720px)] w-full max-w-lg overflow-y-auto rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-5 shadow-xl"
            style={{ color: "var(--theme-text)" }}
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 id="managed-mission-detail-title" className="text-base font-semibold text-[var(--theme-text)]">
                Managed mission
              </h3>
              <Button type="button" size="sm" variant="ghost" className="h-8 px-2 text-[var(--theme-muted)]" onClick={closeDetail}>
                Close
              </Button>
            </div>
            <p className="mt-1 text-xs text-[var(--theme-muted-2)]">
              Source: HAM <span className="font-mono">ManagedMission</span> store (server-observed metadata only).
            </p>

            {detailLoading ? (
              <p className="mt-6 flex items-center gap-2 text-sm text-[var(--theme-muted)]">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </p>
            ) : null}

            {detailError && !detailLoading ? (
              <p className="mt-4 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200/90">
                {detailError}
              </p>
            ) : null}

            {d && !detailLoading ? (
              <div className="mt-4 space-y-1">
                <DetailField label="Mission registry id" value={d.mission_registry_id} mono />
                <DetailField label="Managed by" value={d.mission_handling === "managed" ? "HAM (managed)" : "HAM"} />
                <DetailField label="Cursor agent id" value={d.cursor_agent_id} mono />
                <DetailField label="Lifecycle" value={lifecyclePill(d.mission_lifecycle)} />
                <DetailField label="Deploy approval mode" value={d.mission_deploy_approval_mode ?? "—"} />
                <DetailField label="Control plane run id" value={d.control_plane_ham_run_id ?? "—"} mono />
                <DetailField label="Repository (observed)" value={d.repository_observed ?? "—"} />
                <DetailField label="Ref (observed)" value={d.ref_observed ?? "—"} mono />
                <DetailField label="Branch (launch)" value={d.branch_name_launch ?? "—"} />
                <DetailField label="Repo key" value={d.repo_key ?? "—"} mono />
                <DetailField label="Uplink id" value={d.uplink_id ?? "—"} mono />
                <DetailField label="Cursor status (last observed)" value={d.cursor_status_last_observed ?? "—"} mono />
                <DetailField label="Status reason" value={d.status_reason_last_observed ?? "—"} />
                <DetailField label="Review headline" value={d.last_review_headline ?? "—"} />
                <DetailField label="Review severity" value={d.last_review_severity ?? "—"} />
                <DetailField label="Deploy state (observed)" value={d.last_deploy_state_observed ?? "—"} />
                <DetailField label="Vercel mapping tier" value={d.last_vercel_mapping_tier ?? "—"} />
                <DetailField label="Hook outcome" value={d.last_hook_outcome ?? "—"} />
                <DetailField label="Post-deploy state" value={d.last_post_deploy_state ?? "—"} />
                <DetailField label="Post-deploy reason code" value={d.last_post_deploy_reason_code ?? "—"} />
                <DetailField label="Created" value={fmtIsoLocal(d.created_at)} />
                <DetailField label="Updated" value={fmtIsoLocal(d.updated_at)} />
                <DetailField label="Last server observed" value={fmtIsoLocal(d.last_server_observed_at)} />
              </div>
            ) : null}

            {d && !detailLoading ? (
              <div className="mt-5 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                  Artifacts &amp; logs
                </p>
                <p className="mt-2 text-sm text-[var(--theme-muted-2)]">
                  No artifacts or full run logs are attached to this managed mission in HAM. The API stores bounded,
                  last-seen metadata only — not Cursor transcripts or artifact blobs.
                </p>
              </div>
            ) : null}

            {d?.cursor_agent_id?.trim() && !detailLoading ? (
              <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-[var(--theme-border)] pt-4">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="border border-[var(--theme-border)]"
                  disabled={!!syncAgentId}
                  onClick={() => void runSync(d.cursor_agent_id)}
                >
                  {syncAgentId === d.cursor_agent_id ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCw className="mr-1 h-3.5 w-3.5" />
                  )}
                  Sync from Cursor (server)
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
