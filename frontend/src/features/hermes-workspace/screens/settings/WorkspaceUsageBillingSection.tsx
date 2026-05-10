/**
 * Workspace Settings — Usage & Billing (UI-first).
 * Billing/credits metering is stubbed honestly; no new backend endpoints.
 */
import * as React from "react";
import { CalendarClock, HelpCircle, Info, Sparkles, SquareStack } from "lucide-react";

import { cn } from "@/lib/utils";

type UsageCategoryTabId = "tasks" | "apps" | "computers";

const TABS: ReadonlyArray<{ id: UsageCategoryTabId; label: string }> = [
  { id: "tasks", label: "Tasks" },
  { id: "apps", label: "Apps" },
  { id: "computers", label: "Computers" },
];

const BILLING_DISABLED_TITLE = "Billing is not connected in this build yet.";

function StubStat({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <div
      className="rounded-xl border border-white/[0.06] bg-black/22 px-3 py-3"
      role="region"
      aria-label={title}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/42">{title}</p>
      <p className="mt-2 text-[16px] font-semibold tracking-tight text-white/82">{value}</p>
      <p className="mt-1.5 text-[11px] leading-snug text-white/45">{subtitle}</p>
    </div>
  );
}

export function WorkspaceUsageBillingSection() {
  const [tab, setTab] = React.useState<UsageCategoryTabId>("tasks");

  let categoryGrid: React.ReactNode;
  switch (tab) {
    case "tasks":
      categoryGrid = (
        <div className="grid gap-3 sm:grid-cols-3" data-testid="hww-usage-tab-panel-tasks">
          <StubStat
            title="Agent runs"
            value="Not metered yet"
            subtitle="Hermes-managed runs and audits will summarize here once the usage ledger connects."
          />
          <StubStat
            title="Model calls"
            value="Not metered yet"
            subtitle="Inbound chat and routing calls remain with your configured providers."
          />
          <StubStat
            title="Estimated usage cost"
            value="Usage ledger coming soon"
            subtitle="No autopilot billing or synthesized invoices in HAM OSS yet."
          />
        </div>
      );
      break;
    case "apps":
      categoryGrid = (
        <div className="grid gap-3 sm:grid-cols-3" data-testid="hww-usage-tab-panel-apps">
          <StubStat
            title="Preview runtime"
            value="Not connected"
            subtitle="Hosted preview metering is outside this dashboard until wired."
          />
          <StubStat
            title="Builds / publishes"
            value="Not connected"
            subtitle="Deploy pipelines report usage from your CI host — not surfaced here yet."
          />
          <StubStat
            title="App storage"
            value="Coming soon"
            subtitle="Artifacts and blobs will map to infra meters when available."
          />
        </div>
      );
      break;
    case "computers":
      categoryGrid = (
        <div className="grid gap-3 sm:grid-cols-3" data-testid="hww-usage-tab-panel-computers">
          <StubStat
            title="Local runtime"
            value="Local-only when connected"
            subtitle="HAM local control bridges your machine — no cloud computer charges in this UI."
          />
          <StubStat
            title="Cloud computers"
            value="Coming soon"
            subtitle="Optional pooled runtime is roadmap-only; avoid implying live seats."
          />
          <StubStat
            title="Terminal sessions"
            value="Not metered"
            subtitle="TTY usage is diagnostic-only today."
          />
        </div>
      );
      break;
    default:
      categoryGrid = null;
  }

  return (
    <div className="space-y-8 pb-8" data-testid="hww-usage-billing-root">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight text-[#e8eef8] md:text-2xl">
          Usage &amp; Billing
        </h1>
        <p className="max-w-xl text-[13px] leading-relaxed text-white/52">
          Track workspace usage, credits, and upcoming metering surfaces.
        </p>
      </header>

      <div aria-label="Usage categories" role="tablist">
        <div className="flex flex-wrap gap-1 border-b border-white/[0.08]">
          {TABS.map(({ id, label }) => {
            const active = tab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                id={`hww-usage-tab-${id}`}
                aria-selected={active}
                data-testid={`hww-usage-tab-${id}`}
                tabIndex={active ? 0 : -1}
                onClick={() => setTab(id)}
                className={cn(
                  "relative px-3 pb-3 pt-2 text-[13px] font-medium transition-colors outline-none",
                  "focus-visible:z-[1] focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-emerald-400/35",
                  active ? "text-[#e8eef8]" : "text-white/45 hover:text-white/78",
                )}
              >
                {label}
                {active ? (
                  <span
                    aria-hidden
                    className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full bg-emerald-400/80"
                  />
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <div
        role="tabpanel"
        aria-labelledby={`hww-usage-tab-${tab}`}
        id={`hww-usage-panel-${tab}`}
        className="space-y-6"
      >
        <section className="rounded-2xl border border-white/[0.08] bg-[#040d14]/75 p-5 shadow-inner shadow-black/20">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-dashed border-white/[0.08] pb-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-[16px] font-semibold text-[#e8eef8]">HAM Preview</h2>
                <span className="rounded-full border border-amber-500/35 bg-amber-500/[0.12] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-100/92">
                  Preview
                </span>
              </div>
              <p className="mt-1.5 flex items-center gap-1 text-[12px] text-white/42">
                <CalendarClock className="h-3.5 w-3.5 text-white/35" aria-hidden />
                Renewal / billing cadence · not configured yet
              </p>
              <p className="mt-3 text-[12px] text-white/50">
                HAM OSS does not host paid plans in this dashboard. Stripe and subscription state
                would appear here once connected.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled
                title={BILLING_DISABLED_TITLE}
                aria-label={`Manage (${BILLING_DISABLED_TITLE})`}
                className="inline-flex cursor-not-allowed items-center gap-1 rounded-full border border-white/[0.1] bg-white/[0.04] px-3 py-2 text-[12px] font-semibold text-white/35 outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30"
              >
                Manage
                <span className="text-[10px] font-medium text-white/32">Soon</span>
              </button>
              <button
                type="button"
                disabled
                title={BILLING_DISABLED_TITLE}
                aria-label={`Upgrade (${BILLING_DISABLED_TITLE})`}
                className="cursor-not-allowed rounded-full border border-emerald-500/35 bg-emerald-500/[0.1] px-4 py-2 text-[12px] font-semibold text-emerald-100/65 outline-none opacity-65 focus-visible:ring-2 focus-visible:ring-emerald-400/30"
              >
                Upgrade
              </button>
            </div>
          </div>

          <div className="mt-5 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-white/[0.05] pb-4">
              <div className="flex items-center gap-2 text-[13px] font-medium text-white/82">
                <Sparkles className="h-4 w-4 text-emerald-300/85" aria-hidden />
                Credits
                <span
                  className="inline-flex shrink-0 text-white/38"
                  title="Credits are placeholders until a usage ledger is connected."
                >
                  <HelpCircle className="h-3.5 w-3.5" aria-hidden />
                </span>
              </div>
              <span className="text-[13px] font-semibold tabular-nums text-white/82">Not metered</span>
              <div className="basis-full pt-3 text-[11px] text-white/45">
                Usage ledger is not connected in this build — no pooled HAM credits to spend.
              </div>
              <dl className="basis-full mt-4 space-y-2 border-t border-dashed border-white/[0.08] pt-4 text-[12px]">
                <div className="flex flex-wrap justify-between gap-3">
                  <dt className="text-white/40">Monthly included usage</dt>
                  <dd className="font-medium text-white/82">Coming soon</dd>
                </div>
                <p className="text-[11px] text-white/42">
                  Intended to summarize included agent / model / runtime allowances once policies
                  exist.
                </p>
                <div className="flex flex-wrap items-start justify-between gap-3 pt-2">
                  <dt className="flex items-center gap-1 text-white/40">
                    <CalendarClock className="h-3.5 w-3.5 text-white/32" aria-hidden />
                    Daily refresh credits
                  </dt>
                  <dd className="font-medium text-white/82">Not configured</dd>
                </div>
                <p className="text-[11px] text-white/42">
                  Policy-driven daily refresh bowls are roadmap-only; no midnight auto top-ups wired.
                </p>
              </dl>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] pb-2">
            <h3 className="text-[14px] font-semibold text-white/85">Usage history</h3>
            <span className="inline-flex items-center gap-1 text-[11px] text-white/38">
              <HelpCircle className="h-3.5 w-3.5" aria-hidden /> Ledger offline
            </span>
          </div>
          <div
            data-testid="hww-usage-history-empty"
            className="rounded-xl border border-dashed border-white/[0.1] bg-black/18 px-4 py-8 text-center"
          >
            <Info className="mx-auto mb-3 h-6 w-6 text-white/22" aria-hidden />
            <p className="text-[14px] font-medium text-white/78">No usage events yet.</p>
            <p className="mx-auto mt-2 max-w-md text-[12px] leading-relaxed text-white/45">
              Once metering connects, agent tasks, vendor model calls, local or cloud runtime, app
              builds, ingestion, and credit adjustments could stream here — today the ledger is idle.
            </p>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-2 border-b border-white/[0.06] pb-2">
            <SquareStack className="h-4 w-4 text-white/42" aria-hidden />
            <h3 className="text-[13px] font-semibold text-white/85">Signals for this category</h3>
          </div>
          {categoryGrid}
          <p className="text-[11px] text-white/36">
            Category summaries are scaffolding only — not live billing totals.
          </p>
        </section>
      </div>
    </div>
  );
}
