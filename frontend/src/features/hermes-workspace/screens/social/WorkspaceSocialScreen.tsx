import * as React from "react";
import { AlertTriangle, CheckCircle2, Circle, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  socialAdapter,
  type SocialReactiveReplyApplyResponse,
  type SocialPreviewKind,
  type SocialPreviewResponse,
  type SocialProvider,
  type SocialSnapshot,
  type XCapabilities,
} from "../../adapters/socialAdapter";
import { WorkspaceSurfaceHeader, WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function statusTone(status: string): "ok" | "warn" | "danger" | "muted" {
  if (status === "active" || status === "ready") return "ok";
  if (status === "blocked") return "danger";
  if (status === "coming_soon") return "muted";
  return "warn";
}

function StatusPill({ label, tone = "muted" }: { label: string; tone?: "ok" | "warn" | "danger" | "muted" }) {
  const cls =
    tone === "ok"
      ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-100"
      : tone === "danger"
        ? "border-red-400/25 bg-red-500/10 text-red-100"
        : tone === "warn"
          ? "border-amber-400/25 bg-amber-500/10 text-amber-100"
          : "border-white/10 bg-white/[0.04] text-white/55";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", cls)}>
      {label}
    </span>
  );
}

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm">
      <span className="text-white/68">{label}</span>
      <StatusPill label={value ? "Yes" : "No"} tone={value ? "ok" : "muted"} />
    </div>
  );
}

function ProviderCard({ provider }: { provider: SocialProvider }) {
  const tone = statusTone(provider.status);
  return (
    <article className="rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-white/92">{provider.label}</div>
          <div className="mt-1 text-xs text-white/45">
            {provider.id === "x" ? "First provider, powered by the existing HAM-on-X engine." : "Future provider slot."}
          </div>
        </div>
        <StatusPill label={titleCase(provider.status)} tone={tone} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <StatusPill label={provider.configured ? "Configured" : "Not configured"} tone={provider.configured ? "ok" : "muted"} />
        {provider.coming_soon ? <StatusPill label="Coming soon" tone="muted" /> : <StatusPill label="Read-only" tone="ok" />}
        {provider.enabled_lanes.map((lane) => (
          <StatusPill key={lane} label={titleCase(lane)} tone="warn" />
        ))}
      </div>
    </article>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-black/25 p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-white/60">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function KeyValueGrid({ rows }: { rows: { label: string; value: React.ReactNode }[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {rows.map((row) => (
        <div key={row.label} className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/38">{row.label}</div>
          <div className="mt-1 break-words text-sm text-white/82">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

function RecordPreview({ record, emptyLabel }: { record: Record<string, unknown> | null; emptyLabel: string }) {
  if (!record) {
    return <p className="text-sm text-white/45">{emptyLabel}</p>;
  }
  return (
    <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/30 p-3 text-[11px] leading-relaxed text-white/70">
      {JSON.stringify(record, null, 2)}
    </pre>
  );
}

function CapabilityRows({ capabilities }: { capabilities: XCapabilities }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <BoolRow label="Live read available" value={capabilities.live_read_available} />
      <BoolRow label="Live model available" value={capabilities.live_model_available} />
      <BoolRow label="Broadcast dry-run available" value={capabilities.broadcast_dry_run_available} />
      <BoolRow label="Broadcast live configured" value={capabilities.broadcast_live_available} />
      <BoolRow label="Reactive inbox discovery" value={capabilities.reactive_inbox_discovery_available} />
      <BoolRow label="Reactive dry-run available" value={capabilities.reactive_dry_run_available} />
      <BoolRow label="Reactive reply canary" value={capabilities.reactive_reply_canary_available} />
      <BoolRow label="Reactive batch available" value={capabilities.reactive_batch_available} />
      <BoolRow label="Live apply available" value={capabilities.live_apply_available} />
      <BoolRow label="Read-only API" value={capabilities.read_only} />
    </div>
  );
}

function LoadingCards() {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div key={idx} className="h-32 animate-pulse rounded-2xl border border-white/10 bg-black/25" />
      ))}
    </div>
  );
}

const PREVIEW_LABELS: Record<SocialPreviewKind, string> = {
  reactive_inbox: "Reactive inbox discovery preview",
  reactive_batch_dry_run: "Reactive batch dry-run preview",
  broadcast_preflight: "Broadcast preflight preview",
};

const LIVE_REPLY_CONFIRMATION_PHRASE = "SEND ONE LIVE REPLY";

