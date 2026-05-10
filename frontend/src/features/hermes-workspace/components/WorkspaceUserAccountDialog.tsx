/**
 * Workspace-scoped usage + Account / General panes styled to match the HAM dashboard shell.
 */
import * as React from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useTheme } from "next-themes";
import {
  Calendar,
  Check,
  ChevronDown,
  Copy,
  Info,
  ScrollText,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";

import { useClerk } from "@clerk/clerk-react";

import { cn } from "@/lib/utils";
import { fetchChatSessions, type ChatSessionSummary } from "@/lib/ham/api";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import type { HamMeUser } from "@/lib/ham/workspaceApi";

export interface WorkspaceUserAccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export type WorkspaceUserAccountTabId = "account" | "general" | "usage";

function initialsFromMe(user: HamMeUser): string {
  const raw = (user.display_name ?? user.email ?? "U").trim();
  const parts = raw.split(/\s+/).filter(Boolean);
  if (parts.length >= 2)
    return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase().slice(0, 3);
  return (parts[0]?.[0] ?? "U").toUpperCase();
}

function formatShortDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return "—";
  }
}

function ClerkSignOutButton() {
  const clerk = useClerk();
  return (
    <button
      type="button"
      onClick={() => void clerk.signOut({ redirectUrl: window.location.pathname })}
      className="rounded-full border border-emerald-500/35 bg-emerald-500/15 px-4 py-2 text-[12px] font-semibold text-emerald-100/95 transition-colors outline-none hover:bg-emerald-500/22 focus-visible:ring-2 focus-visible:ring-emerald-400/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[#030a10]"
    >
      Log out
    </button>
  );
}

