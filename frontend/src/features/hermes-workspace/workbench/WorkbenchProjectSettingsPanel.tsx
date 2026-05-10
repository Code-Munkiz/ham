/**
 * Project-aware settings surface embedded in the chat workbench right pane.
 * Tool / provider credentials reuse the same API routes as Workspace Settings; `project_id` is
 * passed through deep links only (backend isolation for tools remains account-scoped today).
 */
import * as React from "react";
import { Link } from "react-router-dom";
import {
  Cpu,
  CreditCard,
  GitBranch,
  Globe,
  KeyRound,
  Monitor,
  Puzzle,
  Sparkles,
} from "lucide-react";
import { DesktopBundlePanel } from "@/components/settings/DesktopBundlePanel";
import {
  ApiKeysPanel,
  ContextAndMemoryPanel,
  EnvironmentReadonlyPanel,
} from "@/components/workspace/UnifiedSettings";
import { cn } from "@/lib/utils";
import { WorkspaceConnectedToolsSection } from "../screens/settings/WorkspaceConnectedToolsSection";

export type WorkbenchSettingsSectionId =
  | "general"
  | "models"
  | "secrets"
  | "github"
  | "integrations"
  | "payment"
  | "domains"
  | "usage";

const NAV_ITEMS: ReadonlyArray<{
  id: WorkbenchSettingsSectionId;
  label: string;
  icon: typeof Monitor;
}> = [
  { id: "general", label: "General", icon: Monitor },
  { id: "models", label: "Model & keys", icon: Cpu },
  { id: "secrets", label: "Secrets", icon: KeyRound },
  { id: "github", label: "GitHub", icon: GitBranch },
  { id: "integrations", label: "Integrations", icon: Puzzle },
  { id: "payment", label: "Payment", icon: CreditCard },
  { id: "domains", label: "Domains", icon: Globe },
  { id: "usage", label: "Usage", icon: Sparkles },
];

function fullSettingsHref(section: string, projectId: string | null): string {
  const params = new URLSearchParams({ section });
  const id = projectId?.trim();
  if (id) params.set("project_id", id);
  return `/workspace/settings?${params.toString()}`;
}

export type WorkbenchProjectSettingsPanelProps = {
  /** Active HAM project id from chat routing (workspace context key). */
  projectId?: string | null;
};

