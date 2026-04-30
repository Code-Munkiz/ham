import * as React from "react";
import { Link } from "react-router-dom";
import { Cloud, Loader2, MessageSquare, RefreshCw, RotateCw, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  cancelManagedMission,
  fetchManagedMissionDetail,
  fetchManagedMissions,
  syncManagedMissionByAgentId,
  type ManagedMissionLifecycle,
  type ManagedMissionSnapshot,
} from "../adapters/managedMissionsAdapter";
import { useManagedMissionFeedLiveStream } from "../hooks/useManagedMissionFeedLiveStream";
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

function shortId(id: string | null | undefined) {
  const s = String(id || "").trim();
  if (!s) return "—";
  if (s.length <= 16) return s;
  return `${s.slice(0, 8)}…${s.slice(-6)}`;
}

function missionTitle(m: ManagedMissionSnapshot) {
  return m.title?.trim() || m.task_summary?.trim() || "Cloud Agent mission";
}

function missionCheckpointLabel(m: ManagedMissionSnapshot) {
  return m.latest_checkpoint || m.cursor_status_last_observed || "Waiting for agent updates";
}

function providerLabel(m: ManagedMissionSnapshot) {
  return m.provider === "cursor" ? "Cursor" : "Cloud Agent";
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
  const [cancelMissionId, setCancelMissionId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [selectedMissionId, setSelectedMissionId] = React.useState<string | null>(null);

  const {
    feed: selectedFeed,
    initialLoading: selectedFeedInitialLoading,
    refetch: refetchSelectedFeed,
    banner: selectedFeedBanner,
    feedScrollAnchorRef,
  } = useManagedMissionFeedLiveStream(selectedMissionId, { refreshSignal });

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
    if (!missions.length) {
      setSelectedMissionId(null);
      return;
    }
    if (!selectedMissionId || !missions.some((m) => m.mission_registry_id === selectedMissionId)) {
      setSelectedMissionId(missions[0].mission_registry_id);
    }
  }, [missions, selectedMissionId]);

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
    await refetchSelectedFeed();
    if (r.mission) {
      setDetailMission((cur) => {
        if (!cur) return cur;
        return cur.mission_registry_id === r.mission?.mission_registry_id ? r.mission! : cur;
      });
    }
  };

  const runCancel = async (missionRegistryId: string) => {
    const mid = missionRegistryId.trim();
    if (!mid) return;
    setActionError(null);
    setCancelMissionId(mid);
    const r = await cancelManagedMission(mid);
    setCancelMissionId(null);
    if (r.error) {
      setActionError(r.error);
      return;
    }
    if (!r.ok) {
      setActionError(r.reasonCode === "cancel_not_supported" ? "Stop is not supported for this provider yet." : (r.reasonCode || "Stop request was not accepted."));
    }
    await load();
    await refetchSelectedFeed();
  };

  const title = "Live Cloud Agent missions";
  const subtitle =
    variant === "operations"
      ? "Mission control for work HAM launched. Track progress, outputs, and next actions."
      : "Live mission control for Cloud Agent runs launched by HAM.";

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
          <p className="font-medium text-[var(--theme-text)]">No Cloud Agent missions yet</p>
          <p className="mt-2">Launch a mission from Chat or Conductor and it will appear here with live progress.</p>
        </div>
      ) : null}

      {!error && missions.length > 0 ? (
        <div className="mt-4 hww-scroll max-h-[min(420px,50vh)] overflow-auto rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead className="sticky top-0 z-[1] border-b border-[var(--theme-border)] bg-[var(--theme-card)]">
              <tr className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Mission</th>
                <th className="px-3 py-2">Repo / ref</th>
                <th className="px-3 py-2">Agent</th>
                <th className="px-3 py-2 text-right">Updated</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => {
                const repo = [m.repository_observed, m.ref_observed].filter(Boolean).join(" @ ") || "—";
                const agentOk = Boolean(m.cursor_agent_id?.trim());
                const rowBusy = syncAgentId === m.cursor_agent_id;
                const rowCancelBusy = cancelMissionId === m.mission_registry_id;
                return (
                  <tr
                    key={m.mission_registry_id}
                    className={cn(
                      "border-b border-[var(--theme-border)]/80 last:border-b-0",
                      selectedMissionId === m.mission_registry_id && "bg-[var(--theme-card)]/60",
                    )}
                    onClick={() => setSelectedMissionId(m.mission_registry_id)}
                  >
                    <td className="px-3 py-2 align-top">{lifecyclePill(m.mission_lifecycle)}</td>
                    <td className="max-w-[240px] px-3 py-2 align-top">
                      <p className="line-clamp-1 text-sm font-medium text-[var(--theme-text)]">{missionTitle(m)}</p>
                      <p className="mt-1 line-clamp-1 text-xs text-[var(--theme-muted)]">
                        {providerLabel(m)} · {missionCheckpointLabel(m)}
                      </p>
                    </td>
                    <td className="max-w-[220px] px-3 py-2 align-top text-xs text-[var(--theme-muted)]">
                      <span className="line-clamp-2">{repo}</span>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <p className="font-mono text-[11px] text-[var(--theme-text)]">{shortId(m.cursor_agent_id)}</p>
                      <p className="mt-1 font-mono text-[10px] text-[var(--theme-muted)]">{shortId(m.mission_registry_id)}</p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 align-top text-right text-xs text-[var(--theme-muted-2)]">
                      {formatRelativeIso(m.last_server_observed_at || m.updated_at, now)}
                    </td>
                    <td className="px-3 py-2 align-top text-right">
                      <div className="flex flex-wrap items-center justify-end gap-1">
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
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="h-7 border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-[11px]"
                          disabled={!!rowCancelBusy}
                          title="Request stop"
                          onClick={() => void runCancel(m.mission_registry_id)}
                        >
                          {rowCancelBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />}
                          Stop
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="h-7 border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-[11px]"
                          asChild
                        >
                          <Link to={`/workspace/chat?mission_id=${encodeURIComponent(m.mission_registry_id)}`}>
                            <MessageSquare className="h-3 w-3" />
                            Open in Chat
                          </Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {!error && missions.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Live mission feed</p>
            {selectedMissionId ? (
              <span className="font-mono text-[10px] text-[var(--theme-muted-2)]">{shortId(selectedMissionId)}</span>
            ) : null}
          </div>
          {selectedFeedBanner.phase !== "idle" && selectedFeedBanner.label ? (
            <p className="mt-2 text-[10px] leading-snug text-[var(--theme-muted-2)]">{selectedFeedBanner.label}</p>
          ) : selectedFeed?.provider_projection?.mode === "rest_projection" ? (
            <p className="mt-2 text-[10px] text-[var(--theme-muted-2)]">
              Provider updates via REST refresh. Native provider realtime stream is unavailable in this integration.
            </p>
          ) : null}
          <div className="mt-2 max-h-[min(320px,40vh)] space-y-2 overflow-auto">
            {selectedFeedInitialLoading && !(selectedFeed?.events || []).length ? (
              <p className="text-sm text-[var(--theme-muted)]">Loading mission feed…</p>
            ) : (selectedFeed?.events || []).length > 0 ? (
              <>
                {(selectedFeed?.events || []).slice(-8).map((ev) => (
                  <div key={`${ev.id}-${ev.time}`} className="rounded-lg border border-[var(--theme-border)]/80 bg-[var(--theme-card)] px-3 py-2">
                    <p className="text-sm text-[var(--theme-text)]">{ev.message}</p>
                    <p className="mt-1 text-xs text-[var(--theme-muted)]">
                      {fmtIsoLocal(ev.time)} · {ev.source}
                      {ev.reason_code ? ` · ${ev.reason_code}` : ""}
                    </p>
                  </div>
                ))}
                <div ref={feedScrollAnchorRef} className="h-px w-full shrink-0" aria-hidden />
              </>
            ) : (
              <p className="text-sm text-[var(--theme-muted-2)]">Waiting for agent progress…</p>
            )}
          </div>
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
            className="hww-scroll max-h-[min(90vh,760px)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--theme-border)] bg-[color-mix(in_srgb,var(--theme-card)_80%,#05070d)] p-5 shadow-[0_30px_90px_rgba(0,0,0,0.55)]"
            style={{ color: "var(--theme-text)" }}
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 id="managed-mission-detail-title" className="text-base font-semibold text-[var(--theme-text)]">
                Mission details
              </h3>
              <Button type="button" size="sm" variant="ghost" className="h-8 px-2 text-[var(--theme-muted)]" onClick={closeDetail}>
                Close
              </Button>
            </div>
            <p className="mt-1 text-xs text-[var(--theme-muted-2)]">Review mission progress, outputs, and technical metadata.</p>

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
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Summary</p>
                  <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <DetailField label="Status" value={lifecyclePill(d.mission_lifecycle)} />
                    <DetailField label="Provider" value={providerLabel(d)} />
                    <DetailField label="Mission" value={missionTitle(d)} />
                    <DetailField label="Latest checkpoint" value={missionCheckpointLabel(d)} />
                    <DetailField label="Repo / ref" value={[d.repository_observed, d.ref_observed].filter(Boolean).join(" @ ") || "—"} />
                    <DetailField label="Updated" value={fmtIsoLocal(d.last_server_observed_at || d.updated_at)} />
                    <DetailField label="Mission id" value={d.mission_registry_id} mono />
                    <DetailField label="Agent id" value={d.cursor_agent_id} mono />
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Progress</p>
                  <div className="mt-2 space-y-2">
                    {(d.progress_events || []).length === 0 ? (
                      <p className="text-sm text-[var(--theme-muted-2)]">
                        {d.mission_lifecycle === "open"
                          ? "Waiting for the agent to report progress…"
                          : "No progress updates were recorded for this mission."}
                      </p>
                    ) : (
                      (d.progress_events || []).map((ev, idx) => (
                        <div key={`${ev.at || "na"}-${ev.label || "progress"}-${idx}`} className="rounded-lg border border-[var(--theme-border)]/80 bg-[var(--theme-card)] px-3 py-2">
                          <p className="text-sm text-[var(--theme-text)]">{ev.label || "Progress update"}</p>
                          <p className="mt-1 text-xs text-[var(--theme-muted)]">
                            {fmtIsoLocal(ev.at || null)}
                            {ev.value ? ` · ${ev.value}` : ""}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">Outputs and artifacts</p>
                  <div className="mt-2 space-y-2">
                    {d.outputs_available && (d.artifacts || []).length > 0 ? (
                      (d.artifacts || []).map((a, idx) => (
                        <div key={`${a.kind || "artifact"}-${idx}`} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--theme-border)]/80 bg-[var(--theme-card)] px-3 py-2">
                          <div>
                            <p className="text-sm text-[var(--theme-text)]">{a.title || "Artifact"}</p>
                            <p className="text-xs text-[var(--theme-muted)]">{a.kind || "output"}</p>
                          </div>
                          {a.url ? (
                            <Button type="button" size="sm" variant="secondary" className="h-7 border border-[var(--theme-border)] px-2 text-[11px]" asChild>
                              <a href={a.url} target="_blank" rel="noreferrer">
                                Open
                              </a>
                            </Button>
                          ) : null}
                        </div>
                      ))
                    ) : d.mission_lifecycle === "open" ? (
                      <p className="text-sm text-[var(--theme-muted-2)]">Waiting for the agent to report outputs…</p>
                    ) : d.mission_lifecycle === "failed" ? (
                      <p className="text-sm text-[var(--theme-muted-2)]">
                        Mission failed{d.error_summary ? `: ${d.error_summary}` : "."}
                      </p>
                    ) : d.mission_lifecycle === "succeeded" ? (
                      <p className="text-sm text-[var(--theme-muted-2)]">Mission completed, but no output artifacts were reported.</p>
                    ) : (
                      <p className="text-sm text-[var(--theme-muted-2)]">No outputs yet.</p>
                    )}
                  </div>
                </div>

                <details className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                  <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--theme-muted)]">
                    Technical details
                  </summary>
                  <div className="mt-2 space-y-1">
                    <DetailField label="Managed by" value={d.mission_handling === "managed" ? "HAM (managed)" : "HAM"} />
                    <DetailField label="Deploy approval mode" value={d.mission_deploy_approval_mode ?? "—"} />
                    <DetailField label="Control plane run id" value={d.control_plane_ham_run_id ?? "—"} mono />
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
                </details>
              </div>
            ) : null}

            {d?.cursor_agent_id?.trim() && !detailLoading ? (
              <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-[var(--theme-border)] pt-4">
                <Button type="button" size="sm" variant="secondary" className="border border-[var(--theme-border)]" asChild>
                  <Link to={`/workspace/chat?mission_id=${encodeURIComponent(d.mission_registry_id)}`}>
                    <MessageSquare className="mr-1 h-3.5 w-3.5" />
                    Open in Chat
                  </Link>
                </Button>
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
                  Sync mission
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="border border-[var(--theme-border)]"
                  disabled={cancelMissionId === d.mission_registry_id}
                  title="Request stop"
                  onClick={() => void runCancel(d.mission_registry_id)}
                >
                  {cancelMissionId === d.mission_registry_id ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Square className="mr-1 h-3.5 w-3.5" />
                  )}
                  Stop mission
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