export function WorkspaceUserAccountDialog({
  open,
  onOpenChange,
}: WorkspaceUserAccountDialogProps) {
  const ham = useHamWorkspace();
  const { resolvedTheme, theme, setTheme } = useTheme();
  const palette = resolvedTheme ?? theme ?? "dark";
  const [tab, setTab] = React.useState<WorkspaceUserAccountTabId>("account");
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = React.useState(false);
  const workspaceMenuRef = React.useRef<HTMLDivElement | null>(null);
  const [productUpdates, setProductUpdates] = React.useState(true);
  const [emailQueue, setEmailQueue] = React.useState(true);
  const [adsConsent, setAdsConsent] = React.useState(false);
  const [copiedId, setCopiedId] = React.useState(false);

  const [usageSessions, setUsageSessions] = React.useState<ChatSessionSummary[]>([]);
  const [usageLoading, setUsageLoading] = React.useState(false);
  const [usageErr, setUsageErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  React.useEffect(() => {
    if (!open) return;
    setCopiedId(false);
  }, [open, tab]);

  React.useEffect(() => {
    if (!workspaceMenuOpen) return;
    function onPointerDown(ev: MouseEvent | PointerEvent) {
      const root = workspaceMenuRef.current;
      const t = ev.target as Node | null;
      if (root && t && !root.contains(t)) setWorkspaceMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [workspaceMenuOpen]);

  const readyWorkspaceId = ham.state.status === "ready" ? ham.state.activeWorkspaceId : null;

  React.useEffect(() => {
    if (!open || tab !== "usage") return;
    if (ham.state.status !== "ready") {
      setUsageSessions([]);
      setUsageErr(null);
      return;
    }
    const wid = readyWorkspaceId;
    if (!wid?.trim()) {
      setUsageSessions([]);
      setUsageErr("Pick a workspace in the sidebar to load scoped usage.");
      return;
    }
    let cancelled = false;
    setUsageLoading(true);
    setUsageErr(null);
    void (async () => {
      try {
        const { sessions } = await fetchChatSessions(80, 0, wid.trim());
        if (!cancelled) setUsageSessions(sessions);
      } catch (e) {
        if (!cancelled) {
          setUsageSessions([]);
          setUsageErr(
            e instanceof Error ? e.message : "Could not load chat sessions for this workspace.",
          );
        }
      } finally {
        if (!cancelled) setUsageLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, tab, ham.state.status, readyWorkspaceId]);

  const me =
    ham.state.status === "ready" || ham.state.status === "onboarding" ? ham.state.me : null;
  const activeWorkspace = ham.state.status === "ready" ? ham.active : null;
  const activeWorkspaceId = ham.state.status === "ready" ? ham.state.activeWorkspaceId : null;

  const canUseClerkSignOut = Boolean(ham.hostedAuth?.clerkConfigured && ham.hostedAuth?.isSignedIn);

  const usageTotals = React.useMemo(() => {
    let turns = 0;
    for (const s of usageSessions) {
      turns += typeof s.turn_count === "number" ? s.turn_count : 0;
    }
    return {
      sessions: usageSessions.length,
      turns,
      tokenHint: turns > 0 ? Math.round(turns * 350) : 0,
    };
  }, [usageSessions]);

  const copyUserId = async () => {
    if (!me?.user?.user_id) return;
    try {
      await navigator.clipboard.writeText(me.user.user_id);
      setCopiedId(true);
      window.setTimeout(() => setCopiedId(false), 2000);
    } catch {
      /* ignore */
    }
  };

  const selectWorkspace = (id: string) => {
    ham.selectWorkspace(id);
    setWorkspaceMenuOpen(false);
  };

  if (!open || typeof document === "undefined") return null;

  const user = me?.user;
  const initials = user ? initialsFromMe(user) : "—";

  const profileLine = user ? (user.display_name ?? user.email ?? "Account") : "Account";
  const workspaceLine =
    activeWorkspace?.name ??
    me?.workspaces?.[0]?.name ??
    (ham.state.status === "onboarding" ? "Pick workspace" : "Workspace");

  const shellLabel = cn(
    "text-[13px] font-semibold outline-none ring-offset-2 ring-offset-[#040d14] transition-colors focus-visible:ring-2 focus-visible:ring-emerald-400/35",
    "flex w-full min-w-0 items-center gap-2 rounded-lg px-1 py-0.5 text-left hover:bg-white/[0.06]",
  );

  const navItems: ReadonlyArray<{
    id: WorkspaceUserAccountTabId;
    label: string;
    icon: typeof UserRound;
  }> = [
    { id: "account", label: "Account", icon: UserRound },
    { id: "general", label: "General", icon: SlidersHorizontal },
    { id: "usage", label: "Usage & Billing", icon: Sparkles },
  ];

  let main: React.ReactNode;
  if (!user) {
    main = (
      <div className="px-6 py-8">
        <h2 className="text-xl font-semibold tracking-tight text-[#e8eef8]">Account</h2>
        <p className="mt-3 max-w-lg text-[13px] leading-relaxed text-white/55">
          Sign in and finish loading your workspace to view account details here.
        </p>
      </div>
    );
  } else {
    switch (tab) {
      case "account":
        main = (
          <div className="px-6 pb-10 pt-6 md:px-8 md:pt-8">
            <h2 className="text-2xl font-semibold tracking-tight text-[#e8eef8]">Account</h2>
            <div className="mt-8 flex flex-wrap items-start gap-5">
              <div
                className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-2xl font-semibold text-white shadow-[0_8px_24px_rgba(16,185,129,0.25)]"
                aria-hidden
              >
                {initials}
              </div>
              <div className="min-w-0 flex-1 space-y-3">
                <label className="block text-[11px] font-semibold uppercase tracking-wide text-white/40">
                  Full name
                </label>
                <div className="rounded-xl border border-white/[0.08] bg-black/25 px-4 py-3 text-[14px] text-white/88">
                  {user.display_name ?? "—"}
                </div>
              </div>
            </div>

            <div className="mt-8 rounded-2xl border border-white/[0.08] bg-[#040d14]/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[15px] font-semibold text-[#e8eef8]">Active workspace</p>
                  <p className="mt-1 text-[13px] text-white/50">
                    {activeWorkspace?.name ?? "Choose a workspace"} · Scoped keys and chat sessions
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled
                    className="inline-flex cursor-not-allowed items-center gap-1 rounded-full border border-white/[0.1] bg-white/[0.04] px-3 py-1.5 text-[12px] font-semibold text-white/35"
                  >
                    Manage
                    <ChevronDown className="h-3.5 w-3.5 opacity-50" aria-hidden />
                  </button>
                  <Link
                    to="/workspace/jobs"
                    onClick={() => onOpenChange(false)}
                    className="inline-flex rounded-full border border-emerald-400/35 bg-emerald-500/[0.16] px-4 py-2 text-[12px] font-semibold text-emerald-100/95 hover:bg-emerald-500/[0.24]"
                  >
                    Open activity
                  </Link>
                </div>
              </div>
              <div className="mt-5 border-t border-dashed border-white/[0.08] pt-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium text-white/82">
                    <Sparkles className="h-4 w-4 text-emerald-300/85" aria-hidden />
                    Credits
                  </div>
                  <span className="text-[13px] tabular-nums text-white/45">
                    HAM-native · not Stripe
                  </span>
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-white/45">
                  Model spend stays with your configured providers (OpenRouter, Claude, Cursor).
                  Workspace usage for chat turns is summarized under Usage &amp; Billing.
                </p>
              </div>
            </div>

            <div className="mt-8 space-y-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                  Email
                </p>
                <p className="mt-1 text-[14px] text-white/82">{user.email ?? "Not provided"}</p>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                  User ID
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="break-all rounded-lg border border-white/[0.08] bg-black/30 px-3 py-2 font-mono text-[11px] text-emerald-200/85">
                    {user.user_id}
                  </span>
                  <button
                    type="button"
                    onClick={() => void copyUserId()}
                    className="inline-flex items-center gap-1 rounded-full border border-white/[0.1] bg-white/[0.05] px-3 py-1.5 text-[12px] font-semibold text-white/75 hover:bg-white/[0.09]"
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden />
                    {copiedId ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-10 space-y-5 border-t border-white/[0.06] pt-8">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[14px] font-semibold text-[#e8eef8]">Log out of this device</p>
                  <p className="mt-1 text-[12px] text-white/45">
                    Ends the Clerk session in this browser (when Clerk is configured).
                  </p>
                </div>
                {canUseClerkSignOut ? (
                  <ClerkSignOutButton />
                ) : (
                  <span className="text-[12px] text-white/40">Sign-in not available.</span>
                )}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-500/20 bg-red-950/25 px-4 py-4">
                <div>
                  <p className="text-[14px] font-semibold text-red-100/95">Delete account</p>
                  <p className="mt-1 text-[12px] text-red-200/70">
                    Not managed in-app — contact support or your identity provider.
                  </p>
                </div>
                <button
                  type="button"
                  disabled
                  className="rounded-full border border-red-400/30 bg-transparent px-4 py-2 text-[12px] font-semibold text-red-200/85 opacity-50"
                >
                  Delete account
                </button>
              </div>
            </div>
          </div>
        );
        break;
      case "general":
        main = (
          <div className="px-6 pb-10 pt-6 md:px-8 md:pt-8">
            <h2 className="text-2xl font-semibold tracking-tight text-[#e8eef8]">General</h2>
            <div className="mt-8 space-y-8">
              <section>
                <h3 className="text-[13px] font-semibold text-white/88">Appearance</h3>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                      Language
                    </label>
                    <select
                      id="hww-acct-lang"
                      disabled
                      className="hww-input mt-2 w-full rounded-xl border-white/[0.08] bg-black/25 px-3 py-2.5 text-[14px] text-white/75"
                      defaultValue="en"
                    >
                      <option value="en">English</option>
                    </select>
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                      Theme
                    </p>
                    <div className="mt-2 inline-flex rounded-full border border-white/[0.08] bg-black/22 p-1">
                      {(["light", "dark"] as const).map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => setTheme(t)}
                          className={cn(
                            "rounded-full px-4 py-1.5 text-[12px] font-semibold capitalize transition-colors",
                            palette === t
                              ? "border border-emerald-400/40 bg-emerald-500/15 text-emerald-100/95 shadow-[inset_0_0_0_1px_rgba(52,211,153,0.2)]"
                              : "text-white/45 hover:text-white/72",
                          )}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-white/42">
                      Sets global app theme classes; Hermes chrome remains dark-heavy.
                    </p>
                  </div>
                </div>
              </section>
              <section className="border-t border-white/[0.06] pt-8">
                <h3 className="text-[13px] font-semibold text-white/88">
                  Communication preferences
                </h3>
                <div className="mt-4 space-y-4">
                  <label className="flex cursor-pointer items-start justify-between gap-4">
                    <span>
                      <span className="block text-[14px] font-medium text-white/85">
                        Receive product updates
                      </span>
                      <span className="mt-0.5 block text-[12px] text-white/45">
                        UI preview only — not wired to outbound email.
                      </span>
                    </span>
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-white/20 bg-black/35 accent-emerald-500"
                      checked={productUpdates}
                      onChange={(e) => setProductUpdates(e.target.checked)}
                    />
                  </label>
                  <label className="flex cursor-pointer items-start justify-between gap-4">
                    <span>
                      <span className="block text-[14px] font-medium text-white/85">
                        Email when a queued mission starts
                      </span>
                      <span className="mt-0.5 block text-[12px] text-white/45">
                        Future hook for managed-mission lifecycle mail.
                      </span>
                    </span>
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-white/20 bg-black/35 accent-emerald-500"
                      checked={emailQueue}
                      onChange={(e) => setEmailQueue(e.target.checked)}
                    />
                  </label>
                </div>
              </section>
              <section className="border-t border-white/[0.06] pt-8">
                <h3 className="text-[13px] font-semibold text-white/88">Product notes</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-white/50">
                  Optional ads / marketing data pathways are disabled in HAM OSS builds unless you
                  hook your own notifier.
                </p>
                <label className="mt-4 flex cursor-pointer items-start justify-between gap-4">
                  <span className="text-[14px] font-medium text-white/82">Share usage for ads</span>
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-white/20 bg-black/35 accent-emerald-500"
                    checked={adsConsent}
                    onChange={(e) => setAdsConsent(e.target.checked)}
                  />
                </label>
              </section>
            </div>
          </div>
        );
        break;
      case "usage":
        main = (
          <div className="px-6 pb-10 pt-6 md:px-8 md:pt-8">
            <h2 className="text-2xl font-semibold tracking-tight text-[#e8eef8]">
              Usage &amp; Billing
            </h2>
            <p className="mt-2 text-[13px] text-white/50">
              Metrics below are scoped to{" "}
              <span className="font-semibold text-white/82">{workspaceLine}</span>
              {activeWorkspaceId ? (
                <>
                  {" "}
                  <span className="font-mono text-[11px] text-white/42">({activeWorkspaceId})</span>
                </>
              ) : null}
              . Provider token billing still lives with each vendor dashboard.
            </p>

            <div className="mt-8 rounded-2xl border border-white/[0.08] bg-[#040d14]/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-dashed border-white/[0.08] pb-4">
                <div>
                  <p className="text-[14px] font-semibold text-[#e8eef8]">
                    Workspace chat index{" "}
                    <span className="text-[11px] font-normal text-white/40">API</span>
                  </p>
                  <p className="mt-1 text-[12px] text-white/45">
                    Persisted Chat sessions (`GET /api/chat/sessions`) for this workspace only.
                  </p>
                </div>
                <Link
                  to="/workspace/chat"
                  onClick={() => onOpenChange(false)}
                  className="rounded-full border border-emerald-400/35 bg-emerald-500/[0.15] px-4 py-2 text-[12px] font-semibold text-emerald-100/95 hover:bg-emerald-500/[0.22]"
                >
                  Open chat
                </Link>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-white/[0.06] bg-black/25 px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                    Indexed sessions
                  </p>
                  <p className="mt-1 text-[20px] font-semibold tabular-nums text-white/90">
                    {usageLoading ? "…" : usageTotals.sessions}
                  </p>
                </div>
                <div className="rounded-xl border border-white/[0.06] bg-black/25 px-3 py-3">
                  <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-white/40">
                    <Sparkles className="h-3 w-3" aria-hidden />
                    Turns persisted
                  </p>
                  <p className="mt-1 text-[20px] font-semibold tabular-nums text-white/90">
                    {usageLoading ? "…" : usageTotals.turns.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl border border-white/[0.06] bg-black/25 px-3 py-3">
                  <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-white/40">
                    <Calendar className="h-3 w-3" aria-hidden />
                    Token heuristic
                  </p>
                  <p className="mt-2 text-[12px] leading-snug text-white/55">
                    ≈{" "}
                    {!usageLoading && usageTotals.turns
                      ? `${usageTotals.tokenHint.toLocaleString()} tokens`
                      : "—"}{" "}
                    <span className="text-white/42">(~350 est. / paired turn • not billed)</span>
                  </p>
                </div>
              </div>

              {usageErr ? <p className="mt-4 text-[13px] text-amber-200/85">{usageErr}</p> : null}
            </div>

            <div className="mt-6 flex items-center justify-between border-b border-white/[0.08] pb-2">
              <h3 className="text-[14px] font-semibold text-white/85">Sessions history</h3>
              <span className="inline-flex items-center gap-1 text-[11px] text-white/40">
                <Info className="h-3.5 w-3.5" aria-hidden /> Newest {usageSessions.length} rows
              </span>
            </div>
            {usageSessions.length === 0 && !usageLoading ? (
              <p className="mt-4 text-[13px] text-white/45">
                No indexed sessions yet for this workspace, or telemetry is unavailable.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-white/[0.06]">
                {usageSessions.slice(0, 20).map((s) => (
                  <li
                    key={s.session_id}
                    className="flex flex-wrap items-baseline justify-between gap-3 py-2.5"
                  >
                    <span className="min-w-0 flex-1 text-[13px] leading-snug text-white/82">
                      {s.preview.trim() ? s.preview : "Untitled conversation"}
                      <span className="mt-0.5 block font-mono text-[10px] text-white/35">
                        {s.session_id}
                      </span>
                    </span>
                    <span className="shrink-0 text-right tabular-nums">
                      <span className="text-[13px] font-medium text-white/75">{s.turn_count}</span>
                      <span className="ml-2 text-[11px] text-white/40"> turns</span>
                      <span className="mt-1 block text-[11px] text-white/38">
                        {formatShortDate(s.created_at)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {ham.workspaces.length > 1 ? (
              <div className="mt-8 rounded-2xl border border-white/[0.08] bg-black/22 p-4">
                <p className="text-[12px] font-semibold uppercase tracking-wide text-white/40">
                  All workspaces
                </p>
                <p className="mt-1 text-[13px] text-white/50">
                  Switch from the picker above — other tenants stay isolated from these rows.
                </p>
              </div>
            ) : null}
          </div>
        );
        break;
      default:
        main = null;
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[420] flex items-center justify-center bg-[#030b11]/80 p-3 backdrop-blur-sm sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Account and preferences"
      data-testid="hww-user-account-dialog"
      onMouseDown={(ev) => {
        if (ev.target === ev.currentTarget) onOpenChange(false);
      }}
    >
      <div className="flex max-h-[min(92vh,900px)] w-full max-w-[min(960px,calc(100vw-24px))] overflow-hidden rounded-2xl border border-white/[0.08] bg-[#030a10] shadow-2xl shadow-black/55 ring-1 ring-white/[0.04]">
        <aside className="relative z-[440] flex w-[min(248px,34vw)] min-w-[205px] flex-col overflow-visible border-r border-white/[0.08] bg-[#040d14]/95">
          <div className="border-b border-white/[0.08] px-3 py-3">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-xs font-semibold text-white shadow-md shadow-emerald-900/35">
                {user ? initials : "?"}
              </div>
              <div ref={workspaceMenuRef} className="relative min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-white/88">{profileLine}</p>
                <button
                  type="button"
                  className={shellLabel}
                  onClick={() => setWorkspaceMenuOpen((v) => !v)}
                >
                  <span className="min-w-0 flex-1 truncate text-left text-[11px] text-white/52">
                    {workspaceLine}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 shrink-0 text-white/45 transition-transform",
                      workspaceMenuOpen && "rotate-180",
                    )}
                    aria-hidden
                  />
                </button>
                {workspaceMenuOpen && ham.state.status === "ready" && ham.workspaces.length > 0 ? (
                  <ul className="absolute left-0 top-full z-[441] mt-1 max-h-52 w-[min(17rem,calc(100vw-3rem))] overflow-y-auto rounded-xl border border-white/[0.1] bg-[#07141c] py-1 text-[13px] shadow-xl ring-1 ring-black/55">
                    {ham.workspaces.map((w) => {
                      const isActive =
                        ham.state.status === "ready" &&
                        ham.state.activeWorkspaceId === w.workspace_id;
                      return (
                        <li key={w.workspace_id}>
                          <button
                            type="button"
                            data-testid={`hww-account-workspace-switch-${w.workspace_id}`}
                            className={cn(
                              "flex w-full items-center gap-2 px-3 py-2 text-left text-white/82 transition-colors hover:bg-white/[0.06]",
                              isActive && "bg-emerald-500/10 text-emerald-100/95",
                            )}
                            onClick={() => selectWorkspace(w.workspace_id)}
                          >
                            <span className="min-w-0 flex-1 truncate">{w.name}</span>
                            {isActive ? (
                              <Check className="h-4 w-4 shrink-0 text-emerald-300/90" />
                            ) : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            </div>
          </div>
          <p className="px-4 pb-1.5 pt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/38">
            Account
          </p>
          <nav className="flex flex-col gap-0.5 px-2 pb-4" aria-label="Account navigation">
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                data-testid={`hww-user-account-tab-${id}`}
                onClick={() => setTab(id)}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-[13px] font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/30",
                  tab === id
                    ? "border border-transparent bg-emerald-500/[0.14] text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(52,211,153,0.18)]"
                    : "border border-transparent text-white/50 hover:bg-white/[0.05] hover:text-white/82",
                )}
              >
                <Icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} aria-hidden />
                {label}
              </button>
            ))}
          </nav>
          <div className="mt-auto border-t border-white/[0.08] px-4 py-3">
            <a
              href="https://github.com/Code-Munkiz/ham/blob/main/README.md"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[#7dd3fc] hover:text-[#a5e9ff]"
            >
              <ScrollText className="h-3.5 w-3.5" aria-hidden />
              Documentation ↗
            </a>
          </div>
        </aside>
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-[#030b11]/50">
          <button
            type="button"
            className="absolute right-4 top-4 z-[1] rounded-full p-2 text-white/40 transition-colors hover:bg-white/[0.08] hover:text-white/88"
            aria-label="Close"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
          <div className="hww-scroll min-h-0 flex-1 overflow-y-auto">{main}</div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