export function WorkbenchProjectSettingsPanel({
  projectId = null,
}: WorkbenchProjectSettingsPanelProps) {
  const [active, setActive] = React.useState<WorkbenchSettingsSectionId>("models");

  const projectSummary = React.useMemo(() => {
    const id = projectId?.trim();
    if (!id) {
      return "No project pinned for this chat tab — prompts still use Workspace Settings on your account.";
    }
    const short = id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
    return `Pinned project · ${short}. Keys and integrations below stay on your HAM server like full Settings; bookmarks can include project_id=${id}.`;
  }, [projectId]);

  let content: React.ReactNode;
  switch (active) {
    case "general":
      content = (
        <div className="space-y-4 pb-10">
          <p className="text-[13px] leading-relaxed text-white/45">
            Desktop bundle density, operator connection strip, and local Hermes controls — same panel
            as Display in full settings.
          </p>
          <DesktopBundlePanel />
          <FooterLink href={fullSettingsHref("display", projectId)}>
            Display / bundle on full-screen settings
          </FooterLink>
        </div>
      );
      break;
    case "models":
      content = (
        <div className="space-y-6 pb-10">
          <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 shadow-none md:p-5">
            <h2 className="text-[15px] font-semibold text-[#e8eef8]">Model &amp; provider keys</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-white/45">
              Cursor, OpenRouter, and related routing credentials stored on the API (never in the
              browser).
            </p>
            <div className="mt-5">
              <ApiKeysPanel variant="workspace" />
            </div>
            <FooterLink href={fullSettingsHref("hermes", projectId)} className="mt-6">
              Open full model catalog &amp; provider diagnostics
            </FooterLink>
          </section>
          <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 shadow-none md:p-5">
            <h3 className="text-[13px] font-semibold text-white/88">Context &amp; memory</h3>
            <p className="mt-1 text-[12px] text-white/45">
              Repo snapshot powering this workspace (read-only probe).
            </p>
            <div className="mt-4">
              <ContextAndMemoryPanel variant="workspace" />
            </div>
          </section>
        </div>
      );
      break;
    case "secrets":
      content = (
        <div className="space-y-4 pb-10">
          <p className="text-[13px] leading-relaxed text-white/45">
            Environment variable names the API exposes (values never shown here). Operational API keys
            for chat models live under Model & keys; OAuth-style tool keys land under Integrations or
            GitHub.
          </p>
          <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 shadow-none md:p-5">
            <h3 className="text-[13px] font-semibold text-white/88">Environment</h3>
            <div className="mt-4">
              <EnvironmentReadonlyPanel variant="workspace" />
            </div>
          </section>
          <FooterLink href={fullSettingsHref("connection", projectId)}>
            Local machine connection &amp; filesystem notes
          </FooterLink>
        </div>
      );
      break;
    case "github":
      content = (
        <div className="pb-10">
          <WorkspaceConnectedToolsSection
            visibleToolIds={["github"]}
            heading="GitHub"
            subtitle="Paste a fine-grained personal access token. The key stays encrypted server-side where supported; expanding a row exposes connect / disconnect controls."
          />
          <FooterLink href={fullSettingsHref("tools", projectId)}>
            Manage all integrations in Settings
          </FooterLink>
        </div>
      );
      break;
    case "integrations":
      content = (
        <div className="pb-10">
          <WorkspaceConnectedToolsSection />
          <FooterLink href={fullSettingsHref("tools", projectId)}>
            Connected tools · full-screen
          </FooterLink>
        </div>
      );
      break;
    case "payment":
      content = (
        <div className="space-y-3 pb-10">
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[13px] font-semibold text-white/88">Payments &amp; revenue</p>
                <p className="mt-2 text-[12px] leading-relaxed text-white/45">
                  The HAM workspace is for command, chat, and automation — billing for your shipped
                  product (Stripe Checkout, invoicing, webhooks, etc.) is configured where you deploy
                  the customer-facing host (for example Vercel or Cloud Run billing integration), not
                  inside HAM Connected Tools.
                </p>
              </div>
              <CreditCard className="h-10 w-10 shrink-0 text-white/20" aria-hidden />
            </div>
            <p className="mt-4 text-[11px] text-white/38">
              If you ship a storefront from this workspace, delegate payment keys to your app&apos;s host
              and keep HAM integrations limited to Cursor, OpenRouter, GitHub, and similar dev tools.
            </p>
          </div>
        </div>
      );
      break;
    case "domains":
      content = (
        <div className="space-y-3 pb-10">
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[13px] font-semibold text-white/88">Custom domains</p>
                <p className="mt-2 text-[12px] leading-relaxed text-white/45">
                  Public HTTPS hostnames attach to whichever surface serves your deployed app — for
                  example Vercel project domains or Cloud Run + load balancer mappings. Chat and
                  local-control stays on this dashboard; DNS is managed with your infra provider.
                </p>
              </div>
              <Globe className="h-10 w-10 shrink-0 text-white/20" aria-hidden />
            </div>
            <p className="mt-4 text-[11px] text-white/38">
              Use your deployment checklist (see repo deploy docs) to confirm CORS origins when the
              chat origin changes.
            </p>
          </div>
        </div>
      );
      break;
    case "usage":
      content = (
        <div className="space-y-4 pb-10">
          <p className="text-[13px] leading-relaxed text-white/45">
            Full Usage &amp; Billing (plan stubs, category tabs, ledger empty state) lives in
            workspace Settings — same route your account uses so we do not duplicate disconnected
            metering UIs.
          </p>
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5">
            <p className="text-[13px] font-semibold text-white/88">HAM-native preview</p>
            <ul className="mt-3 list-inside list-disc space-y-1.5 text-[12px] text-white/50">
              <li>Credits and Stripe-style flows are stubbed honestly (not live billing).</li>
              <li>
                Jobs, Operations, and Cursor runs stay in their existing screens — not rebranded as
                invoices.
              </li>
            </ul>
          </div>
          <FooterLink href={fullSettingsHref("usage", projectId)} data-testid="hww-workbench-usage-full-settings">
            Open Usage &amp; Billing in Settings
          </FooterLink>
          <FooterLink href={`/workspace/jobs${projectId?.trim() ? `?project_id=${encodeURIComponent(projectId.trim())}` : ""}`}>
            Open Jobs for this workspace
          </FooterLink>
        </div>
      );
      break;
    default:
      content = null;
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-col gap-3 text-[12px] text-white/70 md:flex-row md:gap-4">
      <nav
        className={cn(
          "flex shrink-0 gap-1 overflow-x-auto pb-1 md:w-[9.75rem] md:flex-col md:overflow-visible md:pb-0",
        )}
        aria-label="Workbench settings sections"
      >
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = active === id;
          return (
            <button
              key={id}
              type="button"
              data-testid={`hww-workbench-settings-nav-${id}`}
              aria-current={isActive ? "true" : undefined}
              onClick={() => setActive(id)}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[11px] font-medium transition-colors outline-none",
                "focus-visible:ring-2 focus-visible:ring-emerald-400/35",
                isActive
                  ? "bg-emerald-500/[0.14] text-[#e8eef8]"
                  : "text-white/50 hover:bg-white/[0.05] hover:text-white/82",
              )}
            >
              <Icon className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden rounded-xl border border-white/[0.06] bg-black/18 p-3 md:p-4">
        <p className="mb-4 border-b border-white/[0.06] pb-3 text-[11px] leading-snug text-white/45">
          {projectSummary}
        </p>
        {content}
      </div>
    </div>
  );
}

function FooterLink({
  href,
  className,
  children,
  "data-testid": dataTestId,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <p className={cn(className)}>
      <Link
        data-testid={dataTestId}
        className="text-[11px] font-medium text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/55"
        to={href}
      >
        {children}
      </Link>
    </p>
  );
}