function PreviewResultCard({ preview }: { preview: SocialPreviewResponse }) {
  return (
    <section className="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white/85">{PREVIEW_LABELS[preview.preview_kind]}</h2>
          <p className="mt-1 text-xs text-white/48">Preview only. No live X write. No reply/post execution.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={titleCase(preview.status)} tone={preview.status === "completed" ? "ok" : "warn"} />
          <StatusPill label={preview.live_apply_available ? "Live apply available" : "Live apply unavailable"} tone={preview.live_apply_available ? "danger" : "ok"} />
          <StatusPill label={preview.execution_allowed ? "Execution allowed" : "Execution blocked"} tone={preview.execution_allowed ? "danger" : "ok"} />
        </div>
      </div>
      {preview.reasons.length || preview.warnings.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {preview.reasons.map((reason) => (
            <StatusPill key={`reason-${reason}`} label={titleCase(reason)} tone="warn" />
          ))}
          {preview.warnings.map((warning) => (
            <StatusPill key={`warning-${warning}`} label={titleCase(warning)} tone="muted" />
          ))}
        </div>
      ) : null}
      <div className="mt-3">
        <RecordPreview record={preview.result} emptyLabel="No preview result payload." />
      </div>
    </section>
  );
}

export function WorkspaceSocialScreen() {
  const [snapshot, setSnapshot] = React.useState<SocialSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = React.useState<SocialPreviewKind | null>(null);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [previews, setPreviews] = React.useState<Partial<Record<SocialPreviewKind, SocialPreviewResponse>>>({});
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [confirmText, setConfirmText] = React.useState("");
  const [operatorToken, setOperatorToken] = React.useState("");
  const [liveBusy, setLiveBusy] = React.useState(false);
  const [liveError, setLiveError] = React.useState<string | null>(null);
  const [liveResult, setLiveResult] = React.useState<SocialReactiveReplyApplyResponse | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const result = await socialAdapter.loadSnapshot();
    if (result.bridge.status === "pending") {
      setError(result.bridge.detail || result.error || "Social API unavailable.");
      setSnapshot(null);
    } else {
      setSnapshot(result.snapshot);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const runPreview = async (kind: SocialPreviewKind) => {
    setPreviewBusy(kind);
    setPreviewError(null);
    const result =
      kind === "reactive_inbox"
        ? await socialAdapter.previewInboxDiscovery()
        : kind === "reactive_batch_dry_run"
          ? await socialAdapter.previewReactiveBatchDryRun()
          : await socialAdapter.previewBroadcastPreflight();
    setPreviewBusy(null);
    if (result.bridge.status === "pending" || !result.preview) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setPreviewError(detail || "Preview API unavailable.");
      return;
    }
    setPreviews((prev) => ({ ...prev, [kind]: result.preview ?? undefined }));
  };

  const x = snapshot?.xStatus;
  const caps = snapshot?.xCapabilities;
  const inboxPreview = previews.reactive_inbox;
  const canSendOneLiveReply = Boolean(inboxPreview?.proposal_digest && caps?.reactive_reply_apply_available);

  const sendOneLiveReply = async () => {
    if (!inboxPreview?.proposal_digest) return;
    setLiveBusy(true);
    setLiveError(null);
    const result = await socialAdapter.sendOneLiveReply({
      proposalDigest: inboxPreview.proposal_digest,
      confirmationPhrase: confirmText,
      operatorToken,
      clientRequestId: `social-ui-${Date.now()}`,
    });
    setLiveBusy(false);
    if (result.bridge.status === "pending" || !result.apply) {
      const detail = result.bridge.status === "pending" ? result.bridge.detail : result.error;
      setLiveError(detail || "Live reply request failed.");
      return;
    }
    setLiveResult(result.apply);
    setConfirmOpen(false);
    setConfirmText("");
    setOperatorToken("");
    void load();
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-y-auto p-3 md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        eyebrow="Social"
        title="Social Command Center"
        subtitle="Read-only provider status for autonomous social agents. X is the first provider; future providers are placeholders."
        actions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 gap-1.5 border-white/15 bg-white/5 text-white/90"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      <WorkspaceSurfaceStateCard
        title="Read-only surface"
        description="Status panels call read-only GET /api/social endpoints. Preview controls call POST preview endpoints only; they do not run live X writes or reply/post execution."
        tone="neutral"
      />

      {error ? (
        <WorkspaceSurfaceStateCard
          title="Social API unavailable"
          description="The Social provider facade could not be loaded. Other workspace routes may still work."
          tone="amber"
          technicalDetail={error}
          primaryAction={
            <Button type="button" size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : null}

      {loading ? <LoadingCards /> : null}

      {!loading && snapshot ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {snapshot.providers.map((provider) => (
              <ProviderCard key={provider.id} provider={provider} />
            ))}
          </div>

          {x && caps ? (
            <div className="grid gap-4 xl:grid-cols-2">
              <Panel title="Preview controls">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Preview only. These controls produce dry-run result payloads and keep `execution_allowed=false`,
                    `mutation_attempted=false`, and `live_apply_available=false`.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="border-white/15 bg-white/5 text-white/90"
                      onClick={() => void runPreview("reactive_inbox")}
                      disabled={previewBusy !== null}
                    >
                      {previewBusy === "reactive_inbox" ? "Previewing..." : "Preview inbox discovery"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="border-white/15 bg-white/5 text-white/90"
                      onClick={() => void runPreview("reactive_batch_dry_run")}
                      disabled={previewBusy !== null}
                    >
                      {previewBusy === "reactive_batch_dry_run" ? "Previewing..." : "Preview reactive batch dry-run"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      className="border-white/15 bg-white/5 text-white/90"
                      onClick={() => void runPreview("broadcast_preflight")}
                      disabled={previewBusy !== null}
                    >
                      {previewBusy === "broadcast_preflight" ? "Previewing..." : "Preview broadcast preflight"}
                    </Button>
                  </div>
                  <p className="text-xs text-white/42">No live X write. No reply/post execution. Dry-run result only.</p>
                </div>
              </Panel>

              {previewError ? (
                <WorkspaceSurfaceStateCard
                  title="Preview API unavailable"
                  description="A preview request failed. Status panels may still be available."
                  tone="amber"
                  technicalDetail={previewError}
                />
              ) : null}

              {Object.entries(previews).map(([kind, preview]) =>
                preview ? <PreviewResultCard key={kind} preview={preview} /> : null,
              )}

              <Panel title="Confirmed live reply">
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed text-white/58">
                    Confirmed live action. This sends exactly one live X reply from the latest inbox preview. No batch. No retry.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill
                      label={inboxPreview?.proposal_digest ? "Preview digest present" : "Preview digest required"}
                      tone={inboxPreview?.proposal_digest ? "ok" : "warn"}
                    />
                    <StatusPill
                      label={caps.reactive_reply_apply_available ? "Operator apply available" : "Operator apply unavailable"}
                      tone={caps.reactive_reply_apply_available ? "ok" : "muted"}
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="bg-red-600 text-white hover:bg-red-500"
                    disabled={!canSendOneLiveReply}
                    onClick={() => {
                      setConfirmOpen(true);
                      setLiveError(null);
                    }}
                  >
                    Send one live reply
                  </Button>
                  {!canSendOneLiveReply ? (
                    <p className="text-xs text-white/42">
                      Run inbox discovery preview first, and ensure the API reports reactive reply apply availability.
                    </p>
                  ) : null}
                </div>
              </Panel>

              {liveError ? (
                <WorkspaceSurfaceStateCard
                  title="Live reply request blocked"
                  description="The confirmed one-shot live reply did not run."
                  tone="amber"
                  technicalDetail={liveError}
                />
              ) : null}

              {liveResult ? (
                <Panel title="Confirmed live reply result">
                  <RecordPreview record={liveResult as unknown as Record<string, unknown>} emptyLabel="No live result payload." />
                </Panel>
              ) : null}

              <Panel title="X readiness">
                <div className="mb-3 flex flex-wrap gap-2">
                  <StatusPill label={titleCase(x.overall_readiness)} tone={statusTone(x.overall_readiness)} />
                  <StatusPill label={x.read_only ? "Read-only" : "Writable"} tone={x.read_only ? "ok" : "danger"} />
                  <StatusPill
                    label={x.emergency_stop.enabled ? "Emergency stop on" : "Emergency stop off"}
                    tone={x.emergency_stop.enabled ? "danger" : "ok"}
                  />
                  <StatusPill
                    label={caps.live_apply_available ? "Live apply enabled" : "Live apply unavailable"}
                    tone={caps.live_apply_available ? "danger" : "ok"}
                  />
                </div>
                {x.readiness_reasons.length ? (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-white/60">
                    {x.readiness_reasons.map((reason) => (
                      <li key={reason}>{titleCase(reason)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-white/55">No readiness blockers reported.</p>
                )}
              </Panel>

              <Panel title="Capabilities">
                <CapabilityRows capabilities={caps} />
              </Panel>

              <Panel title="Dry-run defaults">
                <div className="grid gap-2 sm:grid-cols-2">
                  <BoolRow label="Global dry-run" value={x.dry_run_defaults.global_dry_run} />
                  <BoolRow label="Controller dry-run" value={x.dry_run_defaults.controller_dry_run} />
                  <BoolRow label="Reactive dry-run" value={x.dry_run_defaults.reactive_dry_run} />
                  <BoolRow label="Reactive batch dry-run" value={x.dry_run_defaults.reactive_batch_dry_run} />
                </div>
              </Panel>

              <Panel title="Broadcast lane">
                <KeyValueGrid
                  rows={[
                    { label: "Enabled", value: x.broadcast_lane.enabled ? "Yes" : "No" },
                    { label: "Controller", value: x.broadcast_lane.controller_enabled ? "Enabled" : "Disabled" },
                    { label: "Live controller", value: x.broadcast_lane.live_controller_enabled ? "Enabled" : "Disabled" },
                    { label: "Dry-run", value: x.broadcast_lane.dry_run_available ? "Available" : "Unavailable" },
                    { label: "Live configured", value: x.broadcast_lane.live_configured ? "Yes" : "No" },
                    { label: "Execution allowed now", value: x.broadcast_lane.execution_allowed_now ? "Yes" : "No" },
                  ]}
                />
                {x.broadcast_lane.reasons.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {x.broadcast_lane.reasons.map((reason) => (
                      <StatusPill key={reason} label={titleCase(reason)} tone="warn" />
                    ))}
                  </div>
                ) : null}
              </Panel>

              <Panel title="Reactive lane">
                <KeyValueGrid
                  rows={[
                    { label: "Enabled", value: x.reactive_lane.enabled ? "Yes" : "No" },
                    { label: "Inbox discovery", value: x.reactive_lane.inbox_discovery_enabled ? "Enabled" : "Disabled" },
                    { label: "Dry-run", value: x.reactive_lane.dry_run_enabled ? "Enabled" : "Disabled" },
                    { label: "Live canary", value: x.reactive_lane.live_canary_enabled ? "Enabled" : "Disabled" },
                    { label: "Batch", value: x.reactive_lane.batch_enabled ? "Enabled" : "Disabled" },
                  ]}
                />
                {x.reactive_lane.reasons.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {x.reactive_lane.reasons.map((reason) => (
                      <StatusPill key={reason} label={titleCase(reason)} tone="warn" />
                    ))}
                  </div>
                ) : null}
              </Panel>

              <Panel title="Caps and cooldowns">
                <KeyValueGrid
                  rows={[
                    { label: "Broadcast daily", value: `${x.cap_cooldown_summary.broadcast_daily_used}/${x.cap_cooldown_summary.broadcast_daily_cap}` },
                    { label: "Broadcast remaining", value: x.cap_cooldown_summary.broadcast_daily_remaining },
                    { label: "Broadcast per run", value: x.cap_cooldown_summary.broadcast_per_run_cap },
                    { label: "Broadcast spacing", value: `${x.cap_cooldown_summary.broadcast_min_spacing_minutes} min` },
                    { label: "Reactive 15m cap", value: x.cap_cooldown_summary.reactive_max_replies_per_15m },
                    { label: "Reactive hourly cap", value: x.cap_cooldown_summary.reactive_max_replies_per_hour },
                    { label: "Reactive per user/day", value: x.cap_cooldown_summary.reactive_max_replies_per_user_per_day },
                    { label: "Reactive per thread/day", value: x.cap_cooldown_summary.reactive_max_replies_per_thread_per_day },
                    { label: "Reactive cooldown", value: `${x.cap_cooldown_summary.reactive_min_seconds_between_replies}s` },
                    { label: "Reactive batch/run", value: x.cap_cooldown_summary.reactive_batch_max_replies_per_run },
                  ]}
                />
              </Panel>

              <Panel title="Last autonomous post">
                <RecordPreview record={x.last_autonomous_post} emptyLabel="No autonomous post found in the bounded journal summary." />
              </Panel>

              <Panel title="Last reactive reply">
                <RecordPreview record={x.last_reactive_reply} emptyLabel="No reactive reply found in the bounded journal summary." />
              </Panel>

              <Panel title="Setup checklist">
                <div className="space-y-2">
                  {snapshot.xSetup.items.map((item) => (
                    <div key={item.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        {item.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}
                        {item.label}
                      </div>
                      <StatusPill label={item.ok ? "OK" : "Missing"} tone={item.ok ? "ok" : "warn"} />
                    </div>
                  ))}
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {Object.entries(snapshot.xSetup.feature_flags).map(([key, value]) => (
                    <BoolRow key={key} label={titleCase(key)} value={value} />
                  ))}
                </div>
              </Panel>

              <Panel title="Journal summary">
                <KeyValueGrid
                  rows={[
                    { label: "Path", value: snapshot.xJournal.journal_path },
                    { label: "Rows scanned", value: snapshot.xJournal.total_count_scanned },
                    { label: "Malformed", value: snapshot.xJournal.malformed_count },
                    { label: "Recent cap", value: snapshot.xJournal.bounds.max_recent_items },
                  ]}
                />
                <div className="mt-3">
                  <RecordPreview record={snapshot.xJournal.counts_by_execution_kind} emptyLabel="No journal counts yet." />
                </div>
                <div className="mt-3 space-y-2">
                  {snapshot.xJournal.recent_items.length ? (
                    snapshot.xJournal.recent_items.map((item, idx) => (
                      <RecordPreview key={idx} record={item} emptyLabel="No journal record." />
                    ))
                  ) : (
                    <p className="text-sm text-white/45">No recent journal items.</p>
                  )}
                </div>
              </Panel>

              <Panel title="Audit summary">
                <KeyValueGrid
                  rows={[
                    { label: "Path", value: snapshot.xAudit.audit_path },
                    { label: "Rows scanned", value: snapshot.xAudit.total_count_scanned },
                    { label: "Malformed", value: snapshot.xAudit.malformed_count },
                    { label: "Recent cap", value: snapshot.xAudit.bounds.max_recent_events },
                  ]}
                />
                <div className="mt-3">
                  <RecordPreview record={snapshot.xAudit.counts_by_event_type} emptyLabel="No audit counts yet." />
                </div>
                {snapshot.xAudit.latest_audit_ids.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {snapshot.xAudit.latest_audit_ids.map((id) => (
                      <StatusPill key={id} label={id} tone="muted" />
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 space-y-2">
                  {snapshot.xAudit.recent_events.length ? (
                    snapshot.xAudit.recent_events.map((event, idx) => (
                      <RecordPreview key={idx} record={event} emptyLabel="No audit event." />
                    ))
                  ) : (
                    <p className="text-sm text-white/45">No recent audit events.</p>
                  )}
                </div>
              </Panel>

              <Panel title="Safety boundary">
                <div className="space-y-2 text-sm text-white/62">
                  <p className="flex gap-2">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                    Frontend uses `hamApiFetch` against read-only `GET /api/social` endpoints only.
                  </p>
                  <p className="flex gap-2">
                    <Circle className="mt-1 h-3 w-3 shrink-0 text-white/40" />
                    Live posting, replies, batch execution, and apply buttons are intentionally absent from this MVP.
                  </p>
                </div>
              </Panel>
            </div>
          ) : null}
        </>
      ) : null}

      {confirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="social-live-reply-title"
            className="w-full max-w-lg rounded-2xl border border-red-400/30 bg-[#071016] p-5 text-white shadow-2xl"
          >
            <h2 id="social-live-reply-title" className="text-lg font-semibold">
              Confirmed live X reply
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-white/65">
              This sends exactly one live reply. No batch. No retry.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Type confirmation phrase
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  value={confirmText}
                  onChange={(event) => setConfirmText(event.target.value)}
                  placeholder={LIVE_REPLY_CONFIRMATION_PHRASE}
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                Operator token
                <input
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-300/50"
                  type="password"
                  value={operatorToken}
                  onChange={(event) => setOperatorToken(event.target.value)}
                  placeholder="HAM_SOCIAL_LIVE_APPLY_TOKEN"
                />
              </label>
              <p className="text-xs text-white/40">
                The frontend sends only the proposal digest, confirmation phrase, and operator token. It never sends reply text.
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setConfirmOpen(false);
                  setConfirmText("");
                  setOperatorToken("");
                }}
                disabled={liveBusy}
              >
                Cancel
              </Button>
              <Button
                type="button"
                className="bg-red-600 text-white hover:bg-red-500"
                onClick={() => void sendOneLiveReply()}
                disabled={liveBusy || confirmText !== LIVE_REPLY_CONFIRMATION_PHRASE || !operatorToken.trim()}
              >
                {liveBusy ? "Sending one live reply..." : "Send one live reply"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
