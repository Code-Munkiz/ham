import * as React from "react";
import {
  socialAdapter,
  type LearningHints,
  type ReviewQueueSummary,
  type SocialSnapshot,
} from "../../adapters/socialAdapter";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";

type ChannelLabel = "Preview only" | "Review required" | "Live controls armed" | "Not available";

type ChannelRow = {
  id: "x" | "telegram" | "discord";
  name: string;
  label: ChannelLabel;
};

function deriveChannelLabel(
  channel: "x" | "telegram" | "discord",
  snapshot: SocialSnapshot | null,
): ChannelLabel {
  if (channel === "discord") return "Not available";
  if (!snapshot) return "Preview only";
  if (channel === "x") {
    const live = snapshot.xCapabilities?.live_apply_available === true;
    const reactiveApply = snapshot.xCapabilities?.reactive_reply_apply_available === true;
    if (live) return "Live controls armed";
    if (reactiveApply) return "Review required";
    return "Preview only";
  }
  const liveTg = snapshot.telegramCapabilities?.live_apply_available === true;
  if (liveTg) return "Live controls armed";
  return "Preview only";
}

export function WorkspaceHamgomoonScreen() {
  const [summary, setSummary] = React.useState<ReviewQueueSummary | null>(null);
  const [hints, setHints] = React.useState<LearningHints | null>(null);
  const [snapshot, setSnapshot] = React.useState<SocialSnapshot | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [reviewRes, hintsRes, snapRes] = await Promise.all([
      socialAdapter.getReviewQueueSummary({ limit: 5 }),
      socialAdapter.getLearningHints({ channel: "x" }),
      socialAdapter.loadSnapshot(),
    ]);
    setSummary(reviewRes.summary);
    setHints(hintsRes.hints);
    setSnapshot(snapRes.snapshot);
    const firstError = reviewRes.error ?? hintsRes.error ?? snapRes.error ?? null;
    if (firstError) setError(firstError);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const channels: ChannelRow[] = [
    { id: "x", name: "X", label: deriveChannelLabel("x", snapshot) },
    { id: "telegram", name: "Telegram", label: deriveChannelLabel("telegram", snapshot) },
    { id: "discord", name: "Discord", label: deriveChannelLabel("discord", snapshot) },
  ];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-y-auto p-3 md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        eyebrow="HAMgomoon"
        title="HAMgomoon"
        subtitle="Preview drafts. Review. Learn."
      />
      {error ? (
        <WorkspaceSurfaceStateCard
          tone="amber"
          title="HAMgomoon is having trouble loading"
          description={error}
        />
      ) : null}

      <section
        aria-label="Drafts to review"
        className="rounded-lg border border-white/10 bg-white/[0.03] p-4"
      >
        <h2 className="mb-2 text-sm font-semibold text-white/90">Drafts to review</h2>
        {loading ? (
          <p className="text-sm text-white/60">Loading…</p>
        ) : !summary || summary.pending_count === 0 ? (
          <p className="text-sm text-white/70">Nothing waiting on you right now.</p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-white/80">
              {summary.pending_count} draft{summary.pending_count === 1 ? "" : "s"} waiting.
            </p>
            <ul className="flex flex-col gap-2">
              {summary.items.slice(0, 5).map((item) => (
                <li
                  key={item.record_id}
                  className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/85"
                >
                  <div className="text-xs uppercase tracking-wide text-white/50">
                    {item.action_type ?? "draft"}
                    {item.channel ? ` · ${item.channel}` : ""}
                  </div>
                  <div className="mt-1 line-clamp-2 break-words">
                    {item.text || "(no preview text)"}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section
        aria-label="What HAMgomoon learned"
        className="rounded-lg border border-white/10 bg-white/[0.03] p-4"
      >
        <h2 className="mb-2 text-sm font-semibold text-white/90">What HAMgomoon learned</h2>
        {loading ? (
          <p className="text-sm text-white/60">Loading…</p>
        ) : !hints || !hints.hints || /no learning hints yet/i.test(hints.hints) ? (
          <p className="text-sm text-white/70">HAMgomoon is just getting started.</p>
        ) : (
          <pre className="whitespace-pre-wrap break-words text-sm text-white/85">{hints.hints}</pre>
        )}
      </section>

      <section
        aria-label="Channels"
        className="rounded-lg border border-white/10 bg-white/[0.03] p-4"
      >
        <h2 className="mb-2 text-sm font-semibold text-white/90">Channels</h2>
        <ul className="flex flex-col gap-2">
          {channels.map((row) => (
            <li
              key={row.id}
              className="flex items-center justify-between gap-3 rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm"
            >
              <span className="text-white/90">{row.name}</span>
              <span className="text-white/70">{row.label}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default WorkspaceHamgomoonScreen;
